"""Single-project local memory service. Signed-log or pinned-registry authority."""
import copy
import json
import os
import sqlite3
import time
from pathlib import Path
from protocol import canonical, digest, validate, recover, project_id
from storage import Store

SCHEMA='''
        CREATE TABLE IF NOT EXISTS meta (name TEXT PRIMARY KEY,value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS refs (kind TEXT,id TEXT,digest TEXT,object TEXT,PRIMARY KEY(kind,id));
        CREATE TABLE IF NOT EXISTS checkpoints (digest TEXT PRIMARY KEY,object TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS inbox (id TEXT PRIMARY KEY,object TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS prepared (digest TEXT PRIMARY KEY,object TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS intents (digest TEXT PRIMARY KEY,object TEXT NOT NULL,status TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS receipts (signer TEXT,nonce TEXT,fingerprint TEXT,expires INTEGER,result TEXT,PRIMARY KEY(signer,nonce));
        '''

ZERO='0x'+'00'*32

def require(condition, code):
    if not condition: raise ValueError(code)

def fields(body, names):
    require(isinstance(body,dict) and set(body)==set(names),'INVALID_PAYLOAD')

class Memory:
    def __init__(self, path, key, config, genesis=None, registry=None):
        self.config=copy.deepcopy(config)
        self.project=config['projectId']; self.owner=config['owner'].lower(); self.domain=config['domain']
        self.registry=registry
        require(registry is not None or set(self.domain)=={'name','version','salt'} and self.domain['name']=='PortableMemory' and self.domain['version']=='0','BASELINE_DOMAIN_REQUIRED')
        Path(path).parent.mkdir(parents=True,exist_ok=True)
        self.db=sqlite3.connect(path,isolation_level=None,timeout=10)
        os.chmod(path,0o600)
        self.db.execute('PRAGMA journal_mode=WAL'); self.db.execute('PRAGMA synchronous=FULL')
        self.store=Store(self.db,key,self.project)
        self.db.executescript(SCHEMA)
        try:
            self.db.execute('BEGIN IMMEDIATE')
            pin=self.db.execute("SELECT value FROM meta WHERE name='config'").fetchone()
            if pin:
                require(self.store.get(pin[0])==config,'CONFIG_MISMATCH')
            else:
                require(genesis is not None,'GENESIS_REQUIRED')
                self.verify_checkpoint(genesis)
                cp=genesis['checkpoint']; control=genesis['control']; snapshot=genesis['snapshot']
                require(cp['sequence']=='0' and cp['previousDigest']==ZERO,'INVALID_GENESIS')
                require(int(cp['deadline'])>=int(time.time()),'EXPIRED')
                validate('snapshot',snapshot)
                require(snapshot=={'formatVersion':'0','projectId':self.project,'previousDigest':ZERO,'records':[],'sources':[],'currentIds':[],'resolutions':[]},'INVALID_GENESIS')
                require(digest('snapshot',snapshot)==control['snapshotDigest'],'CONTENT_MISMATCH')
                self.put_ref('snapshot',control['snapshotDigest'],snapshot)
                self.db.execute('INSERT INTO checkpoints VALUES (?,?)',(cp['controlDigest'],self.store.put('checkpoint-envelope',genesis)))
                self.db.execute('INSERT INTO meta VALUES (?,?)',('head',cp['controlDigest']))
                self.db.execute('INSERT INTO meta VALUES (?,?)',('config',self.store.put('config',config)))
            if not self.db.execute("SELECT 1 FROM meta WHERE name='binding'").fetchone():
                c=self.local_current()['control']
                self.db.execute('INSERT INTO meta VALUES (?,?)',('binding',self.store.put('binding',{'serviceId':c['serviceId'],'storage':c['storage']})))
            self.local_current()
            if self.registry and not pin:
                self.stage_intent(genesis)
            self.db.execute('COMMIT')
        except Exception:
            self.db.execute('ROLLBACK'); self.db.close(); raise
        if self.registry:
            try:
                self.recover_intents()
                self.current()
            except Exception:
                self.db.close(); raise

    def close(self): self.db.close()

    def verify_checkpoint(self, envelope):
        cp=envelope['checkpoint']; c=envelope['control']; sig=envelope['signature']
        validate('checkpoint',cp); validate('control',c)
        require(cp['projectId']==c['projectId']==self.project,'WRONG_PROJECT')
        require(project_id(self.owner,c['creationNonce'])==self.project,'INVALID_GENESIS')
        require(cp['sequence']==c['sequence'] and cp['previousDigest']==c['previousDigest'] and cp['controlDigest']==digest('control',c),'CONTENT_MISMATCH')
        require(recover(self.domain,'Checkpoint',cp,sig)==self.owner,'WRONG_SIGNER')

    def local_current(self):
        head=self.db.execute("SELECT value FROM meta WHERE name='head'").fetchone()[0]
        row=self.db.execute('SELECT object FROM checkpoints WHERE digest=?',(head,)).fetchone()
        require(row is not None,'CONTENT_UNAVAILABLE')
        envelope=self.store.get(row[0]); self.verify_checkpoint(envelope)
        require(envelope['checkpoint']['controlDigest']==head,'INTEGRITY_FAILURE')
        return envelope

    def current(self):
        if not self.registry: return self.local_current()
        view=self.registry.view(self.project)
        if view['owner']==('0x'+'00'*20) and self.db.execute("SELECT 1 FROM intents WHERE status='pending'").fetchone():
            raise ValueError('COMMIT_PENDING')
        require(view['owner']==self.owner,'AUTHORITY_UNAVAILABLE')
        row=self.db.execute('SELECT object FROM checkpoints WHERE digest=?',(view['digest'],)).fetchone()
        if row is None:
            staged=self.db.execute('SELECT object FROM intents WHERE digest=?',(view['digest'],)).fetchone()
            require(staged is not None,'CONTENT_UNAVAILABLE')
            envelope=self.store.get(staged[0])['envelope']
        else: envelope=self.store.get(row[0])
        self.verify_checkpoint(envelope)
        cp=envelope['checkpoint']
        require(cp['controlDigest']==view['digest'] and cp['sequence']==view['sequence'],'INTEGRITY_FAILURE')
        require(self.registry.accepted(cp,self.owner,view) is not None,'AUTHORITY_UNAVAILABLE')
        return envelope

    def stage_intent(self, envelope):
        cp=envelope['checkpoint']
        row=self.db.execute('SELECT object FROM intents WHERE digest=?',(cp['controlDigest'],)).fetchone()
        if row:
            require(self.store.get(row[0])['envelope']==envelope,'CONTENT_MISMATCH')
            return
        require(not self.db.execute("SELECT 1 FROM intents WHERE status='pending'").fetchone(),'COMMIT_PENDING')
        transaction=self.registry.transaction(envelope,self.owner)
        item={'envelope':envelope,'transaction':transaction}
        self.db.execute('INSERT INTO intents VALUES (?,?,?)',(cp['controlDigest'],self.store.put('commit-intent',item),'pending'))

    def recover_intents(self):
        if not self.registry: return
        # The intent and all private content are committed before any network submission.
        require(not self.db.in_transaction,'TRANSACTION_BOUNDARY')
        for ident,obj in self.db.execute("SELECT digest,object FROM intents WHERE status='pending'").fetchall():
            item=self.store.get(obj); envelope=item['envelope']; cp=envelope['checkpoint']
            self.verify_checkpoint(envelope)
            require(cp['controlDigest']==ident,'INTEGRITY_FAILURE')
            view=self.registry.view(self.project)
            event=self.registry.accepted(cp,self.owner,view)
            if event is None:
                # A different revision at this sequence cannot be overwritten by retrying.
                conflict=view['owner']!=('0x'+'00'*20) and int(view['sequence'])>=int(cp['sequence'])
                if not conflict:
                    self.registry.broadcast(item['transaction'])
                    view=self.registry.view(self.project)
                    event=self.registry.accepted(cp,self.owner,view)
                if event is None:
                    receipt=self.registry.receipt(item['transaction'])
                    status='conflict' if conflict else ('failed' if receipt and int(receipt['status'],16)==0 else 'pending')
                    self.db.execute('UPDATE intents SET status=? WHERE digest=?',(status,ident))
                    continue
            # Verify availability before promoting. Missing content stays unavailable, never stale-current.
            self.context(envelope,True)
            self.db.execute('BEGIN IMMEDIATE')
            try:
                self.db.execute('INSERT OR IGNORE INTO checkpoints VALUES (?,?)',(ident,self.store.put('checkpoint-envelope',envelope)))
                self.db.execute("UPDATE meta SET value=? WHERE name='head'",(ident,))
                item['confirmation']={'kind':self.registry.confirmation,'transactionHash':event['transactionHash'],
                    'blockNumber':event['blockNumber'],'blockHash':event['blockHash'],
                    'authorityBlockNumber':view['blockNumber'],'authorityBlockHash':view['blockHash']}
                self.db.execute("UPDATE intents SET status='accepted',object=? WHERE digest=?",(self.store.put('commit-intent',item),ident))
                self.db.execute('COMMIT')
            except Exception:
                self.db.execute('ROLLBACK'); raise

    def registry_result(self, result):
        self.recover_intents()
        row=self.db.execute('SELECT object,status FROM intents WHERE digest=?',(result['committed'],)).fetchone()
        require(row is not None,'INTEGRITY_FAILURE')
        item=self.store.get(row[0]); cp=item['envelope']['checkpoint']
        require(cp['controlDigest']==result['committed'],'INTEGRITY_FAILURE')
        view=self.registry.view(self.project)
        event=self.registry.accepted(cp,self.owner,view)
        if event:
            return {**result,'transactionHash':event['transactionHash'],'confirmation':self.registry.confirmation}
        raise ValueError({'conflict':'BASE_CONFLICT','failed':'TRANSACTION_FAILED'}.get(row[1],'COMMIT_PENDING'))

    def binding(self):
        row=self.db.execute("SELECT value FROM meta WHERE name='binding'").fetchone()
        require(row is not None,'INTEGRITY_FAILURE')
        return self.store.get(row[0])

    def check_binding(self, control):
        require(self.binding()=={'serviceId':control['serviceId'],'storage':control['storage']},'SERVICE_MOVED')

    def put_ref(self, kind, ident, body):
        d=digest(kind,body)
        row=self.db.execute('SELECT digest FROM refs WHERE kind=? AND id=?',(kind,ident)).fetchone()
        if row: require(row[0]==d,'ID_CONFLICT')
        else: self.db.execute('INSERT INTO refs VALUES (?,?,?,?)',(kind,ident,d,self.store.put(kind,body)))
        return d

    def get_ref(self, kind, ident, expected=None):
        row=self.db.execute('SELECT digest,object FROM refs WHERE kind=? AND id=?',(kind,ident)).fetchone()
        require(row is not None,'CONTENT_UNAVAILABLE')
        body=self.store.get(row[1]); actual=digest(kind,body)
        if kind!='snapshot': require(body['id']==ident,'INTEGRITY_FAILURE')
        require(actual==row[0] and (expected is None or actual==expected),'INTEGRITY_FAILURE')
        return body

    def snapshot(self, control):
        return self.get_ref('snapshot',control['snapshotDigest'],control['snapshotDigest'])

    def grant(self, control, signer, right, now):
        if signer==self.owner: return
        require(right!='owner','SCOPE_DENIED')
        require(any(g['application']==signer and g['serviceId']==control['serviceId'] and int(g['expiresAt'])>=now and right in g['rights'] for g in control['grants']),'SCOPE_DENIED')

    def execute(self, wire, now=None):
        now=int(time.time()) if now is None else now
        fields(wire,{'auth','body','signature'})
        auth,body,sig=wire['auth'],wire['body'],wire['signature']
        validate('request-auth',auth); validate('request',body)
        require(auth['projectId']==body['projectId']==self.project,'WRONG_PROJECT')
        require(now<=int(auth['deadline'])<=now+300,'EXPIRED_REQUEST')
        require(auth['requestDigest']==digest('request',body),'CONTENT_MISMATCH')
        signer=recover(self.domain,'Request',auth,sig)
        self.recover_intents()
        self.db.execute('BEGIN IMMEDIATE')
        try:
            current=self.current(); c=current['control']; head=current['checkpoint']['controlDigest']
            self.check_binding(c)
            if body['operation'] in ['proposals','prepare','commit']:
                require(not self.db.execute("SELECT 1 FROM meta WHERE name='frozen'").fetchone(),'WRITES_FROZEN')
            require(auth['serviceId']==c['serviceId'],'WRONG_AUDIENCE')
            right={'context':'read_current','history':'read_history','proposals':'propose','inbox':'read_current','prepare':'owner','commit':'owner'}[body['operation']]
            self.grant(c,signer,right,now)
            self.db.execute('DELETE FROM receipts WHERE expires<?',(now,))
            fingerprint=canonical(auth).decode()
            previous=self.db.execute('SELECT fingerprint,result FROM receipts WHERE signer=? AND nonce=?',(signer,auth['nonce'])).fetchone()
            if previous:
                require(previous[0]==fingerprint,'REPLAY_MISMATCH')
                # Only the exact successful owner commit may be acknowledged across later revisions.
                require(auth['checkpointDigest']==head or (signer==self.owner and body['operation']=='commit'),'BASE_CONFLICT')
                cached=self.store.get(previous[1])
                require(cached['signer']==signer and cached['fingerprint']==fingerprint,'INTEGRITY_FAILURE')
                result=cached['result']
            else:
                require(auth['checkpointDigest']==head,'BASE_CONFLICT')
                require(self.db.execute('SELECT count(*) FROM receipts').fetchone()[0]<10000,'LIMIT_EXCEEDED')
                result=self.dispatch(body['operation'],body['payload'],signer,current,wire,now)
                self.db.execute('INSERT INTO receipts VALUES (?,?,?,?,?)',(signer,auth['nonce'],fingerprint,int(auth['deadline']),self.store.put('response',{'signer':signer,'fingerprint':fingerprint,'result':result})))
            self.db.execute('COMMIT')
        except Exception:
            self.db.execute('ROLLBACK'); raise
        if self.registry and body['operation']=='commit': return self.registry_result(result)
        return result

    def dispatch(self, operation, payload, signer, current, wire, now):
        if operation=='context':
            fields(payload,set()); return self.context(current,False)
        if operation=='history':
            fields(payload,{'checkpointDigest'})
            row=self.db.execute('SELECT object FROM checkpoints WHERE digest=?',(payload['checkpointDigest'],)).fetchone()
            require(row is not None,'CONTENT_UNAVAILABLE')
            envelope=self.store.get(row[0]); self.verify_checkpoint(envelope)
            require(envelope['checkpoint']['controlDigest']==payload['checkpointDigest'],'INTEGRITY_FAILURE')
            return self.context(envelope,True)
        if operation=='proposals': return self.propose(payload,signer,current,wire)
        if operation=='inbox':
            fields(payload,set()); snapshot=self.snapshot(current['control'])
            resolved={r['proposalId']:r for r in snapshot['resolutions']}
            result=[]
            for (obj,) in self.db.execute('SELECT object FROM inbox ORDER BY id'):
                item=self.store.get(obj); proposal=self.load_proposal(item['proposal']['id'])
                if signer!=self.owner and proposal['author']!=signer: continue
                item['status']=resolved.get(proposal['id'],{}).get('state','pending')
                item['stale']=proposal['baseCheckpoint']!=current['checkpoint']['controlDigest']
                result.append(item)
            return {'proposals':result}
        if operation=='prepare': return self.prepare(payload,current,now)
        if operation=='commit': return self.commit(payload,current,now)
        raise ValueError('INVALID_OPERATION')

    def context(self, envelope, history):
        c=envelope['control']; snapshot=self.snapshot(c)
        refs=[r for r in snapshot['records'] if history or r['disposition']=='current']
        records=[self.get_ref('record',r['id'],r['digest']) for r in refs]
        source_ids={sid for r in records for sid in r['sourceIds']}
        sources=[self.get_ref('source',s['id'],s['digest']) for s in snapshot['sources'] if s['id'] in source_ids]
        if self.registry:
            view=self.registry.view(self.project)
            require(self.registry.accepted(envelope['checkpoint'],self.owner,view) is not None,'UNVERIFIED')
            if not history: require(view['digest']==envelope['checkpoint']['controlDigest'],'BASE_CONFLICT')
        return {'authorityMode':self.registry.mode if self.registry else 'signed_log','verification':'historical_verified' if history else 'current_verified',
                'verificationScope':(self.registry.scope if self.registry else 'owner signature and local sequencer; not chain finality'),
                'checkpoint':envelope['checkpoint'],'signature':envelope['signature'],'control':c,'snapshot':snapshot,'records':records,'sources':sources}

    def propose(self, proposal, signer, current, wire):
        validate('proposal',proposal)
        require(proposal['author']==signer and proposal['projectId']==self.project,'WRONG_AUTHOR')
        require(proposal['baseCheckpoint']==current['checkpoint']['controlDigest'],'BASE_CONFLICT')
        require(len(proposal['records'])+len(proposal['retractIds'])>0,'EMPTY_PROPOSAL')
        require(self.db.execute('SELECT count(*) FROM inbox').fetchone()[0]<100,'LIMIT_EXCEEDED')
        for collection in ['records','sources']:
            ids=[x['id'] for x in proposal[collection]]
            require(ids==sorted(set(ids)),'INVALID_ORDER')
        require(proposal['retractIds']==sorted(set(proposal['retractIds'])),'INVALID_ORDER')
        for s in proposal['sources']:
            require(s['projectId']==self.project,'WRONG_PROJECT'); self.put_ref('source',s['id'],s)
        snapshot=self.snapshot(current['control'])
        available={s['id'] for s in snapshot['sources']}|{s['id'] for s in proposal['sources']}
        newids={r['id'] for r in proposal['records']}; oldids={r['id'] for r in snapshot['records']}
        require(not newids.intersection(oldids),'ID_CONFLICT')
        targets=set(proposal['retractIds'])
        for r in proposal['records']:
            require(r['projectId']==self.project and r['author']==signer,'WRONG_AUTHOR')
            require(r['sourceIds']==sorted(set(r['sourceIds'])) and set(r['sourceIds'])<=available,'MISSING_SOURCE')
            if r['replaces']:
                require(r['replaces'] not in targets and r['replaces'] not in newids,'INVALID_TRANSITION')
                targets.add(r['replaces'])
            self.put_ref('record',r['id'],r)
        require(targets<=set(snapshot['currentIds']),'INVALID_TRANSITION')
        d=self.put_ref('proposal',proposal['id'],proposal)
        require(not self.db.execute('SELECT 1 FROM inbox WHERE id=?',(proposal['id'],)).fetchone(),'ID_CONFLICT')
        self.db.execute('INSERT INTO inbox VALUES (?,?)',(proposal['id'],self.store.put('signed-proposal',{'proposal':proposal,'evidence':wire})))
        return {'proposalId':proposal['id'],'proposalDigest':d,'status':'pending'}

    def load_proposal(self, pid):
        proposal=self.get_ref('proposal',pid)
        row=self.db.execute('SELECT object FROM inbox WHERE id=?',(pid,)).fetchone()
        require(row is not None,'CONTENT_UNAVAILABLE')
        item=self.store.get(row[0]); evidence=item['evidence']; auth=evidence['auth']; body=evidence['body']
        require(item['proposal']==proposal and body['operation']=='proposals' and body['payload']==proposal,'INTEGRITY_FAILURE')
        require(auth['projectId']==self.project and auth['requestDigest']==digest('request',body),'INTEGRITY_FAILURE')
        require(recover(self.domain,'Request',auth,evidence['signature'])==proposal['author'],'WRONG_SIGNER')
        return proposal

    def prepare(self, payload, current, now):
        fields(payload,{'accept','reject','grants'})
        require(isinstance(payload['accept'],list) and isinstance(payload['reject'],list),'INVALID_PAYLOAD')
        require(all(isinstance(x,str) for x in payload['accept']+payload['reject']),'INVALID_PAYLOAD')
        ids=payload['accept']+payload['reject']; require(len(ids)==len(set(ids)) and len(ids)<=100,'INVALID_PAYLOAD')
        require(ids or payload['grants'] is not None,'EMPTY_PROPOSAL')
        c=current['control']; old=self.snapshot(c); snapshot=copy.deepcopy(old)
        existing_resolutions={r['proposalId'] for r in snapshot['resolutions']}
        for pid in ids:
            require(pid not in existing_resolutions,'ALREADY_RESOLVED')
            proposal=self.load_proposal(pid)
            accepted=pid in payload['accept']
            if accepted:
                require(proposal['baseCheckpoint']==current['checkpoint']['controlDigest'],'BASE_CONFLICT')
                self.grant(c,proposal['author'],'propose',now)
                current_ids=set(snapshot['currentIds'])
                changes={r['replaces']:'superseded' for r in proposal['records'] if r['replaces']}
                changes.update({rid:'retracted' for rid in proposal['retractIds']})
                require(set(changes)<=current_ids,'INVALID_TRANSITION')
                known={r['id'] for r in snapshot['records']}
                for r in proposal['records']: require(r['id'] not in known,'ID_CONFLICT')
                for ref in snapshot['records']:
                    if ref['id'] in changes: ref['disposition']=changes[ref['id']]
                for r in proposal['records']:
                    snapshot['records'].append({'id':r['id'],'digest':digest('record',r),'disposition':'current'})
                sources={s['id']:s for s in snapshot['sources']}
                for source in proposal['sources']:
                    sources[source['id']]={'id':source['id'],'digest':digest('source',source)}
                snapshot['sources']=sorted(sources.values(),key=lambda s:s['id'])
                snapshot['records'].sort(key=lambda r:r['id'])
                snapshot['currentIds']=sorted(r['id'] for r in snapshot['records'] if r['disposition']=='current')
            snapshot['resolutions'].append({'proposalId':pid,'proposalDigest':digest('proposal',proposal),
                'state':'accepted' if accepted else 'rejected','reason':'Owner reviewed this proposal.'})
        if ids:
            snapshot['previousDigest']=c['snapshotDigest']
            snapshot['resolutions'].sort(key=lambda r:r['proposalId'])
        validate('snapshot',snapshot)
        snapshot_digest=digest('snapshot',snapshot)
        self.put_ref('snapshot',snapshot_digest,snapshot)
        updated={**c,'sequence':str(int(c['sequence'])+1),'previousDigest':current['checkpoint']['controlDigest'],
                 'snapshotDigest':snapshot_digest,'salt':'0x'+os.urandom(32).hex()}
        if payload['grants'] is not None: updated['grants']=payload['grants']
        validate('control',updated)
        cp={'projectId':self.project,'sequence':updated['sequence'],'previousDigest':updated['previousDigest'],
            'controlDigest':digest('control',updated),'deadline':str(now+300)}
        review={'checkpoint':cp,'control':updated,'snapshot':snapshot,
                'records':[self.get_ref('record',r['id'],r['digest']) for r in snapshot['records']],
                'sources':[self.get_ref('source',s['id'],s['digest']) for s in snapshot['sources']],
                'accept':payload['accept'],'reject':payload['reject']}
        self.db.execute('INSERT INTO prepared VALUES (?,?)',(cp['controlDigest'],self.store.put('prepared',review)))
        return review

    def commit(self, payload, current, now):
        fields(payload,{'checkpoint','signature'})
        cp=payload['checkpoint']; validate('checkpoint',cp)
        row=self.db.execute('SELECT object FROM prepared WHERE digest=?',(cp['controlDigest'],)).fetchone()
        require(row is not None,'NOT_PREPARED')
        review=self.store.get(row[0]); require(cp==review['checkpoint'],'CONTENT_MISMATCH')
        envelope={'checkpoint':cp,'control':review['control'],'signature':payload['signature']}
        self.verify_checkpoint(envelope)
        require(int(cp['deadline'])>=now,'EXPIRED')
        require(cp['previousDigest']==current['checkpoint']['controlDigest'] and int(cp['sequence'])==int(current['checkpoint']['sequence'])+1,'BASE_CONFLICT')
        # Expiring app grants must still authorize acceptance when the owner commits.
        for pid in review['accept']:
            self.grant(current['control'],self.load_proposal(pid)['author'],'propose',now)
        if self.registry:
            self.stage_intent(envelope)
            return {'committed':cp['controlDigest'],'sequence':cp['sequence'],'authorityMode':self.registry.mode}
        self.db.execute('INSERT INTO checkpoints VALUES (?,?)',(cp['controlDigest'],self.store.put('checkpoint-envelope',envelope)))
        self.db.execute("UPDATE meta SET value=? WHERE name='head'",(cp['controlDigest'],))
        return {'committed':cp['controlDigest'],'sequence':cp['sequence'],'authorityMode':'signed_log'}

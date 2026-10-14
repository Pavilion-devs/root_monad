"""Owner-local recovery tooling. No SQL, paths, credentials or executable code in archives."""
import os
import sqlite3
import tempfile
from pathlib import Path
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.exceptions import InvalidTag
from memory import Memory, SCHEMA, ZERO, require, fields
from storage import Store
from protocol import canonical, strict_loads, validate, digest, recover, project_id

LIMIT=16*1024*1024
ARCHIVE='portable-memory-recovery/0'
CAPSULE='portable-memory-project-key/0'

def seal(body,key,kind):
    require(len(key)==32,'INVALID_KEY')
    nonce=os.urandom(12)
    return canonical({'format':kind,'nonce':nonce.hex(),'ciphertext':AESGCM(key).encrypt(nonce,canonical(body),kind.encode()).hex()})

def unseal(data,key,kind):
    require(len(data)<=LIMIT,'LIMIT_EXCEEDED')
    try:
        body=strict_loads(data); fields(body,{'format','nonce','ciphertext'})
        require(body['format']==kind,'UNKNOWN_FORMAT')
        return strict_loads(AESGCM(key).decrypt(bytes.fromhex(body['nonce']),bytes.fromhex(body['ciphertext']),kind.encode()))
    except (InvalidTag,TypeError,KeyError,ValueError): raise ValueError('INVALID_RECOVERY_PACKAGE') from None

def read_limited(path):
    with open(path,'rb') as f: data=f.read(LIMIT+1)
    require(len(data)<=LIMIT,'LIMIT_EXCEEDED')
    return data

def sync_directory(path):
    fd=os.open(path,os.O_RDONLY)
    try: os.fsync(fd)
    finally: os.close(fd)

def exclusive(path,data):
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'wb') as f:
        f.write(data); f.flush(); os.fsync(f.fileno())
    sync_directory(Path(path).parent)

def pins(config): return {k:config[k] for k in ['projectId','owner','domain']}

def load_key(path,recovery_key,config):
    body=unseal(read_limited(path),recovery_key,CAPSULE)
    fields(body,{'config','key'})
    require(body['config']==pins(config),'CONFIG_MISMATCH')
    key=bytes.fromhex(body['key']); require(len(key)==32,'INVALID_KEY')
    return key

def validate_package(package,config,registry):
    fields(package,{'formatVersion','config','head','checkpoints','snapshots','records','sources','proposals'})
    require(package['formatVersion']=='0','UNKNOWN_FORMAT')
    require(package['config']==pins(config),'CONFIG_MISMATCH')
    project=config['projectId']; owner=config['owner'].lower(); domain=config['domain']
    for name in ['checkpoints','snapshots','records','sources','proposals']:
        require(isinstance(package[name],list) and len(package[name])<=1000,'LIMIT_EXCEEDED')
    maps={}
    for kind in ['snapshot','record','source']:
        items={}
        for body in package[kind+'s']:
            validate(kind,body); require(body['projectId']==project,'WRONG_PROJECT')
            ident=digest(kind,body) if kind=='snapshot' else body['id']
            require(ident not in items,'DUPLICATE_ENTRY'); items[ident]=body
        maps[kind]=items
    controls={}; previous=ZERO; envelopes=package['checkpoints']
    require(envelopes,'INCOMPLETE_HISTORY')
    for i,env in enumerate(envelopes):
        fields(env,{'checkpoint','control','signature'})
        cp,c=env['checkpoint'],env['control']
        validate('checkpoint',cp);validate('control',c)
        require(cp['projectId']==c['projectId']==project and project_id(owner,c['creationNonce'])==project,'WRONG_PROJECT')
        require(cp['sequence']==c['sequence']==str(i) and cp['previousDigest']==c['previousDigest']==previous,'INCOMPLETE_HISTORY')
        require(cp['controlDigest']==digest('control',c),'CONTENT_MISMATCH')
        require(recover(domain,'Checkpoint',cp,env['signature'])==owner,'WRONG_SIGNER')
        require(c['snapshotDigest'] in maps['snapshot'],'CONTENT_UNAVAILABLE')
        previous=cp['controlDigest']; controls[previous]=c
    require(previous==package['head'],'INCOMPLETE_HISTORY')
    require(set(maps['snapshot'])=={c['snapshotDigest'] for c in controls.values()},'UNREFERENCED_OBJECT')
    proposals={}
    for item in package['proposals']:
        fields(item,{'proposal','evidence'})
        p,e=item['proposal'],item['evidence'];validate('proposal',p)
        fields(e,{'auth','body','signature'}); auth,body=e['auth'],e['body']
        validate('request-auth',auth);validate('request',body)
        require(p['id'] not in proposals,'DUPLICATE_ENTRY')
        base=controls.get(p['baseCheckpoint']);require(base is not None,'INCOMPLETE_HISTORY')
        require(p['projectId']==auth['projectId']==body['projectId']==project,'WRONG_PROJECT')
        require(body['operation']=='proposals' and body['payload']==p and auth['requestDigest']==digest('request',body),'CONTENT_MISMATCH')
        require(auth['checkpointDigest']==p['baseCheckpoint'] and auth['serviceId']==base['serviceId'],'WRONG_AUDIENCE')
        require(recover(domain,'Request',auth,e['signature'])==p['author'],'WRONG_SIGNER')
        require(p['author']==owner or any(g['application']==p['author'] and 'propose' in g['rights'] for g in base['grants']),'SCOPE_DENIED')
        for kind in ['record','source']:
            for entry in p[kind+'s']:
                require(maps[kind].get(entry['id'])==entry,'CONTENT_UNAVAILABLE')
        require(len(p['records'])+len(p['retractIds'])>0,'EMPTY_PROPOSAL')
        base_snapshot=maps['snapshot'][base['snapshotDigest']]
        available={r['id'] for r in base_snapshot['sources']}|{r['id'] for r in p['sources']}
        old_ids={r['id'] for r in base_snapshot['records']};new_ids={r['id'] for r in p['records']}
        require(not old_ids.intersection(new_ids),'ID_CONFLICT')
        targets=set(p['retractIds'])
        require(p['retractIds']==sorted(targets),'INVALID_ORDER')
        for kind in ['record','source']:
            ids=[r['id'] for r in p[kind+'s']];require(ids==sorted(set(ids)),'INVALID_ORDER')
        for r in p['records']:
            require(r['author']==p['author'],'WRONG_AUTHOR')
            require(r['sourceIds']==sorted(set(r['sourceIds'])) and set(r['sourceIds'])<=available,'MISSING_SOURCE')
            if r['replaces']:
                require(r['replaces'] not in targets and r['replaces'] not in new_ids,'INVALID_TRANSITION')
                targets.add(r['replaces'])
        require(targets<=set(base_snapshot['currentIds']),'INVALID_TRANSITION')
        proposals[p['id']]=item
    for s in maps['snapshot'].values():
        for kind in ['record','source']:
            ids=[r['id'] for r in s[kind+'s']]
            require(ids==sorted(set(ids)),'INVALID_MANIFEST')
            for ref in s[kind+'s']:
                body=maps[kind].get(ref['id']);require(body is not None,'CONTENT_UNAVAILABLE')
                require(digest(kind,body)==ref['digest'],'CONTENT_MISMATCH')
        require(s['currentIds']==sorted(r['id'] for r in s['records'] if r['disposition']=='current'),'INVALID_MANIFEST')
        for r in s['records']:
            require(set(maps['record'][r['id']]['sourceIds'])<={x['id'] for x in s['sources']},'MISSING_SOURCE')
        resolved=[r['proposalId'] for r in s['resolutions']]
        require(resolved==sorted(set(resolved)),'INVALID_MANIFEST')
        for resolution in s['resolutions']:
            item=proposals.get(resolution['proposalId']);require(item is not None,'CONTENT_UNAVAILABLE')
            require(digest('proposal',item['proposal'])==resolution['proposalDigest'],'CONTENT_MISMATCH')
    require(registry is not None,'REGISTRY_REQUIRED')
    view=registry.view(project)
    require(view['owner']==owner and view['digest']==package['head'] and view['sequence']==envelopes[-1]['checkpoint']['sequence'],'STALE_EXPORT')
    # Registry predecessor ordering plus the signed contiguous history binds every predecessor.
    require(registry.accepted(envelopes[-1]['checkpoint'],owner,view) is not None,'UNVERIFIED')
    return maps

def export_memory(memory,archive_path,recovery_path):
    require(memory.registry is not None,'REGISTRY_REQUIRED')
    require(Path(archive_path).resolve()!=Path(recovery_path).resolve(),'INVALID_DESTINATION')
    require(not Path(archive_path).exists() and not Path(recovery_path).exists(),'DESTINATION_EXISTS')
    memory.recover_intents()
    memory.db.execute('BEGIN IMMEDIATE')
    try:
        current=memory.current();memory.check_binding(current['control'])
        require(not memory.db.execute("SELECT 1 FROM intents WHERE status='pending'").fetchone(),'COMMIT_PENDING')
        chain=[];head=current['checkpoint']['controlDigest']
        while head!=ZERO:
            require(len(chain)<1000,'LIMIT_EXCEEDED')
            row=memory.db.execute('SELECT object FROM checkpoints WHERE digest=?',(head,)).fetchone()
            require(row is not None,'CONTENT_UNAVAILABLE')
            env=memory.store.get(row[0]);memory.verify_checkpoint(env)
            require(env['checkpoint']['controlDigest']==head,'INTEGRITY_FAILURE')
            chain.append({k:env[k] for k in ['checkpoint','control','signature']});head=env['checkpoint']['previousDigest']
        chain.reverse()
        snapshot_ids=sorted({e['control']['snapshotDigest'] for e in chain})
        package={'formatVersion':'0','config':pins(memory.config),'head':current['checkpoint']['controlDigest'],
                 'checkpoints':chain,'snapshots':[memory.get_ref('snapshot',d,d) for d in snapshot_ids],
                 'records':[],'sources':[],'proposals':[]}
        for kind in ['record','source']:
            package[kind+'s']=[memory.get_ref(kind,ident) for (ident,) in memory.db.execute('SELECT id FROM refs WHERE kind=? ORDER BY id',(kind,))]
        for pid,obj in memory.db.execute('SELECT id,object FROM inbox ORDER BY id'):
            memory.load_proposal(pid);package['proposals'].append(memory.store.get(obj))
        validate_package(package,memory.config,memory.registry)
        memory.db.execute("INSERT OR REPLACE INTO meta VALUES ('frozen','1')")
        memory.db.execute('COMMIT')
    except Exception:
        memory.db.execute('ROLLBACK');raise
    key=os.urandom(32); sealed=seal(package,key,ARCHIVE)
    require(len(sealed)<=LIMIT,'LIMIT_EXCEEDED')
    # Recovery key is a separate owner-held artifact, never part of the archive or stdout.
    exclusive(recovery_path,key.hex().encode()+b'\n')
    exclusive(archive_path,sealed)
    return {'head':package['head'],'archive':str(archive_path),'recoveryKeyFile':str(recovery_path),'writesFrozen':True}

def restore_memory(archive_path,recovery_key,directory,config,binding,registry):
    package=unseal(read_limited(archive_path),recovery_key,ARCHIVE)
    maps=validate_package(package,config,registry)
    fields(binding,{'serviceId','storage'})
    c=package['checkpoints'][-1]['control']
    target={**c,'serviceId':binding['serviceId'],'storage':binding['storage'],
            'grants':[{**g,'serviceId':binding['serviceId']} for g in c['grants']]}
    validate('control',target)
    require(binding['serviceId']!=c['serviceId'] and binding['storage']['providerId']!=c['storage']['providerId'],'NEW_PROVIDER_REQUIRED')
    directory=Path(directory); require(not directory.exists(),'DESTINATION_EXISTS')
    # All validation precedes staging. No archive entry is ever interpreted as a filesystem path.
    staging=Path(tempfile.mkdtemp(prefix='.memory-import-',dir=directory.parent))
    db=None
    try:
        key=os.urandom(32);path=staging/'memory.sqlite'
        db=sqlite3.connect(path,isolation_level=None);os.chmod(path,0o600);db.executescript(SCHEMA)
        store=Store(db,key,config['projectId']);db.execute('BEGIN IMMEDIATE')
        db.execute('INSERT INTO meta VALUES (?,?)',('config',store.put('config',config)))
        db.execute('INSERT INTO meta VALUES (?,?)',('head',package['head']))
        db.execute('INSERT INTO meta VALUES (?,?)',('binding',store.put('binding',binding)))
        db.execute('INSERT INTO meta VALUES (?,?)',('importedHead',package['head']))
        for kind,items in maps.items():
            for ident,body in items.items(): db.execute('INSERT INTO refs VALUES (?,?,?,?)',(kind,ident,digest(kind,body),store.put(kind,body)))
        for env in package['checkpoints']:
            db.execute('INSERT INTO checkpoints VALUES (?,?)',(env['checkpoint']['controlDigest'],store.put('checkpoint-envelope',env)))
        for item in package['proposals']:
            p=item['proposal'];db.execute('INSERT INTO refs VALUES (?,?,?,?)',('proposal',p['id'],digest('proposal',p),store.put('proposal',p)))
            db.execute('INSERT INTO inbox VALUES (?,?)',(p['id'],store.put('signed-proposal',item)))
        db.execute('COMMIT');db.close();db=None
        exclusive(staging/'project-key.enc',seal({'config':pins(config),'key':key.hex()},recovery_key,CAPSULE))
        # Recheck immediately before publishing; owner commit still enforces the base afterward.
        validate_package(package,config,registry)
        require(not directory.exists(),'DESTINATION_EXISTS')
        os.rename(staging,directory)
        sync_directory(directory.parent)
        return {'directory':str(directory),'head':package['head'],'status':'staged_owner_approval_required'}
    finally:
        if db is not None: db.close()
        if staging.exists():
            import shutil
            shutil.rmtree(staging)

def prepare_migration(memory,now):
    require(memory.registry is not None,'REGISTRY_REQUIRED')
    current=memory.current();c=current['control'];binding=memory.binding()
    row=memory.db.execute("SELECT value FROM meta WHERE name='importedHead'").fetchone()
    require(row is not None and row[0]==current['checkpoint']['controlDigest'],'STALE_EXPORT')
    require(binding['serviceId']!=c['serviceId'],'ALREADY_MIGRATED')
    updated={**c,'serviceId':binding['serviceId'],'storage':binding['storage'],
             'grants':[{**g,'serviceId':binding['serviceId']} for g in c['grants']],
             'sequence':str(int(c['sequence'])+1),'previousDigest':current['checkpoint']['controlDigest'],'salt':'0x'+os.urandom(32).hex()}
    validate('control',updated)
    cp={'projectId':memory.project,'sequence':updated['sequence'],'previousDigest':updated['previousDigest'],
        'controlDigest':digest('control',updated),'deadline':str(now+300)}
    review={'checkpoint':cp,'control':updated,'snapshot':memory.snapshot(c),'accept':[],'reject':[]}
    memory.db.execute('INSERT INTO prepared VALUES (?,?)',(cp['controlDigest'],memory.store.put('prepared',review)))
    return review

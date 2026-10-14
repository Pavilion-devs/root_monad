"""Independent signed Python client. Configuration and app key arrive on stdin."""
import json
import os
import sys
import time
from urllib.request import Request,build_opener,HTTPRedirectHandler
from protocol import digest, sign, recover
from registry import registry_for

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs): return None

def request(url, data=None):
    # Signed requests stay on the configured endpoint; never follow a redirect.
    req=Request(url,data,{'Content-Type':'application/json'})
    with build_opener(NoRedirect()).open(req,timeout=30) as response:
        return json.load(response)

def call(url, config, key, operation, payload):
    head=request(url+'/head')
    body={'formatVersion':'0','projectId':config['projectId'],'method':'POST',
          'path':f"/v0/projects/{config['projectId']}/{operation}",'operation':operation,'payload':payload}
    auth={'projectId':config['projectId'],'serviceId':config['serviceId'],'checkpointDigest':head['checkpointDigest'],
          'requestDigest':digest('request',body),'nonce':'0x'+os.urandom(32).hex(),'deadline':str(int(time.time())+120)}
    wire={'body':body,'auth':auth,'signature':sign(key,config['domain'],'Request',auth)}
    return request(url+body['path'],json.dumps(wire).encode())

def verify(config,bundle,historical_digest=None):
    c,cp,s=bundle['control'],bundle['checkpoint'],bundle['snapshot']
    registry=registry_for(config['domain'],config['registry']) if 'registry' in config else None
    try:
        mode=registry.mode if registry else 'signed_log'
        expected='historical_verified' if historical_digest else 'current_verified'
        if bundle['authorityMode']!=mode or bundle['verification']!=expected: raise ValueError('UNVERIFIED')
        if historical_digest and cp['controlDigest']!=historical_digest: raise ValueError('UNVERIFIED')
        if mode=='signed_log' and ('salt' not in config['domain'] or 'chainId' in config['domain']): raise ValueError('UNVERIFIED')
        if not (c['projectId']==cp['projectId']==s['projectId']==config['projectId']): raise ValueError('WRONG_PROJECT')
        if cp['sequence']!=c['sequence'] or cp['previousDigest']!=c['previousDigest']: raise ValueError('CONTENT_MISMATCH')
        if cp['controlDigest']!=digest('control',c) or c['snapshotDigest']!=digest('snapshot',s): raise ValueError('CONTENT_MISMATCH')
        if recover(config['domain'],'Checkpoint',cp,bundle['signature'])!=config['owner'].lower(): raise ValueError('WRONG_SIGNER')
        refs={r['id']:r for r in s['records']}
        current=sorted(r['id'] for r in s['records'] if r['disposition']=='current')
        if len(refs)!=len(s['records']) or current!=s['currentIds']: raise ValueError('INVALID_MANIFEST')
        expected=sorted(refs) if bundle['verification']=='historical_verified' else current
        if sorted(r['id'] for r in bundle['records'])!=expected: raise ValueError('INCOMPLETE_RECORDS')
        source_ids=set()
        for r in bundle['records']:
            if r['projectId']!=config['projectId'] or digest('record',r)!=refs[r['id']]['digest']: raise ValueError('CONTENT_MISMATCH')
            source_ids.update(r['sourceIds'])
        sources={s['id']:s['digest'] for s in s['sources']}
        if len(sources)!=len(s['sources']) or sorted(source_ids)!=sorted(s['id'] for s in bundle['sources']): raise ValueError('INCOMPLETE_SOURCES')
        for source in bundle['sources']:
            if source['projectId']!=config['projectId'] or digest('source',source)!=sources[source['id']]: raise ValueError('CONTENT_MISMATCH')
        if registry:
            view=registry.view(config['projectId'])
            if view['owner']!=config['owner'].lower(): raise ValueError('WRONG_SIGNER')
            if bundle['verification']=='current_verified' and (view['digest']!=cp['controlDigest'] or view['sequence']!=cp['sequence']): raise ValueError('STALE_CONTEXT')
            if not registry.accepted(cp,config['owner'],view): raise ValueError('UNVERIFIED')
        return bundle
    finally:
        if registry: registry.close()

if __name__=='__main__':
    invocation=json.load(sys.stdin)
    result=call(invocation['url'],invocation['config'],invocation['key'],invocation.get('operation','context'),invocation.get('payload',{}))
    if 'records' in result: verify(invocation['config'],result,invocation.get('payload',{}).get('checkpointDigest') if invocation.get('operation')=='history' else None)
    print(json.dumps(result))

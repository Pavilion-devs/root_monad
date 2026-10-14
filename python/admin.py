"""Local owner administration. Read one JSON request from stdin; never print keys."""
import json
import sys
import time
from memory import Memory, require
from protocol import strict_loads
from registry import registry_for
from recovery import export_memory, restore_memory, prepare_migration, load_key, LIMIT

def run(request):
    config=request['config']
    registry=registry_for(config['domain'],request['registry'],request.get('relayerKey'))
    try:
        operation=request['operation']
        if operation=='restore':
            return restore_memory(request['archive'],bytes.fromhex(request['recoveryKey']),request['directory'],config,request['binding'],registry)
        key=load_key(request['keyEnvelope'],bytes.fromhex(request['recoveryKey']),config) if 'keyEnvelope' in request else bytes.fromhex(request['key'])
        memory=Memory(request['db'],key,config,registry=registry)
        try:
            if operation=='export': return export_memory(memory,request['archive'],request['recoveryKeyFile'])
            if operation=='unfreeze':
                memory.check_binding(memory.current()['control'])
                memory.db.execute("DELETE FROM meta WHERE name='frozen'")
                return {'writesFrozen':False}
            if operation=='prepare-migration':
                memory.db.execute('BEGIN IMMEDIATE')
                try:
                    result=prepare_migration(memory,int(time.time()));memory.db.execute('COMMIT');return result
                except Exception:
                    memory.db.execute('ROLLBACK');raise
            if operation=='commit-migration':
                payload=request['payload'];cp=payload['checkpoint']
                row=memory.db.execute('SELECT object FROM prepared WHERE digest=?',(cp['controlDigest'],)).fetchone()
                require(row is not None,'NOT_PREPARED')
                review=memory.store.get(row[0]); memory.check_binding(review['control'])
                require(cp==review['checkpoint'],'CONTENT_MISMATCH')
                memory.verify_checkpoint({'checkpoint':cp,'control':review['control'],'signature':payload['signature']})
                require(review['accept']==review['reject']==[],'INVALID_MIGRATION')
                existing=memory.db.execute('SELECT 1 FROM intents WHERE digest=?',(cp['controlDigest'],)).fetchone()
                if existing:
                    require(payload['signature']==memory.store.get(memory.db.execute('SELECT object FROM intents WHERE digest=?',(cp['controlDigest'],)).fetchone()[0])['envelope']['signature'],'CONTENT_MISMATCH')
                    return memory.registry_result({'committed':cp['controlDigest'],'sequence':cp['sequence'],'authorityMode':registry.mode})
                memory.db.execute('BEGIN IMMEDIATE')
                try:
                    result=memory.commit(payload,memory.current(),int(time.time()));memory.db.execute('COMMIT')
                except Exception:
                    memory.db.execute('ROLLBACK');raise
                return memory.registry_result(result)
            raise ValueError('INVALID_OPERATION')
        finally: memory.close()
    finally:
        if registry: registry.close()

if __name__=='__main__':
    try:
        data=sys.stdin.buffer.read(LIMIT+1);require(len(data)<=LIMIT,'LIMIT_EXCEEDED')
        print(json.dumps(run(strict_loads(data))))
    except Exception as e:
        # Do not include submitted payloads, keys, source excerpts or tracebacks in errors.
        code=str(e) if isinstance(e,ValueError) and str(e).isupper() and len(str(e))<80 else 'ADMIN_FAILED'
        print(json.dumps({'code':code}));sys.exit(1)

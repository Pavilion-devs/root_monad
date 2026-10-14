"""Build an allowlisted source kit. Never includes local state, reports or credentials."""
import hashlib
import json
from pathlib import Path
import zipfile
ROOT=Path(__file__).resolve().parents[1]
NAME='portable-memory-devkit-0.1.0'


def build():
    files={
        'README.md':ROOT/'devkit/README.md',
        '.gitignore':ROOT/'devkit/.gitignore',
        'requirements.lock':ROOT/'integrations/claude-code/requirements.lock',
        'devkit/memory.py':ROOT/'devkit/memory.py',
        'devkit/smoke.py':ROOT/'devkit/smoke.py',
    }
    for name in ('memory','protocol','storage','client','owner_review','owner_cli','recovery','registry','rpc_transport','mcp_bridge','server'):
        files['python/'+name+'.py']=ROOT/'python'/(name+'.py')
    for path in sorted((ROOT/'schemas').glob('*.schema.json')):files['schemas/'+path.name]=path
    payload={name:path.read_bytes() for name,path in files.items()}
    # No user paths, hosted endpoints, testnet project IDs or credential files.
    forbidden=[str(Path.home()).encode(),b'memory.useroot.xyz',b'57.129.106.133',b'0x4a2a2bd1d8d48e3d96f664c3ee1771e030db31db407b7b55a790454ba216813f']
    for name,data in payload.items():
        assert not any(token in data for token in forbidden),name
        assert not name.endswith(('.env','.enc','.sqlite','.key'))
    manifest={'name':NAME,'authority':'signed_log','files':{name:hashlib.sha256(data).hexdigest() for name,data in sorted(payload.items())}}
    payload['MANIFEST.json']=(json.dumps(manifest,indent=2)+'\n').encode()
    target=ROOT/'dist';target.mkdir(exist_ok=True)
    archive=target/(NAME+'.zip')
    with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED) as package:
        for name,data in sorted(payload.items()):
            info=zipfile.ZipInfo(NAME+'/'+name,date_time=(2026,10,13,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o100644<<16
            package.writestr(info,data)
    checksum=hashlib.sha256(archive.read_bytes()).hexdigest()
    (target/'SHA256SUMS').write_text(checksum+'  '+archive.name+'\n')
    print(json.dumps({'archive':str(archive),'sha256':checksum,'fileCount':len(payload),'bytes':archive.stat().st_size}))


if __name__=='__main__':build()

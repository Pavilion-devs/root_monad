"""Portable memory local developer kit. No hosted credentials or public fixture keys."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import signal
import sys
import time
from urllib.error import HTTPError
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'python'))
from eth_account import Account
from memory import Memory,ZERO,require
from protocol import digest,sign,project_id
from recovery import exclusive,sync_directory
from client import call,verify
from owner_cli import Owner,proposal_view,review_view,public_json
from mcp_bridge import Bridge,create_server

APPS=('claude','codex')

def write(path,value):
    exclusive(path,json.dumps(value,indent=2).encode()+b'\n')

def read(path):return json.loads(path.read_text())
def random_id():return '0x'+os.urandom(32).hex()

def connect(state):
    directory=state/'connections';directory.mkdir(exist_ok=True,mode=0o700)
    command=str(Path(sys.executable).absolute())
    def args(app):return [str(Path(__file__).resolve()),'--state',str(state),'mcp',app]
    claude={'mcpServers':{'portable-memory':{'type':'stdio','command':command,'args':args('claude')}}}
    codex='[mcp_servers.portable_memory]\ncommand = '+json.dumps(command)+'\nargs = '+json.dumps(args('codex'))+'\nrequired = true\ntool_timeout_sec = 90\nenabled_tools = ["memory_current", "memory_propose"]\n'
    (directory/'claude.json').write_text(json.dumps(claude,indent=2)+'\n')
    (directory/'codex.toml').write_text(codex)
    return {'claudeConfig':str(directory/'claude.json'),'codexConfig':str(directory/'codex.toml')}


def init(state):
    state.mkdir(parents=True,mode=0o700,exist_ok=False)
    private=state/'private';private.mkdir(mode=0o700)
    owner=Account.create();nonce=random_id();service=random_id()
    config={'projectId':project_id(owner.address.lower(),nonce),'owner':owner.address.lower(),'domain':{'name':'PortableMemory','version':'0','salt':random_id()},'serviceId':service}
    grants=[]
    for name in APPS:
        account=Account.create();directory=private/name;directory.mkdir(mode=0o700)
        write(directory/'identity.json',{'application':account.address.lower(),'key':'0x'+account.key.hex()})
        grants.append({'application':account.address.lower(),'serviceId':service,'rights':['propose','read_current'],'expiresAt':str(int(time.time())+7*86400)})
    snapshot={'formatVersion':'0','projectId':config['projectId'],'previousDigest':ZERO,'records':[],'sources':[],'currentIds':[],'resolutions':[]}
    control={'formatVersion':'0','projectId':config['projectId'],'sequence':'0','previousDigest':ZERO,'creationNonce':nonce,'snapshotDigest':digest('snapshot',snapshot),'serviceId':service,'grants':sorted(grants,key=lambda g:g['application']),'storage':{'providerId':random_id(),'locator':'local://developer-kit'},'salt':random_id()}
    cp={'projectId':config['projectId'],'sequence':'0','previousDigest':ZERO,'controlDigest':digest('control',control),'deadline':str(int(time.time())+300)}
    genesis={'checkpoint':cp,'control':control,'snapshot':snapshot,'signature':sign(owner.key,config['domain'],'Checkpoint',cp)}
    storage=os.urandom(32)
    write(state/'project.json',config)
    write(private/'owner.json',{'key':'0x'+owner.key.hex(),'wrapping':os.urandom(32).hex()})
    write(private/'service.json',{'key':storage.hex()})
    memory=Memory(state/'memory.sqlite',storage,config,genesis);memory.close()
    return {'initialized':True,'authority':'signed_log','projectId':config['projectId'],'connections':connect(state)}


def endpoint(state):
    from urllib.parse import urlsplit
    url=read(state/'endpoint.json')['url'];parsed=urlsplit(url)
    require(parsed.scheme=='http' and parsed.hostname=='127.0.0.1' and parsed.port and not parsed.username and not parsed.password and not parsed.path and not parsed.query and not parsed.fragment,'LOOPBACK_REQUIRED')
    return url


def bridge(state,app):
    identity=read(state/'private'/app/'identity.json')
    profile={'config':read(state/'project.json'),'url':endpoint(state),'application':identity['application']}
    return Bridge(profile,identity['key'],state/'private'/app/'outbox')


def owner(state):
    identity=read(state/'private/owner.json')
    return Owner(endpoint(state),read(state/'project.json'),identity['key'],bytes.fromhex(identity['wrapping']),state/'private/owner-reviews')


def serve(state,port):
    from server import BoundedServer,Handler,http_settings
    with open(state/'service.lock','a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        memory=Memory(state/'memory.sqlite',bytes.fromhex(read(state/'private/service.json')['key']),read(state/'project.json'))
        if port==0 and (state/'endpoint.json').exists():
            from urllib.parse import urlsplit
            port=urlsplit(endpoint(state)).port
        server=BoundedServer(('127.0.0.1',port),Handler)
        server.memory=memory;server.demo=None;_,server.origins=http_settings({},server.server_port)
        value={'url':f'http://127.0.0.1:{server.server_port}','authority':'signed_log'}
        temp=state/('endpoint-'+os.urandom(8).hex()+'.tmp');write(temp,value);os.replace(temp,state/'endpoint.json');sync_directory(state)
        print(public_json(value).replace('\n',''),flush=True)
        def stop(*args):raise SystemExit(0)
        signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
        try:server.serve_forever()
        finally:server.server_close();memory.close()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state',type=Path,default=Path('.memory-workspace'))
    sub=parser.add_subparsers(dest='command',required=True)
    for name in ('init','connect','inbox','apps','resume','doctor'):sub.add_parser(name)
    p=sub.add_parser('serve');p.add_argument('--port',type=int,default=0)
    for name in ('current','mcp'):
        p=sub.add_parser(name);p.add_argument('app',choices=APPS)
    p=sub.add_parser('propose');p.add_argument('app',choices=APPS);p.add_argument('--content',required=True);p.add_argument('--request-id',required=True);p.add_argument('--kind',choices=('decision','observation','open_question'),default='decision')
    for name in ('approve','reject','revoke'):
        p=sub.add_parser(name);p.add_argument('id');p.add_argument('--confirm')
    args=parser.parse_args();state=args.state.expanduser().resolve()
    if args.command=='init':return init(state)
    require((state/'project.json').is_file(),'INITIALIZE_FIRST')
    if args.command=='connect':return connect(state)
    if args.command=='serve':serve(state,args.port);return
    if args.command=='mcp':create_server(bridge(state,args.app)).run(transport='stdio');return
    if args.command in ('current','propose'):
        b=bridge(state,args.app)
        if args.command=='current':return b.read()
        current=b.read()
        return b.propose(args.request_id,current['checkpoint'],args.content,args.kind)
    o=owner(state)
    with open(o.directory/'operator.lock','a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if args.command=='doctor':
            current=o.current();return {'verified':True,'authority':current['authorityMode'],'sequence':current['control']['sequence'],'url':o.url,'recordCount':len(current['records'])}
        if args.command=='inbox':
            before=o.current();return {'sequence':before['control']['sequence'],'proposals':[proposal_view(i,before) for i in o.inbox(before)]}
        if args.command=='apps':return {'grants':o.current()['control']['grants'],'identities':{app:read(state/'private'/app/'identity.json')['application'] for app in APPS}}
        if args.command=='resume':return o.resume()
        target=read(state/'private'/args.id/'identity.json')['application'] if args.command=='revoke' and args.id in APPS else args.id
        if args.confirm:
            saved=o.load();require(saved and saved['action']==args.command and saved['target']==target.lower(),'CONFIRMATION_MISMATCH')
            return o.confirm(args.confirm)
        review=o.prepare(args.command,target)
        print(public_json(review_view(review)),flush=True)
        if sys.stdin.isatty():
            confirmation=input('Paste the full confirmation to sign (Enter cancels): ').strip()
            if confirmation:return o.confirm(confirmation)
        return {'previewOnly':True,'approvalSigned':False}


if __name__=='__main__':
    try:
        result=main()
        if result is not None:print(public_json(result),flush=True)
    except Exception as error:
        code=str(error) if isinstance(error,ValueError) and str(error).isupper() and len(str(error))<80 else type(error).__name__
        if isinstance(error,HTTPError):
            try:code=json.load(error).get('code','SERVICE_UNAVAILABLE')
            except Exception:code='SERVICE_UNAVAILABLE'
        print(json.dumps({'error':code,'help':'Check that the local service is running and the same --state folder is selected. For an interrupted confirmed change use resume; do not delete private state.'}),file=sys.stderr)
        sys.exit(1)

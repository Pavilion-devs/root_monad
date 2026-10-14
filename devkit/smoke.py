"""Exercise a fresh isolated project without a model, cloud account or funded wallet."""
import asyncio
from datetime import timedelta
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
ROOT=Path(__file__).resolve().parents[1]
CLI=ROOT/'devkit/memory.py'


def run(state,*args,success=True):
    result=subprocess.run([sys.executable,str(CLI),'--state',str(state),*args],capture_output=True,text=True,timeout=30)
    if success and result.returncode:raise RuntimeError(result.stderr)
    if not success:
        assert result.returncode!=0
        return json.loads(result.stderr)
    # Review commands deliberately print both the review and a preview-only marker.
    decoder=json.JSONDecoder();remaining=result.stdout.strip();values=[]
    while remaining:
        value,end=decoder.raw_decode(remaining);values.append(value);remaining=remaining[end:].strip()
    return values[0] if len(values)==1 else values


def start(state):
    process=subprocess.Popen([sys.executable,str(CLI),'--state',str(state),'serve'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    ready=json.loads(process.stdout.readline());assert ready['authority']=='signed_log'
    return process


def stop(process):
    process.terminate();process.communicate(timeout=10)


async def mcp_check(state):
    params=StdioServerParameters(command=sys.executable,args=[str(CLI),'--state',str(state),'mcp','codex'])
    async with stdio_client(params) as (r,w):
        async with ClientSession(r,w,read_timeout_seconds=timedelta(seconds=30)) as session:
            await session.initialize();tools=await session.list_tools()
            assert {t.name for t in tools.tools}=={'memory_current','memory_propose'}
            result=await session.call_tool('memory_current',{});assert not result.isError
            data=result.structuredContent or json.loads(result.content[0].text)
            assert data['verification']=='current_verified' and data['sequence']=='1'
            assert data['records'][0]['content']=='Developer-kit sample decision.'


def main():
    with tempfile.TemporaryDirectory(prefix='portable-memory-kit-check-') as folder:
        state=Path(folder)/'new project with spaces'
        initial=run(state,'init')
        assert initial['authority']=='signed_log'
        assert run(state,'init',success=False)['error']=='FileExistsError'
        server=start(state)
        try:
            assert run(state,'current','codex')['records']==[]
            receipt=run(state,'propose','claude','--request-id','sample-1','--content','Developer-kit sample decision.')
            assert receipt['status']=='pending_owner_review'
            assert run(state,'current','codex')['records']==[]
            review,preview=run(state,'approve',receipt['proposalId'])
            assert preview=={'previewOnly':True,'approvalSigned':False}
            assert run(state,'current','codex')['sequence']=='0'
            assert run(state,'approve',receipt['proposalId'],'--confirm','wrong',success=False)['error']=='CONFIRMATION_MISMATCH'
            result=run(state,'approve',receipt['proposalId'],'--confirm',review['confirmation'])
            assert result['verified'] and result['sequence']=='1'
            assert run(state,'resume')['sequence']=='1'
            a=run(state,'current','claude');b=run(state,'current','codex')
            assert a['checkpoint']==b['checkpoint'] and a['records']==b['records']
            asyncio.run(mcp_check(state))
            sys.path.insert(0,str(ROOT/'python'))
            from client import call
            from urllib.error import HTTPError
            config=json.loads((state/'project.json').read_text());app=json.loads((state/'private/codex/identity.json').read_text())
            url=json.loads((state/'endpoint.json').read_text())['url']
            try:call(url,config,app['key'],'prepare',{'accept':[],'reject':[],'grants':[]})
            except HTTPError as error:assert json.load(error)['code']=='SCOPE_DENIED'
            else:raise AssertionError('App has owner authority')
            stop(server);server=start(state)
            assert run(state,'current','codex')['checkpoint']==a['checkpoint']
            p=run(state,'propose','claude','--request-id','reject-1','--content','Unaccepted suggestion.')
            r,_=run(state,'reject',p['proposalId']);run(state,'reject',p['proposalId'],'--confirm',r['confirmation'])
            assert run(state,'current','codex')['records']==a['records']
            r,_=run(state,'revoke','codex');run(state,'revoke','codex','--confirm',r['confirmation'])
            assert run(state,'current','codex',success=False)['error']=='SCOPE_DENIED'
            assert run(state,'current','claude')['records']==a['records']
            raw=(state/'memory.sqlite').read_bytes()
            assert b'Developer-kit sample decision.' not in raw
            for path in (state/'private').rglob('*.json'):
                assert path.stat().st_mode & 0o077==0
            print(json.dumps({'passed':True,'authority':'signed_log','checks':['fresh identities','no overwrite','proposal remains pending','exact owner confirmation','shared verified reads','real MCP stdio','owner scope denial','restart persistence','rejection','revocation','encrypted database','private file permissions'],'modelCalls':0,'chainTransactions':0},indent=2))
        finally:
            if server.poll() is None:stop(server)


if __name__=='__main__':main()

"""Bounded real Claude proposal and fresh Codex memory read; never approves content."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
from hosted import ROOT,DIRECTORY
sys.path.insert(0,str(ROOT/'python'))
from client import call,verify
from memory import require
from mcp_bridge import load_profile

DECISION='Portable memory is a separate project from the agent runtime. Keep its code and documentation in the portable-memory folder, separate from the runtime folder.'


def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m


def execute(command,prompt,env):
    with tempfile.TemporaryDirectory(prefix='portable-memory-handoff-') as directory:
        process=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env,cwd=directory,start_new_session=True)
        try:out,err=process.communicate(prompt.encode(),timeout=240)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid,signal.SIGTERM);process.communicate(timeout=15);raise ValueError('MODEL_ATTEMPT_UNCERTAIN')
    events=[]
    for line in out.decode().splitlines():
        try:events.append(json.loads(line))
        except ValueError:pass
    return process.returncode,events


def propose(env_file):
    report=ROOT/'results/real-project-proposal.json'
    require(not report.exists(),'PROPOSAL_RUN_ALREADY_ATTEMPTED')
    profile,key=load_profile(DIRECTORY/'claude-code/profile.json')
    before=verify(profile['config'],call(profile['url'],profile['config'],key,'context',{}))
    helper=module('claude_launcher',ROOT/'integrations/claude-code/chat.py')
    credentials=module('credentials_reader',ROOT/'scripts/live-assistant.py').credentials(env_file)
    require(credentials.get('ANTHROPIC_API_KEY') and credentials.get('ANTHROPIC_MODEL'),'MODEL_CONFIGURATION_REQUIRED')
    command=helper.launch_arguments(credentials['ANTHROPIC_MODEL'])
    index=command.index('--allowedTools');command[index+1]='mcp__portable-memory__memory_current,mcp__portable-memory__memory_propose'
    command+=['--print','--no-session-persistence','--permission-mode','dontAsk','--output-format','stream-json','--verbose','--max-budget-usd','0.50']
    env={k:v for k,v in os.environ.items() if k in ('HOME','PATH','TMPDIR','USER','LANG','SHELL','TERM','SSL_CERT_FILE')};env.update(credentials)
    if credentials.get('ANTHROPIC_WORKSPACE_ID'):
        workspace=credentials['ANTHROPIC_WORKSPACE_ID'];require('\n' not in workspace and '\r' not in workspace,'INVALID_WORKSPACE')
        env['ANTHROPIC_CUSTOM_HEADERS']='anthropic-workspace-id: '+workspace
    prompt=('The user previously requested a separate folder for this new work to avoid colliding with the agent runtime, and has authorized this cross-app proposal test. '
            'Call memory_current, then submit exactly one memory_propose with request_id real-project-separation-1, kind decision, replaces null, '
            'the current checkpoint you just read, and exactly this content: '+DECISION+
            ' Do not approve anything. Report the pending proposal ID and stop. If a tool fails, stop.')
    report.write_text(json.dumps({'attempted':True,'passed':False})+'\n')
    code,events=execute(command,prompt,env)
    calls=[b for e in events if e.get('type')=='assistant' for b in e.get('message',{}).get('content',[]) if b.get('type')=='tool_use']
    final=[e for e in events if e.get('type')=='result']
    value={'attempted':True,'passed':False,'exitCode':code,'events':[e for e in events if e.get('type') in ('assistant','user','result')],'costUsd':final[-1].get('total_cost_usd') if final else None}
    report.write_text(json.dumps(value,indent=2)+'\n')
    require(code==0 and final and not final[-1].get('is_error'),'CLAUDE_RUN_FAILED')
    require([c['name'] for c in calls]==['mcp__portable-memory__memory_current','mcp__portable-memory__memory_propose'],'UNEXPECTED_TOOL_CALLS')
    after=verify(profile['config'],call(profile['url'],profile['config'],key,'context',{}))
    require(after['checkpoint']==before['checkpoint'] and after['records']==before['records'],'PROPOSAL_CHANGED_ACCEPTED_MEMORY')
    inbox=call(profile['url'],profile['config'],key,'inbox',{})
    matching=[i for i in inbox['proposals'] if len(i['proposal']['records'])==1 and i['proposal']['records'][0]['content']==DECISION]
    require(len(matching)==1 and matching[0]['status']=='pending' and matching[0]['proposal']['author']==profile['application'],'PENDING_PROPOSAL_MISSING')
    p=matching[0]['proposal'];value.update(passed=True,proposalId=p['id'],recordId=p['records'][0]['id'],checkpoint=after['checkpoint']['controlDigest'],content=DECISION)
    report.write_text(json.dumps(value,indent=2)+'\n')
    print(json.dumps({k:v for k,v in value.items() if k!='events'}))


def read():
    launcher=module('codex_launcher',ROOT/'integrations/codex/chat.py')
    profile,key=load_profile(launcher.PROFILE)
    before=verify(profile['config'],call(profile['url'],profile['config'],key,'context',{}))
    # No answer, expected record ID, proposal content or repository context in this prompt.
    prompt='Use memory_current to retrieve verified project memory. List each current accepted record with its kind, exact content, record ID and source IDs. Include the accepted revision and checkpoint. Keep decisions and observations distinct. Do not propose changes or use other tools. If retrieval fails, stop and report that.'
    with tempfile.TemporaryDirectory(prefix='portable-memory-codex-read-') as directory:
        code,events=execute(launcher.arguments(directory,True)+['-'],prompt,launcher.environment())
    value={'passed':False,'exitCode':code,'events':events,'prompt':prompt}
    report=ROOT/'results/codex-memory-read.json';report.write_text(json.dumps(value,indent=2)+'\n')
    require(code==0 and any(e.get('type')=='turn.completed' for e in events),'CODEX_RUN_FAILED')
    items=[e['item'] for e in events if e.get('type')=='item.completed' and 'item' in e]
    calls=[i for i in items if i.get('type')=='mcp_tool_call']
    require(calls and all(i.get('server')=='portable_memory' and i.get('tool')=='memory_current' and i.get('status')=='completed' for i in calls),'EXPECTED_MEMORY_TOOL_MISSING')
    require(not any(i.get('type') in ('command_execution','file_change','web_search','collab_tool_call') for i in items),'UNEXPECTED_TOOL_USED')
    answers=[i['text'] for i in items if i.get('type')=='agent_message']
    answer='\n'.join(answers)
    require(before['checkpoint']['controlDigest'] in answer and all(r['id'] in answer and r['content'] in answer for r in before['records']),'ANSWER_NOT_GROUNDED')
    after=verify(profile['config'],call(profile['url'],profile['config'],key,'context',{}))
    require(before['checkpoint']==after['checkpoint'],'BASE_CONFLICT')
    proposal_file=ROOT/'results/real-project-proposal.json'
    expected=json.loads(proposal_file.read_text()) if proposal_file.exists() else {}
    accepted=any(r['id']==expected.get('recordId') for r in after['records'])
    value.update(passed=True,sequence=after['control']['sequence'],checkpoint=after['checkpoint']['controlDigest'],application=profile['application'],recordCount=len(after['records']),projectDecisionAccepted=accepted,answer=answer)
    report.write_text(json.dumps(value,indent=2)+'\n')
    print(json.dumps({k:v for k,v in value.items() if k not in ('events','prompt')},indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('operation',choices=['propose','read']);parser.add_argument('--env-file');args=parser.parse_args()
    try:
        if args.operation=='propose':require(bool(args.env_file),'ENV_FILE_REQUIRED');propose(args.env_file)
        else:read()
    except Exception as error:
        code=str(error) if isinstance(error,ValueError) and str(error).isupper() and len(str(error))<80 else type(error).__name__
        print(json.dumps({'passed':False,'code':code}));sys.exit(1)

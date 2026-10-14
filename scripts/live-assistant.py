"""Explicit live-test worker; credentials stay in this process, metrics contain no keys."""
import json
import os
import sys
import time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'python'))
from assistant import Assistant, AnthropicModel

def credentials(path):
    allowed={'ANTHROPIC_API_KEY','ANTHROPIC_MODEL','ANTHROPIC_WORKSPACE_ID'}
    values={}
    for line in Path(path).read_text().splitlines():
        line=line.strip()
        if not line or line.startswith('#'):continue
        if line.startswith('export '):line=line[7:]
        name,sep,value=line.partition('=');name=name.strip();value=value.strip()
        if sep and name in allowed:
            if len(value)>=2 and value[0]==value[-1] and value[0] in ['"',"'"]:value=value[1:-1]
            values[name]=value
    return values

if __name__=='__main__':
    started=time.monotonic();metrics={}
    try:
        request=json.load(sys.stdin);env=credentials(request.pop('envFile'))
        model=AnthropicModel(env.get('ANTHROPIC_API_KEY'),env.get('ANTHROPIC_MODEL'),1536,env.get('ANTHROPIC_WORKSPACE_ID'))
        def measured(prompt):
            metrics['modelCalled']=True
            response=model(prompt)
            metrics.update({'model':response.get('model'),'stopReason':response.get('stop_reason'),
                'usage':{k:v for k,v in response.get('usage',{}).items() if isinstance(v,(int,float))},
                'memorySent':prompt['data']['memory']})
            return response
        adapter=Assistant(request['url'],request['config'],request['applicationKey'],request['role'],measured)
        result=adapter.respond(request['question'],request.get('submit',False))
        print(json.dumps({'ok':True,'result':result,'metrics':{**metrics,'elapsedSeconds':round(time.monotonic()-started,3)}}))
    except Exception as error:
        code=str(error) if isinstance(error,ValueError) and str(error).isupper() and len(str(error))<80 else 'LIVE_CHECK_FAILED'
        print(json.dumps({'ok':False,'code':code,'metrics':{**metrics,'elapsedSeconds':round(time.monotonic()-started,3)}}));sys.exit(1)

"""Fixture model injection exists only in tests. The normal CLI uses Anthropic."""
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'python'))
from assistant import Assistant
r=json.load(sys.stdin)
def fixture(prompt):
    memory=prompt['data']['memory']
    # The request must not carry protocol credentials/metadata into the model boundary.
    serialized=json.dumps(prompt)
    for secret in [r['applicationKey'],r['config']['owner'],r['config']['serviceId'],r['config']['projectId']]:
        assert secret not in serialized
    assert all(m['content']!=r.get('forbiddenContent') for m in memory)
    suggestion=r.get('suggestion')
    if suggestion and suggestion['replaces']=='first': suggestion={**suggestion,'replaces':memory[0]['ref']}
    result={'advice':'Generated test advice, not an owner decision.','citations':[m['ref'] for m in memory], 'suggestion':suggestion}
    return {'stop_reason':'end_turn','content':[{'type':'text','text':json.dumps(result)}]}
a=Assistant(r['url'],r['config'],r['applicationKey'],r['role'],fixture)
print(json.dumps(a.respond(r['question'],r.get('submit',False))))

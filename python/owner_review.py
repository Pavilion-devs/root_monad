"""Validate an exact proposed transition locally before the owner signs it."""
import copy
from memory import require
from protocol import digest,validate

def verify_review(config, before, review, proposal=None, grants=None, rejected=False):
    require((proposal is None) != (grants is None),'INVALID_REVIEW_INTENT')
    require(not rejected or proposal is not None,'INVALID_REVIEW_INTENT')
    snapshot=copy.deepcopy(before['snapshot'])
    if proposal is not None:
        validate('proposal',proposal)
        require(not any(r['proposalId']==proposal['id'] for r in snapshot['resolutions']),'ALREADY_RESOLVED')
        require(proposal['projectId']==config['projectId'],'WRONG_PROJECT')
    if proposal is not None and not rejected:
        require(proposal['baseCheckpoint']==before['checkpoint']['controlDigest'],'BASE_CONFLICT')
        require(proposal['projectId']==config['projectId'],'WRONG_PROJECT')
        require(proposal['records'] or proposal['retractIds'],'EMPTY_PROPOSAL')
        for name in ('records','sources'):
            ids=[item['id'] for item in proposal[name]]
            require(ids==sorted(set(ids)),'INVALID_ORDER')
            require(all(item['projectId']==config['projectId'] for item in proposal[name]),'WRONG_PROJECT')
        old_ids={r['id'] for r in snapshot['records']}
        new_ids={r['id'] for r in proposal['records']}
        require(not old_ids.intersection(new_ids),'ID_CONFLICT')
        old_sources={s['id']:s['digest'] for s in snapshot['sources']}
        for source in proposal['sources']:
            require(source['id'] not in old_sources or old_sources[source['id']]==digest('source',source),'ID_CONFLICT')
        available=set(old_sources)|{s['id'] for s in proposal['sources']}
        targets=set(proposal['retractIds'])
        require(proposal['retractIds']==sorted(targets),'INVALID_ORDER')
        for record in proposal['records']:
            require(record['author']==proposal['author'],'WRONG_AUTHOR')
            require(record['sourceIds']==sorted(set(record['sourceIds'])) and set(record['sourceIds'])<=available,'MISSING_SOURCE')
            if record['replaces']:
                require(record['replaces'] not in targets and record['replaces'] not in new_ids,'INVALID_TRANSITION')
                targets.add(record['replaces'])
        changes={r['replaces']:'superseded' for r in proposal['records'] if r['replaces']}
        changes.update({rid:'retracted' for rid in proposal['retractIds']})
        require(set(changes)<=set(snapshot['currentIds']),'INVALID_TRANSITION')
        for ref in snapshot['records']:
            if ref['id'] in changes:ref['disposition']=changes[ref['id']]
        snapshot['records']+= [{'id':r['id'],'digest':digest('record',r),'disposition':'current'} for r in proposal['records']]
        snapshot['records'].sort(key=lambda r:r['id'])
        sources={s['id']:s for s in snapshot['sources']}
        sources.update({s['id']:{'id':s['id'],'digest':digest('source',s)} for s in proposal['sources']})
        snapshot['sources']=sorted(sources.values(),key=lambda s:s['id'])
        snapshot['currentIds']=sorted(r['id'] for r in snapshot['records'] if r['disposition']=='current')
    if proposal is not None:
        snapshot['previousDigest']=before['control']['snapshotDigest']
        snapshot['resolutions'].append({'proposalId':proposal['id'],'proposalDigest':digest('proposal',proposal),'state':'rejected' if rejected else 'accepted','reason':'Owner reviewed this proposal.'})
        snapshot['resolutions'].sort(key=lambda r:r['proposalId'])
    control={**before['control'],'sequence':str(int(before['control']['sequence'])+1),
             'previousDigest':before['checkpoint']['controlDigest'],'snapshotDigest':digest('snapshot',snapshot),'salt':review['control']['salt']}
    if grants is not None:control['grants']=grants
    require(review['snapshot']==snapshot and review['control']==control,'UNEXPECTED_REVIEW_CHANGE')
    require(review['accept']==([proposal['id']] if proposal and not rejected else []) and review['reject']==([proposal['id']] if rejected else []),'UNEXPECTED_REVIEW_CHANGE')
    cp=review['checkpoint'];validate('checkpoint',cp);validate('control',control);validate('snapshot',snapshot)
    require(cp=={'projectId':config['projectId'],'sequence':control['sequence'],'previousDigest':control['previousDigest'],
                 'controlDigest':digest('control',control),'deadline':cp['deadline']},'UNEXPECTED_REVIEW_CHANGE')
    for kind in ('record','source'):
        bodies=review[kind+'s'];refs=snapshot[kind+'s']
        require(len(bodies)==len(refs) and len({b['id'] for b in bodies})==len(bodies),'CONTENT_MISMATCH')
        require({b['id']:digest(kind,b) for b in bodies}=={r['id']:r['digest'] for r in refs},'CONTENT_MISMATCH')
    return review

"""Owner-local review and durable confirmation; never loaded by the MCP bridge."""
import json
import os
import re
import time
from pathlib import Path
from eth_account import Account
from client import call, request, verify
from memory import require
from owner_review import verify_review
from protocol import digest, recover, sign, validate
from recovery import exclusive, seal, unseal, sync_directory

KIND = 'portable-memory-owner-review/1'


def public_json(value):
    # Escape terminal controls and bidi characters in untrusted memory text.
    return json.dumps(value, indent=2, ensure_ascii=True)


class Owner:
    def __init__(self, url, config, key, wrapping, directory):
        require(Account.from_key(key).address.lower() == config['owner'].lower(), 'WRONG_SIGNER')
        self.url, self.config, self.key = url, config, key
        self.wrapping = wrapping
        self.directory = Path(directory)
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.path = self.directory / 'review.enc'

    def call(self, operation, payload):
        return call(self.url, self.config, self.key, operation, payload)

    def send(self, wire):
        return request(self.url + wire['body']['path'], json.dumps(wire).encode())

    def current(self):
        bundle = verify(self.config, self.call('context', {}))
        require(bundle['control']['serviceId'] == self.config['serviceId'], 'SERVICE_MOVED')
        return bundle

    def save(self, state):
        state = {**state, 'config': self.config, 'url': self.url}
        temporary = self.directory / ('review-' + os.urandom(8).hex() + '.tmp')
        try:
            exclusive(temporary, seal(state, self.wrapping, KIND))
            os.replace(temporary, self.path)
            sync_directory(self.directory)
        finally:
            temporary.unlink(missing_ok=True)

    def load(self):
        if not self.path.exists():
            return None
        state = unseal(self.path.read_bytes(), self.wrapping, KIND)
        require(state['config'] == self.config and state['url'] == self.url, 'CONFIG_MISMATCH')
        return state

    def inbox(self, before):
        items = self.call('inbox', {})['proposals']
        resolutions = {r['proposalId']: r for r in before['snapshot']['resolutions']}
        seen = set()
        for item in items:
            p, e = item['proposal'], item['evidence']
            validate('proposal', p)
            body, auth = e['body'], e['auth']
            validate('request', body)
            validate('request-auth', auth)
            require(p['id'] not in seen, 'DUPLICATE_ENTRY')
            seen.add(p['id'])
            require(p['projectId'] == body['projectId'] == auth['projectId'] == self.config['projectId'], 'WRONG_PROJECT')
            require(body['operation'] == 'proposals' and body['payload'] == p, 'CONTENT_MISMATCH')
            require(auth['requestDigest'] == digest('request', body) and auth['checkpointDigest'] == p['baseCheckpoint'], 'CONTENT_MISMATCH')
            require(recover(self.config['domain'], 'Request', auth, e['signature']) == p['author'], 'WRONG_SIGNER')
            resolution = resolutions.get(p['id'])
            if resolution:
                require(resolution['proposalDigest'] == digest('proposal', p), 'CONTENT_MISMATCH')
            # Derive these labels from the verified snapshot, not server-supplied flags.
            item['status'] = resolution['state'] if resolution else 'pending'
            item['stale'] = p['baseCheckpoint'] != before['checkpoint']['controlDigest']
        require(self.current()['checkpoint'] == before['checkpoint'], 'BASE_CONFLICT')
        return items

    def check_review(self, state):
        action = state['action']
        require(action in ('approve', 'reject', 'revoke'), 'INVALID_REVIEW_INTENT')
        if action == 'revoke':
            expected = [g for g in state['before']['control']['grants'] if g['application'] != state['target']]
            require(len(expected) + 1 == len(state['before']['control']['grants']), 'APPLICATION_NOT_GRANTED')
            require(state['grants'] == expected, 'UNEXPECTED_REVIEW_CHANGE')
            verify_review(self.config, state['before'], state['review'], grants=expected)
        else:
            require(state['proposal']['id'] == state['target'], 'INVALID_REVIEW_INTENT')
            verify_review(self.config, state['before'], state['review'], proposal=state['proposal'], rejected=action == 'reject')

    def prepare(self, action, target):
        require(action in ('approve', 'reject', 'revoke'), 'INVALID_REVIEW_INTENT')
        state = self.load()
        require(not state or not state.get('wire') or state.get('done'), 'RESUME_REQUIRED')
        before = self.current()
        target = target.lower()
        require(re.fullmatch(r'0x[0-9a-f]{40}' if action == 'revoke' else r'0x[0-9a-f]{64}', target), 'INVALID_ID')
        if state and not state.get('done') and state['action'] == action and state['target'] == target and state['before']['checkpoint'] == before['checkpoint'] and int(state['review']['checkpoint']['deadline']) > int(time.time()) + 10:
            self.check_review(state)
            return state
        proposal, grants = None, None
        if action == 'revoke':
            grants = [g for g in before['control']['grants'] if g['application'] != target]
            require(len(grants) + 1 == len(before['control']['grants']), 'APPLICATION_NOT_GRANTED')
        else:
            matches = [i for i in self.inbox(before) if i['proposal']['id'] == target]
            require(len(matches) == 1, 'PROPOSAL_NOT_FOUND')
            require(matches[0]['status'] == 'pending', 'ALREADY_RESOLVED')
            proposal = matches[0]['proposal']
            if action == 'approve':
                require(not matches[0]['stale'], 'BASE_CONFLICT')
                self.check_author(before, proposal)
        payload = {'accept': [target] if action == 'approve' else [], 'reject': [target] if action == 'reject' else [], 'grants': grants}
        review = self.call('prepare', payload)
        state = {'action': action, 'target': target, 'before': before, 'proposal': proposal, 'grants': grants, 'review': review}
        self.check_review(state)
        require(int(time.time()) < int(review['checkpoint']['deadline']) <= int(time.time()) + 300, 'REVIEW_EXPIRED')
        self.save(state)
        return state

    def check_author(self, before, proposal):
        author = proposal['author']
        require(author == self.config['owner'].lower() or any(g['application'] == author and g['serviceId'] == self.config['serviceId'] and 'propose' in g['rights'] and int(g['expiresAt']) >= int(time.time()) for g in before['control']['grants']), 'SCOPE_DENIED')

    def confirm(self, confirmation):
        state = self.load()
        require(state is not None, 'PREPARE_FIRST')
        cp = state['review']['checkpoint']
        require(confirmation == cp['controlDigest'], 'CONFIRMATION_MISMATCH')
        if state.get('wire'):
            return self.resume()
        before = self.current()
        require(before['checkpoint'] == state['before']['checkpoint'], 'BASE_CONFLICT')
        self.check_review(state)
        require(int(cp['deadline']) > int(time.time()) + 5, 'REVIEW_EXPIRED')
        if state['action'] == 'approve':
            self.check_author(before, state['proposal'])
        payload = {'checkpoint': cp, 'signature': sign(self.key, self.config['domain'], 'Checkpoint', cp)}
        body = {'formatVersion': '0', 'projectId': self.config['projectId'], 'method': 'POST', 'path': f"/v0/projects/{self.config['projectId']}/commit", 'operation': 'commit', 'payload': payload}
        auth = {'projectId': self.config['projectId'], 'serviceId': self.config['serviceId'], 'checkpointDigest': cp['previousDigest'], 'requestDigest': digest('request', body), 'nonce': '0x' + os.urandom(32).hex(), 'deadline': cp['deadline']}
        state['wire'] = {'body': body, 'auth': auth, 'signature': sign(self.key, self.config['domain'], 'Request', auth)}
        # Persist the exact signed request before any network submission.
        self.save(state)
        return self.resume()

    def resume(self):
        state = self.load()
        require(state is not None and state.get('wire'), 'NO_CONFIRMED_REVIEW')
        self.check_review(state)
        cp = state['review']['checkpoint']
        current = self.current()
        if int(current['checkpoint']['sequence']) >= int(cp['sequence']):
            accepted = current if current['checkpoint']['controlDigest'] == cp['controlDigest'] else verify(self.config, self.call('history', {'checkpointDigest': cp['controlDigest']}), cp['controlDigest'])
            require(accepted['checkpoint'] == cp and accepted['control'] == state['review']['control'] and accepted['snapshot'] == state['review']['snapshot'], 'UNEXPECTED_REVIEW_CHANGE')
            state['done'] = True
            self.save(state)
            return {'committed': cp['controlDigest'], 'sequence': cp['sequence'], 'verified': True, 'currentSequence': current['checkpoint']['sequence']}
        require(current['checkpoint'] == state['before']['checkpoint'], 'BASE_CONFLICT')
        require(int(cp['deadline']) > int(time.time()), 'REVIEW_EXPIRED')
        self.send(state['wire'])
        # A transport acknowledgement alone is not proof of acceptance.
        after = self.current()
        require(after['checkpoint']['controlDigest'] == cp['controlDigest'], 'COMMIT_PENDING')
        require(after['control'] == state['review']['control'] and after['snapshot'] == state['review']['snapshot'], 'UNEXPECTED_REVIEW_CHANGE')
        state['done'] = True
        self.save(state)
        return {'committed': cp['controlDigest'], 'sequence': cp['sequence'], 'verified': True, 'currentSequence': after['checkpoint']['sequence']}


def proposal_view(item, before):
    p = item['proposal']
    current = {r['id']: r for r in before['records']}
    return {'id': p['id'], 'author': p['author'], 'status': item['status'], 'stale': item['stale'], 'baseCheckpoint': p['baseCheckpoint'],
            'records': p['records'], 'sources': p['sources'], 'retractions': [{'id': rid, 'currentRecord': current.get(rid)} for rid in p['retractIds']],
            'replacements': [{'id': r['replaces'], 'currentRecord': current.get(r['replaces'])} for r in p['records'] if r['replaces']]}


def review_view(state):
    before, review = state['before'], state['review']
    view = {'action': state['action'], 'target': state['target'], 'project': before['control']['projectId'],
            'fromSequence': before['control']['sequence'], 'toSequence': review['control']['sequence'],
            'baseCheckpoint': before['checkpoint']['controlDigest'], 'confirmation': review['checkpoint']['controlDigest'],
            'expiresAtUnix': review['checkpoint']['deadline']}
    if state['proposal']:
        view['proposal'] = proposal_view({'proposal': state['proposal'], 'status': 'pending', 'stale': state['proposal']['baseCheckpoint'] != before['checkpoint']['controlDigest']}, before)
        source_ids = {sid for record in state['proposal']['records'] for sid in record['sourceIds']}
        view['referencedSourcesInReview'] = [source for source in review['sources'] if source['id'] in source_ids]
        view['effect'] = 'Accept these records with their stated kinds and apply their replacements/retractions.' if state['action'] == 'approve' else 'Mark this proposal rejected; current records stay unchanged.'
    else:
        view['removedGrant'] = next(g for g in before['control']['grants'] if g['application'] == state['target'])
        view['effect'] = 'Remove this application grant. Copies already retrieved cannot be erased.'
    return view

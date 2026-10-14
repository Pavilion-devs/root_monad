"""Wallet-only onboarding: disposable keys and deterministic chain authority."""
import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from urllib.request import Request, urlopen
from urllib.error import HTTPError
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'python'))
from eth_account import Account
from protocol import digest, project_id, sign
from memory import ZERO
from onboarding import Onboarding
from onboarding_server import WalletServer


def ident(): return '0x'+os.urandom(32).hex()


class Chain:
    chain_id = 10143
    address = '0x'+'ab'*20
    confirmation = 'finalized_rpc_verified'
    mode = 'monad_testnet'
    scope = 'deterministic test authority'
    def __init__(self): self.heads = {}; self.events = {}; self.available = True
    def view(self, project):
        if not self.available: raise ValueError('AUTHORITY_UNAVAILABLE')
        return self.heads.get(project, {'owner': '0x'+'00'*20, 'sequence': '0', 'digest': ZERO, 'blockNumber': '0x1', 'blockHash': ZERO})
    def accepted(self, cp, owner, view): return self.events.get(cp['controlDigest'])
    def accept(self, owner, cp):
        event = {'transactionHash': ident(), 'blockNumber': '0x2', 'blockHash': ident()}
        self.events[cp['controlDigest']] = event
        self.heads[cp['projectId']] = {'owner': owner, 'sequence': cp['sequence'], 'digest': cp['controlDigest'], **event}
    def transaction(self, *args): raise AssertionError('Service must not sign transactions')
    def broadcast(self, *args): raise AssertionError('Service must not broadcast transactions')
    def receipt(self, *args): raise AssertionError('Service must not trust a submitted transaction hash')


class OnboardingFixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.directory = Path(self.tmp.name)
        self.key = os.urandom(32); self.chain = Chain(); self.owner = Account.create(); self.other = Account.create()
        self.settings = {'domain': {'name': 'PortableMemory', 'version': '0', 'chainId': 10143, 'verifyingContract': self.chain.address},
                         'serviceId': ident(), 'providerId': ident(), 'runtimeCodeHash': ident(), 'rpcUrl': 'https://rpc.invalid'}
        self.hub = Onboarding(self.directory, self.key, self.settings, self.chain)
    def tearDown(self): self.hub.close(); self.tmp.cleanup()
    def setup(self, account=None):
        account = account or self.owner; owner = account.address.lower(); nonce = ident(); project = project_id(owner, nonce)
        snapshot = {'formatVersion': '0', 'projectId': project, 'previousDigest': ZERO, 'records': [], 'sources': [], 'currentIds': [], 'resolutions': []}
        control = {'formatVersion': '0', 'projectId': project, 'sequence': '0', 'previousDigest': ZERO, 'creationNonce': nonce,
                   'snapshotDigest': digest('snapshot', snapshot), 'grants': [], 'serviceId': self.settings['serviceId'],
                   'storage': {'providerId': self.settings['providerId'], 'locator': 'project:'+project}, 'salt': ident()}
        cp = {'projectId': project, 'sequence': '0', 'previousDigest': ZERO, 'controlDigest': digest('control', control), 'deadline': str(int(time.time())+900)}
        return {'owner': owner, 'genesis': {'snapshot': snapshot, 'control': control, 'checkpoint': cp,
                'signature': sign(account.key, self.settings['domain'], 'Checkpoint', cp)}}
    def resign(self, payload, account=None):
        genesis = payload['genesis']; genesis['checkpoint']['controlDigest'] = digest('control', genesis['control'])
        genesis['signature'] = sign((account or self.owner).key, self.settings['domain'], 'Checkpoint', genesis['checkpoint'])
        return payload
    def wire(self, payload, operation='context', body_payload=None, account=None, checkpoint=None):
        account = account or self.owner; cp = checkpoint or payload['genesis']['checkpoint']; project = cp['projectId']
        body = {'formatVersion': '0', 'projectId': project, 'method': 'POST', 'path': f'/v0/projects/{project}/{operation}', 'operation': operation, 'payload': body_payload or {}}
        auth = {'projectId': project, 'serviceId': self.settings['serviceId'], 'checkpointDigest': cp['controlDigest'],
                'requestDigest': digest('request', body), 'nonce': ident(), 'deadline': str(int(time.time())+120)}
        return {'body': body, 'auth': auth, 'signature': sign(account.key, self.settings['domain'], 'Request', auth)}


class OnboardingTests(OnboardingFixture):
    def test_pending_is_durable_without_service_signing_or_spending(self):
        payload = self.setup(); first = self.hub.stage(payload)
        self.assertEqual(first['status'], 'pending'); self.assertFalse(first['verified'])
        self.assertEqual(first['transaction']['value'], '0x0'); self.assertNotIn('rawTransaction', first['transaction'])
        project = first['projectId']; self.assertTrue((self.directory/f'{project}.sqlite').is_file())
        self.hub.close(); self.hub = Onboarding(self.directory, self.key, self.settings, self.chain)
        self.assertEqual(self.hub.stage(payload), first)
        self.chain.accept(payload['owner'], payload['genesis']['checkpoint'])
        recovered = self.hub.status(project)
        self.assertTrue(recovered['verified']); self.assertEqual(recovered['sequence'], '0')
        context = self.hub.execute(project, self.wire(payload))
        self.assertEqual(context['records'], []); self.assertEqual(context['control']['grants'], [])
    def test_tenant_isolation_and_no_unauthorized_reads(self):
        a, b = self.setup(), self.setup(self.other)
        for payload in (a, b):
            self.hub.stage(payload); self.chain.accept(payload['owner'], payload['genesis']['checkpoint'])
        project = a['genesis']['checkpoint']['projectId']
        with self.assertRaisesRegex(ValueError, 'WRONG_PROJECT'): self.hub.execute(project, self.wire(b, account=self.other))
        with self.assertRaisesRegex(ValueError, 'SCOPE_DENIED'): self.hub.execute(project, self.wire(a, account=self.other))
        self.assertEqual(self.hub.execute(project, self.wire(a))['records'], [])
    def test_wrong_signer_nonempty_grants_and_changed_binding_rejected_before_allocation(self):
        bad = self.setup(); bad['genesis']['signature'] = sign(self.other.key, self.settings['domain'], 'Checkpoint', bad['genesis']['checkpoint'])
        with self.assertRaisesRegex(ValueError, 'WRONG_SIGNER'): self.hub.stage(bad)
        for change in ('service', 'storage', 'grants'):
            bad = self.setup(); c = bad['genesis']['control']
            if change == 'service': c['serviceId'] = ident()
            elif change == 'storage': c['storage']['locator'] = 'somewhere-else'
            else: c['grants'] = [{'application': self.other.address.lower(), 'serviceId': c['serviceId'], 'rights': ['read_current'], 'expiresAt': '9999999999'}]
            with self.subTest(change=change), self.assertRaisesRegex(ValueError, 'INVALID_GENESIS'): self.hub.stage(self.resign(bad))
        self.assertEqual(self.hub.db.execute('SELECT count(*) FROM projects').fetchone()[0], 0)
    def test_expiry_capacity_and_conflicting_retry(self):
        payload = self.setup(); payload['genesis']['checkpoint']['deadline'] = str(int(time.time())-1)
        with self.assertRaisesRegex(ValueError, 'EXPIRED'): self.hub.stage(self.resign(payload))
        payload = self.setup(); self.hub.stage(payload)
        changed = copy.deepcopy(payload); changed['genesis']['control']['salt'] = ident()
        with self.assertRaisesRegex(ValueError, 'PROJECT_ALREADY_STAGED'): self.hub.stage(self.resign(changed))
        self.hub.per_owner = 1
        with self.assertRaisesRegex(ValueError, 'OWNER_PROJECT_LIMIT'): self.hub.stage(self.setup())
        self.hub.max_projects = 1
        with self.assertRaisesRegex(ValueError, 'CAPACITY_REACHED'): self.hub.stage(self.setup(self.other))
    def test_outage_and_competing_chain_state_never_report_success(self):
        payload = self.setup(); self.hub.stage(payload); project = payload['genesis']['checkpoint']['projectId']
        self.chain.available = False
        with self.assertRaisesRegex(ValueError, 'AUTHORITY_UNAVAILABLE'): self.hub.status(project)
        self.chain.available = True
        conflicting = {**payload['genesis']['checkpoint'], 'controlDigest': ident()}
        self.chain.accept(payload['owner'], conflicting)
        with self.assertRaisesRegex(ValueError, 'CONTENT_UNAVAILABLE'): self.hub.status(project)
    def test_wallet_commit_persists_before_external_submission_and_recovers(self):
        payload = self.setup(); self.hub.stage(payload); cp = payload['genesis']['checkpoint']; project = cp['projectId']
        self.chain.accept(payload['owner'], cp)
        grant = {'application': self.other.address.lower(), 'serviceId': self.settings['serviceId'], 'rights': ['propose','read_current'], 'expiresAt': str(int(time.time())+3600)}
        review = self.hub.execute(project, self.wire(payload, 'prepare', {'accept': [], 'reject': [], 'grants': [grant]}))
        checkpoint = review['checkpoint']; signature = sign(self.owner.key, self.settings['domain'], 'Checkpoint', checkpoint)
        wire = self.wire(payload, 'commit', {'checkpoint': checkpoint, 'signature': signature})
        with self.assertRaisesRegex(ValueError, 'COMMIT_PENDING'): self.hub.execute(project, wire)
        self.chain.accept(payload['owner'], checkpoint)
        self.assertEqual(self.hub.status(project)['sequence'], '1')
        self.assertEqual(self.hub.execute(project, wire)['sequence'], '1')
        self.assertEqual(self.hub.execute(project, self.wire(payload, account=self.other, checkpoint=checkpoint))['records'], [])
    def test_catalog_content_is_encrypted_and_settings_cannot_change(self):
        payload = self.setup(); self.hub.stage(payload)
        stored = self.hub.db.execute('SELECT object FROM projects').fetchone()[0]
        raw = self.hub.db.execute('SELECT ciphertext FROM objects WHERE id=?', (stored,)).fetchone()[0]
        self.assertNotIn(payload['genesis']['signature'].encode(), raw)
        self.hub.close()
        with self.assertRaisesRegex(ValueError, 'CONFIG_MISMATCH'): Onboarding(self.directory, self.key, {**self.settings, 'providerId': ident()}, self.chain)
        self.hub = Onboarding(self.directory, self.key, self.settings, self.chain)


class OnboardingHttpTests(OnboardingFixture):
    def test_http_signed_paths_host_origin_and_private_files(self):
        assets = self.directory/'assets'; assets.mkdir(); (assets/'index.html').write_text('<h1>Setup</h1>')
        server = WalletServer(self.hub, assets)
        def http(path, body=None, headers=None):
            def fetch():
                req = Request(server.origin+path, None if body is None else json.dumps(body).encode(),
                              {'Content-Type': 'application/json', 'Origin': server.origin, **(headers or {})})
                try: response = urlopen(req, timeout=5)
                except HTTPError as error: response = error
                with response: return response.status, response.read()
            with ThreadPoolExecutor(1) as pool:
                task = pool.submit(fetch); server.handle_request(); return task.result()
        try:
            self.assertEqual(http('/start')[0], 200)
            self.assertEqual(http('/wallet/config', headers={'Origin': 'https://evil.test'})[0], 403)
            self.assertEqual(http('/wallet/config', headers={'Host': 'evil.test'})[0], 403)
            self.assertEqual(http('/storage.key')[0], 404)
            payload = self.setup(); project = payload['genesis']['checkpoint']['projectId']
            self.assertEqual(http('/wallet/projects', payload)[0], 200)
            self.assertEqual(http('/p/'+project+'/head')[0], 503)
            self.chain.accept(payload['owner'], payload['genesis']['checkpoint'])
            self.assertEqual(http('/p/'+project+'/head')[0], 200)
            wire = self.wire(payload)
            self.assertEqual(http('/p/'+project+wire['body']['path'], wire)[0], 200)
            self.assertEqual(http('/p/'+ident()+wire['body']['path'], wire)[0], 400)
        finally: server.server_close()


if __name__ == '__main__': unittest.main()

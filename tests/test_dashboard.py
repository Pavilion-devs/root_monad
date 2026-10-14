"""Real HTTP boundary tests against disposable signed memory."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sys
import time
import unittest
from urllib.request import Request, urlopen
from urllib.error import HTTPError
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'python'))
import test_owner_cli
from dashboard_server import Dashboard


class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.fixture = test_owner_cli.OwnerCommandTests()
        self.fixture.setUp()
        self.owner, self.p = self.fixture.owner, self.fixture.p
        assets = Path(self.fixture.fixture.tmp.name) / 'assets'
        assets.mkdir()
        (assets / 'index.html').write_text('<h1>Workspace</h1>')
        self.server = Dashboard(self.owner, assets, {self.p['author']: 'Disposable assistant'})
        self.cookie = ''

    def tearDown(self):
        self.server.server_close()
        self.fixture.tearDown()

    def http(self, path, body=None, headers=None):
        supplied = {'Origin': self.server.origin, 'Cookie': self.cookie}
        if body is not None:
            supplied['Content-Type'] = 'application/json'
        supplied.update(headers or {})
        def fetch():
            req = Request(self.server.origin + path, None if body is None else json.dumps(body).encode(), supplied)
            try:
                response = urlopen(req, timeout=10)
            except HTTPError as error:
                response = error
            with response:
                raw = response.read()
                value = json.loads(raw) if response.headers.get_content_type() == 'application/json' else raw.decode()
                return response.status, value, response.headers
        with ThreadPoolExecutor(1) as pool:
            future = pool.submit(fetch)
            self.server.handle_request()
            return future.result()

    def unlock(self):
        status, result, headers = self.http('/api/unlock', {'code': self.server.pairing})
        self.assertEqual(status, 200)
        self.assertIn('HttpOnly', headers['Set-Cookie'])
        self.assertIn('SameSite=Strict', headers['Set-Cookie'])
        self.cookie = headers['Set-Cookie'].split(';')[0]

    def test_auth_origin_and_path_boundaries(self):
        self.assertEqual(self.http('/api/workspace')[0], 401)
        self.assertEqual(self.http('/app')[0], 200)
        self.assertEqual(self.http('/%2e%2e/private.json')[0], 404)
        self.assertEqual(self.http('/api/unlock', {'code': self.server.pairing}, {'Origin': 'https://evil.test'})[0], 403)
        self.assertEqual(self.http('/app', headers={'Host': 'evil.test'})[0], 403)
        self.unlock()
        self.assertEqual(self.http('/api/unlock', {'code': self.server.pairing})[0], 401)
        self.assertEqual(self.http('/api/workspace', headers={'Origin': 'https://evil.test'})[0], 403)
        self.assertEqual(self.http('/api/review', {'action': 'approve', 'target': self.p['id']}, {'Origin': 'null'})[0], 403)
        self.assertNotIn('wire', self.owner.load() or {})

    def test_review_confirm_and_verified_refresh(self):
        self.unlock()
        status, data, headers = self.http('/api/workspace')
        self.assertEqual(status, 200, data)
        self.assertEqual(data['records'], [])
        self.assertEqual(data['proposals'][0]['status'], 'pending')
        self.assertNotIn(self.owner.key, json.dumps(data))
        self.assertEqual(headers['Cache-Control'], 'no-store')
        status, view, _ = self.http('/api/review', {'action': 'approve', 'target': self.p['id']})
        self.assertEqual(status, 200, view)
        self.assertEqual(view['proposal']['records'], self.p['records'])
        self.assertEqual(self.fixture.sent, [])
        wrong = {'action': 'approve', 'target': self.p['id'], 'confirmation': 'wrong'}
        self.assertEqual(self.http('/api/confirm', wrong)[1]['code'], 'CONFIRMATION_MISMATCH')
        self.assertEqual(self.fixture.sent, [])
        right = {**wrong, 'confirmation': view['confirmation']}
        status, result, _ = self.http('/api/confirm', right)
        self.assertEqual(status, 200, result)
        self.assertTrue(result['verified'])
        data = self.http('/api/workspace')[1]
        self.assertEqual(data['records'], self.p['records'])
        self.assertEqual(data['proposals'][0]['status'], 'accepted')
        self.assertFalse(data['pendingCommit'])
        self.assertEqual(self.http('/api/confirm', right)[1]['code'], 'CONFIRMATION_MISMATCH')
        self.assertEqual(len(self.fixture.sent), 1)

    def test_lost_ack_recovers_exact_confirmed_change(self):
        self.unlock()
        view = self.http('/api/review', {'action': 'approve', 'target': self.p['id']})[1]
        send = self.owner.send
        def lost(wire):
            send(wire)
            raise TimeoutError()
        self.owner.send = lost
        self.assertEqual(self.http('/api/confirm', {'action': view['action'], 'target': view['target'], 'confirmation': view['confirmation']})[0], 503)
        self.assertTrue(self.http('/api/workspace')[1]['pendingCommit'])
        self.owner.send = lambda _: self.fail('Must not duplicate accepted commit')
        self.assertTrue(self.http('/api/resume', {})[1]['verified'])
        self.assertEqual(len(self.fixture.sent), 1)

    def test_replaced_cli_preview_cannot_be_signed_by_old_page(self):
        self.unlock()
        view = self.http('/api/review', {'action': 'approve', 'target': self.p['id']})[1]
        self.owner.prepare('reject', self.p['id'])
        self.assertEqual(self.http('/api/confirm', {'action': view['action'], 'target': view['target'], 'confirmation': view['confirmation']})[1]['code'], 'CONFIRMATION_MISMATCH')
        self.assertEqual(self.fixture.sent, [])

    def test_expiry_lock_and_arbitrary_operations(self):
        self.unlock()
        self.assertEqual(self.http('/api/grant', {})[0], 404)
        self.assertEqual(self.http('/api/review', {'action': 'grant', 'target': self.p['author']})[0], 400)
        self.assertEqual(self.http('/api/lock', {})[0], 200)
        self.assertEqual(self.http('/api/workspace')[0], 401)
        self.server.session = self.cookie.split('=', 1)[1]
        self.server.session_expires = time.time() - 1
        self.assertEqual(self.http('/api/workspace')[0], 401)

    def test_no_stale_fallback_or_exception_leak(self):
        self.unlock()
        self.owner.current = lambda: (_ for _ in ()).throw(ValueError('AUTHORITY_UNAVAILABLE'))
        status, data, _ = self.http('/api/workspace')
        self.assertEqual((status, data), (503, {'code': 'AUTHORITY_UNAVAILABLE'}))
        self.owner.current = lambda: (_ for _ in ()).throw(RuntimeError('secret diagnostic'))
        self.assertEqual(self.http('/api/workspace')[1], {'code': 'SERVICE_UNAVAILABLE'})

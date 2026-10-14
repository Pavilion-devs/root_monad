import copy
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'python'))
import test_memory
from owner_cli import Owner, public_json, review_view
from protocol import digest


class OwnerCommandTests(unittest.TestCase):
    def setUp(self):
        self.fixture = test_memory.MemoryTests()
        self.fixture.setUp()
        self.m = self.fixture.m
        self.p = self.fixture.proposal()
        self.m.execute(self.fixture.wire('proposals', self.p))
        self.config = {**self.fixture.config, 'serviceId': self.m.current()['control']['serviceId']}
        self.owner = Owner('https://example.test', self.config, test_memory.V['testOwnerKey'], os.urandom(32), Path(self.fixture.tmp.name) / 'owner')
        self.owner.call = lambda op, payload: self.m.execute(self.fixture.wire(op, payload, test_memory.V['testOwnerKey']))
        self.sent = []
        def send(wire):
            self.sent.append(copy.deepcopy(wire))
            return self.m.execute(wire)
        self.owner.send = send

    def tearDown(self):
        self.fixture.tearDown()

    def test_preview_does_not_sign_and_exact_confirmation_accepts(self):
        with patch('owner_cli.sign', side_effect=AssertionError('Preview must not sign a checkpoint')):
            state = self.owner.prepare('approve', self.p['id'])
        self.assertEqual(self.m.current()['control']['sequence'], '0')
        self.assertNotIn('wire', self.owner.load())
        with self.assertRaisesRegex(ValueError, 'CONFIRMATION_MISMATCH'):
            self.owner.confirm('0x' + 'ab' * 32)
        self.assertEqual(self.sent, [])
        result = self.owner.confirm(state['review']['checkpoint']['controlDigest'])
        self.assertTrue(result['verified'])
        self.assertEqual(self.owner.current()['records'], self.p['records'])
        self.assertEqual(len(self.sent), 1)
        self.assertNotIn(self.p['records'][0]['content'].encode(), self.owner.path.read_bytes())
        self.assertEqual(self.owner.path.stat().st_mode & 0o777, 0o600)

    def test_reject_stale_proposal_preserves_current_records(self):
        other = self.fixture.proposal()
        self.m.execute(self.fixture.wire('proposals', other))
        self.fixture.approve({'accept': [other['id']], 'reject': [], 'grants': None})
        before = self.owner.current()
        with self.assertRaisesRegex(ValueError, 'BASE_CONFLICT'):
            self.owner.prepare('approve', self.p['id'])
        state = self.owner.prepare('reject', self.p['id'])
        self.owner.confirm(state['review']['checkpoint']['controlDigest'])
        after = self.owner.current()
        self.assertEqual(after['records'], before['records'])
        self.assertEqual(next(r for r in after['snapshot']['resolutions'] if r['proposalId'] == self.p['id'])['state'], 'rejected')
        with self.assertRaisesRegex(ValueError, 'ALREADY_RESOLVED'):
            self.owner.prepare('reject', self.p['id'])

    def test_revoke_blocks_app_and_preserves_records(self):
        self.fixture.approve({'accept': [self.p['id']], 'reject': [], 'grants': None})
        before = self.owner.current()
        state = self.owner.prepare('revoke', self.p['author'])
        self.owner.confirm(state['review']['checkpoint']['controlDigest'])
        self.assertEqual(self.owner.current()['records'], before['records'])
        with self.assertRaisesRegex(ValueError, 'SCOPE_DENIED'):
            self.m.execute(self.fixture.wire('context', {}))

    def test_response_loss_reconciles_after_restart_without_resending(self):
        state = self.owner.prepare('approve', self.p['id'])
        send = self.owner.send
        def lost(wire):
            send(wire)
            raise TimeoutError()
        self.owner.send = lost
        with self.assertRaises(TimeoutError):
            self.owner.confirm(state['review']['checkpoint']['controlDigest'])
        self.assertIn('wire', self.owner.load())
        with self.assertRaisesRegex(ValueError, 'RESUME_REQUIRED'):
            self.owner.prepare('revoke', self.p['author'])
        restarted = Owner(self.owner.url, self.config, self.owner.key, self.owner.wrapping, self.owner.directory)
        restarted.call = self.owner.call
        restarted.send = lambda wire: self.fail('Must reconcile without a second submission')
        self.assertTrue(restarted.resume()['verified'])
        self.assertEqual(len(self.sent), 1)

    def test_unsent_request_retry_is_byte_identical(self):
        state = self.owner.prepare('approve', self.p['id'])
        send = self.owner.send
        self.owner.send = lambda wire: (_ for _ in ()).throw(TimeoutError())
        with self.assertRaises(TimeoutError):
            self.owner.confirm(state['review']['checkpoint']['controlDigest'])
        saved = self.owner.load()['wire']
        self.owner.send = send
        self.owner.resume()
        self.assertEqual(saved, self.sent[0])

    def test_reconcile_after_a_later_accepted_revision(self):
        state = self.owner.prepare('approve', self.p['id'])
        send = self.owner.send
        def lost(wire):
            send(wire)
            raise TimeoutError()
        self.owner.send = lost
        with self.assertRaises(TimeoutError):
            self.owner.confirm(state['review']['checkpoint']['controlDigest'])
        self.fixture.approve({'accept': [], 'reject': [], 'grants': []})
        self.assertEqual(self.owner.resume()['currentSequence'], '2')
        self.assertEqual(len(self.sent), 1)

    def test_changed_head_and_expired_review_cannot_be_signed(self):
        state = self.owner.prepare('approve', self.p['id'])
        with patch('owner_cli.time.time', return_value=int(state['review']['checkpoint']['deadline']) + 1):
            with self.assertRaisesRegex(ValueError, 'REVIEW_EXPIRED'):
                self.owner.confirm(state['review']['checkpoint']['controlDigest'])
        self.fixture.approve({'accept': [], 'reject': [], 'grants': []})
        with self.assertRaisesRegex(ValueError, 'BASE_CONFLICT'):
            self.owner.confirm(state['review']['checkpoint']['controlDigest'])
        self.assertEqual(self.sent, [])

    def test_inbox_forged_proposal_rejected_and_status_derived_locally(self):
        call = self.owner.call
        def lying(op, payload):
            result = call(op, payload)
            if op == 'inbox':
                result['proposals'][0]['status'] = 'accepted'
            return result
        self.owner.call = lying
        self.assertEqual(self.owner.inbox(self.owner.current())[0]['status'], 'pending')
        def forged(op, payload):
            result = call(op, payload)
            if op == 'inbox':
                result['proposals'][0]['proposal']['records'][0]['content'] = 'Forged'
            return result
        self.owner.call = forged
        with self.assertRaisesRegex(ValueError, 'CONTENT_MISMATCH'):
            self.owner.inbox(self.owner.current())

    def test_hidden_grant_change_and_reject_content_change_fail(self):
        call = self.owner.call
        def changed(op, payload):
            result = call(op, payload)
            if op == 'prepare':
                result['control']['grants'] = []
                result['checkpoint']['controlDigest'] = digest('control', result['control'])
            return result
        self.owner.call = changed
        with self.assertRaisesRegex(ValueError, 'UNEXPECTED_REVIEW_CHANGE'):
            self.owner.prepare('reject', self.p['id'])
        self.assertFalse(self.owner.path.exists())

    def test_terminal_text_is_escaped_and_review_shows_exact_sources(self):
        rendered = public_json({'text': '\x1b[2J\r\u202e'})
        self.assertNotIn('\x1b', rendered)
        self.assertNotIn('\u202e', rendered)
        state = self.owner.prepare('approve', self.p['id'])
        view = review_view(state)
        self.assertEqual(view['proposal']['sources'], self.p['sources'])
        self.assertNotIn('signature', public_json(view))


if __name__ == '__main__':
    unittest.main()

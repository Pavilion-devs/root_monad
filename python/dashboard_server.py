"""Loopback owner companion. Browser sessions never receive signing or storage keys."""
from contextlib import contextmanager
import fcntl
import hmac
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import mimetypes
from pathlib import Path
import re
import secrets
import time
from urllib.error import HTTPError
from urllib.parse import urlsplit, unquote

from owner_cli import proposal_view, review_view
from client import verify
from protocol import strict_loads


class Dashboard(HTTPServer):
    def __init__(self, owner, assets, labels=None, mode='local', port=0, after_commit=None):
        super().__init__(('127.0.0.1', port), Handler)
        self.owner = owner
        self.assets = Path(assets).resolve()
        self.labels = labels or {}
        self.mode = mode
        self.after_commit = after_commit
        self.origin = f'http://127.0.0.1:{self.server_port}'
        self.cookie_name = f'pm_session_{self.server_port}'
        self.pairing = secrets.token_urlsafe(32)
        self.pairing_expires = time.time() + 1200
        self.session = None
        self.session_expires = 0
        self.review_ticket = None
        self.failures = 0

    def get_request(self):
        sock, address = super().get_request()
        sock.settimeout(10)
        return sock, address

    @contextmanager
    def locked(self):
        # Shares the CLI's lock and durable journal; never races another owner UI.
        with open(self.owner.directory / 'operator.lock', 'a') as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise ValueError('OWNER_BUSY')
            try:
                yield
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)

    def workspace(self):
        before = self.owner.current()
        proposals = [proposal_view(i, before) for i in self.owner.inbox(before)]
        history = verify(self.owner.config, self.owner.call('history', {'checkpointDigest': before['checkpoint']['controlDigest']}), before['checkpoint']['controlDigest'])
        dispositions = {r['id']: r['disposition'] for r in history['snapshot']['records']}
        grants = {g['application']: g for g in before['control']['grants']}
        applications = []
        for address in sorted(set(self.labels) | set(grants)):
            grant = grants.get(address)
            applications.append({'address': address, 'name': self.labels.get(address, 'Application'),
                'status': 'removed' if not grant else 'expired' if int(grant['expiresAt']) < time.time() else 'active',
                'rights': grant['rights'] if grant else [], 'expiresAt': grant['expiresAt'] if grant else None})
        journal = self.owner.load()
        # Fail closed if the accepted state moved while the view was assembled.
        if self.owner.current()['checkpoint'] != before['checkpoint']:
            raise ValueError('BASE_CONFLICT')
        return {'projectId': before['control']['projectId'], 'owner': self.owner.config['owner'],
            'sequence': before['checkpoint']['sequence'], 'checkpoint': before['checkpoint']['controlDigest'],
            'authority': before['authorityMode'], 'mode': self.mode, 'verifiedAt': int(time.time()),
            'records': before['records'], 'sources': before['sources'], 'proposals': proposals,
            'applications': applications,
            'history': [{**r, 'disposition': dispositions[r['id']]} for r in history['records'] if dispositions[r['id']] != 'current'],
            'historySources': history['sources'],
            'pendingCommit': bool(journal and journal.get('wire') and not journal.get('done'))}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def reply(self, status, value, kind='application/json', cookie=None):
        body = json.dumps(value).encode() if kind == 'application/json' else value
        self.send_response(status)
        self.send_header('Content-Type', kind)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Cross-Origin-Resource-Policy', 'same-origin')
        self.send_header('Permissions-Policy', 'camera=(), microphone=(), geolocation=()')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; img-src 'self' data: https://hoirqrkdgbmvpwutwuwj.supabase.co; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        if cookie:
            self.send_header('Set-Cookie', cookie)
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def origin_ok(self, mutation=False):
        hosts, origins = self.headers.get_all('Host', []), self.headers.get_all('Origin', [])
        return hosts == [urlsplit(self.server.origin).netloc] and (origins == [self.server.origin] if mutation else origins in ([], [self.server.origin]))

    def authenticated(self):
        try:
            cookie = SimpleCookie(self.headers.get('Cookie', ''))
            value = cookie[self.server.cookie_name].value
            return self.server.session and time.time() < self.server.session_expires and hmac.compare_digest(value, self.server.session)
        except (KeyError, ValueError, TypeError):
            return False

    def error(self, error):
        if isinstance(error, HTTPError):
            try:
                code = json.load(error).get('code', 'SERVICE_UNAVAILABLE')
            except Exception:
                code = 'SERVICE_UNAVAILABLE'
        else:
            code = str(error) if isinstance(error, ValueError) else 'SERVICE_UNAVAILABLE'
        if not isinstance(code, str) or not re.fullmatch('[A-Z][A-Z0-9_]{0,79}', code):
            code = 'SERVICE_UNAVAILABLE'
        self.reply(409 if code in ('BASE_CONFLICT', 'RESUME_REQUIRED', 'CONFIRMATION_MISMATCH', 'REVIEW_EXPIRED', 'OWNER_BUSY') else 503, {'code': code})

    def do_GET(self):
        if not self.origin_ok():
            return self.reply(403, {'code': 'ORIGIN_DENIED'})
        path = urlsplit(self.path).path
        if path.startswith('/api/'):
            if not self.authenticated():
                return self.reply(401, {'code': 'CONNECT_REQUIRED'})
            if path != '/api/workspace':
                return self.reply(404, {'code': 'NOT_FOUND'})
            try:
                with self.server.locked():
                    value = self.server.workspace()
                return self.reply(200, value)
            except Exception as error:
                return self.error(error)
        if path == '/' or path == '/app' or path.startswith('/app/'):
            file = self.server.assets / 'index.html'
        else:
            file = (self.server.assets / unquote(path).lstrip('/')).resolve()
        if not file.is_relative_to(self.server.assets) or not file.is_file():
            return self.reply(404, {'code': 'NOT_FOUND'})
        return self.reply(200, file.read_bytes(), mimetypes.guess_type(file)[0] or 'application/octet-stream')

    def do_POST(self):
        if not self.origin_ok(mutation=True):
            return self.reply(403, {'code': 'ORIGIN_DENIED'})
        if self.headers.get('Content-Type') != 'application/json' or self.headers.get('Transfer-Encoding') or len(self.headers.get_all('Content-Length', [])) != 1:
            return self.reply(400, {'code': 'INVALID_REQUEST'})
        try:
            length = int(self.headers.get('Content-Length', '-1'))
            if not 0 <= length <= 4096:
                raise ValueError()
            body = strict_loads(self.rfile.read(length))
            if not isinstance(body, dict):
                raise ValueError()
        except (ValueError, UnicodeError):
            return self.reply(400, {'code': 'INVALID_REQUEST'})
        if self.path == '/api/unlock':
            code = body.get('code')
            if not isinstance(code, str) or not re.fullmatch(r'[A-Za-z0-9_-]{43}', code) or self.server.failures >= 10 or time.time() >= self.server.pairing_expires or not hmac.compare_digest(code, self.server.pairing):
                self.server.failures += 1
                return self.reply(401, {'code': 'PAIRING_EXPIRED'})
            self.server.pairing_expires = 0  # One use; restarting the companion pairs a new browser.
            self.server.session = secrets.token_urlsafe(32)
            self.server.session_expires = time.time() + 8 * 3600
            return self.reply(200, {'connected': True}, cookie=f'{self.server.cookie_name}={self.server.session}; HttpOnly; SameSite=Strict; Path=/; Max-Age=28800')
        if not self.authenticated():
            return self.reply(401, {'code': 'CONNECT_REQUIRED'})
        if self.path == '/api/lock':
            self.server.session = None
            return self.reply(200, {'locked': True}, cookie=f'{self.server.cookie_name}=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0')
        try:
            with self.server.locked():
                if self.path == '/api/review':
                    action, target = body.get('action'), body.get('target')
                    if action not in ('approve', 'reject', 'revoke') or not isinstance(target, str):
                        return self.reply(400, {'code': 'INVALID_REQUEST'})
                    view = review_view(self.server.owner.prepare(action, target))
                    self.server.review_ticket = (view['action'], view['target'], view['confirmation'])
                    return self.reply(200, view)
                if self.path == '/api/confirm':
                    ticket = (body.get('action'), body.get('target'), body.get('confirmation'))
                    state = self.server.owner.load()
                    if ticket != self.server.review_ticket or not state or (state['action'], state['target'], state['review']['checkpoint']['controlDigest']) != ticket:
                        raise ValueError('CONFIRMATION_MISMATCH')
                    result = self.server.owner.confirm(body['confirmation'])
                elif self.path == '/api/resume':
                    result = self.server.owner.resume()
                else:
                    return self.reply(404, {'code': 'NOT_FOUND'})
                self.server.review_ticket = None
                if self.server.after_commit:
                    try:
                        self.server.after_commit(self.server.owner)
                    except Exception:
                        result['reportWarning'] = 'Local operations report could not be refreshed.'
                return self.reply(200, result)
        except Exception as error:
            return self.error(error)

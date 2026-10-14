"""Wallet onboarding HTTP surface, separate from the existing owner companion."""
import json
import mimetypes
import re
from pathlib import Path
from jsonschema import ValidationError
from server import BoundedServer, Handler, http_settings
from protocol import strict_loads


class WalletHandler(Handler):
    def failure(self, error):
        code = str(error)
        statuses = {'PROJECT_NOT_FOUND': 404, 'CAPACITY_REACHED': 503, 'OWNER_PROJECT_LIMIT': 409,
                    'PROJECT_ALREADY_STAGED': 409, 'WRONG_SIGNER': 401, 'EXPIRED': 409,
                    'SCOPE_DENIED': 403, 'WRONG_PROJECT': 403, 'WRONG_AUDIENCE': 403,
                    'EXPIRED_REQUEST': 401, 'INVALID_SIGNATURE': 401, 'REPLAY_MISMATCH': 401,
                    'CONTENT_MISMATCH': 422, 'INTEGRITY_FAILURE': 422, 'BASE_CONFLICT': 409,
                    'COMMIT_PENDING': 503, 'AUTHORITY_UNAVAILABLE': 503, 'CONTENT_UNAVAILABLE': 503,
                    'WRONG_CHAIN': 503, 'REGISTRY_MISSING': 503, 'INVALID_GENESIS': 400,
                    'INVALID_OWNER': 400, 'INVALID_PROJECT': 400, 'WRONG_PATH': 400}
        self.reply(statuses.get(code, 400), {'code': code if code in statuses else 'INVALID_REQUEST'})

    def do_GET(self):
        if not self.allowed(): return self.reply(403, {'code': 'ORIGIN_DENIED'})
        try:
            if self.path == '/healthz': return self.reply(200, {'status': 'alive'})
            if self.path == '/wallet/config': return self.reply(200, self.server.hub.settings)
            match = re.fullmatch(r'/wallet/projects/(0x[0-9a-f]{64})', self.path)
            if match: return self.reply(200, self.server.hub.status(match[1]))
            match = re.fullmatch(r'/p/(0x[0-9a-f]{64})/head', self.path)
            if match:
                result = self.server.hub.status(match[1])
                if not result['verified']: return self.reply(503, {'code': 'COMMIT_PENDING'})
                return self.reply(200, {k: result[k] for k in ('checkpointDigest', 'sequence')})
            if self.path == '/':
                self.send_response(302); self.send_header('Location', '/start')
                self.send_header('Content-Length', '0'); self.send_header('Cache-Control', 'no-store')
                self.end_headers(); return
            if self.path == '/start':
                return self.reply(200, (self.server.assets/'index.html').read_bytes(), 'text/html; charset=utf-8')
            if re.fullmatch(r'/(assets|previews)/[A-Za-z0-9_.-]+', self.path):
                path = (self.server.assets/self.path[1:]).resolve()
                if path.is_relative_to(self.server.assets.resolve()) and path.is_file():
                    kind = mimetypes.guess_type(path.name)[0] or 'application/octet-stream'
                    return self.reply(200, path.read_bytes(), kind)
            return self.reply(404, {'code': 'NOT_FOUND'})
        except (ValueError, ValidationError, KeyError, TypeError) as error: self.failure(error)
        except Exception: self.reply(500, {'code': 'INTERNAL_ERROR'})

    def do_POST(self):
        if not self.allowed(): return self.reply(403, {'code': 'ORIGIN_DENIED'})
        lengths = self.headers.get_all('Content-Length', [])
        if self.headers.get('Transfer-Encoding') or self.headers.get('Content-Type') != 'application/json' or len(lengths) != 1:
            return self.reply(400, {'code': 'INVALID_REQUEST'})
        try: length = int(lengths[0])
        except ValueError: length = -1
        if not 0 <= length <= 65536: return self.reply(413, {'code': 'LIMIT_EXCEEDED'})
        try:
            payload = strict_loads(self.rfile.read(length))
            if self.path == '/wallet/projects':
                return self.reply(200, self.server.hub.stage(payload))
            # Project base URLs preserve the signed protocol path for existing MCP clients.
            match = re.fullmatch(r'/p/(0x[0-9a-f]{64})(/v0/projects/(0x[0-9a-f]{64})/[a-z]+)', self.path)
            if not match or match[1] != match[3] or payload['body']['path'] != match[2]:
                raise ValueError('WRONG_PATH')
            return self.reply(200, self.server.hub.execute(match[1], payload))
        except (ValueError, ValidationError, KeyError, TypeError, UnicodeError) as error: self.failure(error)
        except Exception: self.reply(500, {'code': 'INTERNAL_ERROR'})


class WalletServer(BoundedServer):
    def __init__(self, hub, assets, port=0, public_origin=None, bind='127.0.0.1'):
        startup = {'bindHost': bind, 'publicOrigin': public_origin}
        http_settings(startup, port)
        super().__init__((bind, port), WalletHandler)
        _, self.origins = http_settings(startup, self.server_port)
        self.hub, self.assets = hub, Path(assets)
        self.origin = public_origin or f'http://127.0.0.1:{self.server_port}'

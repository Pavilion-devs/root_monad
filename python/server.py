"""Signed API; loopback by default, explicit HTTPS origin for hosted deployments."""
import json
import sys
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlsplit
import signal
from memory import Memory
from protocol import strict_loads
from jsonschema import ValidationError

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args): pass
    def reply(self, status, data, kind='application/json'):
        body=json.dumps(data).encode() if kind=='application/json' else data
        self.send_response(status); self.send_header('Content-Type',kind)
        self.send_header('Content-Length',str(len(body))); self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'")
        self.end_headers(); self.wfile.write(body)
    def allowed(self):
        # Forwarding headers are never authority. Only explicit Host/Origin pairs qualify.
        hosts=self.headers.get_all('Host',[])
        origins=self.headers.get_all('Origin',[])
        return len(hosts)==1 and len(origins)<=1 and hosts[0] in self.server.origins and (not origins or origins[0]==self.server.origins[hosts[0]])
    def do_GET(self):
        if not self.allowed(): return self.reply(403,{'code':'ORIGIN_DENIED'})
        if self.path=='/healthz': return self.reply(200,{'status':'alive'})
        if self.path=='/head':
            try:
                self.server.memory.recover_intents()
                cp=self.server.memory.current()['checkpoint']
                return self.reply(200,{'checkpointDigest':cp['controlDigest'],'sequence':cp['sequence']})
            except ValueError as error:
                code=str(error)
                statuses={'CONTENT_UNAVAILABLE':503,'AUTHORITY_UNAVAILABLE':503,'COMMIT_PENDING':503,
                          'INTEGRITY_FAILURE':422,'CONTENT_MISMATCH':422,'SERVICE_MOVED':409,
                          'WRONG_CHAIN':503,'REGISTRY_MISSING':503}
                return self.reply(statuses.get(code,500),{'code':code if code in statuses else 'INTERNAL_ERROR'})
            except Exception: return self.reply(500,{'code':'INTERNAL_ERROR'})
        if self.server.demo is not None:
            if self.path=='/demo-config': return self.reply(200,self.server.demo)
            files={'/':('index.html','text/html; charset=utf-8'),'/app.js':('app.js','text/javascript; charset=utf-8'),'/style.css':('style.css','text/css; charset=utf-8')}
            if self.path in files:
                name,kind=files[self.path]
                return self.reply(200,(Path(__file__).resolve().parents[1]/'web'/name).read_bytes(),kind)
        self.reply(404,{'code':'NOT_FOUND'})
    def do_POST(self):
        if not self.allowed(): return self.reply(403,{'code':'ORIGIN_DENIED'})
        if self.headers.get('Transfer-Encoding') or self.headers.get('Content-Type')!='application/json':
            return self.reply(400,{'code':'INVALID_REQUEST'})
        try: length=int(self.headers.get('Content-Length','-1'))
        except ValueError: length=-1
        if length<0 or length>65536: return self.reply(413,{'code':'LIMIT_EXCEEDED'})
        try:
            wire=strict_loads(self.rfile.read(length))
            if self.path!=wire['body']['path']: raise ValueError('WRONG_PATH')
            result=self.server.memory.execute(wire)
            self.reply(200,result)
        except (ValidationError, KeyError, TypeError, UnicodeError, json.JSONDecodeError):
            self.reply(400,{'code':'INVALID_REQUEST'})
        except ValueError as e:
            code=str(e)
            mapping={'BASE_CONFLICT':409,'ALREADY_RESOLVED':409,'ID_CONFLICT':409,'SCOPE_DENIED':403,
              'WRONG_AUTHOR':403,'WRONG_PROJECT':403,'WRONG_AUDIENCE':403,'WRONG_SIGNER':401,
              'EXPIRED_REQUEST':401,'EXPIRED':401,'INVALID_SIGNATURE':401,'REPLAY_MISMATCH':401,
              'SERVICE_MOVED':409,'WRITES_FROZEN':409,'COMMIT_PENDING':503,'AUTHORITY_UNAVAILABLE':503,'TRANSACTION_FAILED':409,'FEE_LIMIT_EXCEEDED':503,'CONTENT_UNAVAILABLE':503,'INTEGRITY_FAILURE':422,'CONTENT_MISMATCH':422,'LIMIT_EXCEEDED':413}
            self.reply(mapping.get(code,400),{'code':code if code in mapping or code in ['INVALID_TRANSITION','MISSING_SOURCE','NOT_PREPARED','EMPTY_PROPOSAL','INVALID_PAYLOAD','INVALID_ORDER','WRONG_PATH'] else 'INVALID_REQUEST'})
        except Exception:
            self.reply(500,{'code':'INTERNAL_ERROR'})

def http_settings(startup,port):
    bind=startup.get('bindHost','127.0.0.1')
    if bind not in ('127.0.0.1','0.0.0.0'): raise ValueError('INVALID_BIND_HOST')
    origins={f'127.0.0.1:{port}':f'http://127.0.0.1:{port}'}
    public=startup.get('publicOrigin')
    if public:
        value=urlsplit(public)
        if value.scheme!='https' or not value.hostname or value.username or value.password or value.path or value.query or value.fragment or public!=f'https://{value.netloc}' or '*' in value.netloc:
            raise ValueError('INVALID_PUBLIC_ORIGIN')
        if startup.get('demo') is not None: raise ValueError('HOSTED_DEMO_KEYS_FORBIDDEN')
        origins[value.netloc]=public
    if bind=='0.0.0.0' and not public: raise ValueError('PUBLIC_ORIGIN_REQUIRED')
    return bind,origins

class BoundedServer(HTTPServer):
    request_queue_size=16
    def get_request(self):
        connection,address=super().get_request()
        connection.settimeout(10)
        return connection,address

if __name__=='__main__':
    startup=strict_loads(sys.stdin.readline())
    http_settings(startup,startup.get('port',0))
    from registry import registry_for
    registry=registry_for(startup['config']['domain'],startup['registry'],startup['relayerKey']) if 'registry' in startup else None
    if 'keyEnvelope' in startup:
        from recovery import load_key
        key=load_key(startup['keyEnvelope'],bytes.fromhex(startup['recoveryKey']),startup['config'])
    else: key=bytes.fromhex(startup['key'])
    # Genesis must finalize before serving. Retries reopen the same durable intent.
    deadline=time.monotonic()+8
    while True:
        try:
            memory=Memory(startup['db'],key,startup['config'],startup.get('genesis'),registry)
            break
        except ValueError as error:
            if str(error)!='COMMIT_PENDING' or time.monotonic()>=deadline: raise
            time.sleep(0.25)
    server=BoundedServer((startup.get('bindHost','127.0.0.1'),startup.get('port',0)),Handler)
    _,server.origins=http_settings(startup,server.server_port)
    server.memory=memory; server.demo=startup.get('demo')
    print(json.dumps({'url':f'http://127.0.0.1:{server.server_port}'}),flush=True)
    def stop(signum,frame): raise SystemExit(0)
    signal.signal(signal.SIGTERM,stop)
    try: server.serve_forever()
    finally:
        memory.close(); server.server_close()
        if registry:registry.close()

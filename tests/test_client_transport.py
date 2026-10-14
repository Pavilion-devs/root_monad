import json
import sys
import threading
import unittest
from pathlib import Path
from http.server import BaseHTTPRequestHandler,HTTPServer
from urllib.error import HTTPError
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'python'))
from client import request

class ClientTransportTests(unittest.TestCase):
    def test_signed_payload_does_not_follow_redirect(self):
        received=[]
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_POST(self):
                received.append(self.path)
                self.rfile.read(int(self.headers.get('Content-Length','0')))
                self.send_response(307);self.send_header('Location','/other');self.end_headers()
        server=HTTPServer(('127.0.0.1',0),Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            with self.assertRaises(HTTPError) as error:
                request(f'http://127.0.0.1:{server.server_port}/signed',json.dumps({'signature':'fixture'}).encode())
            self.assertEqual(error.exception.code,307)
            error.exception.close()
            self.assertEqual(received,['/signed'])
        finally:server.shutdown();server.server_close();thread.join()

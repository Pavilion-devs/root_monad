import io
import sys
import unittest
from pathlib import Path
from http.client import parse_headers
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'python'))
from server import Handler,http_settings

class HostedHttpTests(unittest.TestCase):
    def test_loopback_default_and_explicit_https_host(self):
        self.assertEqual(http_settings({},9000),('127.0.0.1',{'127.0.0.1:9000':'http://127.0.0.1:9000'}))
        _,origins=http_settings({'bindHost':'0.0.0.0','publicOrigin':'https://memory.example'},9000)
        def allowed(headers):
            handler=object.__new__(Handler)
            handler.headers=parse_headers(io.BytesIO(headers.encode()+b'\r\n'))
            handler.server=SimpleNamespace(origins=origins)
            return handler.allowed()
        self.assertTrue(allowed('Host: memory.example\r\n'))
        self.assertTrue(allowed('Host: memory.example\r\nOrigin: https://memory.example\r\n'))
        self.assertFalse(allowed('Host: memory.example\r\nOrigin: https://other.example\r\n'))
        self.assertFalse(allowed('Host: wrong.example\r\nX-Forwarded-Host: memory.example\r\n'))
        self.assertFalse(allowed('Host: memory.example\r\nHost: memory.example\r\n'))
        self.assertFalse(allowed('Host: memory.example\r\nOrigin: https://memory.example\r\nOrigin: https://memory.example\r\n'))
    def test_public_exposure_requires_origin_and_never_demo_keys(self):
        for startup in ({'bindHost':'0.0.0.0'},{'publicOrigin':'http://memory.example'},{'publicOrigin':'https://user:pass@memory.example'}, {'publicOrigin':'https://memory.example/path'}, {'publicOrigin':'https://*.example'}, {'publicOrigin':'https://memory.example','demo':{}}, {'bindHost':'10.0.0.1'}):
            with self.subTest(startup=startup),self.assertRaises(ValueError):http_settings(startup,9000)

    def test_head_preserves_authority_content_and_integrity_errors(self):
        for error,status,code in [(ValueError('AUTHORITY_UNAVAILABLE'),503,'AUTHORITY_UNAVAILABLE'),
                                  (ValueError('CONTENT_UNAVAILABLE'),503,'CONTENT_UNAVAILABLE'),
                                  (ValueError('INTEGRITY_FAILURE'),422,'INTEGRITY_FAILURE'),
                                  (RuntimeError('private diagnostic'),500,'INTERNAL_ERROR')]:
            with self.subTest(code=code):
                handler=object.__new__(Handler)
                handler.path='/head';handler.allowed=lambda:True
                def fail():raise error
                handler.server=SimpleNamespace(memory=SimpleNamespace(recover_intents=lambda:None,current=fail))
                replies=[];handler.reply=lambda *args:replies.append(args)
                handler.do_GET()
                self.assertEqual(replies,[(status,{'code':code})])

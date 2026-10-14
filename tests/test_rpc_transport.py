import json
import sys
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'python'))
from rpc_transport import RpcTransport

class Handler(BaseHTTPRequestHandler):
    protocol_version='HTTP/1.1'
    def log_message(self,*args):pass
    def do_POST(self):
        body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        self.server.requests+=1
        if self.server.mode in ('disconnect','disconnect_once'):
            if self.server.mode=='disconnect_once':self.server.mode='ok'
            self.close_connection=True;return
        many=isinstance(body,list);messages=body if many else [body]
        result=[{'jsonrpc':'2.0','id':m['id'],'result':m['method']} for m in reversed(messages)]
        mode=self.server.mode
        if mode=='duplicate':result=[result[0],result[0]]
        if mode=='missing':result=result[:-1]
        if mode=='wrong_id':result[0]['id']+=100
        if mode=='boolean_id':result[0]['id']=True
        if mode=='error':result[0]={'jsonrpc':'2.0','id':result[0]['id'],'error':{'code':-1,'message':'private diagnostic'}}
        if mode=='bad_version':result[0]['jsonrpc']='1.0'
        data=json.dumps(result if many else result[0]).encode()
        self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)

class RpcTests(unittest.TestCase):
    def setUp(self):
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler);self.server.mode='ok';self.server.requests=0
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.rpc=RpcTransport(f'http://127.0.0.1:{self.server.server_port}')
    def tearDown(self):self.rpc.close();self.server.shutdown();self.server.server_close();self.thread.join()
    def test_reuse_and_out_of_order_batch_without_result_cache(self):
        self.assertEqual(self.rpc.call('eth_chainId',[]),'eth_chainId')
        self.assertEqual(self.rpc.batch([('eth_chainId',[]),('eth_getCode',[])]),['eth_chainId','eth_getCode'])
        self.assertEqual(self.rpc.call('eth_chainId',[]),'eth_chainId')
        self.assertEqual(self.rpc.metrics['connectionsOpened'],1)
        self.assertEqual(self.rpc.metrics['httpRequests'],3)
        self.assertEqual(self.rpc.metrics['rpcCalls'],4)
    def test_bad_batches_fail_whole_check_and_discard_connection(self):
        for mode in ('duplicate','missing','wrong_id','boolean_id','error','bad_version'):
            with self.subTest(mode=mode):
                self.server.mode=mode
                with self.assertRaisesRegex(ValueError,'^AUTHORITY_UNAVAILABLE$'):self.rpc.batch([('eth_chainId',[]),('eth_getCode',[])])
                self.assertIsNone(self.rpc.connection)
        self.server.mode='ok';self.assertEqual(self.rpc.call('eth_chainId',[]),'eth_chainId')
    def test_uncertain_broadcast_is_not_automatically_retried(self):
        self.server.mode='disconnect'
        with self.assertRaisesRegex(ValueError,'AUTHORITY_UNAVAILABLE'):self.rpc.call('eth_sendRawTransaction',['synthetic-signed-bytes'])
        self.assertEqual(self.server.requests,1)
        self.assertIsNone(self.rpc.connection)
        self.server.mode='ok';self.rpc.call('eth_chainId',[])
        self.assertEqual(self.server.requests,2)
    def test_reused_read_reconnects_once_and_preserves_batch_results(self):
        self.rpc.call('eth_chainId',[])
        self.server.mode='disconnect_once'
        self.assertEqual(self.rpc.batch([('eth_chainId',[]),('eth_getCode',[])]),['eth_chainId','eth_getCode'])
        self.assertEqual(self.server.requests,3)
        self.assertEqual(self.rpc.metrics['connectionsOpened'],2)
        self.assertEqual(self.rpc.metrics['readReconnects'],1)
    def test_reused_read_retry_is_bounded(self):
        self.rpc.call('eth_chainId',[])
        self.server.mode='disconnect'
        with self.assertRaisesRegex(ValueError,'AUTHORITY_UNAVAILABLE'):self.rpc.call('eth_chainId',[])
        self.assertEqual(self.server.requests,3)
        self.assertIsNone(self.rpc.connection)
    def test_reused_broadcast_is_never_replayed(self):
        self.rpc.call('eth_chainId',[])
        self.server.mode='disconnect_once'
        with self.assertRaisesRegex(ValueError,'AUTHORITY_UNAVAILABLE'):self.rpc.call('eth_sendRawTransaction',['synthetic-signed-bytes'])
        self.assertEqual(self.server.requests,2)
        self.assertEqual(self.rpc.metrics['readReconnects'],0)
    def test_idle_connection_is_replaced_before_request(self):
        self.rpc.call('eth_chainId',[])
        self.rpc.last_used=time.monotonic()-11
        self.rpc.call('eth_chainId',[])
        self.assertEqual(self.rpc.metrics['connectionsOpened'],2)
        self.assertEqual(self.server.requests,2)
    def test_invalid_response_on_reused_connection_is_not_retried(self):
        self.rpc.call('eth_chainId',[])
        self.server.mode='wrong_id'
        with self.assertRaisesRegex(ValueError,'AUTHORITY_UNAVAILABLE'):self.rpc.call('eth_chainId',[])
        self.assertEqual(self.server.requests,2)
        self.assertEqual(self.rpc.metrics['readReconnects'],0)
    def test_mutations_cannot_be_batched(self):
        with self.assertRaisesRegex(ValueError,'INVALID_RPC_BATCH'):self.rpc.batch([('eth_sendRawTransaction',[])])
        self.assertEqual(self.server.requests,0)

if __name__=='__main__':unittest.main()

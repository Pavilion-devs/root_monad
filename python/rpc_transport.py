"""Bounded persistent JSON-RPC transport. No result cache; one fresh-connection retry for interrupted reused reads."""
import http.client
import json
import threading
import time
from urllib.parse import urlsplit

BATCH_READS=frozenset(('eth_chainId','eth_getBlockByNumber','eth_getCode','eth_call','eth_getTransactionReceipt','eth_getTransactionCount','eth_gasPrice'))
SAFE_READS=BATCH_READS | {'eth_getLogs'}
CONNECTION_ERRORS=(http.client.RemoteDisconnected,http.client.IncompleteRead,BrokenPipeError,ConnectionResetError,TimeoutError)
IDLE_SECONDS=10
LIMIT=4*1024*1024

class RpcTransport:
    def __init__(self,url,timeout=3):
        self.url=url;self.timeout=timeout;self.connection=None;self.sequence=0;self.last_used=None
        self.lock=threading.Lock()
        self.metrics={'httpRequests':0,'rpcCalls':0,'connectionsOpened':0,'errors':0,'readReconnects':0,'elapsedSeconds':0.0}

    def close(self):
        with self.lock:self._disconnect()

    def _disconnect(self):
        if self.connection is not None:self.connection.close();self.connection=None

    def call(self,method,params):return self._send([(method,params)],False)[0]

    def batch(self,calls):
        if not calls or len(calls)>16 or any(method not in BATCH_READS for method,_ in calls):
            raise ValueError('INVALID_RPC_BATCH')
        return self._send(calls,True)

    def _send(self,calls,batch):
        with self.lock:
            started=time.perf_counter()
            try:
                if self.last_used is not None and time.monotonic()-self.last_used>=IDLE_SECONDS:
                    self._disconnect()
                for attempt in range(2):
                    reused=self.connection is not None and self.connection.sock is not None
                    self.metrics['httpRequests']+=1;self.metrics['rpcCalls']+=len(calls)
                    try:
                        return self._attempt(calls,batch)
                    except Exception as error:
                        self.metrics['errors']+=1;self._disconnect()
                        # Retry only transport interruption on a reused socket, and only
                        # known read methods. Validation failures and broadcasts fail closed.
                        if attempt==0 and reused and isinstance(error,CONNECTION_ERRORS) and all(method in SAFE_READS for method,_ in calls):
                            self.metrics['readReconnects']+=1
                            continue
                        raise ValueError('AUTHORITY_UNAVAILABLE') from error
            finally:
                self.last_used=time.monotonic()
                self.metrics['elapsedSeconds']+=time.perf_counter()-started

    def _attempt(self,calls,batch):
        url=urlsplit(self.url)
        if self.connection is None:
            cls=http.client.HTTPSConnection if url.scheme=='https' else http.client.HTTPConnection
            self.connection=cls(url.hostname,url.port,timeout=self.timeout)
        if self.connection.sock is None:self.metrics['connectionsOpened']+=1
        messages=[]
        for method,params in calls:
            self.sequence+=1
            messages.append({'jsonrpc':'2.0','id':self.sequence,'method':method,'params':params})
        path=(url.path or '/')+('?' + url.query if url.query else '')
        self.connection.request('POST',path,body=json.dumps(messages if batch else messages[0]).encode(),headers={'Content-Type':'application/json'})
        response=self.connection.getresponse()
        data=response.read(LIMIT+1)
        if response.status!=200 or len(data)>LIMIT:raise ValueError('RPC_REJECTED')
        value=json.loads(data)
        values=value if batch else [value]
        if not isinstance(values,list) or len(values)!=len(messages):raise ValueError('RPC_REJECTED')
        expected={m['id'] for m in messages};results={}
        for item in values:
            if not isinstance(item,dict) or item.get('jsonrpc')!='2.0' or type(item.get('id')) is not int or item['id'] not in expected or item['id'] in results or 'error' in item or 'result' not in item:
                raise ValueError('RPC_REJECTED')
            results[item['id']]=item['result']
        return [results[m['id']] for m in messages]

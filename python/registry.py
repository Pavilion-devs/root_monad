"""Pinned RPC adapters. Finalized RPC evidence is not a light-client proof."""
import json
import time
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from rpc_transport import RpcTransport
from eth_account import Account
from eth_abi import encode, decode
from eth_utils import keccak, to_checksum_address


def raw(value): return bytes.fromhex(value.removeprefix('0x'))
def selector(signature): return keccak(text=signature)[:4]

class LocalRegistry:
    chain_id=31337
    mode='local_registry'
    confirmation='local_inclusion_only'
    scope='local registry inclusion; not Monad finality'
    block_tag='latest'

    def __init__(self, domain, settings, relayer_key=None):
        parsed=urlparse(settings['rpcUrl'])
        local=parsed.scheme=='http' and parsed.hostname=='127.0.0.1'
        remote=parsed.scheme=='https' and bool(parsed.hostname)
        if not (local if self.chain_id==31337 else remote) or parsed.username or parsed.password or parsed.fragment:
            raise ValueError('INVALID_REGISTRY_RPC')
        if set(domain)!={'name','version','chainId','verifyingContract'} or domain['name']!='PortableMemory' or domain['version']!='0' or int(domain['chainId'])!=self.chain_id:
            raise ValueError('WRONG_CHAIN')
        self.url=settings['rpcUrl']; self.address=domain['verifyingContract']; self.key=relayer_key
        self.settings=settings
        self._transport=None

    def rpc(self, method, params):
        request=Request(self.url,json.dumps({'jsonrpc':'2.0','id':1,'method':method,'params':params}).encode(),{'Content-Type':'application/json'})
        try:
            with urlopen(request,timeout=3) as response: result=json.load(response)
            if 'error' in result: raise ValueError('RPC_REJECTED')
            return result['result']
        except Exception as error: raise ValueError('AUTHORITY_UNAVAILABLE') from error

    def close(self):
        if self._transport:self._transport.close()

    def rpc_many(self,calls):
        return [self.rpc(method,params) for method,params in calls]

    def block(self):
        chain,block=self.rpc_many([('eth_chainId',[]),('eth_getBlockByNumber',[self.block_tag,False])])
        if int(chain,16)!=self.chain_id: raise ValueError('WRONG_CHAIN')
        if not block or not block.get('hash') or not block.get('number'): raise ValueError('AUTHORITY_UNAVAILABLE')
        return block

    def view(self, project):
        block=self.block()
        tag=block['number']
        data='0x'+(selector('heads(bytes32)')+raw(project)).hex()
        code,result=self.rpc_many([('eth_getCode',[self.address,tag]),('eth_call',[{'to':self.address,'data':data},tag])])
        if code=='0x': raise ValueError('REGISTRY_MISSING')
        owner,sequence,digest=decode(['address','uint256','bytes32'],raw(result))
        return {'owner':owner.lower(),'sequence':str(sequence),'digest':'0x'+digest.hex(),'blockNumber':tag,'blockHash':block['hash']}

    def accepted(self, cp, owner, view):
        topics=['0x'+keccak(text='Advanced(bytes32,address,uint256,bytes32,bytes32)').hex(),cp['projectId'],'0x'+'00'*12+owner.removeprefix('0x').lower()]
        logs=self.rpc('eth_getLogs',[{'address':self.address,'fromBlock':'0x0','toBlock':view['blockNumber'],'topics':topics}])
        matches=[]
        for log in logs:
            seq,previous,digest=decode(['uint256','bytes32','bytes32'],raw(log['data']))
            if str(seq)==cp['sequence'] and '0x'+previous.hex()==cp['previousDigest'] and '0x'+digest.hex()==cp['controlDigest'] and not log.get('removed',False):
                matches.append(log)
        # Reject an RPC view that changed while it was being checked.
        block=self.rpc('eth_getBlockByNumber',[view['blockNumber'],False])
        if not block or block['hash']!=view['blockHash']: raise ValueError('AUTHORITY_UNAVAILABLE')
        return matches[0] if len(matches)==1 else None

    def transaction(self, envelope, owner):
        if self.key is None: raise ValueError('RELAYER_REQUIRED')
        cp=envelope['checkpoint']; c=envelope['control']
        value=(raw(cp['projectId']),int(cp['sequence']),raw(cp['previousDigest']),raw(cp['controlDigest']),int(cp['deadline']))
        typ='(bytes32,uint256,bytes32,bytes32,uint256)'
        if cp['sequence']=='0':
            data=selector(f'create(address,bytes32,{typ},bytes)')+encode(['address','bytes32',typ,'bytes'],[owner,raw(c['creationNonce']),value,raw(envelope['signature'])])
        else:
            data=selector(f'advance({typ},bytes)')+encode([typ,'bytes'],[value,raw(envelope['signature'])])
        account=Account.from_key(self.key)
        if int(self.rpc('eth_chainId',[]),16)!=self.chain_id: raise ValueError('WRONG_CHAIN')
        tx={'chainId':self.chain_id,'nonce':int(self.rpc('eth_getTransactionCount',[account.address,'pending']),16),
            'to':to_checksum_address(self.address),'value':0,'gas':300000,
            'gasPrice':int(self.rpc('eth_gasPrice',[]),16),'data':data}
        if self.chain_id!=31337:
            # Explicit per-transaction budget; never silently raise the spend cap.
            cap=int(self.settings.get('maxTransactionFeeWei',0))
            if cap<=0 or tx['gas']*tx['gasPrice']>cap: raise ValueError('FEE_LIMIT_EXCEEDED')
        signed=Account.sign_transaction(tx,self.key)
        return {'rawTransaction':'0x'+signed.raw_transaction.hex(),'transactionHash':'0x'+signed.hash.hex()}

    def broadcast(self, transaction):
        if '0x'+keccak(raw(transaction['rawTransaction'])).hex()!=transaction['transactionHash']:
            raise ValueError('INTEGRITY_FAILURE')
        # Re-submission uses the very same bytes/hash. Never replace an uncertain transaction.
        try: self.rpc('eth_sendRawTransaction',[transaction['rawTransaction']])
        except ValueError: pass  # Already known, mined, rejected, or uncertain: resolve by chain evidence.

    def receipt(self, transaction):
        return self.rpc('eth_getTransactionReceipt',[transaction['transactionHash']])


class MonadTestnetRegistry(LocalRegistry):
    chain_id=10143
    mode='monad_testnet'
    confirmation='finalized_rpc_verified'
    scope='Monad testnet finalized state from pinned trusted RPC; not a light-client proof'
    block_tag='finalized'

    def transport(self):
        if self._transport is None or self._transport.url!=self.url:
            self.close();self._transport=RpcTransport(self.url)
        return self._transport

    def rpc(self,method,params):return self.transport().call(method,params)

    def rpc_many(self,calls):return self.transport().batch(calls)

    def block(self):
        block=super().block()
        # A lagging endpoint must not keep presenting obsolete permissions as current.
        age=time.time()-int(block['timestamp'],16)
        if age>120 or age < -30: raise ValueError('AUTHORITY_UNAVAILABLE')
        return block

    def stable(self, view):
        block=self.rpc('eth_getBlockByNumber',[view['blockNumber'],False])
        if not block or block['hash']!=view['blockHash']: raise ValueError('AUTHORITY_UNAVAILABLE')

    def finalized_receipt(self, transaction_hash, view):
        receipt=self.rpc('eth_getTransactionReceipt',[transaction_hash])
        if receipt is None: return None
        number=receipt.get('blockNumber')
        if number is None or int(number,16)>int(view['blockNumber'],16): return None
        if receipt.get('transactionHash','').lower()!=transaction_hash.lower() or receipt.get('status') not in ('0x0','0x1'):
            raise ValueError('AUTHORITY_UNAVAILABLE')
        # Both reads occur after the first receipt; the authority-block recheck stays last.
        block,second=self.rpc_many([('eth_getBlockByNumber',[number,False]),('eth_getTransactionReceipt',[transaction_hash])])
        if not block or block['hash']!=receipt.get('blockHash'): raise ValueError('AUTHORITY_UNAVAILABLE')
        if receipt!=second: raise ValueError('AUTHORITY_UNAVAILABLE')
        self.stable(view)
        return receipt

    def receipt(self, transaction):
        block=self.block()
        return self.finalized_receipt(transaction['transactionHash'],{'blockNumber':block['number'],'blockHash':block['hash']})

    def accepted(self, cp, owner, view):
        data='0x'+(selector('acceptedAt(bytes32,uint256)')+encode(['bytes32','uint256'],[raw(cp['projectId']),int(cp['sequence'])])).hex()
        number=decode(['uint256'],raw(self.rpc('eth_call',[{'to':self.address,'data':data},view['blockNumber']])))[0]
        if number==0:
            self.stable(view)
            return None
        if number>int(view['blockNumber'],16): raise ValueError('AUTHORITY_UNAVAILABLE')
        topics=['0x'+keccak(text='Advanced(bytes32,address,uint256,bytes32,bytes32)').hex(),cp['projectId'],'0x'+'00'*12+owner.removeprefix('0x').lower()]
        logs=self.rpc('eth_getLogs',[{'address':self.address,'fromBlock':hex(number),'toBlock':hex(number),'topics':topics}])
        matches=[]
        for log in logs:
            if log.get('removed',False) or log.get('address','').lower()!=self.address.lower() or log.get('topics')!=topics or int(log['blockNumber'],16)!=number:
                raise ValueError('AUTHORITY_UNAVAILABLE')
            seq,previous,digest=decode(['uint256','bytes32','bytes32'],raw(log['data']))
            if str(seq)==cp['sequence'] and '0x'+previous.hex()==cp['previousDigest'] and '0x'+digest.hex()==cp['controlDigest']:
                matches.append(log)
        if not matches:
            self.stable(view)
            return None
        if len(matches)!=1: raise ValueError('AUTHORITY_UNAVAILABLE')
        event=matches[0]
        receipt=self.finalized_receipt(event['transactionHash'],view)
        if not receipt or receipt['status']!='0x1' or receipt.get('to','').lower()!=self.address.lower() or receipt['blockHash']!=event['blockHash'] or receipt['blockNumber']!=event['blockNumber'] or event not in receipt.get('logs',[]):
            raise ValueError('AUTHORITY_UNAVAILABLE')
        return event


def registry_for(domain, settings, relayer_key=None):
    adapters={31337:LocalRegistry,10143:MonadTestnetRegistry}
    adapter=adapters.get(int(domain.get('chainId',0)))
    if adapter is None: raise ValueError('WRONG_CHAIN')
    return adapter(domain,settings,relayer_key)

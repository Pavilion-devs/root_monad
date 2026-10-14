"""Deterministic adversarial RPC responses. No public RPC or wallet use."""
import copy
import sys
import time
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'python'))
from eth_abi import encode
from registry import MonadTestnetRegistry, registry_for, selector

ADDRESS='0x'+'ab'*20
OWNER='0x'+'11'*20
PROJECT='0x'+'22'*32
DIGEST='0x'+'33'*32
HASH='0x'+'44'*32
TX='0x'+'55'*32
DOMAIN={'name':'PortableMemory','version':'0','chainId':10143,'verifyingContract':ADDRESS}

class RegistryTests(unittest.TestCase):
    def setUp(self):
        self.registry=MonadTestnetRegistry(DOMAIN,{'rpcUrl':'https://rpc.invalid'})
        self.cp={'projectId':PROJECT,'sequence':'1','previousDigest':'0x'+'00'*32,'controlDigest':DIGEST}
        from eth_utils import keccak
        self.event={'address':ADDRESS,'topics':['0x'+keccak(text='Advanced(bytes32,address,uint256,bytes32,bytes32)').hex(),PROJECT,'0x'+'00'*12+OWNER[2:]],
          'data':'0x'+encode(['uint256','bytes32','bytes32'],[1,bytes(32),bytes.fromhex(DIGEST[2:])]).hex(),
          'blockNumber':'0xa','blockHash':HASH,'transactionHash':TX,'logIndex':'0x0','removed':False}
        self.receipt={'transactionHash':TX,'blockNumber':'0xa','blockHash':HASH,'to':ADDRESS,'status':'0x1','logs':[self.event]}
        self.block={'number':'0xa','hash':HASH,'timestamp':hex(int(time.time()))}
        self.mode='ok';self.reads=0;self.calls=[]
        self.registry.rpc=self.rpc
        self.registry.rpc_many=lambda calls:[self.rpc(m,p) for m,p in calls]

    def rpc(self,method,params):
        self.calls.append((method,params))
        if method=='eth_chainId': return '0x1' if self.mode=='wrong_chain' else hex(10143)
        if method=='eth_gasPrice': return '0x1'
        if method=='eth_getTransactionCount': return '0x0'
        if method=='eth_getBlockByNumber':
            if params[0]=='finalized':
                if self.mode=='outage': raise ValueError('AUTHORITY_UNAVAILABLE')
                if self.mode=='missing_block': return None
                return {**self.block,'timestamp':hex(int(time.time())-300)} if self.mode=='stale' else self.block
            return {**self.block,'hash':'0x'+'ff'*32} if self.mode=='reorg' else self.block
        if method=='eth_getCode': return '0x' if self.mode=='missing_code' else '0xab'
        if method=='eth_call':
            if self.mode=='state_unavailable': raise ValueError('AUTHORITY_UNAVAILABLE')
            if params[0]['data'].startswith('0x'+selector('heads(bytes32)').hex()):
                return '0x'+encode(['address','uint256','bytes32'],[OWNER,1,bytes.fromhex(DIGEST[2:])]).hex()
            return '0x'+encode(['uint256'],[0 if self.mode=='not_accepted' else 10]).hex()
        if method=='eth_getLogs':
            self.assertEqual(params[0]['fromBlock'],params[0]['toBlock'])
            return [] if self.mode=='missing_event' else [copy.deepcopy(self.event)]
        if method=='eth_getTransactionReceipt':
            self.reads+=1
            if self.mode=='disappear' and self.reads>1: return None
            value=copy.deepcopy(self.receipt)
            if self.mode=='change' and self.reads>1: value['blockHash']='0x'+'ff'*32
            if self.mode=='unfinalized': value['blockNumber']='0xb';value['status']='0x0'
            if self.mode=='failed': value['status']='0x0'
            if self.mode=='receipt_no_event': value['logs']=[]
            return value
        raise AssertionError(method)

    def test_finalized_acceptance_and_single_block_lookup(self):
        self.assertEqual(self.registry.accepted(self.cp,OWNER,self.registry.view(PROJECT)),self.event)
        self.assertEqual(self.registry.confirmation,'finalized_rpc_verified')
        self.assertFalse(any(params and params[0]=='latest' for _,params in self.calls))

    def test_receipt_alone_does_not_finalize_failure(self):
        self.mode='unfinalized'
        self.assertIsNone(self.registry.receipt({'transactionHash':TX}))
        self.mode='failed'
        self.assertEqual(self.registry.receipt({'transactionHash':TX})['status'],'0x0')

    def test_changed_missing_and_noncanonical_receipts_fail_closed(self):
        for mode in ('change','disappear','reorg','receipt_no_event','failed'):
            with self.subTest(mode=mode):
                self.mode=mode;self.reads=0
                with self.assertRaises(ValueError): self.registry.accepted(self.cp,OWNER,self.registry.view(PROJECT))

    def test_unavailable_wrong_chain_stale_and_empty_contract_fail_closed(self):
        for mode in ('outage','wrong_chain','stale','missing_block','state_unavailable','missing_code'):
            with self.subTest(mode=mode):
                self.mode=mode
                with self.assertRaises(ValueError): self.registry.view(PROJECT)
        self.assertFalse(any(params and params[0]=='latest' for _,params in self.calls))

    def test_missing_event_or_competing_digest_is_not_accepted(self):
        self.mode='not_accepted'
        self.assertIsNone(self.registry.accepted(self.cp,OWNER,self.registry.view(PROJECT)))
        self.mode='missing_event'
        self.assertIsNone(self.registry.accepted(self.cp,OWNER,self.registry.view(PROJECT)))
        self.mode='ok'
        self.assertIsNone(self.registry.accepted({**self.cp,'controlDigest':'0x'+'ff'*32},OWNER,self.registry.view(PROJECT)))

    def test_chain_and_transport_are_pinned(self):
        for domain,url in (({**DOMAIN,'chainId':143},'https://rpc.invalid'),(DOMAIN,'http://127.0.0.1'),(DOMAIN,'https://user:password@rpc.invalid')):
            with self.assertRaises(ValueError): registry_for(domain,{'rpcUrl':url})
        self.assertIsInstance(registry_for(DOMAIN,{'rpcUrl':'https://rpc.invalid'}),MonadTestnetRegistry)

    def test_relayer_requires_explicit_fee_cap_and_rechecks_chain(self):
        self.registry.key='0x'+'44'*32
        envelope={'checkpoint':{**self.cp,'deadline':str(int(time.time())+60)},'control':{},'signature':'0x'+'00'*65}
        for cap in (None,'1'):
            if cap is not None: self.registry.settings['maxTransactionFeeWei']=cap
            with self.assertRaisesRegex(ValueError,'FEE_LIMIT_EXCEEDED'): self.registry.transaction(envelope,OWNER)
        self.registry.settings['maxTransactionFeeWei']='300000'
        tx=self.registry.transaction(envelope,OWNER)
        from eth_utils import keccak
        self.assertEqual(tx['transactionHash'],'0x'+keccak(bytes.fromhex(tx['rawTransaction'][2:])).hex())
        self.mode='wrong_chain'
        with self.assertRaisesRegex(ValueError,'WRONG_CHAIN'): self.registry.transaction(envelope,OWNER)

if __name__=='__main__': unittest.main()

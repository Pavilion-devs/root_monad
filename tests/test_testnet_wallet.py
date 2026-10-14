import copy
import os
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'python'))
from cryptography.exceptions import InvalidTag
from eth_account import Account
from testnet_wallet import seal,unseal,public,exclusive_json
from monad_deploy import prepare_intent,deploy,KIND
from recovery import unseal as unseal_intent
from eth_utils import keccak
import testnet_wallet

class FakeRegistry:
    def __init__(self): self.sent=[];self.ready=False;self.balance=10**18;self.price=1;self.checked=0
    def block(self): self.checked+=1;return {'number':'0x1'}
    def rpc(self,method,params):
        return {'eth_getTransactionCount':'0x0','eth_gasPrice':hex(self.price),'eth_estimateGas':'0x10000','eth_getBalance':hex(self.balance),'eth_getCode':'0x6000'}[method]
    def broadcast(self,intent): self.sent.append(intent)
    def receipt(self,intent):
        if not self.ready:return None
        return {'status':'0x1','contractAddress':intent['contractAddress'],'blockNumber':'0x1','blockHash':'0x'+'11'*32,'gasUsed':'0x10000','effectiveGasPrice':'0x1'}

class TestnetWalletTests(unittest.TestCase):
    def test_setup_is_idempotent_and_recovers_only_missing_public_metadata(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(testnet_wallet,'STATE',Path(folder)), patch.object(testnet_wallet,'keychain_read',return_value=os.urandom(32)):
            initial=testnet_wallet.create()
            self.assertEqual(testnet_wallet.create(),initial)
            (Path(folder)/'public.json').unlink()
            self.assertEqual(testnet_wallet.create(),initial)
            (Path(folder)/'wallet.enc').unlink()
            with self.assertRaisesRegex(ValueError,'ENCRYPTED_WALLET_MISSING'):testnet_wallet.create()

    def test_encrypted_vault_tamper_and_identity(self):
        body={role+'Key':'0x'+Account.create().key.hex() for role in ('relayer','owner','planning','coding')}
        key=os.urandom(32);sealed=seal(body,key)
        self.assertEqual(unseal(sealed,key),body)
        self.assertEqual(len(set(public(body)['addresses'].values())),4)
        self.assertFalse(any(value in str(sealed) for value in body.values()))
        with self.assertRaises(InvalidTag):unseal(sealed,os.urandom(32))
        bad=copy.deepcopy(sealed);bad['chainId']=143
        with self.assertRaisesRegex(ValueError,'WALLET_FORMAT'):unseal(bad,key)
        bad=copy.deepcopy(sealed);bad['ciphertext']='00'+bad['ciphertext'][2:]
        if bad['ciphertext']==sealed['ciphertext']:bad['ciphertext']='ff'+bad['ciphertext'][2:]
        with self.assertRaises(InvalidTag):unseal(bad,key)

    def test_exclusive_wallet_file_does_not_replace_existing_key_material(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'key.enc';exclusive_json(path,{'test':1})
            self.assertEqual(path.stat().st_mode&0o777,0o600)
            with self.assertRaises(FileExistsError):exclusive_json(path,{'test':2})

    def test_deployment_pending_resume_uses_same_encrypted_intent(self):
        data='0x6000';artifact={'chainId':10143,'unsignedTransaction':{'chainId':'0x279f','value':'0x0','data':data},'creationBytecodeKeccak256':'0x'+keccak(bytes.fromhex(data[2:])).hex(),'sourceSha256':'fixture'}
        account=Account.create();rpc=FakeRegistry();key=os.urandom(32)
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(ValueError,'DEPLOYMENT_PENDING'):deploy(rpc,account,artifact,folder,key,timeout=0)
            saved=unseal_intent((Path(folder)/'deployment-intent.enc').read_bytes(),key,KIND)
            self.assertEqual(saved['transactionHash'],rpc.sent[0]['transactionHash'])
            rpc.ready=True;result=deploy(rpc,account,artifact,folder,key,timeout=0)
            self.assertEqual(result['transactionHash'],saved['transactionHash'])
            self.assertEqual(rpc.sent[0],rpc.sent[1])
            with self.assertRaisesRegex(ValueError,'BUILD_MISMATCH'):deploy(rpc,account,{**artifact,'sourceSha256':'changed'},folder,key,timeout=0)
            with self.assertRaisesRegex(ValueError,'IDENTITY_MISMATCH'):deploy(rpc,Account.create(),artifact,folder,key,timeout=0)
        for mode in ('funds','fee','chain'):
            with self.subTest(mode=mode):
                r=FakeRegistry();a=copy.deepcopy(artifact)
                if mode=='funds':r.balance=0
                if mode=='fee':r.price=10**18
                if mode=='chain':a['chainId']=143
                with self.assertRaises(ValueError):prepare_intent(r,account,a)
                self.assertFalse(r.sent)

if __name__=='__main__':unittest.main()

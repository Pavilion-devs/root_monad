"""Opt-in testnet deployment with an encrypted, durable, idempotent transaction intent."""
import hashlib
import json
import time
from pathlib import Path
import rlp
from eth_account import Account
from eth_utils import keccak,to_checksum_address
from registry import MonadTestnetRegistry,raw
from recovery import exclusive,seal,unseal
from memory import require

KIND='portable-memory-monad-deployment/1'
RPC='https://testnet-rpc.monad.xyz'
MAX_FEE=200_000_000_000_000_000  # 0.2 test MON, deployment only.

def adapter(address='0x'+'00'*20,key=None):
    return MonadTestnetRegistry({'name':'PortableMemory','version':'0','chainId':10143,'verifyingContract':address},
        {'rpcUrl':RPC,'maxTransactionFeeWei':'100000000000000000'},key)

def prepare_intent(registry,account,artifact):
    registry.block()  # Chain and finalized-tip freshness are mandatory before signing.
    data=artifact['unsignedTransaction']['data']
    require(artifact['chainId']==10143 and int(artifact['unsignedTransaction']['chainId'],16)==10143,'WRONG_CHAIN')
    require(artifact['unsignedTransaction']['value']=='0x0' and 'to' not in artifact['unsignedTransaction'],'INVALID_DEPLOYMENT')
    require('0x'+keccak(raw(data)).hex()==artifact['creationBytecodeKeccak256'],'BYTECODE_MISMATCH')
    nonce=int(registry.rpc('eth_getTransactionCount',[account.address,'pending']),16)
    fee=int(registry.rpc('eth_gasPrice',[]),16)
    estimate=int(registry.rpc('eth_estimateGas',[{'from':account.address,'data':data,'value':'0x0'}]),16)
    gas=(estimate*120+99)//100
    require(gas*fee<=MAX_FEE,'FEE_LIMIT_EXCEEDED')
    require(int(registry.rpc('eth_getBalance',[account.address,'latest']),16)>=gas*fee,'TESTNET_FUNDS_REQUIRED')
    transaction={'chainId':10143,'nonce':nonce,'value':0,'data':data,'gas':gas,'gasPrice':fee}
    signed=account.sign_transaction(transaction)
    contract=to_checksum_address(keccak(rlp.encode([raw(account.address),nonce]))[-20:])
    return {'chainId':10143,'sender':account.address,'contractAddress':contract,
        'bytecodeHash':artifact['creationBytecodeKeccak256'],'sourceSha256':artifact['sourceSha256'],
        'maximumFeeWei':str(gas*fee),'rawTransaction':'0x'+signed.raw_transaction.hex(),'transactionHash':'0x'+signed.hash.hex()}

def deploy(registry,account,artifact,directory,key,timeout=60):
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True,mode=0o700)
    path=directory/'deployment-intent.enc'
    if path.exists(): intent=unseal(path.read_bytes(),key,KIND)
    else:
        intent=prepare_intent(registry,account,artifact)
        exclusive(path,seal(intent,key,KIND))
    require(intent['chainId']==10143 and intent['sender']==account.address,'DEPLOYMENT_IDENTITY_MISMATCH')
    require(intent['bytecodeHash']==artifact['creationBytecodeKeccak256'] and intent['sourceSha256']==artifact['sourceSha256'],'DEPLOYMENT_BUILD_MISMATCH')
    require('0x'+keccak(raw(intent['rawTransaction'])).hex()==intent['transactionHash'],'INTEGRITY_FAILURE')
    require(Account.recover_transaction(intent['rawTransaction'])==account.address,'WRONG_SIGNER')
    # Even resumption of a saved transaction must pin the endpoint to testnet.
    registry.block()
    started=time.monotonic();registry.broadcast(intent)
    while True:
        receipt=registry.receipt(intent)
        if receipt:
            require(receipt['status']=='0x1','DEPLOYMENT_REVERTED')
            require(receipt.get('contractAddress','').lower()==intent['contractAddress'].lower(),'DEPLOYMENT_ADDRESS_MISMATCH')
            code=registry.rpc('eth_getCode',[intent['contractAddress'],receipt['blockNumber']])
            require(code!='0x','REGISTRY_MISSING')
            return {'chainId':10143,'contractAddress':intent['contractAddress'],'deployer':account.address,
                'transactionHash':intent['transactionHash'],'blockNumber':receipt['blockNumber'],'blockHash':receipt['blockHash'],
                'confirmation':'finalized_rpc_verified','gasUsed':str(int(receipt['gasUsed'],16)),
                'feeWei':str(int(receipt['gasUsed'],16)*int(receipt['effectiveGasPrice'],16)),
                'runtimeCodeHash':'0x'+keccak(raw(code)).hex(),'creationBytecodeHash':intent['bytecodeHash'],
                'sourceSha256':intent['sourceSha256'],'observedAtUnix':int(time.time()),
                'resumeOrSubmissionElapsedSeconds':round(time.monotonic()-started,3)}
        if time.monotonic()-started>=timeout: raise ValueError('DEPLOYMENT_PENDING')
        time.sleep(1)

def checked_artifact(path):
    artifact=json.loads(Path(path).read_text())
    source=Path(__file__).resolve().parents[1]/'contracts'/'MemoryRegistry.sol'
    require(hashlib.sha256(source.read_bytes()).hexdigest()==artifact['sourceSha256'],'DEPLOYMENT_BUILD_MISMATCH')
    return artifact

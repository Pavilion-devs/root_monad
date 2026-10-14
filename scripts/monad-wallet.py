"""Wallet public status and explicit testnet-only deployment. Secrets stay in-process."""
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'python'))
from eth_account import Account
from testnet_wallet import STATE,create,load,public
from monad_deploy import adapter,deploy,checked_artifact

def main():
    operation=sys.argv[1] if len(sys.argv)>1 else 'status'
    if operation not in ('create','status','deploy'): raise ValueError('INVALID_OPERATION')
    if operation=='create': return create()
    wallet=load();account=Account.from_key(wallet['relayerKey']);registry=adapter()
    block=registry.block()
    balance=int(registry.rpc('eth_getBalance',[account.address,'latest']),16)
    if operation=='status':
        return {**public(wallet),'balanceWei':str(balance),'finalizedBlock':block['number']}
    if sys.argv[2:]!=['--live']: raise ValueError('EXPLICIT_LIVE_FLAG_REQUIRED')
    if balance==0: raise ValueError('TESTNET_FUNDS_REQUIRED')
    result=deploy(registry,account,checked_artifact('results/monad-deployment-preparation.json'),STATE,bytes.fromhex(wallet['recoveryKey']))
    Path('results/monad-deployment.json').write_text(json.dumps(result,indent=2)+'\n')
    return result

if __name__=='__main__':
    try: print(json.dumps(main(),indent=2))
    except Exception as error:
        code=str(error) if isinstance(error,ValueError) and str(error).isupper() and len(str(error))<80 else 'TESTNET_OPERATION_FAILED'
        print(json.dumps({'code':code}));sys.exit(1)

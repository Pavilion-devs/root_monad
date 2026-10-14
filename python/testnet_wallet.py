"""Dedicated Monad testnet identities, encrypted locally with a macOS Keychain key."""
import json
import os
import subprocess
from pathlib import Path
from eth_account import Account
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

STATE=Path.home()/'Library'/'Application Support'/'PortableMemory'/'monad-testnet'
SERVICE='portable-memory.monad-testnet.v1'
ACCOUNT='local-test-wallet'
AAD=b'portable-memory:testnet-wallet:10143:v1'

def keychain_read():
    result=subprocess.run(['/usr/bin/security','find-generic-password','-s',SERVICE,'-a',ACCOUNT,'-w'],capture_output=True)
    if result.returncode: raise ValueError('KEYCHAIN_UNLOCK_REQUIRED')
    return bytes.fromhex(result.stdout.decode().strip())

def keychain_create(secret):
    # Interactive stdin keeps the generated secret out of process arguments and logs.
    command=f'add-generic-password -s {SERVICE} -a {ACCOUNT} -w {secret.hex()}\n'
    subprocess.run(['/usr/bin/security','-i'],input=command.encode(),capture_output=True)
    if keychain_read()!=secret: raise ValueError('KEYCHAIN_WRITE_FAILED')

def exclusive_json(path,value):
    with open(os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),'w') as stream:
        json.dump(value,stream,indent=2);stream.write('\n');stream.flush();os.fsync(stream.fileno())
    parent=os.open(Path(path).parent,os.O_RDONLY)
    try: os.fsync(parent)
    finally: os.close(parent)

def seal(payload,key):
    nonce=os.urandom(12)
    return {'formatVersion':1,'chainId':10143,'nonce':nonce.hex(),'ciphertext':AESGCM(key).encrypt(nonce,json.dumps(payload).encode(),AAD).hex()}

def unseal(envelope,key):
    if envelope.get('formatVersion')!=1 or envelope.get('chainId')!=10143: raise ValueError('WALLET_FORMAT_INVALID')
    return json.loads(AESGCM(key).decrypt(bytes.fromhex(envelope['nonce']),bytes.fromhex(envelope['ciphertext']),AAD))

def public(payload):
    return {'chainId':10143,'network':'monad_testnet','addresses':{role:Account.from_key(payload[role+'Key']).address for role in ('relayer','owner','planning','coding')},'custody':'AES-256-GCM encrypted vault; unlock key in macOS Keychain'}

def load():
    payload=unseal(json.loads((STATE/'wallet.enc').read_text()),keychain_read())
    if public(payload)!=json.loads((STATE/'public.json').read_text()): raise ValueError('WALLET_IDENTITY_MISMATCH')
    return payload

def create():
    STATE.mkdir(parents=True,exist_ok=True,mode=0o700)
    os.chmod(STATE,0o700)
    if (STATE/'wallet.enc').exists():
        # Recover only public metadata if initialization stopped after the encrypted write.
        if not (STATE/'public.json').exists():
            payload=unseal(json.loads((STATE/'wallet.enc').read_text()),keychain_read())
            exclusive_json(STATE/'public.json',public(payload))
        return public(load())
    if (STATE/'public.json').exists(): raise ValueError('ENCRYPTED_WALLET_MISSING')
    try: key=keychain_read()
    except ValueError:
        key=os.urandom(32);keychain_create(key)
    payload={role+'Key':'0x'+Account.create().key.hex() for role in ('relayer','owner','planning','coding')}
    payload.update(storageKey=os.urandom(32).hex(),recoveryKey=os.urandom(32).hex())
    exclusive_json(STATE/'wallet.enc',seal(payload,key))
    exclusive_json(STATE/'public.json',public(payload))
    return public(load())

if __name__=='__main__':
    try: print(json.dumps({**create(),'stateDirectory':str(STATE)},indent=2))
    except Exception:
        print(json.dumps({'code':'WALLET_SETUP_FAILED','detail':'Check macOS Keychain access; no secrets were printed.'}))
        raise SystemExit(1)

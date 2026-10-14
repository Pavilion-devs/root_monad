"""Independent Python encoding and EIP-712 implementation for the authority spike."""
import hashlib
import json
import math
from pathlib import Path
import rfc8785
from eth_account import Account
from eth_account.messages import encode_typed_data
from eth_abi import encode
from eth_utils import keccak
from jsonschema import Draft7Validator

ROOT = Path(__file__).resolve().parents[1]
MAX_UINT = 2**256 - 1
TYPES = {
    'Checkpoint': [{'name': name, 'type': typ} for typ, name in [
        ('bytes32', 'projectId'), ('uint256', 'sequence'), ('bytes32', 'previousDigest'),
        ('bytes32', 'controlDigest'), ('uint256', 'deadline')]],
    'Request': [{'name': name, 'type': typ} for typ, name in [
        ('bytes32', 'projectId'), ('bytes32', 'serviceId'), ('bytes32', 'checkpointDigest'),
        ('bytes32', 'requestDigest'), ('bytes32', 'nonce'), ('uint256', 'deadline')]],
}
VALIDATORS = {name: Draft7Validator(json.loads((ROOT/'schemas'/f'{name}.schema.json').read_text()))
              for name in ['control', 'checkpoint', 'request', 'request-auth', 'source', 'record', 'proposal', 'snapshot']}

def canonical(value):
    def check(v):
        if isinstance(v, str):
            v.encode('utf-8', errors='strict')
        elif isinstance(v, (float, int)) and not isinstance(v, bool):
            if not math.isfinite(v) or abs(v) > 2**53-1:
                raise ValueError('UNSAFE_NUMBER')
        elif isinstance(v, list):
            for child in v: check(child)
        elif isinstance(v, dict):
            for k, child in v.items(): check(k); check(child)
    check(value)
    return rfc8785.dumps(value)

def strict_loads(text):
    def pairs(items):
        result = {}
        for k, v in items:
            if k in result: raise ValueError('DUPLICATE_KEY')
            result[k] = v
        return result
    value = json.loads(text, object_pairs_hook=pairs)
    canonical(value)
    return value

def validate(kind, body):
    canonical(body)
    VALIDATORS[kind].validate(body)
    for key in ['sequence', 'deadline']:
        if key in body and int(body[key]) > MAX_UINT: raise ValueError('UINT_OVERFLOW')
    if kind == 'control':
        addresses = [g['application'] for g in body['grants']]
        if addresses != sorted(set(addresses)): raise ValueError('UNSORTED_GRANTS')
        for grant in body['grants']:
            if grant['serviceId'] != body['serviceId'] or int(grant['expiresAt']) > MAX_UINT:
                raise ValueError('INVALID_GRANT')
            if grant['rights'] != sorted(grant['rights']): raise ValueError('UNSORTED_RIGHTS')
    if kind == 'request' and body['path'] != f"/v0/projects/{body['projectId']}/{body['operation']}":
        raise ValueError('WRONG_PATH')

def digest(kind, body):
    validate(kind, body)
    return '0x' + hashlib.sha256(f'portable-memory/v0/{kind}\0'.encode() + canonical(body)).hexdigest()

def project_id(owner, nonce):
    return '0x' + keccak(encode(['address', 'bytes32'], [owner, bytes.fromhex(nonce[2:])])).hex()

def message(domain, kind, body):
    validate('checkpoint' if kind == 'Checkpoint' else 'request-auth', body)
    return encode_typed_data(domain, {kind: TYPES[kind]}, body)

def sign(key, domain, kind, body):
    return '0x' + Account.sign_message(message(domain, kind, body), key).signature.hex()

def recover(domain, kind, body, signature):
    import re
    order = 0xfffffffffffffffffffffffffffffffebaaedce6af48a03bbfd25e8cd0364141
    if not re.fullmatch(r'0x[0-9a-fA-F]{130}', signature): raise ValueError('INVALID_SIGNATURE')
    r, s, v = int(signature[2:66], 16), int(signature[66:130], 16), int(signature[130:], 16)
    if not (0 < r < order and 0 < s <= order//2 and v in (27, 28)):
        raise ValueError('INVALID_SIGNATURE')
    return Account.recover_message(message(domain, kind, body), signature=signature).lower()

if __name__ == '__main__':
    import sys
    request = strict_loads(sys.stdin.read())
    result = {'projectId': project_id(request['owner'], request['control']['creationNonce']),
              'canonical': canonical(request['control']).decode(),
              'controlDigest': digest('control', request['control']),
              'requestDigest': digest('request', request['requestBody']),
              'checkpointSigner': recover(request['domain'], 'Checkpoint', request['checkpoint'], request['checkpointSignature']),
              'requestSigner': recover(request['domain'], 'Request', request['requestAuth'], request['requestSignature']),
              'checkpointSignature': sign(request['testOwnerKey'], request['domain'], 'Checkpoint', request['checkpoint']),
              'requestSignature': sign(request['testAppKey'], request['domain'], 'Request', request['requestAuth'])}
    print(json.dumps(result))

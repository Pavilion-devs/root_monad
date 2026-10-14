import copy
import json
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'python'))
from protocol import canonical, strict_loads, validate, digest, recover, project_id
ROOT=Path(__file__).resolve().parents[1]
VECTOR=json.loads((ROOT/'fixtures/authority-vector.json').read_text())

class ProtocolTests(unittest.TestCase):
    def test_fixed_vector(self):
        self.assertEqual(project_id(VECTOR['owner'], VECTOR['control']['creationNonce']),VECTOR['control']['projectId'])
        self.assertEqual(digest('control',VECTOR['control']),VECTOR['checkpoint']['controlDigest'])
        self.assertEqual(digest('request',VECTOR['requestBody']),VECTOR['requestAuth']['requestDigest'])
        self.assertEqual(recover(VECTOR['domain'],'Checkpoint',VECTOR['checkpoint'],VECTOR['checkpointSignature']),VECTOR['owner'])
        self.assertEqual(recover(VECTOR['domain'],'Request',VECTOR['requestAuth'],VECTOR['requestSignature']),VECTOR['app'])

    def test_json_boundary(self):
        for text in ['{"a":1,"a":2}','{"a":{"b":1,"b":2}}','{"a":"\\ud800"}','{"a":1e999}','{"a":9007199254740992}','{"a":1,}']:
            with self.subTest(text=text), self.assertRaises((ValueError, UnicodeError)):
                strict_loads(text)
        self.assertEqual(canonical({'\ufb33':1,'😀':2}).decode(),'{"😀":2,"דּ":1}')

    def test_invalid_authority_fields(self):
        for patch in [{'owner_confirmed':True},{'sequence':'01'},{'sequence':str(2**256)}]:
            with self.subTest(patch=patch), self.assertRaises(Exception):
                validate('control',{**VECTOR['control'],**patch})

    def test_grant_order_and_audience(self):
        for mutate in ['duplicate','rights','service']:
            body=copy.deepcopy(VECTOR['control'])
            if mutate=='duplicate': body['grants']*=2
            if mutate=='rights': body['grants'][0]['rights'].reverse()
            if mutate=='service': body['grants'][0]['serviceId']='0x'+'ff'*32
            with self.subTest(mutate=mutate), self.assertRaises(ValueError): validate('control',body)

    def test_changed_content_and_domain(self):
        cp={**VECTOR['checkpoint'],'controlDigest':'0x'+'aa'*32}
        self.assertNotEqual(recover(VECTOR['domain'],'Checkpoint',cp,VECTOR['checkpointSignature']),VECTOR['owner'])
        domain={**VECTOR['domain'],'salt':'0x'+'bb'*32}
        self.assertNotEqual(recover(domain,'Checkpoint',VECTOR['checkpoint'],VECTOR['checkpointSignature']),VECTOR['owner'])

    def test_malleable_and_truncated_signatures(self):
        sig=VECTOR['checkpointSignature']
        order=0xfffffffffffffffffffffffffffffffebaaedce6af48a03bbfd25e8cd0364141
        high_s=f'{order-int(sig[66:130],16):064x}'
        for bad in [sig[:-2],sig[:66]+high_s+sig[130:],'0x'+'00'*65]:
            with self.subTest(signature=bad), self.assertRaises(ValueError):
                recover(VECTOR['domain'],'Checkpoint',VECTOR['checkpoint'],bad)

if __name__=='__main__': unittest.main()

import copy
import json
import os
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'python'))
import test_memory
from recovery import export_memory, unseal, seal, restore_memory, validate_package, ARCHIVE, CAPSULE, load_key
from jsonschema import ValidationError

class Authority:
    """Only the package-validation unit tests use this fixed authority stub."""
    def __init__(self, memory): self.envelope=memory.local_current();self.owner=memory.owner
    def view(self,project):
        cp=self.envelope['checkpoint']
        return {'owner':self.owner,'sequence':cp['sequence'],'digest':cp['controlDigest']}
    def accepted(self,cp,owner,view): return {'transactionHash':'fixture'} if cp==self.envelope['checkpoint'] and owner==self.owner else None

class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.fixture=test_memory.MemoryTests();self.fixture.setUp();self.m=self.fixture.m
        proposal=self.fixture.proposal();self.m.execute(self.fixture.wire('proposals',proposal))
        self.fixture.approve({'accept':[proposal['id']],'reject':[],'grants':None})
        self.registry=Authority(self.m);self.m.registry=self.registry
        self.root=Path(self.fixture.tmp.name)
        self.archive=self.root/'archive.enc';self.keyfile=self.root/'owner.key'
        export_memory(self.m,self.archive,self.keyfile)
        self.key=bytes.fromhex(self.keyfile.read_text().strip())
        self.package=unseal(self.archive.read_bytes(),self.key,ARCHIVE)
        self.binding={'serviceId':'0x'+'ab'*32,'storage':{'providerId':'0x'+'cd'*32,'locator':'fixture://second'}}
    def tearDown(self): self.fixture.tearDown()
    def attempt(self,package):
        path=self.root/'modified.enc';path.write_bytes(seal(package,self.key,ARCHIVE))
        return restore_memory(path,self.key,self.root/'restored',self.m.config,self.binding,self.registry)
    def test_missing_and_modified_records_fail_even_with_valid_archive_encryption(self):
        for change in ['missing','modified']:
            p=copy.deepcopy(self.package)
            if change=='missing':p['records']=[]
            else:p['records'][0]['content']='Forged owner-approved content'
            with self.subTest(change=change),self.assertRaisesRegex(ValueError,'CONTENT_UNAVAILABLE|CONTENT_MISMATCH'):
                self.attempt(p)
            self.assertFalse((self.root/'restored').exists())
    def test_duplicate_inventory_and_broken_history_fail(self):
        p=copy.deepcopy(self.package);p['sources'].append(p['sources'][0])
        with self.assertRaisesRegex(ValueError,'DUPLICATE_ENTRY'): self.attempt(p)
        p=copy.deepcopy(self.package);p['checkpoints']=p['checkpoints'][1:]
        with self.assertRaisesRegex(ValueError,'INCOMPLETE_HISTORY'): self.attempt(p)
    def test_forged_labels_and_unknown_archive_fields_fail(self):
        p=copy.deepcopy(self.package);p['records'][0]['owner_confirmed']=True
        with self.assertRaises(ValidationError): self.attempt(p)
        p=copy.deepcopy(self.package);p['../../outside']='payload'
        with self.assertRaisesRegex(ValueError,'INVALID_PAYLOAD'): self.attempt(p)
        p=copy.deepcopy(self.package);p['formatVersion']='999'
        with self.assertRaisesRegex(ValueError,'UNKNOWN_FORMAT'): self.attempt(p)
        self.assertFalse((self.root/'restored').exists())
    def test_missing_proposal_evidence_and_forged_signatures_fail(self):
        p=copy.deepcopy(self.package);p['proposals']=[]
        with self.assertRaisesRegex(ValueError,'CONTENT_UNAVAILABLE'):self.attempt(p)
        p=copy.deepcopy(self.package);p['proposals'][0]['evidence']['signature']='0x'+'00'*65
        with self.assertRaisesRegex(ValueError,'INVALID_SIGNATURE'):self.attempt(p)
    def test_capsule_requires_recovery_key_and_pinned_identity(self):
        self.attempt(self.package);path=self.root/'restored'/'project-key.enc'
        new_key=load_key(path,self.key,self.m.config)
        self.assertEqual(len(new_key),32);self.assertNotEqual(new_key,self.fixture.key)
        with self.assertRaisesRegex(ValueError,'INVALID_RECOVERY_PACKAGE'):load_key(path,os.urandom(32),self.m.config)
        with self.assertRaisesRegex(ValueError,'CONFIG_MISMATCH'):load_key(path,self.key,{**self.m.config,'owner':'0x'+'ab'*20})
    def test_export_freezes_mutations_and_does_not_overwrite_files(self):
        with self.assertRaisesRegex(ValueError,'WRITES_FROZEN'):
            self.m.execute(self.fixture.wire('proposals',self.fixture.proposal()))
        original=self.archive.read_bytes()
        with self.assertRaisesRegex(ValueError,'DESTINATION_EXISTS'):
            export_memory(self.m,self.archive,self.keyfile)
        self.assertEqual(self.archive.read_bytes(),original)

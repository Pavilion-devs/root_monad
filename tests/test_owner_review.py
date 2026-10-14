import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'python'))
import test_memory
from owner_review import verify_review
from protocol import digest

class OwnerReviewTests(unittest.TestCase):
    def setUp(self):
        self.fixture=test_memory.MemoryTests();self.fixture.setUp()
        self.m=self.fixture.m;self.p=self.fixture.proposal()
        self.m.execute(self.fixture.wire('proposals',self.p))
        self.before=self.m.context(self.m.current(),False)
        self.review=self.m.execute(self.fixture.wire('prepare',{'accept':[self.p['id']],'reject':[],'grants':None},test_memory.V['testOwnerKey']))
    def tearDown(self):self.fixture.tearDown()
    def test_accepts_exact_proposal_and_exact_grant_change(self):
        verify_review(self.fixture.config,self.before,self.review,self.p)
        revoke=self.m.execute(self.fixture.wire('prepare',{'accept':[],'reject':[],'grants':[]},test_memory.V['testOwnerKey']))
        verify_review(self.fixture.config,self.before,revoke,grants=[])
    def test_self_consistent_hidden_permission_change_is_rejected(self):
        review=copy.deepcopy(self.review);review['control']['grants']=[]
        review['checkpoint']['controlDigest']=digest('control',review['control'])
        with self.assertRaisesRegex(ValueError,'UNEXPECTED_REVIEW_CHANGE'):
            verify_review(self.fixture.config,self.before,review,self.p)
    def test_self_consistent_hidden_record_change_is_rejected(self):
        review=copy.deepcopy(self.review);review['records'][0]['content']='Unexpected owner decision'
        review['snapshot']['records'][0]['digest']=digest('record',review['records'][0])
        review['control']['snapshotDigest']=digest('snapshot',review['snapshot'])
        review['checkpoint']['controlDigest']=digest('control',review['control'])
        with self.assertRaisesRegex(ValueError,'UNEXPECTED_REVIEW_CHANGE'):
            verify_review(self.fixture.config,self.before,review,self.p)
    def test_existing_source_cannot_be_rewritten_by_a_new_proposal(self):
        self.fixture.approve({'accept':[self.p['id']],'reject':[],'grants':None})
        before=self.m.context(self.m.current(),False)
        proposal=self.fixture.proposal()
        proposal['sources']=copy.deepcopy(self.p['sources'])
        proposal['sources'][0]['excerpt']='Rewritten earlier evidence'
        proposal['records'][0]['sourceIds']=[proposal['sources'][0]['id']]
        with self.assertRaisesRegex(ValueError,'ID_CONFLICT'):
            verify_review(self.fixture.config,before,self.review,proposal)

    def test_record_author_cannot_differ_from_signed_proposer(self):
        proposal=copy.deepcopy(self.p)
        proposal['records'][0]['author']=test_memory.V['owner']
        with self.assertRaisesRegex(ValueError,'WRONG_AUTHOR'):
            verify_review(self.fixture.config,self.before,self.review,proposal)

    def test_wrong_checkpoint_and_tampered_review_body_are_rejected(self):
        for part in ('checkpoint','body'):
            review=copy.deepcopy(self.review)
            if part=='checkpoint':review['checkpoint']['sequence']='999'
            else:review['records'][0]['content']='Uncommitted replacement'
            with self.subTest(part=part),self.assertRaisesRegex(ValueError,'UNEXPECTED_REVIEW_CHANGE|CONTENT_MISMATCH'):
                verify_review(self.fixture.config,self.before,review,self.p)

if __name__=='__main__':unittest.main()

import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'ops'))
spec=importlib.util.spec_from_file_location('hosted_journey',ROOT/'ops/hosted-assistants.py')
journey=importlib.util.module_from_spec(spec);spec.loader.exec_module(journey)

class JourneyResumeTests(unittest.TestCase):
    def test_saved_model_output_resumes_without_another_model_call(self):
        runner=journey.Journey.__new__(journey.Journey)
        output={'advice':{'status':'model_generated_unverified','text':'Saved answer'}}
        runner.state={'_modelAttempts':['planning'],'calls':[{'step':'planning','ok':True,'result':output}]}
        with patch.object(journey.subprocess,'run',side_effect=AssertionError('Must not start a worker')):
            self.assertEqual(runner.model('planning','planning','Question'),output)
    def test_uncertain_model_attempt_does_not_repeat(self):
        runner=journey.Journey.__new__(journey.Journey)
        runner.state={'_modelAttempts':['planning']}
        with patch.object(journey.subprocess,'run',side_effect=AssertionError('Must not start a worker')):
            with self.assertRaisesRegex(ValueError,'MODEL_ATTEMPT_UNCERTAIN'):
                runner.model('planning','planning','Question')

if __name__=='__main__':unittest.main()

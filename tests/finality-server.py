"""Test-only URL injection; exercise the actual persistent/batched transport."""
import runpy
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'python'))
from registry import MonadTestnetRegistry

original_init=MonadTestnetRegistry.__init__
def init(self,domain,settings,relayer_key=None):
    original_init(self,domain,settings,relayer_key)
    self.url=settings['testTransportUrl']
MonadTestnetRegistry.__init__=init
runpy.run_path('python/server.py',run_name='__main__')

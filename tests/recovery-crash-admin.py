"""Test-only process death after submitting the migration transaction."""
import os
import runpy
import sys
from pathlib import Path
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/'python'))
from registry import LocalRegistry
original=LocalRegistry.broadcast
def crash(self, transaction):
    original(self,transaction)
    os._exit(73)
LocalRegistry.broadcast=crash
runpy.run_path(str(root/'python/admin.py'),run_name='__main__')

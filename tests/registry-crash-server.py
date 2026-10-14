"""Fault injector lives only in tests: kill the process at the submission boundary."""
import os
import runpy
import sys
from pathlib import Path
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/'python'))
from registry import LocalRegistry
original=LocalRegistry.broadcast
mode=sys.argv[1]
def crash(self, transaction):
    if mode=='after': original(self,transaction)
    os._exit(73)
LocalRegistry.broadcast=crash
runpy.run_path(str(root/'python/server.py'),run_name='__main__')

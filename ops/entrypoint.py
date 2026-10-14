"""Read the service-only secret mount; never place secret contents in argv or logs."""
import os
import runpy
import sys
os.umask(0o077)
sys.path.insert(0,'/app/python')
with open('/run/secrets/startup.json') as source:
    sys.stdin=source
    runpy.run_path('/app/python/server.py',run_name='__main__')

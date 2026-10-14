"""Verify the built archive in an extracted directory and entirely fresh virtualenv."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile
ROOT=Path(__file__).resolve().parents[1]


def main():
    archive=ROOT/'dist/portable-memory-devkit-0.1.0.zip'
    checksum=hashlib.sha256(archive.read_bytes()).hexdigest()
    assert (ROOT/'dist/SHA256SUMS').read_text().split()[0]==checksum
    with tempfile.TemporaryDirectory(prefix='portable-memory-release-check-') as folder:
        with zipfile.ZipFile(archive) as z:
            assert all(name.startswith(archive.stem+'/') and '..' not in Path(name).parts for name in z.namelist())
            z.extractall(folder)
        package=Path(folder)/archive.stem
        manifest=json.loads((package/'MANIFEST.json').read_text())
        assert all(hashlib.sha256((package/name).read_bytes()).hexdigest()==value for name,value in manifest['files'].items())
        subprocess.run([sys.executable,'-m','venv',str(package/'.venv')],check=True,capture_output=True)
        py=package/'.venv/bin/python'
        for command in ([str(py),'-m','pip','install','--disable-pip-version-check','-r','requirements.lock'],[str(py),'-m','pip','check']):
            completed=subprocess.run(command,cwd=package,capture_output=True,text=True,timeout=240)
            if completed.returncode:raise RuntimeError('CLEAN_DEPENDENCY_CHECK_FAILED')
        smoke=subprocess.run([str(py),'devkit/smoke.py'],cwd=package,capture_output=True,text=True,timeout=120)
        if smoke.returncode:raise RuntimeError('CLEAN_SMOKE_FAILED')
        result=json.loads(smoke.stdout);assert result['passed']
        report={'passed':True,'archive':archive.name,'sha256':checksum,'fileCount':len(manifest['files'])+1,'cleanVenv':True,'manifestVerified':True,'pipCheck':completed.stdout.strip(),'python':sys.version.split()[0],'platform':sys.platform,'sourceCheckoutUsed':False,'modelCalls':0,'chainTransactions':0,'smoke':result}
        (ROOT/'results/devkit-clean-install.json').write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps(report,indent=2))


if __name__=='__main__':main()

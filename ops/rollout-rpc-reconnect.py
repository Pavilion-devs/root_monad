"""Target-side, one-time app-only rollout; image must already be built and tested."""
import json
import subprocess
import time

APP = 'portable-memory'
OLD = 'portable-memory-before-rpc-reconnect'
NETWORK = 'portable-memory-net'
IMAGE = 'portable-memory:rpc-reconnect-v1'
BASE = 'sha256:cabb16731a680354042fda93680e56ed6bfb19af57b39ff289bdc0c5c5117c9d'


def run(*args):
    return subprocess.check_output(['docker', *args], stderr=subprocess.PIPE).decode().strip()


def inspect(name):
    return json.loads(run('inspect', name))[0]


def main():
    before = inspect(APP)
    proxy = inspect('portable-memory-proxy')
    assert before['Image'] == BASE and before['State']['Running']
    assert set(before['NetworkSettings']['Networks']) == {NETWORK}
    assert not before['HostConfig']['PortBindings']
    assert subprocess.run(['docker', 'inspect', OLD], capture_output=True).returncode != 0
    image = inspect(IMAGE)
    assert image['Config']['User'] == '10002:10002'
    assert image['Config']['Entrypoint'] == before['Config']['Entrypoint']
    expected = {('/srv/portable-memory/data', '/data', True),
                ('/srv/portable-memory/secrets/startup.json', '/run/secrets/startup.json', False)}
    assert {(m['Source'], m['Destination'], m['RW']) for m in before['Mounts']} == expected
    ip = before['NetworkSettings']['Networks'][NETWORK]['IPAddress']
    args = ['run', '-d', '--name', APP, '--label', 'project=portable-memory',
            '--network', NETWORK, '--ip', ip, '--restart', 'unless-stopped',
            '--read-only', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges:true',
            '--memory', '256m', '--memory-swap', '256m', '--cpus', '0.25', '--pids-limit', '64',
            '--tmpfs', '/tmp:rw,noexec,nosuid,size=16m', '--log-driver', 'json-file',
            '--log-opt', 'max-size=5m', '--log-opt', 'max-file=2',
            '--mount', 'type=bind,src=/srv/portable-memory/data,dst=/data',
            '--mount', 'type=bind,src=/srv/portable-memory/secrets/startup.json,dst=/run/secrets/startup.json,readonly',
            '--health-cmd', before['Config']['Healthcheck']['Test'][1],
            '--health-interval', '30s', '--health-timeout', '5s', '--health-retries', '3', '--health-start-period', '30s', IMAGE]
    run('stop', '--time', '20', APP)
    run('rename', APP, OLD)
    try:
        run('network', 'disconnect', NETWORK, OLD)
        run(*args)
        check = 'import urllib.request; assert urllib.request.urlopen("http://127.0.0.1:8080/healthz",timeout=4).status==200'
        for attempt in range(20):
            if subprocess.run(['docker', 'exec', APP, 'python', '-c', check], capture_output=True).returncode == 0:
                break
            time.sleep(1)
        else:
            raise RuntimeError('NEW_APP_UNAVAILABLE')
        assert inspect('portable-memory-proxy')['Id'] == proxy['Id']
        assert inspect('portable-memory-proxy')['State']['StartedAt'] == proxy['State']['StartedAt']
        print(json.dumps({'updated': APP, 'image': image['Id'], 'rollbackContainer': OLD, 'proxyUnchanged': True, 'samePrivateIp': ip}))
    except Exception:
        if subprocess.run(['docker', 'inspect', APP], capture_output=True).returncode == 0:
            run('stop', '--time', '10', APP)
            run('network', 'disconnect', NETWORK, APP)
            run('rename', APP, APP + '-failed-rpc-reconnect')
        if NETWORK not in inspect(OLD)['NetworkSettings']['Networks']:
            run('network', 'connect', '--ip', ip, '--alias', APP, NETWORK, OLD)
        run('rename', OLD, APP)
        run('start', APP)
        raise


if __name__ == '__main__':
    main()

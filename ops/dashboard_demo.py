"""Launch the dashboard with isolated, explicitly synthetic local state."""
import argparse
import json
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
from dashboard import load_devkit, ROOT
sys.path.insert(0, str(ROOT / 'python'))
from dashboard_server import Dashboard


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=0)
    parser.add_argument('--connection-file', type=Path)
    args = parser.parse_args()
    assets = ROOT / 'frontend/ui/dist'
    if not (assets / 'index.html').is_file():
        parser.error('Build first: npm --prefix frontend/ui run build')
    kit = load_devkit()
    with tempfile.TemporaryDirectory(prefix='portable-memory-dashboard-') as temporary:
        state = Path(temporary) / 'workspace'
        kit.init(state)
        service = subprocess.Popen([sys.executable, str(ROOT / 'devkit/memory.py'), '--state', str(state), 'serve'], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        try:
            if not service.stdout.readline():
                raise RuntimeError('Local sample service did not start')
            owner = kit.owner(state)
            bridge = kit.bridge(state, 'claude')
            for number, kind, content in [
                (1, 'decision', 'Example project: keep project decisions with their original sources when switching assistants.'),
                (2, 'open_question', 'Example project: which timestamp starts the retention period? The owner has not decided yet.'),
            ]:
                current = bridge.read()
                bridge.propose(f'dashboard-example-{number}', current['checkpoint'], content, kind)
                before = owner.current()
                item = next(i for i in owner.inbox(before) if i['status'] == 'pending')
                review = owner.prepare('approve', item['proposal']['id'])
                owner.confirm(review['review']['checkpoint']['controlDigest'])
            current = bridge.read()
            bridge.propose('dashboard-example-review', current['checkpoint'], 'Example project: add a boundary test after the owner clarifies the retention timestamp.', 'observation')
            labels = {kit.read(state / 'private' / app / 'identity.json')['application']: name for app, name in [('claude', 'Claude sample identity'), ('codex', 'Codex sample identity')]}
            server = Dashboard(owner, assets, labels, 'demo', args.port)
            connection = {'url': server.origin + '/app#connect=' + server.pairing, 'mode': 'demo', 'state': str(state)}
            if args.connection_file:
                from recovery import exclusive
                exclusive(args.connection_file, json.dumps(connection).encode())
                print('Isolated sample dashboard at ' + server.origin + '; private connection saved.', flush=True)
            else:
                print('Synthetic local preview. No model or blockchain calls.\n' + connection['url'], flush=True)
            def stop(*_):
                raise SystemExit(0)
            signal.signal(signal.SIGTERM, stop)
            signal.signal(signal.SIGINT, stop)
            try:
                server.serve_forever()
            finally:
                server.server_close()
        finally:
            service.terminate()
            try:
                service.wait(timeout=5)
            except subprocess.TimeoutExpired:
                service.kill()
                service.wait()
            if args.connection_file:
                args.connection_file.unlink(missing_ok=True)


if __name__ == '__main__':
    main()

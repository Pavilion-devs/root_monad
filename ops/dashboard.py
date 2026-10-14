"""Serve the owner dashboard locally; opt into the existing hosted testnet project."""
import argparse
import importlib.util
import json
from pathlib import Path
import signal
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'python'))
from dashboard_server import Dashboard


def load_devkit():
    spec = importlib.util.spec_from_file_location('local_devkit', ROOT / 'devkit/memory.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--state', type=Path, help='Existing local developer-kit workspace (its service must be running)')
    source.add_argument('--hosted', action='store_true', help='Existing Monad testnet project; owner keys remain on this Mac')
    parser.add_argument('--port', type=int, default=0)
    parser.add_argument('--connection-file', type=Path, help='Write a private one-use browser connection link for local tooling')
    args = parser.parse_args()
    assets = ROOT / 'frontend/ui/dist'
    if not (assets / 'index.html').is_file():
        parser.error('Build the frontend first: npm --prefix frontend/ui run build')
    after_commit = None
    if args.hosted:
        from hosted import secrets, DIRECTORY, ORIGIN, public_state, save_report
        from owner_cli import Owner
        from eth_account import Account
        wallet, host = secrets()
        config = {**host['config'], 'serviceId': host['serviceId'], 'registry': {'rpcUrl': 'https://testnet-rpc.monad.xyz'}}
        if config['domain']['chainId'] != 10143:
            raise ValueError('TESTNET_REQUIRED')
        owner = Owner(ORIGIN, config, wallet['ownerKey'], bytes.fromhex(wallet['recoveryKey']), DIRECTORY / 'owner-cli')
        labels = {Account.from_key(wallet[k]).address.lower(): name for k, name in [('planningKey', 'Planning reference client'), ('codingKey', 'Coding reference client')]}
        for app, name in [('claude-code', 'Claude Code'), ('codex', 'Codex')]:
            profile = DIRECTORY / app / 'profile.json'
            if profile.is_file():
                labels[json.loads(profile.read_text())['application']] = name
        def after_commit(owner):
            current = owner.current()
            report = public_state()
            report.update(acceptedDigest=current['checkpoint']['controlDigest'], expectedRecords=current['records'])
            if 'backup' in report:
                report['backup']['current'] = False
            save_report(report)
        mode = 'hosted'
    else:
        kit = load_devkit()
        state = args.state.expanduser().resolve()
        owner = kit.owner(state)
        labels = {kit.read(state / 'private' / app / 'identity.json')['application']: name for app, name in [('claude', 'Claude integration'), ('codex', 'Codex integration')]}
        mode = 'local'
    server = Dashboard(owner, assets, labels, mode, args.port, after_commit)
    connection = {'url': server.origin + '/app#connect=' + server.pairing, 'mode': mode}
    if args.connection_file:
        from recovery import exclusive
        exclusive(args.connection_file, json.dumps(connection).encode())
        print('Dashboard ready at ' + server.origin + '; private connection link saved.', flush=True)
    else:
        print('Open this one-use link in your browser (valid for 20 minutes):\n' + connection['url'], flush=True)
    def stop(*_):
        raise SystemExit(0)
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        server.serve_forever()
    finally:
        server.server_close()
        if args.connection_file:
            args.connection_file.unlink(missing_ok=True)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        pass

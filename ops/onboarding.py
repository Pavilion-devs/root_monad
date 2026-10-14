#!/usr/bin/env python3
"""Start the isolated wallet-owned project service. Never loads an owner key."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import signal
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'python'))
from onboarding import Onboarding
from onboarding_server import WalletServer
from registry import registry_for
from recovery import exclusive


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state', type=Path, required=True, help='Separate persistent onboarding state directory')
    parser.add_argument('--port', type=int, default=0)
    args = parser.parse_args()
    os.umask(0o077)
    state = args.state.expanduser().resolve()
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    # Serialize initialization and ownership of the catalog; no existing owner
    # companion/hosted state is imported or modified.
    lock = (state/'service.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    assets = ROOT/'frontend/ui/dist'
    if not (assets/'index.html').is_file(): parser.error('Build frontend/ui first.')
    if not (state/'service.json').exists():
        deployment = json.loads((ROOT/'results/monad-deployment.json').read_text())
        settings = {'serviceId': '0x'+os.urandom(32).hex(), 'providerId': '0x'+os.urandom(32).hex(),
                    'domain': {'name': 'PortableMemory', 'version': '0', 'chainId': 10143,
                               'verifyingContract': deployment['contractAddress']},
                    'runtimeCodeHash': deployment['runtimeCodeHash'],
                    'rpcUrl': 'https://testnet-rpc.monad.xyz'}
        exclusive(state/'service.json', json.dumps(settings).encode())
    if not (state/'storage.key').exists():
        if (state/'catalog.sqlite').exists(): raise ValueError('STORAGE_KEY_MISSING')
        exclusive(state/'storage.key', os.urandom(32))
    settings = json.loads((state/'service.json').read_text())
    registry = registry_for(settings['domain'], {'rpcUrl': settings['rpcUrl']})
    hub = Onboarding(state, (state/'storage.key').read_bytes(), settings, registry)
    server = WalletServer(hub, assets, args.port)
    print(f'Wallet onboarding ready: {server.origin}/start', flush=True)
    def stop(*_): raise SystemExit(0)
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try: server.serve_forever()
    finally:
        server.server_close(); hub.close(); registry.close(); lock.close()


if __name__ == '__main__': main()

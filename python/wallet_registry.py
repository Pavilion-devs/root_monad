"""Durable intents submitted by an external wallet, never a service-held signer."""
from eth_abi import encode
from registry import raw, selector


class WalletRegistry:
    def __init__(self, registry):
        self.registry = registry

    def __getattr__(self, name):
        return getattr(self.registry, name)

    def transaction(self, envelope, owner):
        cp = envelope['checkpoint']
        value = (raw(cp['projectId']), int(cp['sequence']), raw(cp['previousDigest']),
                 raw(cp['controlDigest']), int(cp['deadline']))
        typ = '(bytes32,uint256,bytes32,bytes32,uint256)'
        if cp['sequence'] == '0':
            data = selector(f'create(address,bytes32,{typ},bytes)') + encode(
                ['address', 'bytes32', typ, 'bytes'],
                [owner, raw(envelope['control']['creationNonce']), value, raw(envelope['signature'])])
        else:
            data = selector(f'advance({typ},bytes)') + encode([typ, 'bytes'], [value, raw(envelope['signature'])])
        return {'kind': 'external_wallet', 'chainId': hex(self.chain_id),
                'to': self.address, 'value': '0x0', 'data': '0x' + data.hex()}

    def broadcast(self, transaction):
        if transaction.get('kind') != 'external_wallet':
            raise ValueError('INVALID_WALLET_INTENT')
        # Memory has already persisted this intent. Only the user's wallet submits it.

    def receipt(self, transaction):
        # A wallet-supplied hash is not authority. Recovery uses the exact finalized
        # registry event through accepted(), including canonical receipt checks.
        return None

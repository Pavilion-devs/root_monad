"""Isolated multi-project wallet onboarding. No wallet keys or relayer funding."""
import copy
import hmac
import os
import re
import sqlite3
import time
from pathlib import Path
from memory import Memory, ZERO, fields, require
from protocol import canonical, digest, project_id, recover, validate
from storage import Store
from wallet_registry import WalletRegistry

ID = re.compile(r'0x[0-9a-f]{64}')
ADDRESS = re.compile(r'0x[0-9a-f]{40}')


class Onboarding:
    def __init__(self, directory, key, settings, registry, max_projects=64, per_owner=3):
        self.directory = Path(directory)
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.key, self.settings = key, copy.deepcopy(settings)
        self.registry = WalletRegistry(registry)
        self.max_projects, self.per_owner = max_projects, per_owner
        self.db = sqlite3.connect(self.directory/'catalog.sqlite', isolation_level=None)
        os.chmod(self.directory/'catalog.sqlite', 0o600)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('PRAGMA synchronous=FULL')
        self.store = Store(self.db, key, settings['serviceId'])
        self.db.executescript('''CREATE TABLE IF NOT EXISTS projects
            (id TEXT PRIMARY KEY, owner TEXT NOT NULL, object TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS settings (object TEXT NOT NULL);''')
        try:
            pin = self.db.execute('SELECT object FROM settings').fetchone()
            if pin:
                require(self.store.get(pin[0]) == settings, 'CONFIG_MISMATCH')
            else:
                self.db.execute('INSERT INTO settings VALUES (?)', (self.store.put('settings', settings),))
        except Exception:
            self.db.close()
            raise

    def close(self):
        self.db.close()

    def config(self, owner, project):
        return {'projectId': project, 'owner': owner, 'domain': self.settings['domain']}

    def item(self, project):
        require(isinstance(project, str) and ID.fullmatch(project), 'INVALID_PROJECT')
        row = self.db.execute('SELECT object FROM projects WHERE id=?', (project,)).fetchone()
        require(row is not None, 'PROJECT_NOT_FOUND')
        return self.store.get(row[0])

    def memory(self, project):
        item = self.item(project)
        key = hmac.digest(self.key, b'portable-memory/wallet-project/' + project.encode(), 'sha256')
        return Memory(self.directory/f'{project}.sqlite', key,
                      self.config(item['owner'], project), item['genesis'], self.registry)

    def stage(self, payload):
        fields(payload, {'owner', 'genesis'})
        owner, genesis = payload['owner'], payload['genesis']
        require(isinstance(owner, str) and ADDRESS.fullmatch(owner), 'INVALID_OWNER')
        fields(genesis, {'checkpoint', 'control', 'snapshot', 'signature'})
        cp, c, snapshot = genesis['checkpoint'], genesis['control'], genesis['snapshot']
        validate('checkpoint', cp); validate('control', c); validate('snapshot', snapshot)
        project = project_id(owner, c['creationNonce'])
        require(cp['projectId'] == c['projectId'] == snapshot['projectId'] == project, 'WRONG_PROJECT')
        require(cp['sequence'] == c['sequence'] == '0' and cp['previousDigest'] == c['previousDigest'] == ZERO, 'INVALID_GENESIS')
        require(snapshot == {'formatVersion': '0', 'projectId': project, 'previousDigest': ZERO,
                             'records': [], 'sources': [], 'currentIds': [], 'resolutions': []}, 'INVALID_GENESIS')
        require(c['grants'] == [] and c['serviceId'] == self.settings['serviceId'] and
                c['storage'] == {'providerId': self.settings['providerId'], 'locator': f'project:{project}'}, 'INVALID_GENESIS')
        require(c['snapshotDigest'] == digest('snapshot', snapshot) and
                cp['controlDigest'] == digest('control', c), 'CONTENT_MISMATCH')
        require(recover(self.settings['domain'], 'Checkpoint', cp, genesis['signature']) == owner, 'WRONG_SIGNER')
        self.db.execute('BEGIN IMMEDIATE')
        try:
            row = self.db.execute('SELECT object FROM projects WHERE id=?', (project,)).fetchone()
            if row:
                require(self.store.get(row[0]) == payload, 'PROJECT_ALREADY_STAGED')
            else:
                now = int(time.time())
                require(now <= int(cp['deadline']) <= now + 900, 'EXPIRED')
                require(self.db.execute('SELECT count(*) FROM projects').fetchone()[0] < self.max_projects, 'CAPACITY_REACHED')
                require(self.db.execute('SELECT count(*) FROM projects WHERE owner=?', (owner,)).fetchone()[0] < self.per_owner, 'OWNER_PROJECT_LIMIT')
                self.db.execute('INSERT INTO projects VALUES (?,?,?)', (project, owner, self.store.put('project', payload)))
            self.db.execute('COMMIT')
        except Exception:
            self.db.execute('ROLLBACK')
            raise
        # No caller may submit a transaction until both catalog and Memory intent
        # are durable. If this fails, a retry reopens the exact same project.
        return self.status(project)

    def status(self, project):
        item = self.item(project)
        result = {'projectId': project, 'owner': item['owner'], 'domain': self.settings['domain'],
                  'serviceId': self.settings['serviceId'], 'genesis': item['genesis'],
                  'transaction': self.registry.transaction(item['genesis'], item['owner'])}
        try:
            memory = self.memory(project)
        except ValueError as error:
            if str(error) != 'COMMIT_PENDING':
                raise
            return {**result, 'status': 'pending', 'verified': False}
        try:
            head = memory.current()['checkpoint']
            return {**result, 'status': 'ready', 'verified': True,
                    'checkpointDigest': head['controlDigest'], 'sequence': head['sequence'],
                    'confirmation': self.registry.confirmation}
        finally:
            memory.close()

    def execute(self, project, wire):
        require(wire['body']['projectId'] == project, 'WRONG_PROJECT')
        memory = self.memory(project)
        try:
            return memory.execute(wire)
        finally:
            memory.close()

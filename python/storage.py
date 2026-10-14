"""Encrypted object store inside a caller-owned SQLite transaction."""
import hashlib
import os
import sqlite3
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.exceptions import InvalidTag
from protocol import canonical, strict_loads

class Store:
    def __init__(self, db, key, project):
        if len(key)!=32: raise ValueError('INVALID_KEY')
        self.db,self.key,self.project=db,key,project
        db.execute('CREATE TABLE IF NOT EXISTS objects (id TEXT PRIMARY KEY, nonce BLOB, ciphertext BLOB, wrap_nonce BLOB UNIQUE, wrapped_key BLOB)')

    def put(self, kind, body):
        plain=canonical(body)
        oid=kind+':'+hashlib.sha256(plain).hexdigest()
        if self.db.execute('SELECT 1 FROM objects WHERE id=?',(oid,)).fetchone():
            if self.get(oid)!=body: raise ValueError('INTEGRITY_FAILURE')
            return oid
        aad=canonical({'projectId':self.project,'formatVersion':'0','objectId':oid,'keyEpoch':'0'})
        key=os.urandom(32); nonce=os.urandom(12)
        while True:
            wrap_nonce=os.urandom(12)
            if not self.db.execute('SELECT 1 FROM objects WHERE wrap_nonce=?',(wrap_nonce,)).fetchone(): break
        self.db.execute('INSERT INTO objects VALUES (?,?,?,?,?)',(oid,nonce,AESGCM(key).encrypt(nonce,plain,aad),wrap_nonce,AESGCM(self.key).encrypt(wrap_nonce,key,aad)))
        return oid

    def get(self, oid):
        row=self.db.execute('SELECT nonce,ciphertext,wrap_nonce,wrapped_key FROM objects WHERE id=?',(oid,)).fetchone()
        if row is None: raise ValueError('CONTENT_UNAVAILABLE')
        aad=canonical({'projectId':self.project,'formatVersion':'0','objectId':oid,'keyEpoch':'0'})
        try:
            nonce,ciphertext,wrap_nonce,wrapped=row
            key=AESGCM(self.key).decrypt(wrap_nonce,wrapped,aad)
            plain=AESGCM(key).decrypt(nonce,ciphertext,aad)
            if hashlib.sha256(plain).hexdigest()!=oid.split(':',1)[1]: raise ValueError('INTEGRITY_FAILURE')
            return strict_loads(plain)
        except (InvalidTag,UnicodeError,TypeError): raise ValueError('INTEGRITY_FAILURE') from None

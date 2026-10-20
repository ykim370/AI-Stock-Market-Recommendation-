"""One-use approval inbox. Approval records intent only; there is no broker adapter."""
import hashlib
import json
import os
import secrets
import sqlite3
from pathlib import Path
from .recommendations import blockers

def connect():
    path = Path(os.getenv('APPROVAL_DB', 'private/approvals.sqlite'))
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute('CREATE TABLE IF NOT EXISTS proposals (token_hash TEXT PRIMARY KEY, card TEXT NOT NULL, status TEXT NOT NULL, decided_at TEXT)')
    conn.commit()
    return conn

def digest(token):
    return hashlib.sha256(token.encode()).hexdigest()

def create(card):
    token = secrets.token_urlsafe(32)
    with connect() as conn:
        conn.execute('INSERT INTO proposals VALUES (?, ?, ?, NULL)', (digest(token), json.dumps(card), 'PENDING'))
    return token

def get(token):
    with connect() as conn:
        row = conn.execute('SELECT * FROM proposals WHERE token_hash=?', (digest(token),)).fetchone()
    if not row:
        raise ValueError('Unknown recommendation')
    return json.loads(row['card']), row['status']

def decide(token, decision):
    if decision not in ('ACCEPT', 'REJECT'):
        raise ValueError('Invalid decision')
    with connect() as conn:
        conn.execute('BEGIN IMMEDIATE')
        row = conn.execute('SELECT * FROM proposals WHERE token_hash=?', (digest(token),)).fetchone()
        if not row or row['status'] != 'PENDING':
            raise ValueError('Recommendation missing or already decided')
        card = json.loads(row['card'])
        if decision == 'ACCEPT':
            reasons = blockers(card)
            if reasons:
                raise ValueError('; '.join(reasons))
        status = 'ACCEPTED_RESEARCH_ONLY' if decision == 'ACCEPT' else 'REJECTED'
        conn.execute("UPDATE proposals SET status=?, decided_at=strftime('%Y-%m-%dT%H:%M:%SZ','now') WHERE token_hash=?", (status, digest(token)))
    return status

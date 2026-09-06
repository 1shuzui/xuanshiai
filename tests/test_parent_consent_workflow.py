"""Service and HTTP consent workflow using an isolated SQLite persistence boundary.

MySQL row-lock concurrency is deliberately a separate deployment check; these
tests exercise the real queries, ownership checks, writes, replay and revocation.
"""
import asyncio
import sqlite3
from datetime import date, datetime

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.api.dependencies import CurrentUser, get_verified_user
from app.api.routes.parent import router
from app.db.session import get_db
from app.schemas.parent import ParentConsentAccept, ParentConsentCode
from app.services import parent


class Result:
    def __init__(self, cursor):
        self.lastrowid, self.rowcount = cursor.lastrowid, cursor.rowcount
        self.rows = []
        for row in cursor.fetchall():
            item = dict(row)
            for key, value in item.items():
                if value and key.endswith('_at'): item[key] = datetime.fromisoformat(value)
                elif value and key == 'birthday': item[key] = date.fromisoformat(value)
            self.rows.append(item)
    def mappings(self): return self
    def first(self): return self.rows[0] if self.rows else None
    def all(self): return self.rows
    def scalar(self): return next(iter(self.rows[0].values())) if self.rows else None


class Store:
    def __init__(self):
        self.connection = sqlite3.connect(':memory:', check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.connection.executescript('''
            CREATE TABLE users (id INTEGER PRIMARY KEY, nickname TEXT, status INTEGER, birthday TEXT);
            CREATE TABLE user_auth (user_id INTEGER PRIMARY KEY, realname_status INTEGER);
            CREATE TABLE parent_relationship (parent_id INTEGER PRIMARY KEY, child_id INTEGER,
                status TEXT DEFAULT 'pending', expires_at TEXT, consent_version TEXT DEFAULT 'parent-consent@1',
                invite_hash TEXT UNIQUE, invite_expires_at TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP);
            CREATE TABLE parent_action_event (id INTEGER PRIMARY KEY AUTOINCREMENT, actor_id INTEGER,
                parent_id INTEGER, child_id INTEGER, action TEXT, target_id INTEGER, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
            CREATE TABLE parent_preferences (user_id INTEGER PRIMARY KEY, message_notifications INTEGER DEFAULT 1, allow_parent_photo INTEGER DEFAULT 0);
            INSERT INTO users VALUES (101, '父母账号', 1, '1968-01-01'), (202, '成年子女', 1, '1995-01-01'), (303, '无关账号', 1, '1990-01-01');
            INSERT INTO user_auth VALUES (101,2), (202,2), (303,2);
        ''')
    async def execute(self, statement, params=None):
        sql = str(statement).replace(' FOR UPDATE', '').replace('INSERT IGNORE', 'INSERT OR IGNORE').replace('UTC_TIMESTAMP(6)', 'CURRENT_TIMESTAMP')
        values = {key: value.isoformat() if isinstance(value, (datetime, date)) else value for key, value in (params or {}).items()}
        return Result(self.connection.execute(sql, values))
    async def commit(self): self.connection.commit()
    async def rollback(self): self.connection.rollback()


def user(user_id): return CurrentUser(user_id, 1, 'test', 1, 2)


def test_invite_confirm_replay_revoke_and_new_invitation():
    async def workflow():
        store = Store()
        invitation = await parent.create_invitation(store, user(101))
        stored = store.connection.execute('SELECT invite_hash FROM parent_relationship').fetchone()[0]
        assert stored != invitation.code and len(stored) == 64
        preview = await parent.preview_invitation(store, user(202), ParentConsentCode(code=invitation.code))
        assert preview.parent_id == 101 and len(preview.scopes) == 5
        consent = ParentConsentAccept(code=invitation.code, confirmed=True)
        granted = await parent.accept_invitation(store, user(202), consent)
        repeated = await parent.accept_invitation(store, user(202), consent)
        assert repeated.expires_at == granted.expires_at
        assert (await parent.authorize_parent(store, user(101), 202))['child_id'] == 202
        with pytest.raises(HTTPException):
            await parent.accept_invitation(store, user(303), consent)
        with pytest.raises(HTTPException):
            await parent.revoke_relationship(store, user(303), 101)
        await parent.revoke_relationship(store, user(202), 101)
        with pytest.raises(HTTPException): await parent.authorize_parent(store, user(101), 202)
        with pytest.raises(HTTPException): await parent.accept_invitation(store, user(202), consent)
        assert store.connection.execute("SELECT COUNT(*) FROM parent_action_event WHERE action='consent.granted'").fetchone()[0] == 1
        new_invite = await parent.create_invitation(store, user(101))
        assert new_invite.code != invitation.code
        with pytest.raises(HTTPException):
            await parent.accept_invitation(store, user(303), ParentConsentAccept(code=new_invite.code, confirmed=True))
    asyncio.run(workflow())


def test_http_contract_authorizes_real_child_and_rejects_unconfirmed_body():
    store = Store()
    current = {'id': 101}
    app = FastAPI()
    app.include_router(router, prefix='/api/v1')
    app.dependency_overrides[get_verified_user] = lambda: user(current['id'])
    async def db(): yield store
    app.dependency_overrides[get_db] = db
    with TestClient(app) as client:
        invitation = client.post('/api/v1/parent/invitations')
        assert invitation.status_code == 201
        code = invitation.json()['code']
        current['id'] = 202
        assert client.post('/api/v1/parent/invitations/accept', json={'code': code, 'confirmed': False}).status_code == 422
        accepted = client.post('/api/v1/parent/invitations/accept', json={'code': code, 'confirmed': True, 'consentVersion': 'parent-consent@1'})
        assert accepted.status_code == 200 and accepted.json()['childId'] == 202
        current['id'] = 303
        assert client.get('/api/v1/parent/children/202/message/list').status_code == 403
        current['id'] = 202
        assert client.delete('/api/v1/parent/relationships/101').status_code == 200
        current['id'] = 101
        assert client.get('/api/v1/parent/children/202/message/list').status_code == 403

"""Opt-in real MySQL + ASGI HTTP integration; isolated runner owns the database.

JWT, sessions, dependencies, routes, response models, SQL and row locks are real.
Redis quota counters alone use the existing development fallback, exposed through
a read adapter so no machine Redis instance is touched.
"""
import asyncio
from datetime import timedelta
import os

import pytest

pytestmark = pytest.mark.skipif(os.getenv('RUN_PARENT_MYSQL') != '1', reason='Use scripts/verify_parent_mbti_mysql.py')


def test_parent_and_mbti_real_database_workflows(monkeypatch):
    from httpx import ASGITransport, AsyncClient
    from sqlalchemy import text
    from app.core import redis as quota_store
    from app.core.security import create_token
    from app.db.session import engine, session_factory
    from app.main import app
    from app.services import discovery, message

    class LocalQuotaReader:
        async def get(self, key):
            return quota_store._local_quota_counts.get(key, 0)
    monkeypatch.setattr(discovery, 'redis_client', LocalQuotaReader())

    async def run():
        async with session_factory() as db:
            constraints = (await db.execute(text("""SELECT COUNT(*) FROM information_schema.REFERENTIAL_CONSTRAINTS
                WHERE CONSTRAINT_SCHEMA = DATABASE() AND CONSTRAINT_NAME LIKE 'fk_parent_%'"""))).scalar()
            assert constraints == 6, 'new delegation tables must enforce user references in MySQL'
            for uid in [101, 202, 303, 404, 505]:
                await db.execute(text("""INSERT INTO users
                    (id, phone, nickname, avatar, gender, birthday, is_married, data_complete_rate)
                    VALUES (:id, :phone, :name, :avatar, :gender, '1996-05-01', 1, 100)"""),
                    dict(id=uid, phone=f'test-{uid}', name=f'测试{uid}', avatar=f'https://test.invalid/private-{uid}.webp', gender=1 if uid == 202 else 2))
                await db.execute(text('INSERT INTO user_auth (user_id, realname_status) VALUES (:id, 2)'), {'id': uid})
                await db.execute(text("""INSERT INTO user_profile
                    (user_id, height, education_level, occupation, self_intro, residence_province_code, residence_city_code)
                    VALUES (:id, 175, 3, '工程师', '认真沟通', '320000', '320100')"""), {'id': uid})
                await db.execute(text('INSERT INTO user_profile_completion (user_id, score) VALUES (:id, 100)'), {'id': uid})
                await db.execute(text("""INSERT INTO user_session
                    (id, user_id, refresh_token_hash, access_expire_at, refresh_expire_at)
                    VALUES (:id, :id, :hash, UTC_TIMESTAMP() + INTERVAL 1 HOUR, UTC_TIMESTAMP() + INTERVAL 1 DAY)"""),
                    {'id': uid, 'hash': str(uid).zfill(64)})
            await db.commit()

        async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
            async def request(uid, method, path, expected=200, **kwargs):
                response = await client.request(method, '/api/v1' + path, headers={'Authorization': 'Bearer ' +
                    create_token(uid, uid, 'access', timedelta(hours=1))}, **kwargs)
                assert response.status_code == expected, (method, path, response.status_code, response.text)
                return response.json()

            nickname = await request(202, 'PATCH', '/users/me/nickname', json={'nickname': '  本人新昵称  '})
            assert nickname['nickname'] == '本人新昵称' and nickname['user_id'] == 202
            own_profile = await request(202, 'GET', '/users/me/profile')
            assert own_profile['nickname'] == '本人新昵称'
            await request(202, 'PATCH', '/users/me/nickname', 422, json={'nickname': '   '})
            await request(202, 'PATCH', '/users/me/nickname', 422, json={'nickname': '甲' * 65})
            await request(202, 'PATCH', '/users/me/nickname', 422, json={'nickname': '越权', 'user_id': 303})
            context = await request(101, 'GET', '/parent/context')
            assert context['child'] is None
            child_path = '/parent/children/202'
            await request(101, 'GET', child_path + '/candidates', 403)
            invitation = await request(101, 'POST', '/parent/invitations', 201)
            preview = await request(202, 'POST', '/parent/invitations/preview', json={'code': invitation['code']})
            assert preview['parentId'] == 101 and len(preview['scopes']) == 5
            await request(202, 'POST', '/parent/invitations/accept', 422, json={'code': invitation['code'], 'confirmed': False})
            accepted = await request(202, 'POST', '/parent/invitations/accept', json={'code': invitation['code'], 'confirmed': True})
            repeated = await request(202, 'POST', '/parent/invitations/accept', json={'code': invitation['code'], 'confirmed': True})
            assert accepted['expiresAt'] == repeated['expiresAt']
            await request(404, 'GET', child_path + '/candidates', 403)
            recommendations = await request(101, 'GET', child_path + '/candidates')
            assert any(item['id'] == 303 for item in recommendations['items'])
            candidate = next(item for item in recommendations['items'] if item['id'] == 303)
            assert candidate['birthYear'] == 1996 and candidate['genderText'] == '女' and candidate['education'] == '本科'
            assert 'private-' not in str(recommendations)
            detail = await request(101, 'GET', child_path + '/candidates/303')
            assert not detail['canViewClearPhoto']
            await request(303, 'PATCH', '/parent/preferences', json={'allowParentPhoto': True})
            detail = await request(101, 'GET', child_path + '/candidates/303')
            assert detail['canViewClearPhoto'] and 'private-303' in detail['clearAvatar']
            await request(101, 'PUT', child_path + '/likes/303', json={'liked': True})
            liked = await request(101, 'GET', child_path + '/candidates?liked=true')
            assert [item['id'] for item in liked['items']] == [303]
            assert liked['items'][0]['job'] == '工程师'
            assert 'private-' not in str(liked)
            permission = await request(101, 'GET', child_path + '/message/chat/permission?userId=303')
            assert not permission['canChat']
            command = {'userId': 303, 'type': 'text', 'content': '家人协助沟通', 'clientMessageId': 'x' * 128}
            await request(101, 'POST', child_path + '/message/send', 403, json=command)
            # Same request in parallel must allocate one application and debit one quota.
            applies = await asyncio.gather(*[request(101, 'POST', child_path + '/applications/303', json={'note': '认真了解'}) for _ in range(2)])
            assert applies[0]['applicationId'] == applies[1]['applicationId']
            assert all(item['remainingApplications'] == 2 for item in applies)
            application_id = applies[0]['applicationId']
            outgoing = await request(101, 'GET', child_path + '/message/applications?direction=outgoing')
            assert any(item['id'] == application_id for item in outgoing['list'])
            incoming = await request(303, 'GET', '/message/applications')
            assert any(item['id'] == application_id for item in incoming['list'])
            handled = await request(303, 'POST', '/message/application/handle', json={'applicationId': application_id, 'action': 'accept', 'clientCommandId': 'accept-303'})
            assert handled['canChat']
            sent = await request(101, 'POST', child_path + '/message/send', json=command)
            replay = await request(101, 'POST', child_path + '/message/send', json=command)
            assert sent['messageId'] == replay['messageId']
            assert not sent['deduplicated'] and replay['deduplicated']
            assert sent['message']['clientMessageId'] == command['clientMessageId']
            chat = await request(303, 'GET', '/message/chat?userId=202')
            assert len(chat) == 1 and chat[0]['content'] == command['content']
            private_chat = await request(101, 'GET', child_path + '/message/chat?userId=303')
            assert 'private-' not in str(private_chat)
            await request(101, 'PATCH', '/parent/preferences', json={'messageNotifications': False})
            assert not (await request(101, 'GET', child_path + '/alerts'))['enabled']

            # Revoke exactly after idempotency commits its reservation. The second
            # authorization check must reject the send before any chat row is added.
            reserved, resume = asyncio.Event(), asyncio.Event()
            original_reserve = message.reserve_or_replay
            async def paused_reserve(*args, **kwargs):
                result = await original_reserve(*args, **kwargs)
                reserved.set()
                await asyncio.wait_for(resume.wait(), 5)
                return result
            monkeypatch.setattr(message, 'reserve_or_replay', paused_reserve)
            late = asyncio.create_task(request(101, 'POST', child_path + '/message/send', 403,
                json={**command, 'clientMessageId': 'after-revoke', 'content': 'must not persist'}))
            await asyncio.wait_for(reserved.wait(), 5)
            await request(202, 'DELETE', '/parent/relationships/101')
            resume.set()
            await late
            monkeypatch.setattr(message, 'reserve_or_replay', original_reserve)
            chat = await request(303, 'GET', '/message/chat?userId=202')
            assert len(chat) == 1
            await request(101, 'GET', child_path + '/message/list', 403)
            report = await request(101, 'POST', child_path + '/reports/303', json={'reasonId': 'other', 'detail': '合成安全测试'})
            assert report['id'] > 0

            # Regrant, block, and expire: all read and write surfaces share the gate.
            invitation = await request(101, 'POST', '/parent/invitations', 201)
            await request(202, 'POST', '/parent/invitations/accept', json={'code': invitation['code'], 'confirmed': True})
            await request(101, 'PUT', child_path + '/blocks/303')
            assert not (await request(101, 'GET', child_path + '/message/chat/permission?userId=303'))['canChat']
            await request(101, 'GET', child_path + '/candidates/303', 403)
            assert not (await request(101, 'GET', child_path + '/candidates?liked=true'))['items']
            await request(101, 'PUT', child_path, 422, json={'displayName': '子女', 'birthYear': 1990, 'city': '南京'})
            edited = await request(101, 'PUT', child_path, json={'displayName': '子女', 'birthYear': 1996, 'city': '南京', 'job': '设计师'})
            assert edited['displayName'] == '子女' and edited['birthYear'] == 1996
            async with session_factory() as db:
                await db.execute(text('UPDATE parent_relationship SET expires_at = UTC_TIMESTAMP() - INTERVAL 1 SECOND WHERE parent_id=101'))
                await db.commit()
            await request(101, 'GET', child_path + '/alerts', 403)

            # Concurrent draft creation, persisted camel-case result, explicit profile
            # confirmation, ownership, and a repeat submission all use real routes.
            async def start():
                return await client.post('/api/v1/emotion-lab/sessions', headers={'Authorization': 'Bearer ' + create_token(505, 505, 'access', timedelta(hours=1))}, json={'assessmentId': 'mbti-core'})
            sessions = await asyncio.gather(start(), start())
            assert sorted(item.status_code for item in sessions) == [200, 409]
            session = next(item.json() for item in sessions if item.status_code == 200)
            path = '/emotion-lab/sessions/' + session['id']
            answers = [{'questionId': qid, 'value': 4} for qid in session['questionIds']]
            await request(404, 'PUT', path + '/answers', 404, json={'answers': answers[:1]})
            submitted = await request(505, 'POST', path + '/submit', json={'answers': answers})
            repeated = await request(505, 'POST', path + '/submit', json={'answers': answers})
            assert submitted['result'] == repeated['result']
            summary = await request(505, 'GET', '/emotion-lab/summary')
            assert summary['activeSession']['result'] == submitted['result']
            source = await request(505, 'PUT', '/emotion-lab/profile-source', json={'source': 'assessment', 'mbtiType': submitted['result']['mbtiType'], 'resultId': submitted['result']['id'], 'confirmed': True})
            async with session_factory() as db:
                assert (await db.execute(text('SELECT mbti FROM user_profile WHERE user_id=505'))).scalar() == source['mbtiType']
                assert (await db.execute(text('SELECT COUNT(*) FROM parent_action_event'))).scalar() >= 8
    async def isolated_workflow():
        try:
            await run()
        finally:
            await quota_store.redis_client.aclose()
            await engine.dispose()
    asyncio.run(isolated_workflow())

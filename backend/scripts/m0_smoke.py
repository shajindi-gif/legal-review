"""M0 smoke test on production: simulate /sms/send via direct DB insert,
then walk /register/phone -> /me -> /login -> /quota -> /refresh.
Also verify Demo user still works.
"""
import asyncio
import sys
import json
import urllib.request
import urllib.error
from datetime import datetime, UTC, timedelta
from uuid import UUID

sys.path.insert(0, "/app")

from sqlalchemy import select, delete
import bcrypt

from app.db.session import get_session_factory
from app.models.identity import VerificationCode
from app.models.user import User

API = "http://localhost:8000"
PHONE = "13911112222"
TARGET = "+8613911112222"
CODE = "102030"
PASSWORD = "Test@2024abc"


def http(method, path, body=None, token=None):
    headers = {"content-type": "application/json"}
    if token:
        headers["authorization"] = "Bearer " + token
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(API + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, {"raw": raw[:300].decode(errors="replace")}


async def with_session(fn):
    factory = get_session_factory()
    async with factory() as s:
        return await fn(s)


async def main():
    print("=== M0 smoke: clean state ===")

    async def clean(s):
        # 先清掉上次 smoke 留下的 user (会被 audit_records 外键引用)
        from sqlalchemy import text
        u = await s.scalar(select(User).where(User.phone.in_([PHONE, TARGET])))
        if u is not None:
            await s.execute(text("DELETE FROM audit_records WHERE actor_id = :uid"), {"uid": u.id})
            await s.execute(text("DELETE FROM user_login_events WHERE user_id = :uid"), {"uid": u.id})
            await s.execute(text("DELETE FROM refresh_tokens WHERE user_id = :uid"), {"uid": u.id})
            await s.execute(text("DELETE FROM user_plans WHERE user_id = :uid"), {"uid": u.id})
            await s.execute(text("DELETE FROM user_events WHERE user_id = :uid"), {"uid": u.id})
            await s.execute(text("DELETE FROM user_acquisition_sources WHERE user_id = :uid"), {"uid": u.id})
            await s.execute(delete(User).where(User.id == u.id))
            await s.execute(text("DELETE FROM organizations WHERE id = :oid"), {"oid": u.organization_id})
        await s.execute(delete(VerificationCode).where(VerificationCode.target == TARGET))
        await s.commit()
        code_hash = bcrypt.hashpw(CODE.encode(), bcrypt.gensalt(rounds=10)).decode()
        now = datetime.now(UTC).replace(tzinfo=None)
        row = VerificationCode(
            target=TARGET,
            channel="sms",
            purpose="register",
            code_hash=code_hash,
            expires_at=now + timedelta(minutes=5),
            attempt_count=0,
            max_attempts=5,
            used_at=None,
            ip_address="127.0.0.1",
            user_agent="m0-smoke",
        )
        s.add(row)
        await s.commit()
        print("inserted verification_codes row for target=" + TARGET)

    await with_session(clean)

    print("\n=== 1. POST /api/v1/auth/register/phone (new user) ===")
    status, body = http("POST", "/api/v1/auth/register/phone", {
        "phone": PHONE,
        "code": CODE,
        "password": PASSWORD,
    })
    print("  ->", status, json.dumps(body, ensure_ascii=False)[:400])
    assert status == 201, "register failed: " + str(status) + " " + str(body)
    access = body["access_token"]
    refresh = body["refresh_token"]
    user_id = body["user_id"]
    print("  user_id =", user_id)

    print("\n=== 2. GET /api/v1/auth/me ===")
    status, me = http("GET", "/api/v1/auth/me", token=access)
    print("  ->", status, json.dumps(me, ensure_ascii=False)[:400])
    assert status == 200
    assert me.get("id") == user_id
    assert me.get("role") == "submitter"
    assert me.get("plan_tier") == "free"
    assert me.get("quota_daily") == 3

    print("\n=== 3. POST /api/v1/auth/login/phone (new user) ===")
    status, login_body = http("POST", "/api/v1/auth/login/phone", {
        "phone": PHONE,
        "password": PASSWORD,
    })
    print("  ->", status, json.dumps(login_body, ensure_ascii=False)[:400])
    assert status == 200
    assert "access_token" in login_body
    access2 = login_body["access_token"]

    print("\n=== 4. GET /api/v1/auth/quota (LegalAI core) ===")
    status, quota = http("GET", "/api/v1/auth/quota", token=access2)
    print("  ->", status, json.dumps(quota, ensure_ascii=False)[:400])
    assert status == 200

    print("\n=== 5. POST /api/v1/auth/refresh ===")
    status, ref = http("POST", "/api/v1/auth/refresh", {"refresh_token": refresh})
    print("  ->", status, json.dumps(ref, ensure_ascii=False)[:400])
    assert status == 200
    assert "access_token" in ref

    print("\n=== 6. User row / hash / field validation ===")

    async def check_user(s):
        u = await s.scalar(select(User).where(User.id == UUID(user_id)))
        assert u is not None
        h = u.password_hash
        print("  password_hash prefix:", h[:7], "length:", len(h))
        assert h.startswith("$argon2id$") or h.startswith("$2b$") or h.startswith("$2a$"), \
            "unexpected hash format: " + h[:20]
        assert u.phone_verified_at is not None
        assert u.status == "active"
        assert u.password_changed_at is not None
        assert u.agreed_terms_at is not None
        plan_id = getattr(u, "plan_id", None)
        print("  role=" + u.role, "status=" + u.status,
              "org_id=" + str(u.organization_id),
              "plan_id=" + str(plan_id))
        vc = await s.scalar(
            select(VerificationCode)
            .where(VerificationCode.target == TARGET)
            .order_by(VerificationCode.created_at.desc())
            .limit(1)
        )
        assert vc is not None and vc.used_at is not None
        print("  verification_codes.used_at =", vc.used_at.isoformat())

    await with_session(check_user)

    print("\n=== 7. Demo user regression: demo@shajindi.com ===")
    status, demo_login = http("POST", "/api/v1/auth/login", {
        "email": "demo@shajindi.com",
        "password": "Demo@2024",
    })
    print("  ->", status, json.dumps(demo_login, ensure_ascii=False)[:400])
    assert status == 200, "demo login regressed: " + str(status) + " " + str(demo_login)
    assert "access_token" in demo_login
    status, demo_me = http("GET", "/api/v1/auth/me", token=demo_login["access_token"])
    print("  /me ->", status, json.dumps(demo_me, ensure_ascii=False)[:200])
    assert status == 200
    assert demo_me.get("email") == "demo@shajindi.com"

    print("\n*** ALL ASSERTIONS PASSED ***")


asyncio.run(main())

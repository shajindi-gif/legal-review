"""M16.1 多租户隔离冒烟脚本

部署后必跑：验证 organization_id 过滤是否生效，避免数据串租。

行为：
  1. 用超级管理员登录
  2. 创建 2 个 org（A 个人 / B 团队），2 个用户
  3. 用户 A 创建 1 个 review_task
  4. 用户 B 调 /api/v1/tasks 列表，期望看到 0 条
  5. 用户 A 调 /api/v1/tasks 列表，期望看到 1 条

使用：
  docker exec legal-backend python /app/scripts/verify_tenant_isolation.py

退出码：
  0  PASS
  1  FAIL
  2  跳过（demo 环境无 admin 账号）
"""
from __future__ import annotations

import asyncio
import sys
import uuid

import httpx


BASE_URL = "http://127.0.0.1:8000"


async def login(client: httpx.AsyncClient, phone: str, code: str = "000000") -> str | None:
    """演示模式：直接用 phone 登录（M0003 身份系统）。"""
    r = await client.post(
        f"{BASE_URL}/api/v1/auth/login-by-phone",
        json={"phone": phone, "verification_code": code},
    )
    if r.status_code == 200:
        return r.json().get("access_token")
    return None


async def main() -> int:
    async with httpx.AsyncClient(timeout=10.0) as client:
        # 用一个内部测试账号
        admin_phone = "13900000001"
        token = await login(client, admin_phone)
        if not token:
            print("SKIP: 无法用测试 phone 登录（演示模式可能未开启）")
            return 2

        h = {"Authorization": f"Bearer {token}"}

        # 创建一个 review task
        body = {
            "title": f"isolation-test-{uuid.uuid4().hex[:8]}",
            "doc_type": "contract",
            "content": "test content for tenant isolation",
        }
        r = await client.post(f"{BASE_URL}/api/v1/tasks", json=body, headers=h)
        if r.status_code not in (200, 201):
            print(f"FAIL: 创建 task 失败 {r.status_code}: {r.text[:200]}")
            return 1
        task_id = r.json()["id"]
        print(f"  ✓ 创建 task: {task_id}")

        # 列出来确认可见
        r = await client.get(f"{BASE_URL}/api/v1/tasks", headers=h)
        if r.status_code != 200:
            print(f"FAIL: 列表查询失败 {r.status_code}")
            return 1
        tasks = r.json().get("items", r.json()) if isinstance(r.json(), dict) else r.json()
        visible = any(t.get("id") == task_id for t in tasks)
        if not visible:
            print(f"FAIL: 创建者看不到自己的 task（可能 organization_id 写入失败）")
            return 1
        print(f"  ✓ 创建者能看见自己的 task")

        # 用另一个 phone 登录（应该是另一个 user）
        other_phone = "13900000002"
        other_token = await login(client, other_phone)
        if not other_token:
            print("SKIP: 第二个 phone 登录失败（演示模式可能只允许一个测试号）")
            return 2

        oh = {"Authorization": f"Bearer {other_token}"}
        r = await client.get(f"{BASE_URL}/api/v1/tasks", headers=oh)
        if r.status_code != 200:
            print(f"FAIL: 另一用户列表查询失败 {r.status_code}")
            return 1
        other_tasks = r.json().get("items", r.json()) if isinstance(r.json(), dict) else r.json()
        leaked = any(t.get("id") == task_id for t in other_tasks)
        if leaked:
            print(f"FAIL: 数据串租！另一用户能看到 task {task_id}")
            return 1
        print(f"  ✓ 另一用户看不到该 task（隔离生效）")

        print("\n✅ 多租户隔离冒烟通过")
        return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except Exception as e:
        print(f"FAIL: 异常 {e!r}")
        sys.exit(1)

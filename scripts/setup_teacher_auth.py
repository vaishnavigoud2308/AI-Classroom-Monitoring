"""
One-time teacher auth setup (run from project root).

Requires SUPABASE_SERVICE_ROLE_KEY in environment or .env
(never put this key in frontend code).

What it does:
1) Confirms the teacher Auth user email
2) Upserts public.teachers linked via auth_user_id (column must already exist)
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv
from supabase import create_client

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "")
SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

TEACHER_EMAIL = os.environ.get("TEACHER_EMAIL", "vaishnavigoud2308@gmail.com")
TEACHER_NAME = os.environ.get("TEACHER_NAME", "Vaishnavi")
AUTH_USER_ID = os.environ.get("TEACHER_AUTH_USER_ID", "e4564511-ab3a-46ee-99c3-12689bda219e")


def fail(msg: str) -> None:
    print(f"ERROR: {msg}")
    sys.exit(1)


def confirm_email() -> None:
    if not SERVICE_ROLE_KEY:
        fail(
            "SUPABASE_SERVICE_ROLE_KEY missing. "
            "Add it to root .env temporarily, or confirm the user in "
            "Supabase Dashboard → Authentication → Users."
        )
    resp = httpx.put(
        f"{SUPABASE_URL}/auth/v1/admin/users/{AUTH_USER_ID}",
        headers={
            "apikey": SERVICE_ROLE_KEY,
            "Authorization": f"Bearer {SERVICE_ROLE_KEY}",
            "Content-Type": "application/json",
        },
        json={"email_confirm": True},
        timeout=30,
    )
    if resp.status_code >= 400:
        fail(f"Could not confirm email ({resp.status_code}): {resp.text}")
    print("OK: Auth email confirmed")


def link_teacher_row() -> None:
    # Prefer service role for upsert; fall back to anon if column exists and RLS is off
    key = SERVICE_ROLE_KEY or ANON_KEY
    if not key:
        fail("No Supabase key available")
    client = create_client(SUPABASE_URL, key)

    existing = (
        client.table("teachers")
        .select("*")
        .eq("email", TEACHER_EMAIL)
        .limit(1)
        .execute()
    )
    payload = {
        "name": TEACHER_NAME,
        "email": TEACHER_EMAIL,
        "auth_user_id": AUTH_USER_ID,
    }
    if existing.data:
        client.table("teachers").update(
            {"auth_user_id": AUTH_USER_ID, "name": TEACHER_NAME}
        ).eq("email", TEACHER_EMAIL).execute()
        print(f"OK: Linked existing teacher row for {TEACHER_EMAIL}")
    else:
        client.table("teachers").insert(payload).execute()
        print(f"OK: Created teacher row for {TEACHER_EMAIL}")


def main() -> None:
    if not SUPABASE_URL:
        fail("SUPABASE_URL missing in .env")
    confirm_email()
    try:
        link_teacher_row()
    except Exception as e:
        print(
            "WARN: Could not link teachers.auth_user_id yet.\n"
            "      Run the approved SQL migration in Supabase SQL Editor first.\n"
            f"      Details: {e}"
        )
        sys.exit(2)
    print("DONE: Teacher auth setup complete")


if __name__ == "__main__":
    main()

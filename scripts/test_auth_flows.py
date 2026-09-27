"""
Auth smoke tests against live Supabase Auth (no UI).
Run: .venv/Scripts/python.exe scripts/test_auth_flows.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from supabase import create_client

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

URL = os.environ["SUPABASE_URL"]
KEY = os.environ["SUPABASE_ANON_KEY"]
EMAIL = os.environ.get("TEACHER_EMAIL", "vaishnavigoud2308@gmail.com")
PASSWORD = os.environ.get("TEACHER_PASSWORD")
if not PASSWORD:
    print("Set TEACHER_PASSWORD in the environment to run this test.")
    sys.exit(1)


def main() -> None:
    c = create_client(URL, KEY)
    passed = 0

    # 1) invalid login
    try:
        c.auth.sign_in_with_password({"email": EMAIL, "password": "wrong-password-xxx"})
        print("FAIL invalid login: unexpectedly succeeded")
        sys.exit(1)
    except Exception as e:
        print(f"PASS invalid login blocked ({e})")
        passed += 1

    # 2) valid login
    try:
        res = c.auth.sign_in_with_password({"email": EMAIL, "password": PASSWORD})
        assert res.session and res.user
        print(f"PASS valid login ({res.user.email})")
        access = res.session.access_token
        passed += 1
    except Exception as e:
        print(f"FAIL valid login: {e}")
        print(
            "\nIf you see 'Email not confirmed':\n"
            "  Supabase Dashboard > Authentication > Users > open the user > Confirm email\n"
            "Or set Confirm email = OFF under Authentication > Providers > Email, then re-test."
        )
        sys.exit(1)

    # 3) session restore (get_user with token)
    try:
        user_res = c.auth.get_user(access)
        assert user_res.user and user_res.user.email == EMAIL
        print("PASS session token restores user")
        passed += 1
    except Exception as e:
        print(f"FAIL session restore: {e}")
        sys.exit(1)

    # 4) logout
    try:
        c.auth.sign_out()
        print("PASS logout")
        passed += 1
    except Exception as e:
        print(f"FAIL logout: {e}")
        sys.exit(1)

    # 5) after logout, password login still works (account intact)
    try:
        res2 = c.auth.sign_in_with_password({"email": EMAIL, "password": PASSWORD})
        assert res2.session
        c.auth.sign_out()
        print("PASS re-login after logout")
        passed += 1
    except Exception as e:
        print(f"FAIL re-login after logout: {e}")
        sys.exit(1)

    print(f"\nAll API auth checks passed ({passed}/5).")
    print("Also verify in the browser: refresh while logged in, and dashboard blocked when logged out.")


if __name__ == "__main__":
    main()

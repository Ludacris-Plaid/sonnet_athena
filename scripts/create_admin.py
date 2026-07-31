"""
Create the first platform admin: creates a real Supabase Auth user (via the
service role key, which can create users directly without email
confirmation) and the matching RealtyAI profile row with is_admin=True.

    python scripts/create_admin.py you@company.com "Your Name" "your-password"

Requires SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in .env.
"""
import sys

from supabase import create_client

from app.core.config import settings
from app.core.database import SessionLocal, init_db
from app.models.org import Organization, User, PlanTier


def main(email: str, full_name: str, password: str):
    if not settings.SUPABASE_URL or not settings.SUPABASE_SERVICE_ROLE_KEY:
        print("SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY must be set in .env")
        sys.exit(1)

    init_db()

    # Service-role client can create a confirmed user directly — no email
    # verification loop needed for this one-time bootstrap step.
    admin_client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
    auth_response = admin_client.auth.admin.create_user(
        {"email": email, "password": password, "email_confirm": True}
    )
    supabase_user_id = auth_response.user.id

    db = SessionLocal()
    org = Organization(name="RealtyAI Platform Admin", plan_tier=PlanTier.HEAVY)
    db.add(org)
    db.commit()
    db.refresh(org)

    admin = User(id=supabase_user_id, org_id=org.id, email=email, full_name=full_name, is_admin=True)
    db.add(admin)
    db.commit()

    print(f"Admin user created: {email} (supabase_user_id={supabase_user_id}, org_id={org.id})")
    print("Log in from the frontend using this email/password — Supabase Auth handles the session.")
    db.close()


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Usage: python scripts/create_admin.py <email> <full_name> <password>")
        sys.exit(1)
    main(sys.argv[1], sys.argv[2], sys.argv[3])

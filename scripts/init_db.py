"""
Run once to create all tables:
    python scripts/init_db.py
"""
from app.core.database import init_db

if __name__ == "__main__":
    init_db()
    print("Database initialized.")

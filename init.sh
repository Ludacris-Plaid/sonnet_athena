#!/usr/bin/env bash
set -e

echo "=== RealtyAI setup ==="

# 1. Python virtual environment
python3 -m venv venv
source venv/bin/activate

# 2. Install dependencies
pip install --upgrade pip
pip install -r requirements.txt

# 3. Env file
if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created .env from .env.example — fill in DEEPSEEK_API_KEY before running."
fi

# 5. Data dir for vector index / local voice cache
mkdir -p data

# 6. Postgres: if DATABASE_URL in .env still points at localhost, spin up
# the local docker-compose db. If you've pointed it at Supabase already,
# skip this — comment out the next 5 lines.
if grep -q "localhost:5432" .env; then
  docker compose up -d db
  echo "Waiting for local Postgres to be ready..."
  until docker exec realtyai_db pg_isready -U realtyai > /dev/null 2>&1; do
    sleep 1
  done
fi

# 7. Initialize tables (works against local Postgres or Supabase — whatever
# DATABASE_URL points to)
python scripts/init_db.py

echo ""
echo "=== Setup complete ==="
echo "Next steps:"
echo "  1. Edit .env: DEEPSEEK_API_KEY, and SUPABASE_URL/SUPABASE_ANON_KEY/SUPABASE_SERVICE_ROLE_KEY"
echo "  2. Run scripts/supabase_rls.sql in the Supabase SQL editor (optional but recommended)"
echo "  3. source venv/bin/activate"
echo "  4. uvicorn app.main:app --reload"
echo "  5. python scripts/create_admin.py you@company.com \"Your Name\" \"password\""
echo "  6. Visit http://localhost:8000/docs"

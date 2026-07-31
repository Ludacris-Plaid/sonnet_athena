"""
Ad-hoc "add missing columns" migration helper — this project doesn't use
Alembic, so when a model gains a new field (which has happened often across
this build), the deployed Postgres database needs to catch up. This walks
every model's columns and adds any that don't exist yet, safely
(IF NOT EXISTS), rather than requiring a full migration framework.

Run this any time you pull new code before restarting the server — it's
safe to run repeatedly (a no-op for columns that already exist).

    python scripts/migrate_columns.py

Originally found in a version of the deployed server code and adapted
here: fixed the hardcoded absolute path (`/opt/realtyai`, `/home/dysthemix/...`)
that would only work on one specific machine, and updated the model import
list to match every model file that currently exists in this project.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, inspect, text

from app.core.config import settings
from app.core.database import Base

# Import every model module so Base.metadata knows about all of them —
# keep this list in sync with app/core/database.py's init_db() imports.
import app.models.org
import app.models.client
import app.models.property
import app.models.neighborhood
import app.models.comparable
import app.models.message
import app.models.trust
import app.models.price_history
import app.models.alert
import app.models.document
import app.models.crm_connection
import app.models.admin_audit
import app.models.calendar_event
import app.models.email_connection
import app.models.conversation
import app.models.platform_setting

engine = create_engine(settings.DATABASE_URL.replace("+psycopg2", "").replace("+asyncpg", ""))
insp = inspect(engine)

added = 0
for table_name, table in Base.metadata.tables.items():
    if not insp.has_table(table_name):
        print(f"  (skipping {table_name} — table doesn't exist yet; run scripts/init_db.py first)")
        continue

    existing = {c["name"] for c in insp.get_columns(table_name)}
    for col in table.columns:
        if col.name in existing:
            continue

        col_type = col.type.compile(engine.dialect)
        nullable = "" if col.nullable else " NOT NULL"
        default = ""
        if col.default is not None and str(col.default.arg) not in ("", "None"):
            dv = str(col.default.arg)
            if dv == "False":
                dv = "false"
            elif dv == "True":
                dv = "true"
            default = f" DEFAULT '{dv}'" if col.type.python_type is str else f" DEFAULT {dv}"
        elif not col.nullable:
            if col.type.python_type is bool:
                default = " DEFAULT false"
            elif col.type.python_type is str:
                default = " DEFAULT ''"
            elif col.type.python_type is int:
                default = " DEFAULT 0"

        sql = f"ALTER TABLE {table_name} ADD COLUMN IF NOT EXISTS {col.name} {col_type}{nullable}{default}"
        try:
            with engine.begin() as conn:
                conn.execute(text(sql))
            print(f"  + {table_name}.{col.name} {col_type}")
            added += 1
        except Exception as e:  # noqa: BLE001 — report and keep going, one bad column shouldn't stop the rest
            print(f"  ! {table_name}.{col.name}: {e}")

print(f"Done. {added} column(s) added.")

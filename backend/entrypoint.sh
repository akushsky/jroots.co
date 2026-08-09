#!/bin/sh
set -e

echo "Running database migrations..."

# Fresh DBs created from db/init.sql already include columns/indexes that
# early Alembic revisions add. Detect that and stamp past those revisions
# so `alembic upgrade head` only applies the rest. Existing prod DBs that
# already have alembic_version are left alone.
python -c "
import asyncio, asyncpg, os, subprocess

async def decide_stamp():
    url = os.environ['DATABASE_URL'].replace('+asyncpg', '').replace('postgresql://', 'postgres://')
    conn = await asyncpg.connect(url)
    try:
        has_alembic = await conn.fetchval(\"\"\"
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'alembic_version'
            )
        \"\"\")
        if has_alembic:
            return None
        has_file_path = await conn.fetchval(\"\"\"
            SELECT EXISTS (
                SELECT FROM information_schema.columns
                WHERE table_name = 'images' AND column_name = 'image_file_path'
            )
        \"\"\")
        # init.sql ships with image file paths and no username unique —
        # equivalent to schema after 003_drop_username_unique.
        return '003_drop_username_unique' if has_file_path else '001_baseline'
    finally:
        await conn.close()

stamp = asyncio.run(decide_stamp())
if stamp:
    print(f'First Alembic run — stamping {stamp}...')
    subprocess.run(['alembic', 'stamp', stamp], check=True)
else:
    print('alembic_version table exists, skipping stamp.')
"

alembic upgrade head

echo "Migrations complete."

if [ -n "${BOOTSTRAP_ADMIN_EMAIL:-}" ]; then
  echo "Ensuring bootstrap admin (${BOOTSTRAP_ADMIN_EMAIL})..."
  python -m app.bootstrap_admin
fi

echo "Starting server..."
exec "$@"

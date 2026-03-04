#!/bin/sh
set -e

echo "Running database migrations..."

# If alembic_version table doesn't exist, this is the first deploy with Alembic.
# Stamp baseline so Alembic knows production is at the pre-migration state.
python -c "
import asyncio, asyncpg, os

async def check():
    url = os.environ['DATABASE_URL'].replace('+asyncpg', '').replace('postgresql://', 'postgres://')
    conn = await asyncpg.connect(url)
    row = await conn.fetchval(\"\"\"
        SELECT EXISTS (
            SELECT FROM information_schema.tables
            WHERE table_name = 'alembic_version'
        )
    \"\"\")
    await conn.close()
    return row

exists = asyncio.run(check())
if not exists:
    print('First Alembic run — stamping baseline...')
    import subprocess
    subprocess.run(['alembic', 'stamp', '001_baseline'], check=True)
else:
    print('alembic_version table exists, skipping stamp.')
"

alembic upgrade head

echo "Migrations complete. Starting server..."
exec "$@"

# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

JRoots.co — Jewish genealogy archive search platform. Aggregates archival materials (Ukrainian, Belarusian, Lithuanian archives) into a single searchable database with full-text and fuzzy search.

## Commands

### Backend (from `backend/`)
```bash
poetry install                                    # Install deps
poetry run uvicorn app.main:app --reload          # Dev server (port 8000)
poetry run ruff check app/ tests/                 # Lint
poetry run pytest tests/ -v                       # All tests
poetry run pytest tests/test_api_search.py -v     # Single test file
poetry run pytest tests/ -v --cov=app --cov-report=term-missing  # With coverage (60% min)
```

Tests use SQLite via aiosqlite (env: `DATABASE_URL=sqlite+aiosqlite:///./test.db`). CI sets `ENVIRONMENT=test`. See CI env vars in `.github/workflows/ci.yml` for the full set needed.

### Frontend (from `frontend/`)
```bash
npm ci                    # Install deps
npm run dev               # Dev server (port 5173, proxies /api → localhost:8000)
npm run lint              # ESLint
npx tsc --noEmit          # Type check
npm test                  # Vitest (run once)
npm run test:watch        # Vitest (watch mode)
npm run build             # tsc + vite build
```

### E2E (from `e2e/`)
```bash
npm ci && npx playwright install --with-deps chromium
npx playwright test                 # Headless
npx playwright test --headed        # With browser
```
Requires the full stack running via `docker-compose.ci.yml`.

### Database
```bash
cd db && docker compose up -d       # Local PostgreSQL 16
```

### CLI (from `cli/`)
```bash
pip install -e .          # Installs as `jroots` command
jroots login admin        # Get JWT token
jroots status             # Check API
jroots validate --images-csv images.csv --objects-csv objects.csv
jroots upload-all --images-csv images.csv --objects-csv objects.csv
```

### Pre-commit
Configured in `.pre-commit-config.yaml` — runs ruff, pytest, eslint, tsc, frontend build, and npm audit on commit. Uses the root `.venv` (see `run-tests.sh`).

## Architecture

**Monorepo** with four packages: `backend/`, `frontend/`, `cli/`, `db/`.

### Backend (FastAPI, async)
- `app/main.py` — App factory with lifespan, CORS, middleware
- `app/config.py` — Pydantic Settings (all env vars)
- `app/database.py` — Async SQLAlchemy engine + session factory
- `app/models/` — ORM models: `User`, `Image`, `SearchObject`, `ImageSource`, `ImagePurchase`
- `app/schemas/` — Pydantic request/response schemas
- `app/routers/` — API routes: `auth`, `search`, `images`, `admin`, `telegram`
- `app/services/` — Business logic: `auth` (JWT/passwords), `email` (Resend), `telegram`
- `app/middleware/` — Request logging + tracing
- `alembic/` — Database migrations

### Frontend (React 19 + Vite)
- Uses Tailwind CSS v4 (via `@tailwindcss/vite` plugin, no `tailwind.config.js`)
- shadcn/ui components in `src/components/ui/`
- Path alias: `@/*` → `src/*`
- `src/contexts/AuthContext.tsx` — JWT auth state
- `src/components/SearchPage.tsx` — Main search interface
- Vite proxies `/api` to backend in dev

### Database (PostgreSQL 16)
- Requires `pg_trgm` and `fuzzystrmatch` extensions
- Custom `best_word_levenshtein()` function for fuzzy matching
- Schema initialized from `db/init.sql`
- 25+ archive sources pre-seeded (Ukrainian, Belarusian, Lithuanian state archives)

### Search
Full-text search with PostgreSQL `tsvector`/`tsquery`, trigram similarity, and Levenshtein distance. Supports filtering by archive source, sort order (relevance/date), and search mode (exact/fuzzy).

## Deployment

Docker Compose on Hetzner via **Coolify**. Production config in `docker-compose.prod.yml`. Backend runs Gunicorn (4 workers), frontend runs nginx. Media stored in a named Docker volume. CDN via Bunny.net (`jroots.b-cdn.net`).

## Key Patterns

- All backend DB operations are async (`async def` + `AsyncSession`)
- Tests use `asyncio_mode = auto` — no need for `@pytest.mark.asyncio`
- Ruff config: line-length 120, target Python 3.11, ignores E402
- Coverage excludes `app/utils/logging_config.py` and `alembic/`
- Frontend uses `jsdom` test environment via Vitest

# JRoots.co

Jewish genealogy archive search platform. Aggregates scattered archival materials from across the internet into a single searchable database.

## Architecture

- **Backend:** Python / FastAPI / SQLAlchemy (async) / PostgreSQL
- **Frontend:** React 19 / TypeScript / Vite / Tailwind CSS / shadcn/ui
- **Deployment:** Docker Compose on Hetzner via Coolify

## Project Structure

```
├── backend/
│   ├── app/                  # Application package
│   │   ├── main.py           # FastAPI app factory
│   │   ├── config.py         # Pydantic settings
│   │   ├── database.py       # Async SQLAlchemy engine
│   │   ├── models/           # SQLAlchemy models
│   │   ├── schemas/          # Pydantic schemas
│   │   ├── routers/          # API route handlers
│   │   ├── services/         # Business logic
│   │   ├── middleware/        # Request logging, tracing
│   │   └── utils/            # Logging config
│   ├── tests/                # Pytest test suite
│   ├── alembic/              # Database migrations
│   ├── Dockerfile
│   └── pyproject.toml
├── frontend/
│   ├── src/
│   │   ├── components/       # React components
│   │   ├── contexts/         # Auth context
│   │   ├── hooks/            # Custom hooks
│   │   ├── api/              # API client
│   │   └── types/            # TypeScript types
│   ├── Dockerfile
│   └── package.json
├── db/
│   ├── init.sql              # Database schema
│   └── docker-compose.yaml   # Local PostgreSQL
├── cli/                      # CLI tools (installable package)
│   ├── jroots_cli/           # Package source
│   └── pyproject.toml
├── docker-compose.prod.yml   # Production deployment
└── .github/workflows/ci.yml  # CI pipeline
```

## Development Setup

### Prerequisites

- Python 3.11+
- Node.js 20+
- PostgreSQL 16+
- Poetry

### Backend

```bash
cd backend
poetry install
cp .env.example .env  # Configure your environment
poetry run uvicorn app.main:app --reload
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

### Database

```bash
cd db
docker compose up -d
```

### Running Tests

```bash
cd backend
poetry run pytest tests/ -v
```

### CLI Tools

```bash
cd cli
pip install -e .
```

The CLI installs as the `jroots` command. All commands accept `--api-url` (or `JROOTS_API_URL`) and `--token` (or `JROOTS_API_TOKEN`) options.

**Login and get a token:**

```bash
jroots login admin
export JROOTS_API_TOKEN=<token from output>
```

**Validate CSVs before uploading:**

```bash
jroots validate --images-csv images.csv --objects-csv objects.csv
```

**Upload images and search objects:**

```bash
# Upload everything at once
jroots upload-all --images-csv images.csv --objects-csv objects.csv

# Or upload separately
jroots upload-images --csv images.csv
jroots upload-objects --csv objects.csv --images-csv images.csv

# Preview with --dry-run
jroots upload-all --images-csv images.csv --objects-csv objects.csv --dry-run
```

**Check API connectivity:**

```bash
jroots status
```

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `SECRET_KEY` | Yes | JWT signing secret |
| `ALGORITHM` | No | JWT algorithm (default: HS256) |
| `ADMIN_PASSWORD` | Yes | Admin account password |
| `DATABASE_URL` | Yes | PostgreSQL connection string |
| `CORS_ORIGINS` | No | Comma-separated allowed origins |
| `FRONTEND_URL` | No | Frontend URL for email links |
| `TELEGRAM_BOT_TOKEN` | No | Telegram bot token for notifications |
| `TELEGRAM_CHAT_ID` | No | Telegram chat for admin notifications |
| `HCAPTCHA_SECRET_KEY` | No | hCaptcha verification key |
| `RESEND_API_KEY` | No | Resend email API key |
| `MEDIA_PATH` | No | Path for image storage (default: /app/media) |
| `JROOTS_API_URL` | No | API base URL for CLI (default: http://localhost:8000) |
| `JROOTS_API_TOKEN` | No | Bearer token for CLI authentication |

## Deployment

The project is deployed via Coolify using `docker-compose.prod.yml`.

```bash
docker compose -f docker-compose.prod.yml up --build -d
```

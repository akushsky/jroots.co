FROM python:3.11-slim AS builder

WORKDIR /app

COPY ./backend/pyproject.toml ./

RUN apt-get update && apt-get install -y --no-install-recommends fonts-dejavu \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir "poetry>=1.8,<2" \
    && poetry config virtualenvs.create false \
    && poetry install --no-interaction --no-dev

COPY ./backend /app
RUN chmod +x /app/entrypoint.sh

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8000/api/health').raise_for_status()" || exit 1

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["gunicorn", "app.main:app", "-k", "uvicorn.workers.UvicornWorker", "-w", "4", "--bind", "0.0.0.0:8000"]

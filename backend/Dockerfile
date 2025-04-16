FROM python:3.11-slim

WORKDIR /app

COPY ./backend/pyproject.toml ./

RUN pip install poetry && poetry config virtualenvs.create false \
  && poetry install --no-interaction

COPY ./backend /app

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
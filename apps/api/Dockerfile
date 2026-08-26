FROM python:3.13.7-slim AS production

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml alembic.ini ./
COPY migrations ./migrations
COPY review_hub ./review_hub

RUN pip install --no-cache-dir .

RUN mkdir -p /data && chown -R 1000:1000 /data /app
USER 1000:1000

CMD ["sh", "-c", "alembic upgrade head && exec uvicorn review_hub.main:app --host 0.0.0.0 --port 8000 --workers 1"]

FROM python:3.13.7-slim AS development

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml alembic.ini ./
COPY migrations ./migrations
COPY review_hub ./review_hub

RUN pip install --no-cache-dir -e .

EXPOSE 8000

CMD ["sh", "-c", "alembic upgrade head && exec uvicorn review_hub.main:app --host 0.0.0.0 --port 8000 --workers 1 --reload --reload-dir /app/review_hub --reload-dir /app/migrations"]

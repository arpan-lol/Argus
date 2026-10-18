FROM python:3.12-slim@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 libxml2 libxslt1.1 \
    && rm -rf /var/lib/apt/lists/*

COPY backend/python/requirements-lock.txt /tmp/requirements-lock.txt
RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu "torch==2.14.1" \
    && pip install --no-cache-dir --no-deps -r /tmp/requirements-lock.txt

COPY backend/python/app /app/backend/python/app
COPY backend/python/migrations /app/backend/python/migrations
COPY backend/python/licenses /app/backend/python/licenses

RUN useradd --create-home --uid 10001 argus \
    && mkdir -p /app/data/originals \
    && chown -R argus:argus /app/data

USER argus
EXPOSE 4000
CMD ["uvicorn", "app.main:app", "--app-dir", "/app/backend/python", "--host", "0.0.0.0", "--port", "4000"]

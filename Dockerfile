FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PYTHONPATH=/app
WORKDIR /app
RUN groupadd --system app && useradd --system --gid app --home /app app
RUN chown app:app /app
COPY requirements-runtime.txt ./
RUN pip install --no-cache-dir -r requirements-runtime.txt
COPY --chown=app:app alembic.ini ./
COPY --chown=app:app app ./app
COPY --chown=app:app migrations ./migrations
COPY --chown=app:app schemas ./schemas
COPY --chown=app:app scripts ./scripts
USER app
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --retries=6 CMD ["python","-c","import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)"]
CMD ["uvicorn","app.main:app","--host","0.0.0.0","--port","8000"]

FROM base AS quality
USER root
COPY requirements-quality.txt requirements.txt ./
RUN pip install --no-cache-dir -r requirements-quality.txt
COPY --chown=app:app tests ./tests
USER app

FROM base AS runtime

# Pin the existing Python 3.12.13 series to the reviewed linux/amd64 Alpine
# digest. Debian Bookworm and Trixie both retain vulnerable essential Perl
# packages; Alpine 3.24 avoids Perl and carries the fixed SQLite 3.53.2.
FROM python:3.12-alpine@sha256:6d43704baacd1bfbe7c295d7f13079d5d8104ed33568873133f8fc69980419df AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PYTHONPATH=/app
WORKDIR /app
RUN addgroup -S app && adduser -S -G app -h /app app
RUN chown app:app /app
COPY requirements-runtime.txt ./
# Pin the installer used by build/quality stages to the first release fixing
# all reviewed pip advisories. It is removed from the runtime stage below.
RUN python -m pip install --no-cache-dir --upgrade "pip==26.1.2" \
    && python -m pip install --no-cache-dir -r requirements-runtime.txt
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
USER root
RUN python -m pip uninstall -y pip
USER app

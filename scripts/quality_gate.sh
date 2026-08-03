#!/bin/sh
set -eu
python -m compileall -q app tests scripts
python scripts/secret_scan.py
python scripts/export_openapi.py
(cd frontend && npm run openapi:check && npm test && npm run build && npm audit --omit=dev)
pytest -q

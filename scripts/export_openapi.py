"""Generate the canonical OpenAPI file. Generated output; do not hand-edit schemas/openapi.yaml."""
import json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.main import app
document=app.openapi();document["x-generated-file"]="DO NOT EDIT: run python scripts/export_openapi.py"
Path("schemas/openapi.yaml").write_text(json.dumps(document,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8")

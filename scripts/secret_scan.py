"""Local-only secret scanner. Reports file and kind, never the matched value."""

import re
import subprocess
import sys
from pathlib import Path

PATTERNS = {
    "AWS access key": r"AKIA[0-9A-Z]{16}",
    "OpenAI key": r"sk-[A-Za-z0-9]{20,}",
    "Anthropic key": r"sk-ant-[A-Za-z0-9_-]{20,}",
    "Stripe live key": r"sk_live_[A-Za-z0-9]{16,}",
    "PEM private key": r"BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY",
    "Card number": r"[3-6](?:\d[ -]?){12,18}",
}
ALLOW = {
    "docs/staging_readiness.md",
    "docs/staging_deployment_checklist.md",
    "scripts/secret_scan.py",
}


def tracked():
    return subprocess.check_output(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"], text=True
    ).splitlines()


def main():
    findings = []
    for name in tracked():
        if name in ALLOW:
            continue
        try:
            data = Path(name).read_text(errors="ignore")
        except OSError:
            continue
        for kind, pattern in PATTERNS.items():
            if kind == "Card number" and name.startswith("quality-results/"):
                continue
            if re.search(pattern, data):
                findings.append((name, kind))
    for name, kind in sorted(set(findings)):
        print(f"{name}: {kind}")
    if findings:
        return 1
    # History checks only filenames containing high-confidence key prefixes; values are never printed.
    history = subprocess.run(
        [
            "git",
            "log",
            "-G",
            "AKIA[0-9A-Z]{16}|sk_live_|sk-ant-",
            "--all",
            "--name-only",
            "--pretty=format:",
        ],
        capture_output=True,
        text=True,
    ).stdout
    names = sorted({x for x in history.splitlines() if x.strip() and x not in ALLOW})
    for name in names:
        print(f"{name}: possible secret pattern in Git history")
    return 1 if names else 0


if __name__ == "__main__":
    sys.exit(main())

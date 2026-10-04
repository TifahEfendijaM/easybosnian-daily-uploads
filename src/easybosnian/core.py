import json
import os
import subprocess
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
REPO = "TifahEfendijaM/easybosnian-daily-uploads"
PROJECT = "tifahefendijam-easybosnian-daily-uploads-v1"
ZONE = ZoneInfo("Europe/Sarajevo")


def today():
    return datetime.now(ZONE).date().isoformat()


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def verify_repository(remote=False):
    """Every GitHub operation must call this guard immediately before its request."""
    if os.getenv("GITHUB_REPOSITORY", REPO) != REPO:
        raise RuntimeError("Repository mismatch: refusing GitHub operation")
    if remote:
        p = subprocess.run(["gh", "api", f"repos/{REPO}", "--jq", ".full_name + \" \" + (.private|tostring)"], capture_output=True, text=True)
        if p.returncode or p.stdout.strip() != REPO + " true":
            raise RuntimeError("Exact private target repository is unavailable; authorize TifahEfendijaM first")


def gh(*args, input_text=None):
    verify_repository(remote=True)
    result = subprocess.run(["gh", *args], input=input_text, text=True, capture_output=True)
    if result.returncode:
        raise RuntimeError("GitHub operation failed; check account access and repository permissions")
    return result.stdout


def publishing_enabled():
    if os.getenv('GITHUB_ACTIONS') == 'true':
        return os.getenv('DAILY_POSTING_ENABLED') == 'true'
    return gh('variable', 'get', 'DAILY_POSTING_ENABLED', '--repo', REPO, '--json', 'value', '--jq', '.value').strip() == 'true'


def require_publishing():
    """Every live entry point checks the real repository kill switch."""
    if not publishing_enabled():
        raise ValueError('DAILY_POSTING_ENABLED is false or missing; live publishing is disabled')

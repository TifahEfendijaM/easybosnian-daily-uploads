import hashlib
import json
import os
import re
import subprocess
import unicodedata
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
REPO = "TifahEfendijaM/easybosnian-daily-uploads"
PROJECT = "tifahefendijam-easybosnian-daily-uploads-v1"
ZONE = ZoneInfo("Europe/Sarajevo")
LAYOUTS = ("editorial", "framed", "notebook", "ribbon", "split-cards", "minimal", "rounded", "poster")


def today():
    return datetime.now(ZONE).date().isoformat()


def canonical(value):
    value = value.replace("đ", "d").replace("Đ", "D")
    value = unicodedata.normalize("NFKD", value.casefold())
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", "".join(c for c in value if not unicodedata.combining(c))).split())


def digest(package):
    return hashlib.sha256(json.dumps(package, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


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


def publication_monitoring_ready(config):
    return config.get("monitoring_ready") is True or (
        config.get("healthchecks_deferred") is True
        and config.get("github_monitoring_ready") is True
    )

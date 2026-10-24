import json
import os
import subprocess
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
REPO = "TifahEfendijaM/easybosnian-daily-uploads"
REPOSITORY_ID = 1401814933
OWNER_ID = 50710040
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


class RepositoryIdentityError(RuntimeError):
    """An exact-target failure, distinct from a ChatGPT login failure."""


def valid_repository(value):
    return (isinstance(value,dict) and value.get('full_name')==REPO
            and type(value.get('id')) is int and value['id']==REPOSITORY_ID
            and isinstance(value.get('owner'),dict) and value['owner'].get('id')==OWNER_ID
            and value.get('default_branch')=='main' and type(value.get('private')) is bool)


def private_github_outputs():
    # The trusted workflow supplies this from repository metadata. Unknown
    # runner visibility fails closed; local files retain their normal behavior.
    return os.getenv('GITHUB_ACTIONS')!='true' or os.getenv('GITHUB_REPOSITORY_VISIBILITY')=='private'


def verify_repository(remote=False):
    """Pin the owner's original repository, regardless of public/private visibility."""
    if os.getenv("GITHUB_REPOSITORY", REPO) != REPO:
        raise RepositoryIdentityError("Repository mismatch: refusing GitHub operation")
    if remote:
        p = subprocess.run(["gh", "api", f"repos/{REPO}"], capture_output=True, text=True)
        try:value=json.loads(p.stdout) if not p.returncode else None
        except (ValueError,TypeError):value=None
        if not valid_repository(value):
            raise RepositoryIdentityError("Exact repository identity check failed; verify owner, repository ID, access and default branch main")
        return value


def gh(*args, input_text=None):
    identity=verify_repository(remote=True)
    if args[:2]==('issue','create') and not identity['private']:
        raise RepositoryIdentityError('Private-only issue reporting is disabled for this public repository')
    result = subprocess.run(["gh", *args], input=input_text, text=True, capture_output=True)
    if result.returncode:
        raise RuntimeError("GitHub operation failed; check account access and repository permissions")
    return result.stdout


def gh_binary(*args):
    """Protected artifact reads; never decode or print an archive/provider response."""
    verify_repository(remote=True)
    result = subprocess.run(["gh", *args], capture_output=True)
    if result.returncode:
        raise RuntimeError("GitHub artifact read failed; check repository access")
    return result.stdout


def publishing_enabled():
    if os.getenv('GITHUB_ACTIONS') == 'true':
        return os.getenv('DAILY_POSTING_ENABLED') == 'true'
    return gh('variable', 'get', 'DAILY_POSTING_ENABLED', '--repo', REPO, '--json', 'value', '--jq', '.value').strip() == 'true'


def require_publishing():
    """Every live entry point checks the real repository kill switch."""
    if not publishing_enabled():
        raise ValueError('DAILY_POSTING_ENABLED is false or missing; live publishing is disabled')

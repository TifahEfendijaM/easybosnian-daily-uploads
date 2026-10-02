"""Read-only checks using the same protected credentials as the scheduled publisher."""
import os
from datetime import datetime, timezone

from .core import REPO, PROJECT, verify_repository
from .http import request
from .meta import Instagram
from .store import Store


def check_infrastructure():
    required=("EASYBOSNIAN_WORKER_URL", "EASYBOSNIAN_ADMIN_TOKEN", "INSTAGRAM_ACCESS_TOKEN",
              "INSTAGRAM_USER_ID", "INSTAGRAM_TOKEN_ISSUED_AT", "META_GRAPH_VERSION", "GH_SECRETS_TOKEN")
    missing=[name for name in required if not os.environ.get(name)]
    if missing:
        raise ValueError("Missing protected setup credentials: " + ", ".join(missing))
    verify_repository(remote=True)
    store=Store()
    if store.call("GET", "/health").get("project")!=PROJECT or store.history().get("project")!=PROJECT:
        raise ValueError("Cloudflare health/history does not belong to this project")
    config=store.call("GET", "/v1/config")
    info=Instagram().verify_account()
    issued=datetime.fromisoformat(os.environ["INSTAGRAM_TOKEN_ISSUED_AT"].replace("Z", "+00:00"))
    age=(datetime.now(timezone.utc)-issued).total_seconds()
    if age<0 or age>=60*86400:
        raise ValueError("Instagram token issuance is invalid or its refresh window has expired")
    # This checks the selected renewal token's access without refreshing or replacing credentials.
    headers={"Authorization":"Bearer "+os.environ["GH_SECRETS_TOKEN"],
             "Accept":"application/vnd.github+json", "X-GitHub-Api-Version":"2022-11-28"}
    base="https://api.github.com/repos/"+REPO
    for path in ("/actions/secrets/public-key", "/contents/queue"):
        identity=request("GET",base,headers=headers)
        if identity.get("full_name")!=REPO or identity.get("private") is not True:
            raise ValueError("Renewal credential does not authorize the exact private repository")
        request("GET",base+path,headers=headers)
    return {"repository":REPO, "cloudflare":"health and private history verified",
            "instagram":"@"+info["username"]+" professional account verified",
            "renewal_access":"repository secrets and queue read access verified",
            "healthchecks":"deferred by user" if config.get("healthchecks_deferred") is True else "not deferred",
            "publication":"nothing published by this read-only check"}

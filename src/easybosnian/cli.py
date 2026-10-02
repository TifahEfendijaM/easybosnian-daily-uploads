import argparse
import base64
import getpass
import importlib.util
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image

from .core import ROOT, REPO, PROJECT, digest, gh, read_json, today, verify_repository, write_json, publication_monitoring_ready
from .http import redact
from .meta import Instagram, Facebook, facebook_page_token
from .facebook import pipeline_facebook, export_tiktok
from .daily import daily
from .stories import pipeline_stories
from .notify import heartbeat, failure
from .pipeline import pipeline
from .render import render
from .readiness import check_infrastructure
from .store import Store
from .validate import reservations, validate


def load_env():
    path=ROOT / ".env"
    if os.getenv("GITHUB_ACTIONS") or not path.exists(): return
    for line in path.read_text().splitlines():
        if line and not line.startswith("#"):
            key,sep,value=line.partition("=")
            if sep and re.fullmatch(r"[A-Z_]+",key): os.environ.setdefault(key,value)


def create_repository():
    # Never inspect other repositories. Verify only the account and exact target endpoint.
    result=subprocess.run(["gh","api","user","--jq",".login"],capture_output=True,text=True)
    if result.returncode or result.stdout.strip()!="TifahEfendijaM":
        raise ValueError("Sign GitHub CLI in as TifahEfendijaM before creating the new private repository")
    existing=subprocess.run(["gh","api",f"repos/{REPO}","--jq",".full_name"],capture_output=True,text=True)
    if existing.returncode==0:
        raise ValueError("The target name already exists. Inspect it with the user; creation cannot silently reuse it")
    if "404" not in existing.stderr:
        raise ValueError("Cannot establish availability of the exact requested name")
    verify_repository()
    created=subprocess.run(["gh","api","user/repos","--method","POST","-f","name=easybosnian-daily-uploads","-F","private=true","-f","description=Reviewed daily EasyBosnian carousels with Cloudflare and Instagram Login","--jq",".full_name"],capture_output=True,text=True)
    if created.returncode or created.stdout.strip()!=REPO:
        raise ValueError("Could not create the requested repository; no alternative repository was used")
    verify_repository(remote=True)
    # Initialization only inside this fresh project folder.
    subprocess.run(["git","init","-b","main",str(ROOT)],check=True,capture_output=True)
    subprocess.run(["git","-C",str(ROOT),"remote","add","origin",f"https://github.com/{REPO}.git"],check=True)
    print("Created private " + REPO)


def fit_check(package):
    path=ROOT / "build/fit-background.jpg"
    path.parent.mkdir(exist_ok=True)
    Image.new("RGB",(1080,1350),"#7492a5").save(path)
    for card in package["cards"]:
        render(card,package["design_palette"],path,ROOT / "build" / (card["kind"]+"-fit.jpg"))


def prepare(path):
    stage="preparation/queue save"
    date=today()
    try:
        verify_repository(remote=True)
        heartbeat("preparation","start","Preparing reviewed content for "+date)
        package=read_json(path); date=package["date"]
        if date!=today(): raise ValueError("Daily preparation must use today's Sarajevo date")
        store=Store(); history=store.history()
        stage="validation"
        validate(package,history); fit_check(package)
        stage="preparation/queue save"
        h=digest(package)
        store.call("POST","/v1/queue",{"package":package,"hash":h,"reservation_keys":reservations(package)})
        # Cloudflare reservation comes first. If GitHub saving fails it stays reserved;
        # rerunning the same package/date resumes this save without choosing new words.
        content=json.dumps(package,ensure_ascii=False,indent=2)+"\n"
        repo_path=f"queue/{date}.json"
        payload={"message":f"Prepare reviewed EasyBosnian batch {date}","content":base64.b64encode(content.encode()).decode(),"branch":"main"}
        verify_repository(remote=True)
        existing=subprocess.run(["gh","api",f"repos/{REPO}/contents/{repo_path}"],capture_output=True,text=True)
        if existing.returncode==0:
            current=json.loads(existing.stdout)
            original=json.loads(base64.b64decode(current["content"]))
            if digest(original)!=h: raise ValueError("GitHub already has different reviewed content for this date")
        else:
            if "404" not in existing.stderr: raise ValueError("Cannot check the exact queue path")
            gh("api",f"repos/{REPO}/contents/{repo_path}","--method","PUT","--input","-",input_text=json.dumps(payload))
        saved=json.loads(gh("api",f"repos/{REPO}/contents/{repo_path}"))
        if digest(json.loads(base64.b64decode(saved["content"])))!=h:
            raise ValueError("GitHub queue read-back does not match the reviewed package")
        write_json(ROOT / repo_path,package)
        config=store.call("GET","/v1/config")
        config["preparation_verified"]=True
        store.call("PUT","/v1/config",config)
        heartbeat("preparation",message=f"Batch {date}; reviewed JSON saved and read back in {REPO}; nothing published")
        print(f"Saved reviewed JSON for {date}; package hash {h}; nothing published")
    except Exception as error:
        report=failure(date,stage,error,"nothing published",os.getenv("GITHUB_RUN_URL"))
        try: heartbeat("preparation","fail",report)
        except Exception: print("Preparation notification could not be delivered; inspect Scheduled and GitHub issue/logs")
        raise RuntimeError(redact(error)) from None


def set_secret(name,local=False):
    if not re.fullmatch(r"[A-Z_]+",name): raise ValueError("Invalid secret name")
    value=getpass.getpass(f"Enter {name} privately (hidden): ").strip()
    if not value: raise ValueError("Empty secret")
    gh("secret","set",name,"--repo",REPO,input_text=value)
    if local:
        path=ROOT / ".env"
        lines=path.read_text().splitlines() if path.exists() else []
        lines=[s for s in lines if not s.startswith(name+"=")]
        lines.append(name+"="+value)
        path.write_text("\n".join(lines)+"\n")
        path.chmod(0o600)
    print(name+" stored privately")


def authorize_instagram():
    # The Meta app dashboard can issue a long-lived token for the account's app role.
    # Tokens are entered only into this local hidden prompt, never into chat.
    verify_repository(remote=True)
    token=getpass.getpass("Instagram Login token (hidden): ").strip()
    version=input("Supported Graph version shown by your Meta app [v26.0]: ").strip() or "v26.0"
    os.environ["META_GRAPH_VERSION"]=version
    ig=Instagram(token,"")
    info=ig.verify_account()
    print("Verified authorized username: @"+info["username"])
    issued=datetime.now(timezone.utc).isoformat()
    for name,value in (("INSTAGRAM_ACCESS_TOKEN",token),("INSTAGRAM_USER_ID",ig.user_id),("INSTAGRAM_TOKEN_ISSUED_AT",issued),("META_GRAPH_VERSION",version)):
        gh("secret","set",name,"--repo",REPO,input_text=value)
    print("Instagram credentials stored in exact repository secrets; no post was made")


def set_worker_secret(name):
    verify_repository(remote=True)
    value=getpass.getpass(f"Enter {name} privately (hidden): ").strip()
    spec=importlib.util.spec_from_file_location('easybosnian_cloudflare_setup',ROOT/'scripts/cloudflare_deploy.py')
    setup=importlib.util.module_from_spec(spec); spec.loader.exec_module(setup)
    setup.put_worker_secret(name,value)


def authorize_facebook():
    verify_repository(remote=True)
    os.environ["META_GRAPH_VERSION"] = input("Supported Graph version [v26.0]: ").strip() or "v26.0"
    app_id = input("Facebook app ID [1987873818544936]: ").strip() or "1987873818544936"
    if app_id != "1987873818544936":
        raise ValueError("Use only this project's confirmed Pages-capable Meta app")
    page_id = input("Confirmed Easy Bosnian Page ID [1284422991426579]: ").strip() or "1284422991426579"
    if page_id != "1284422991426579":
        raise ValueError("Use only the Easy Bosnian Page selected in this project's confirmed consent")
    token = getpass.getpass("Facebook user token with the three Page permissions (hidden): ").strip()
    secret = getpass.getpass("This Meta app's secret, for long-lived exchange only (hidden): ").strip()
    value, info = facebook_page_token(token, app_id, secret, page_id)
    for name, content in (("FACEBOOK_PAGE_TOKEN", value), ("FACEBOOK_PAGE_ID", page_id)):
        gh("secret", "set", name, "--repo", REPO, input_text=content)
    # Credential verification alone does not establish that Meta's app can distribute
    # public Page posts. Arm the separate publisher only after its app checklist is complete.
    write_json(ROOT / "docs/facebook-authorization.json", {**info, "verified_at": datetime.now(timezone.utc).isoformat(), "publication": "nothing published during authorization"})
    print("Verified EasyBosnian Page and stored its separate long-lived credentials; finish the Meta public-app checklist before arming Facebook; no post made")


def activate(action,date=None):
    verify_repository(remote=True)
    store=Store(); config=store.call("GET","/v1/config")
    if action=="test-monitoring":
        # Check both external pings and the independent Worker's notification access.
        report=failure(today(),"scheduling","Notification self-test: no pipeline failure and no post","nothing published")
        heartbeat("pipeline","fail",report,force=True)
        heartbeat("preparation","fail",report,force=True)
        store.call("POST","/v1/monitoring/check")
        config.update(monitoring_ready=True,github_monitoring_ready=True,healthchecks_deferred=False)
    elif action=="defer-healthchecks":
        # This explicit user choice retains verified GitHub alerts without claiming email readiness.
        result=store.call("POST","/v1/monitoring/check",{"healthchecks":False})
        if result.get("repository")!=REPO or result.get("github_notification_check")!="accepted":
            raise ValueError("GitHub monitoring access has not been verified")
        config.update(healthchecks_deferred=True,github_monitoring_ready=True)
    elif action=="enable-daily":
        # The user explicitly authorized daily posting and waived preview/live-test gates.
        config.update(daily_authorized=True,daily_enabled=True,active_since=today())
        if not config.get("preparation_verified") or not publication_monitoring_ready(config): raise ValueError("First verify preparation save/read-back and the selected failure reporting setup")
        if os.getenv("GITHUB_ACTIONS") == "true":
            if os.getenv("DAILY_POSTING_ENABLED") != "true":
                raise ValueError("Arm the authorized scheduled pipeline variable before cloud activation")
        else:
            gh("variable","set","DAILY_POSTING_ENABLED","--repo",REPO,"--body","true")
    elif action=="disable-daily":
        config["daily_enabled"]=False
        gh("variable","set","DAILY_POSTING_ENABLED","--repo",REPO,"--body","false")
    store.call("PUT","/v1/config",config)
    print("Saved activation setting: "+action)


def main():
    load_env()
    parser=argparse.ArgumentParser(description="Private EasyBosnian project")
    subs=parser.add_subparsers(dest="command",required=True)
    subs.add_parser("create-repository")
    subs.add_parser("history")
    subs.add_parser("check-infrastructure")
    v=subs.add_parser("validate"); v.add_argument("path")
    p=subs.add_parser("prepare"); p.add_argument("path")
    p=subs.add_parser("pipeline"); p.add_argument("--date",default=None); p.add_argument("--mode",choices=["preview","live","reconcile"],default="preview")
    p=subs.add_parser("daily"); p.add_argument("--date",default=None); p.add_argument("--mode",choices=["preview","live","reconcile"],default="preview")
    p=subs.add_parser("facebook"); p.add_argument("--date",default=None); p.add_argument("--mode",choices=["live","reconcile"],default="reconcile")
    p=subs.add_parser("export-tiktok"); p.add_argument("--date",default=None)
    p=subs.add_parser("stories"); p.add_argument("--date",default=None); p.add_argument("--mode",choices=["live","reconcile"],default="reconcile")
    p=subs.add_parser("set-secret"); p.add_argument("name"); p.add_argument("--local",action="store_true")
    p=subs.add_parser("set-worker-secret"); p.add_argument("name",choices=["NOTIFY_GITHUB_TOKEN","HC_WATCHDOG_URL"])
    subs.add_parser("authorize-instagram")
    subs.add_parser("authorize-facebook")
    subs.add_parser("verify-facebook")
    p=subs.add_parser("activation"); p.add_argument("action",choices=["test-monitoring","defer-healthchecks","enable-daily","disable-daily"]); p.add_argument("--date")
    args=parser.parse_args()
    if args.command=="create-repository": create_repository()
    elif args.command=="history": print(json.dumps(Store().history(),ensure_ascii=False,indent=2))
    elif args.command=="check-infrastructure": print(json.dumps(check_infrastructure(),indent=2))
    elif args.command=="validate": validate(read_json(args.path)); print("Content validation passed")
    elif args.command=="prepare": prepare(args.path)
    elif args.command=="pipeline": pipeline(args.date,args.mode)
    elif args.command=="daily": daily(args.date,args.mode)
    elif args.command=="facebook": pipeline_facebook(args.date,args.mode)
    elif args.command=="export-tiktok": export_tiktok(args.date)
    elif args.command=="stories": pipeline_stories(args.date,args.mode)
    elif args.command=="set-secret": set_secret(args.name,args.local)
    elif args.command=="set-worker-secret": set_worker_secret(args.name)
    elif args.command=="authorize-instagram": authorize_instagram()
    elif args.command=="authorize-facebook": authorize_facebook()
    elif args.command=="verify-facebook": print(Facebook().verify_page())
    elif args.command=="activation": activate(args.action,args.date)


if __name__=="__main__": main()

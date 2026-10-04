import argparse
import getpass
import importlib.util
import json
import os
import re
import subprocess
from datetime import date as calendar_date, datetime, timezone
from pathlib import Path

from PIL import Image

from .core import ROOT, REPO, PROJECT, gh, read_json, today, verify_repository, write_json
from .http import redact
from .meta import Instagram, Facebook, facebook_page_token, instagram_deletion_token
from .daily import daily
from .buffer import Buffer
from .notify import failure
from .hybrid import render_hybrid
from .story_layouts import tall_story_image
from .levels import KEEP_CURRENT, LEVELS, set_level
from .readiness import check_infrastructure
from .store import Store
from .validate import validate
from .batches import BATCH_ID, identity, plan_batch


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
    verify_repository(remote=True)
    subprocess.run(["git","-C",str(ROOT),"remote","add","origin",f"https://github.com/{REPO}.git"],check=True)
    print("Created private " + REPO)


def fit_check(package):
    path=ROOT / "build/fit-background.jpg"
    path.parent.mkdir(exist_ok=True)
    Image.new("RGB",(1080,1350),"#7492a5").save(path)
    for card in package["cards"]:
        render_hybrid(card,package["design_palette"],path,ROOT / "build" / (card["kind"]+"-hybrid-fit.jpg"))
        palette=read_json(ROOT/'data/design-palettes.json')[package['design_palette']]
        tall_story_image(card,path,ROOT/'build'/(card['kind']+'-story-fit.jpg'),palette)


def prepare(path,selection=None,batch_target='today',run_date=None,plan=None):
    verify_repository(remote=True)
    package=read_json(path)
    for card in package.get("cards",[]):card.pop("design_template",None)
    from .selection import batch_date, check_selection, novelty_history, word_levels
    store=Store();history=store.history()
    if package['date']!=batch_date(history,run_date or today(),batch_target):
        raise ValueError('Content must use the selected Sarajevo batch date')
    if plan:
        publications=store.publications_for_date(run_date or today()) if batch_target=='all_today' else []
        expected=plan_batch(history,run_date or today(),batch_target,publication_batch_ids=[item['batch_id'] for item in publications])
        existing=any(identity(row)==plan['batch_id'] for row in history['days'])
        if (not BATCH_ID.fullmatch(plan['batch_id']) or package.get('batch_id')!=plan['batch_id']
                or plan['date']!=package['date'] or plan['source_batch_id']!=expected['source_batch_id']
                or plan['cleanup_batch_id']!=expected['cleanup_batch_id']
                or (expected['cleanup_batch_id'] and plan['batch_id']!=expected['batch_id'])
                or (not expected['cleanup_batch_id'] and existing)):
            raise ValueError('Draft does not match the trusted independent/replacement batch plan')
        if batch_target=='all_today' and any(plan.get(field)!=expected[field] for field in ('cleanup_batch_ids','prune_history_ids')):
            raise ValueError('Draft does not match the trusted current-date cleanup scope')
    if selection:
        check_selection(package,selection);history=novelty_history(history,package['date'],selection,package)
    from .levels import load_level
    level=load_level()
    validate(package,history,include_today=True,require_website_footer=True,require_quiz_format=True,require_caption_level=True,target_cefr=level,word_level_targets=word_levels(package,selection or {'choice':'new'},level));fit_check(package)
    store.save_content(package)
    print('Reviewed content saved in private history for '+package['date'])
    return package


def prepared_date(mode):
    """Use the trusted preparation result's date, never the clock at publication time."""
    result=read_json(ROOT/'build/preparation-result.json')
    date=result.get('date')
    if (mode not in ('preview','daily') or result.get('mode')!=mode or result.get('project')!=PROJECT
            or result.get('status')!='reviewed content available in private history'
            or not isinstance(date,str) or calendar_date.fromisoformat(date).isoformat()!=date or date>today()):
        raise ValueError('No successful preparation result for this mode and batch date')
    return date


def prepared_batch(mode,details=False):
    date=prepared_date(mode);result=read_json(ROOT/'build/preparation-result.json')
    batch_id=result.get('batch_id');cleanup=result.get('cleanup_batch_id')
    if (not isinstance(batch_id,str) or not BATCH_ID.fullmatch(batch_id)
            or cleanup not in (None,batch_id) or result.get('batch_target') not in ('latest','none','today','all_today')
            or (result['batch_target']!='latest' and cleanup is not None)):
        raise ValueError('No trusted batch identity and cleanup scope for this preparation')
    scope={}
    if result['batch_target']=='all_today':
        targets=result.get('cleanup_batch_ids');prune=result.get('prune_history_ids')
        if (date!=result.get('run_date') or not isinstance(targets,list) or not isinstance(prune,list)
                or any(not isinstance(key,str) or not BATCH_ID.fullmatch(key) for key in targets+prune)
                or len(set(targets))!=len(targets) or len(set(prune))!=len(prune)
                or batch_id in targets or not set(prune).issubset(targets)):
            raise ValueError('No trusted all-today cleanup scope for this preparation')
        scope={'cleanup_batch_ids':targets,'prune_history_ids':prune,'cleanup_all':True}
    elif result.get('cleanup_batch_ids') or result.get('prune_history_ids'):
        raise ValueError('Multiple-batch cleanup requires all_today')
    values=(date,batch_id,cleanup is not None)
    return (*values,scope) if details else values


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


def authorize_buffer(key=None):
    verify_repository(remote=True)
    key = key or getpass.getpass("Buffer personal API key (hidden): ").strip()
    buffer = Buffer(key=key)
    account = buffer.discover()
    gh("secret", "set", "BUFFER_API_KEY", "--repo", REPO, input_text=key)
    for name, value in (("BUFFER_TIKTOK_CHANNEL_ID", buffer.channel_id), ("BUFFER_ORGANIZATION_ID", buffer.organization_id)):
        gh("variable", "set", name, "--repo", REPO, "--body", value)
    write_json(ROOT / "docs/buffer-authorization.json", {
        "provider": "Buffer", "account": "@easy.bosnian", "channel_id": account["id"],
        "organization_id": account["organizationId"], "service_id": account["serviceId"],
        "scopes": account["scopes"], "verified_at": datetime.now(timezone.utc).isoformat(),
        "automatic_connection_verified": True, "publication": "nothing submitted or published during authorization"})
    print("Verified connected, unpaused @easy.bosnian channel with automatic publishing; credentials stored in the exact repository; nothing published")


def authorize_instagram_deletion(token=None,secret=None):
    verify_repository(remote=True)
    token=token or getpass.getpass('Facebook user token with Instagram deletion permissions (hidden): ').strip()
    secret=secret or getpass.getpass('EasyBosnian Daily Uploads app secret for long-lived exchange (hidden): ').strip()
    value,info=instagram_deletion_token(token,secret)
    for name,content in [('INSTAGRAM_DELETE_ACCESS_TOKEN',value),('INSTAGRAM_DELETE_USER_ID',info['instagram_id'])]:
        gh('secret','set',name,'--repo',REPO,input_text=content)
    write_json(ROOT/'docs/instagram-deletion-authorization.json',info)
    print('Separate Instagram deletion authorization verified and saved privately. Existing publishing credentials unchanged; no social content deleted.')


def activate(action):
    if action not in ('enable-daily','disable-daily'): raise ValueError('Unknown activation action')
    gh('variable','set','DAILY_POSTING_ENABLED','--repo',REPO,'--body','true' if action=='enable-daily' else 'false')
    print('Saved daily publishing kill switch: '+action)


def main():
    load_env()
    parser=argparse.ArgumentParser(description="Private EasyBosnian project")
    subs=parser.add_subparsers(dest="command",required=True)
    subs.add_parser("create-repository")
    subs.add_parser("history")
    subs.add_parser("check-infrastructure")
    level=subs.add_parser('set-level');level.add_argument('--level',choices=(KEEP_CURRENT,*LEVELS),required=True)
    v=subs.add_parser("validate"); v.add_argument("path")
    p=subs.add_parser("prepare"); p.add_argument("path")
    p=subs.add_parser('run');target=p.add_mutually_exclusive_group();target.add_argument('--date',default=None);target.add_argument('--prepared',action='store_true');p.add_argument('--mode',choices=['verify','preview','daily'],default='verify')
    p=subs.add_parser("set-secret"); p.add_argument("name"); p.add_argument("--local",action="store_true")
    p=subs.add_parser("set-worker-secret"); p.add_argument("name",choices=["GITHUB_DISPATCH_TOKEN"])
    subs.add_parser("authorize-instagram")
    subs.add_parser("authorize-facebook")
    subs.add_parser("authorize-instagram-deletion")
    subs.add_parser("authorize-buffer")
    subs.add_parser("verify-facebook")
    p=subs.add_parser("activation"); p.add_argument("action",choices=["enable-daily","disable-daily"])
    args=parser.parse_args()
    if args.command=="create-repository": create_repository()
    elif args.command=="history": print(json.dumps(Store().history(),ensure_ascii=False,indent=2))
    elif args.command=="check-infrastructure": print(json.dumps(check_infrastructure(),indent=2))
    elif args.command=='set-level':
        result=set_level(args.level);print(json.dumps(result))
        if os.getenv('GITHUB_STEP_SUMMARY'):
            with Path(os.environ['GITHUB_STEP_SUMMARY']).open('a',encoding='utf-8') as summary:
                summary.write(f"Current saved difficulty: **{result['bosnian_level']}**\n\n"
                              +('Saved and read back from main.' if result['updated'] else 'Kept the existing saved setting; no file was changed.')
                              +'\n\nThis level applies to future preparations. No content was prepared or published.\n')
    elif args.command=="validate": validate(read_json(args.path)); print("Content validation passed")
    elif args.command=="prepare": prepare(args.path)
    elif args.command=='run':
        if args.prepared:
            date,batch_id,replace,scope=prepared_batch(args.mode,details=True);daily(date,args.mode,batch_id=batch_id,replace=replace,**scope)
        else:daily(args.date,args.mode)
    elif args.command=="set-secret": set_secret(args.name,args.local)
    elif args.command=="set-worker-secret": set_worker_secret(args.name)
    elif args.command=="authorize-instagram": authorize_instagram()
    elif args.command=="authorize-facebook": authorize_facebook()
    elif args.command=="authorize-instagram-deletion": authorize_instagram_deletion()
    elif args.command=="authorize-buffer": authorize_buffer()
    elif args.command=="verify-facebook": print(Facebook().verify_page())
    elif args.command=="activation": activate(args.action)


if __name__=="__main__": main()

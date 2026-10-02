import io
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image

from .core import ROOT, REPO, digest, read_json, today, write_json, verify_repository, publication_monitoring_ready
from .http import redact, request
from .meta import Instagram
from .notify import failure, heartbeat
from .providers import provider
from .render import render
from .store import Store
from .validate import validate


def verify_media(ig, record):
    state, package = record["state"], record["package"]
    actual = ig.media(state["media_id"])
    expected = package["caption"] + "\n\n" + " ".join(package["hashtags"])
    if actual.get("caption", "") != expected or actual.get("media_type") != "CAROUSEL_ALBUM" or len(actual.get("children", {}).get("data", [])) != 3:
        raise ValueError("Published media does not match the expected caption and three-image carousel")
    if not actual.get("permalink", "").startswith("https://www.instagram.com/"):
        raise ValueError("Instagram has not returned an actual publication permalink")
    state.update(verified=True, permalink=actual["permalink"], verified_at=datetime.now(timezone.utc).isoformat())
    return actual["permalink"]


def reconcile(ig, store, date, record):
    state=record["state"]
    if state.get("media_id"):
        verify_media(ig, record)
        store.save(date, record)
        return
    if not state.get("publish_intent"):
        raise ValueError("No publication intent to reconcile; inspect the saved batch")
    package=record["package"]
    caption=package["caption"] + "\n\n" + " ".join(package["hashtags"])
    intent=datetime.fromisoformat(state["publish_intent_at"])
    matches=[]
    for item in ig.recent():
        timestamp=datetime.fromisoformat(item["timestamp"].replace("Z", "+00:00"))
        if item.get("caption")==caption and timestamp>=intent and item.get("media_type")=="CAROUSEL_ALBUM":
            matches.append(item)
    if len(matches)!=1:
        raise ValueError("Publication remains uncertain. Inspect Instagram manually; no publish request will be repeated")
    state["media_id"]=matches[0]["id"]
    store.save(date, record)
    verify_media(ig, record)
    store.save(date, record)


def pipeline(date=None, mode="preview"):
    verify_repository(remote=True)
    date=date or today()
    stage="storage"
    record=None
    run_url=os.getenv("GITHUB_RUN_URL")
    monitored=bool(os.getenv("HC_PIPELINE_URL"))
    try:
        if monitored:
            heartbeat("pipeline","start",f"Batch {date}; mode {mode}; {run_url or 'local deliberate run'}")
        store=Store()
        config=store.call("GET","/v1/config")
        record=store.batch(date)
        state,package=record["state"],record["package"]
        expected=os.getenv("EXPECTED_PACKAGE_HASH", "")
        if expected:
            stage="validation"
            if not re.fullmatch(r"[a-f0-9]{64}",expected) or record["hash"]!=expected or digest(package)!=expected:
                raise ValueError("Automatic handoff does not match the exact reviewed preparation package")
        state["run_url"]=run_url
        state["started_at"]=datetime.now(timezone.utc).isoformat()
        store.save(date,record)
        stage="validation"
        local=read_json(ROOT / "queue" / f"{date}.json")
        if digest(package)!=record["hash"] or digest(local)!=record["hash"]:
            raise ValueError("GitHub queue and immutable Cloudflare package differ or preparation has not finished")
        validate(package,store.history())
        if mode=="live":
            allowed = config.get("daily_enabled") and config.get("daily_authorized")
            if not allowed:
                raise ValueError("Daily publishing is authorized but account/preparation setup has not been activated")
            if not publication_monitoring_ready(config):
                raise ValueError("Verify failure reporting or the user's deferred Healthchecks setup before daily publishing")
        output=ROOT / "build" / date
        output.mkdir(parents=True,exist_ok=True)
        if state.get("verified"):
            write_json(output / "result.json",{"status":"confirmed published","permalink":state["permalink"],"batch":date})
            if monitored: heartbeat("pipeline",message=f"Batch {date}; already confirmed published; {state['permalink']}")
            return state
        if mode=="reconcile":
            stage="authorization"
            ig=Instagram(); ig.refresh_if_needed(); ig.verify_account()
            stage="publication verification"
            reconcile(ig,store,date,record)
        else:
            if state.get("publish_intent"):
                raise ValueError("A previous publish request is uncertain. Use reconcile; ordinary reruns cannot publish again")
            for card in package["cards"]:
                kind=card["kind"]
                item=state.setdefault("cards",{}).setdefault(kind,{})
                background=output / f"{kind}-background.jpg"
                rendered=output / f"{kind}-card.jpg"
                if item.get("background_saved"):
                    stage="storage"
                    background.write_bytes(store.get_file(date,background.name))
                else:
                    stage="FLUX generation"
                    # Convert provider output to JPEG without introducing text or logos.
                    Image.open(io.BytesIO(provider().generate(card["background_prompt"],date,kind))).convert("RGB").save(background,"JPEG",quality=95)
                    stage="storage"
                    store.put_file(date,background.name,background.read_bytes())
                    item["background_saved"]=True
                    store.save(date,record)
                if item.get("render_saved"):
                    stage="storage"
                    rendered.write_bytes(store.get_file(date,rendered.name))
                else:
                    stage="Pillow rendering"
                    item["metrics"]=render(card,package["design_palette"],background,rendered)
                    stage="storage"
                    store.put_file(date,rendered.name,rendered.read_bytes())
                    item["render_saved"]=True
                    store.save(date,record)
            if mode=="preview":
                write_json(output / "result.json",{"status":"unpublished preview","package_hash":record["hash"],"batch":date})
                if monitored: heartbeat("pipeline",message=f"Batch {date}; unpublished preview completed; {run_url or 'local'}")
                return state
            stage="authorization"
            ig=Instagram(); ig.refresh_if_needed(); ig.verify_account()
            for card in package["cards"]:
                item=state["cards"][card["kind"]]
                if not item.get("public_url"):
                    stage="storage"
                    item["public_url"]=store.expose(date,card["kind"]+"-card.jpg")
                    store.save(date,record)
                stage="storage"
                fetched=request("GET",item["public_url"],raw=True)
                local_bytes=(output / (card["kind"]+"-card.jpg")).read_bytes()
                if fetched!=local_bytes:
                    raise ValueError("Public image bytes do not match the approved renderer output")
                stage="publishing"
                if not item.get("container_id"):
                    item["container_id"]=ig.child(item["public_url"],card["alt_text"])
                    store.save(date,record)
                ig.ready(item["container_id"])
            caption=package["caption"] + "\n\n" + " ".join(package["hashtags"])
            if not state.get("carousel_id"):
                state["carousel_id"]=ig.carousel([state["cards"][c["kind"]]["container_id"] for c in package["cards"]],caption)
                store.save(date,record)
            ig.ready(state["carousel_id"])
            # Persist intent BEFORE any publish request. A timeout cannot cause a blind repost.
            state["publish_intent"]=True
            state["publish_intent_at"]=datetime.now(timezone.utc).isoformat()
            store.save(date,record)
            state["media_id"]=ig.publish(state["carousel_id"])
            store.save(date,record)
            stage="publication verification"
            verify_media(ig,record)
            store.save(date,record)
        state.pop("failed_stage",None)
        store.save(date,record)
        write_json(output / "result.json",{"status":"confirmed published","permalink":state["permalink"],"batch":date})
        if monitored: heartbeat("pipeline",message=f"Batch {date}; confirmed published; {state['permalink']}")
        return state
    except Exception as error:
        stage=getattr(error,"stage",None) or stage
        state=record["state"] if record else {}
        publication="confirmed published" if state.get("verified") else "published; verification pending" if state.get("media_id") else "uncertain" if state.get("publish_intent") else "nothing published"
        message=redact(error)
        if record:
            state.update(failed_stage=stage,last_error=message)
            try: store.save(date,record)
            except Exception: pass  # Original failure remains fatal and is reported through independent channels.
        report=failure(date,stage,message,publication,run_url)
        try:
            store.call("POST","/v1/events",{"date":date,"stage":stage,"error":message,"publication":publication,"run_url":run_url})
        except Exception:
            report += "Cloudflare diagnostic event could not be saved.\n"
        if monitored:
            try: heartbeat("pipeline","fail",report)
            except Exception:
                report += "External notification failed; use the saved artifact and native GitHub Actions email.\n"
        print(report)
        raise RuntimeError("Pipeline failed at " + stage) from None

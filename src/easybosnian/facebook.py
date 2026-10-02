"""Publish the immutable daily batch independently to the authorized Facebook Page."""
import os
import re
from datetime import datetime, timezone
from urllib.parse import urlparse

from .artwork import artwork
from .core import ROOT, digest, read_json, today, verify_repository, write_json, publication_monitoring_ready
from .http import redact, request
from .meta import Facebook
from .notify import failure
from .store import Store
from .validate import validate


def caption(package):
    return package["caption"] + "\n\n" + " ".join(package["hashtags"])


def checked_batch(store, date):
    record = store.batch(date)
    expected = os.getenv("EXPECTED_PACKAGE_HASH", "")
    if expected and (not re.fullmatch(r"[a-f0-9]{64}", expected) or expected != record["hash"]):
        raise ValueError("Platform handoff differs from the exact reviewed preparation package")
    if digest(record["package"]) != record["hash"] or digest(read_json(ROOT / "queue" / f"{date}.json")) != record["hash"]:
        raise ValueError("Private history and reviewed GitHub queue do not match")
    validate(record["package"], store.history())
    return record


def verify_post(facebook, record):
    state = record["state"]["platforms"]["facebook"]
    actual = facebook.post(state["post_id"])
    if actual.get("id") != state["post_id"] or actual.get("from", {}).get("id") != facebook.page_id:
        raise ValueError("Facebook returned a post from a different Page")
    if actual.get("message") != caption(record["package"]) or actual.get("is_published") is not True:
        raise ValueError("Facebook post is unpublished or its caption differs from the reviewed batch")
    attachments = actual.get("attachments", {}).get("data", [])
    photos = [a for attachment in attachments for a in attachment.get("subattachments", {}).get("data", [])]
    expected = [state["cards"][c["kind"]]["photo_id"] for c in record["package"]["cards"]]
    if len(photos) != 3 or [str(p.get("target", {}).get("id", "")) for p in photos] != expected or any(p.get("type") != "photo" for p in photos):
        raise ValueError("Facebook post does not contain the exact three reviewed photo IDs in order")
    permalink = actual.get("permalink_url", "")
    parsed = urlparse(permalink)
    if parsed.scheme != "https" or parsed.hostname not in ("www.facebook.com", "facebook.com", "m.facebook.com") or not parsed.path.strip("/"):
        raise ValueError("Facebook has not returned an actual publication permalink")
    state.update(verified=True, permalink=permalink, verified_at=datetime.now(timezone.utc).isoformat())
    return permalink


def reconcile(facebook, store, date, record):
    state = record["state"]["platforms"]["facebook"]
    if not state.get("post_id"):
        if not state.get("publish_intent"):
            raise ValueError("No Facebook publication intent exists; inspect any uncertain unpublished photo upload")
        intent = datetime.fromisoformat(state["publish_intent_at"])
        recent = facebook.recent(int(intent.timestamp()))
        # Do not follow arbitrary provider paging URLs containing credentials.
        if recent.get("paging", {}).get("next"):
            raise ValueError("Facebook reconciliation is incomplete; inspect the Page manually without reposting")
        matches = [p for p in recent["data"] if p.get("message") == caption(record["package"]) and datetime.fromisoformat(p["created_time"].replace("Z", "+00:00")) >= intent]
        if len(matches) != 1:
            raise ValueError("Facebook outcome remains uncertain; no publish request will be repeated")
        state["post_id"] = matches[0]["id"]
        store.save(date, record)
    verify_post(facebook, record)
    store.save(date, record)


def pipeline_facebook(date=None, mode="live"):
    verify_repository(remote=True)
    date = date or today()
    stage, record = "Facebook storage", None
    store = Store()
    try:
        stage = "Facebook validation"
        record = checked_batch(store, date)
        state = record["state"].setdefault("platforms", {}).setdefault("facebook", {})
        output = ROOT / "build" / date
        if mode not in ("live", "reconcile"):
            raise ValueError("Facebook supports live publishing or read-only reconciliation")
        config = store.call("GET", "/v1/config")
        if mode == "live" and (os.getenv("FACEBOOK_POSTING_ENABLED") != "true" or not config.get("daily_enabled") or not config.get("daily_authorized") or not publication_monitoring_ready(config)):
            raise ValueError("Facebook authorization/activation or reviewed daily preparation is incomplete")
        if state.get("verified"):
            write_json(output / "facebook-result.json", {"batch": date, "status": "confirmed published", "permalink": state["permalink"]})
            return state
        if mode == "live" and state.get("publish_intent"):
            raise ValueError("Previous Facebook outcome is uncertain; use read-only reconciliation before any further attempt")
        stage = "Facebook authorization"
        facebook = Facebook()
        facebook.verify_page()
        if state.get("page_id") and state["page_id"] != facebook.page_id:
            raise ValueError("This batch already belongs to a different confirmed Facebook Page ID")
        state.update(run_url=os.getenv("GITHUB_RUN_URL"), page_id=facebook.page_id)
        store.save(date, record)
        if mode == "reconcile":
            stage = "Facebook publication verification"
            reconcile(facebook, store, date, record)
        else:
            output = artwork(store, date, record)
            for card in record["package"]["cards"]:
                kind = card["kind"]
                item = state.setdefault("cards", {}).setdefault(kind, {})
                if item.get("photo_id"):
                    continue
                if item.get("upload_intent"):
                    raise ValueError("Facebook photo upload outcome is uncertain; inspect saved state, do not silently upload again")
                shared = record["state"]["cards"][kind]
                stage = "Facebook storage"
                if not shared.get("public_url"):
                    shared["public_url"] = store.expose(date, kind + "-card.jpg")
                    store.save(date, record)
                if request("GET", shared["public_url"], raw=True) != (output / (kind + "-card.jpg")).read_bytes():
                    raise ValueError("Facebook image bytes differ from the reviewed renderer output")
                stage = "Facebook photo upload"
                item.update(upload_intent=True, upload_intent_at=datetime.now(timezone.utc).isoformat())
                store.save(date, record)
                item["photo_id"] = facebook.photo(shared["public_url"], card["alt_text"])
                store.save(date, record)
            stage = "Facebook publishing"
            state.update(publish_intent=True, publish_intent_at=datetime.now(timezone.utc).isoformat())
            store.save(date, record)
            state["post_id"] = facebook.publish([state["cards"][c["kind"]]["photo_id"] for c in record["package"]["cards"]], caption(record["package"]))
            store.save(date, record)
            stage = "Facebook publication verification"
            verify_post(facebook, record)
            store.save(date, record)
        state.pop("failed_stage", None)
        state.pop("last_error", None)
        store.save(date, record)
        write_json(output / "facebook-result.json", {"batch": date, "status": "confirmed published", "permalink": state["permalink"]})
        return state
    except Exception as error:
        stage = getattr(error, "stage", None) or stage
        state = record["state"].get("platforms", {}).get("facebook", {}) if record else {}
        status = "confirmed published" if state.get("verified") else "published; verification pending" if state.get("post_id") else "uncertain" if state.get("publish_intent") else "nothing published to Facebook"
        message = redact(error)
        if record:
            state.update(failed_stage=stage, last_error=message)
            try: store.save(date, record)
            except Exception: pass
        report = failure(date, stage, message, status, os.getenv("GITHUB_RUN_URL"))
        try: store.call("POST", "/v1/events", {"date": date, "stage": stage, "error": message, "publication": status, "run_url": os.getenv("GITHUB_RUN_URL")})
        except Exception: pass
        print(report)
        raise RuntimeError("Facebook pipeline failed at " + stage) from None


def export_tiktok(date=None):
    verify_repository(remote=True)
    date = date or today()
    store = Store()
    record = checked_batch(store, date)
    output = artwork(store, date, record, vertical=True)
    # No answer key or private review is included in the manual posting package.
    (output / "tiktok-caption.txt").write_text(caption(record["package"]) + "\n", encoding="utf-8")
    write_json(output / "tiktok-result.json", {"batch": date, "status": "vertical cards ready; manual TikTok publication required", "size": [1080, 1920], "files": [c["kind"] + "-tiktok.jpg" for c in record["package"]["cards"]], "published": False})
    return {"status": "vertical cards ready; manual TikTok publication required", "published": False}

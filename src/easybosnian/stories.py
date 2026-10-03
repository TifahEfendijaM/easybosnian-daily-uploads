"""Instagram Stories from the exact published slides; Highlights stay manual."""
import os
from datetime import datetime, timezone
from urllib.parse import urlparse

from PIL import Image

from .artwork import artwork
from .core import ROOT, today, verify_repository, write_json, read_json, publication_monitoring_ready
from .facebook import checked_batch
from .http import redact, request
from .meta import Instagram
from .notify import failure
from .store import Store


HIGHLIGHTS = {"quiz": "Pitanje dana", "lesson": "Znaš li?", "word": "Riječ dana"}


def story_image(source, destination, palette):
    """Pad the published slide, preserving every pixel, word and its watermark."""
    with Image.open(source) as image:
        if image.size != (1080, 1350):
            raise ValueError("Story source must be the exact 1080×1350 published slide")
        canvas = Image.new("RGB", (1080, 1920), palette["panel"])
        canvas.paste(image.convert("RGB"), (0, 285))
        canvas.save(destination, "JPEG", quality=94, subsampling=0, optimize=True)


def verify_story(ig, item):
    actual = ig.story_media(item["media_id"])
    owned = ig.stories()
    if actual.get("id") != item["media_id"] or actual.get("media_type") != "IMAGE" or actual.get("media_product_type") != "STORY":
        raise ValueError("Instagram did not return the expected published image Story")
    if not any(str(s.get("id")) == item["media_id"] for s in owned.get("data", [])):
        raise ValueError("Published Story is not visible on the authorized @easy_bosnian account; no repost will be attempted")
    parsed = urlparse(actual.get("permalink", ""))
    if parsed.scheme != "https" or parsed.hostname != "www.instagram.com" or not parsed.path.startswith("/stories/"):
        raise ValueError("Instagram has not returned an actual Story permalink")
    item.update(verified=True, permalink=actual["permalink"], verified_at=datetime.now(timezone.utc).isoformat(), highlight_status="manual action required")


def pipeline_stories(date=None, mode="live"):
    verify_repository(remote=True)
    date = date or today()
    stage, record = "Instagram Stories validation", None
    store = Store()
    try:
        record = checked_batch(store, date)
        if mode == "live" and os.getenv("INSTAGRAM_STORY_MODE", "native_reshare_manual") != "image":
            raise ValueError("Native post resharing requires the Instagram app; standalone image Stories were superseded by the user's request")
        if mode not in ("live", "reconcile") or not record["state"].get("verified"):
            raise ValueError("Stories require independently confirmed publication of this exact three-slide Instagram post")
        state = record["state"].setdefault("platforms", {}).setdefault("instagram_stories", {})
        config = store.call("GET", "/v1/config")
        if mode == "live" and (os.getenv("INSTAGRAM_STORIES_ENABLED") != "true" or not config.get("daily_enabled") or not config.get("daily_authorized") or not publication_monitoring_ready(config)):
            raise ValueError("Daily Story publishing has not been activated")
        stage = "Instagram Stories authorization"
        ig = Instagram(); ig.refresh_if_needed(); ig.verify_account()
        output = ROOT / "build" / date
        if not state.get("verified"):
            if mode == "live":
                output = artwork(store, date, record)
                palette = read_json(ROOT / "data/design-palettes.json")[record["package"]["design_palette"]]
            for card in record["package"]["cards"]:
                kind = card["kind"]
                item = state.setdefault("cards", {}).setdefault(kind, {})
                item["highlight"] = HIGHLIGHTS[kind]
                if item.get("verified"):
                    continue
                if not item.get("media_id"):
                    if mode == "reconcile" or item.get("publish_intent"):
                        raise ValueError("Story publication ID is missing or its response was uncertain; inspect Instagram manually, never blindly repost")
                    stage = "Instagram Stories rendering"
                    rendered = output / (kind + "-story.jpg")
                    if item.get("render_saved"):
                        rendered.write_bytes(store.get_file(date, rendered.name))
                    else:
                        story_image(output / (kind + "-card.jpg"), rendered, palette)
                        store.put_file(date, rendered.name, rendered.read_bytes())
                        item["render_saved"] = True
                        store.save(date, record)
                    if not item.get("public_url"):
                        item["public_url"] = store.expose(date, rendered.name)
                        store.save(date, record)
                    if request("GET", item["public_url"], raw=True) != rendered.read_bytes():
                        raise ValueError("Story bytes differ from the exact padded published slide")
                    stage = "Instagram Stories publishing"
                    if not item.get("container_id"):
                        item["container_id"] = ig.story(item["public_url"])
                        store.save(date, record)
                    ig.ready(item["container_id"])
                    item.update(publish_intent=True, publish_intent_at=datetime.now(timezone.utc).isoformat())
                    state["publish_intent"] = True
                    store.save(date, record)
                    item["media_id"] = ig.publish(item["container_id"])
                    store.save(date, record)
                stage = "Instagram Stories verification"
                verify_story(ig, item)
                store.save(date, record)
            state.update(verified=True, verified_at=datetime.now(timezone.utc).isoformat())
            state.pop("failed_stage", None); state.pop("last_error", None)
            store.save(date, record)
        highlights = [{"slide": c["kind"], "highlight": HIGHLIGHTS[c["kind"]], "story_id": state["cards"][c["kind"]]["media_id"], "story_permalink": state["cards"][c["kind"]]["permalink"], "status": "manual action required"} for c in record["package"]["cards"]]
        write_json(output / "instagram-stories-result.json", {"batch": date, "status": "three Stories confirmed published; Highlights need manual addition", "stories": highlights, "highlights_automated": False})
        return {"status": "three Stories confirmed published; Highlights need manual addition", "verified": True}
    except Exception as error:
        stage = getattr(error, "stage", None) or stage
        state = record["state"].get("platforms", {}).get("instagram_stories", {}) if record else {}
        cards = state.get("cards", {}).values()
        status = "all three Stories confirmed published" if state.get("verified") else "partial/uncertain; inspect saved Story IDs" if any(c.get("publish_intent") for c in cards) else "nothing published to Stories"
        message = redact(error)
        if record:
            state.update(failed_stage=stage, last_error=message)
            try: store.save(date, record)
            except Exception: pass
        print(failure(date, stage, message, status, os.getenv("GITHUB_RUN_URL")))
        raise RuntimeError("Instagram Stories failed at " + stage) from None

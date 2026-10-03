"""TikTok publishing through the user's Free Buffer account; no TikTok app/client."""
import os
import re
import time
from datetime import datetime, timezone
from urllib.parse import urlparse

from .artwork import artwork
from .core import ROOT, gh, today, verify_repository, write_json, publication_monitoring_ready
from .facebook import checked_batch
from .http import SafeError, redact, request
from .notify import failure
from .store import Store


TARGET = "easy.bosnian"
CHANNEL_FIELDS = """id name service serviceId organizationId externalLink scopes
    isDisconnected isLocked isQueuePaused
    metadata { ... on TiktokMetadata { defaultToReminders } }"""
POST_FIELDS = """id channelId channelService text status schedulingType externalLink createdAt sentAt
    assets { id mimeType source }"""


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r"[a-f0-9]{24}", value):
        raise ValueError("Buffer requires a confirmed 24-character channel/organization/post ID")
    return value


def caption(package):
    # TikTok allows five hashtags. Select only already-reviewed public hashtags.
    text = package["caption"] + "\n\n" + " ".join(package["hashtags"][:5])
    if len(text) > 2200:
        raise ValueError("Reviewed TikTok caption exceeds 2200 characters; do not truncate it")
    return text


class Buffer:
    def __init__(self, key=None, channel_id=None, organization_id=None):
        self.key = key or os.environ["BUFFER_API_KEY"]
        self.channel_id = channel_id or os.getenv("BUFFER_TIKTOK_CHANNEL_ID", "")
        self.organization_id = organization_id or os.getenv("BUFFER_ORGANIZATION_ID", "")
        if not self.key.strip():
            raise ValueError("Missing protected Buffer API key")

    def call(self, query, variables=None):
        result = request("POST", "https://api.buffer.com", {"query": query, "variables": variables or {}},
                         headers={"Authorization": "Bearer " + self.key}, timeout=45)
        # GraphQL errors can echo credentials or public/private content. Never print them.
        if not isinstance(result, dict) or result.get("errors") or not isinstance(result.get("data"), dict):
            raise SafeError("Buffer API rejected the operation; inspect API access, quota and channel permissions")
        return result["data"]

    def discover(self):
        orgs = self.call("query { account { organizations { id } } }")["account"]["organizations"]
        matches = []
        for org in orgs:
            org_id = identifier(org["id"])
            channels = self.call("query($input: ChannelsInput!) { channels(input:$input) { " + CHANNEL_FIELDS + " } }",
                                 {"input": {"organizationId": org_id}})["channels"]
            matches.extend(c for c in channels if c.get("service") == "tiktok" and c.get("name", "").lstrip("@").lower() == TARGET)
        if len(matches) != 1:
            raise ValueError("Buffer must contain exactly one connected @easy.bosnian TikTok channel")
        self.channel_id = identifier(matches[0]["id"])
        self.organization_id = identifier(matches[0]["organizationId"])
        return self.verify_channel()

    def verify_channel(self):
        identifier(self.channel_id); identifier(self.organization_id)
        actual = self.call("query($input: ChannelInput!) { channel(input:$input) { " + CHANNEL_FIELDS + " } }",
                           {"input": {"id": self.channel_id}})["channel"]
        if (actual.get("id") != self.channel_id or actual.get("organizationId") != self.organization_id
                or actual.get("service") != "tiktok" or actual.get("name", "").lstrip("@").lower() != TARGET
                or not actual.get("serviceId")):
            raise ValueError("Buffer channel does not match the confirmed @easy.bosnian TikTok identity")
        if any(actual.get(k) is not False for k in ("isDisconnected", "isLocked", "isQueuePaused")):
            raise ValueError("Buffer TikTok channel is disconnected, locked or paused; repair the connection in Buffer")
        if (actual.get("metadata") or {}).get("defaultToReminders") is not False:
            raise ValueError("Disable default notification publishing in Buffer before automatic TikTok publishing")
        if not {"user.info.basic", "user.info.username", "video.publish", "video.list"}.issubset(set(actual.get("scopes", []))):
            raise ValueError("Buffer has not confirmed TikTok identity, direct publishing and public-post permissions")
        return actual

    def create(self, text, urls):
        if len(urls) != 3 or len(set(urls)) != 3:
            raise ValueError("TikTok requires the three distinct reviewed images in order")
        result = self.call("mutation($input: CreatePostInput!) { createPost(input:$input) { __typename "
                           "... on PostActionSuccess { post { " + POST_FIELDS + " } } "
                           "... on MutationError { __typename } } }", {"input": {
                               "channelId": self.channel_id, "text": text, "schedulingType": "automatic",
                               "mode": "shareNow", "needsApproval": False, "saveToDraft": False, "aiAssisted": True,
                               "assets": [{"image": {"url": url}} for url in urls]}})["createPost"]
        if result.get("__typename") != "PostActionSuccess" or not result.get("post", {}).get("id"):
            raise SafeError("Buffer did not accept automatic TikTok publishing; inspect its channel/plan restrictions; no retry")
        return result["post"]

    def post(self, post_id):
        identifier(post_id)
        return self.call("query($input: PostInput!) { post(input:$input) { " + POST_FIELDS + " } }",
                         {"input": {"id": post_id}})["post"]

    def recent(self):
        return self.call("query($input: PostsInput!) { posts(first:100,input:$input) { "
                         "edges { node { " + POST_FIELDS + " } } pageInfo { hasNextPage } } }", {"input": {
                             "organizationId": self.organization_id,
                             "filter": {"channelIds": [self.channel_id]},
                             "sort": [{"field": "createdAt", "direction": "desc"}]}})["posts"]


def checked_post(buffer, record, actual, capture=False):
    state = record["state"]["platforms"]["tiktok"]
    if (actual.get("id") != state.get("post_id") or actual.get("channelId") != buffer.channel_id
            or actual.get("channelService") != "tiktok" or actual.get("text") != caption(record["package"])
            or actual.get("schedulingType") != "automatic"):
        raise ValueError("Buffer post identity, caption or automatic publishing differs from the reviewed batch")
    assets = actual.get("assets", [])
    if len(assets) != 3 or any(not a.get("mimeType", "").startswith("image/") or not a.get("source") for a in assets):
        raise ValueError("Buffer post does not contain three identified image assets")
    if capture:
        if [a["source"] for a in assets] != state["image_urls"]:
            raise ValueError("Buffer's submitted image URLs differ from the three reviewed cards in order")
        # The official Asset interface permits a null ID for remote media.
        # In that case the exact source URL is the stable image identity.
        state["asset_ids"] = [a.get("id") for a in assets]
    else:
        expected = state.get("asset_ids", [])
        if len(expected) != 3 or any(
                a.get("id") != asset_id if asset_id else a["source"] != url
                for a, asset_id, url in zip(assets, expected, state["image_urls"])):
            raise ValueError("Buffer post image identities or order have changed")
    return state


def verify_post(buffer, store, date, record, actual):
    state = checked_post(buffer, record, actual)
    state["buffer_status"] = actual["status"]
    if actual["status"] == "error":
        raise ValueError("Buffer reports TikTok publication failed; inspect the post in Buffer; no retry")
    if actual["status"] not in ("scheduled", "sending", "sent"):
        raise ValueError("TikTok post is a draft or needs approval instead of automatic publication")
    if actual["status"] != "sent" or not actual.get("externalLink"):
        store.save(date, record)
        return False
    parsed = urlparse(actual["externalLink"])
    if (parsed.scheme != "https" or parsed.hostname not in ("www.tiktok.com", "tiktok.com")
            or not re.fullmatch(r"/@easy\.bosnian/(photo|video)/[0-9]+/?", parsed.path)
            or not actual.get("sentAt")):
        raise ValueError("Buffer has not returned an actual @easy.bosnian TikTok publication permalink")
    state.update(verified=True, permalink=actual["externalLink"], verified_by="Buffer API sent status and asset read-back",
                 verified_at=datetime.now(timezone.utc).isoformat())
    store.save(date, record)
    return True


def reconcile(buffer, store, date, record):
    state = record["state"]["platforms"]["tiktok"]
    if not state.get("publish_intent"):
        raise ValueError("No TikTok submission intent exists to reconcile")
    if not state.get("post_id"):
        recent = buffer.recent()
        if recent.get("pageInfo", {}).get("hasNextPage"):
            raise ValueError("Buffer reconciliation exceeds one page; inspect Buffer manually without reposting")
        intent = datetime.fromisoformat(state["publish_intent_at"])
        matches = [e["node"] for e in recent["edges"] if e["node"].get("text") == caption(record["package"])
                   and e["node"].get("channelId") == buffer.channel_id
                   and datetime.fromisoformat(e["node"]["createdAt"].replace("Z", "+00:00")) >= intent
                   and [a.get("source") for a in e["node"].get("assets", [])] == state["image_urls"]]
        if len(matches) != 1:
            raise ValueError("TikTok submission remains uncertain; no new Buffer post will be created")
        state["post_id"] = identifier(matches[0]["id"])
        checked_post(buffer, record, matches[0], capture=True)
        store.save(date, record)
    actual = buffer.post(state["post_id"])
    if not state.get("asset_ids"):
        checked_post(buffer, record, actual, capture=True)
        store.save(date, record)
    return verify_post(buffer, store, date, record, actual)


def pipeline_tiktok(date=None, mode="reconcile"):
    verify_repository(remote=True)
    date = date or today()
    stage, record = "TikTok storage", None
    store = Store()
    try:
        stage = "TikTok validation"
        record = checked_batch(store, date)
        state = record["state"].setdefault("platforms", {}).setdefault("tiktok", {})
        if mode not in ("live", "reconcile"):
            raise ValueError("TikTok supports live publishing or read-only reconciliation")
        config = store.call("GET", "/v1/config")
        if mode == "live" and (os.getenv("TIKTOK_POSTING_ENABLED") != "true" or not config.get("daily_enabled")
                               or not config.get("daily_authorized") or not publication_monitoring_ready(config)):
            raise ValueError("Buffer TikTok authorization/activation or reviewed preparation is incomplete")
        stage = "TikTok authorization"
        buffer = Buffer()
        account = buffer.verify_channel()
        if state.get("channel_id") and (state["channel_id"] != buffer.channel_id or state.get("service_id") != account["serviceId"]):
            raise ValueError("This TikTok batch already belongs to another confirmed account")
        state.update(channel_id=buffer.channel_id, service_id=account["serviceId"], run_url=os.getenv("GITHUB_RUN_URL"))
        store.save(date, record)
        if state.get("verified"):
            if not verify_post(buffer, store, date, record, buffer.post(state["post_id"])):
                raise ValueError("Previously confirmed TikTok post is no longer confirmed by Buffer; inspect it manually")
        elif mode == "reconcile":
            stage = "TikTok publication verification"
            if not reconcile(buffer, store, date, record):
                raise ValueError("Buffer has not confirmed TikTok publication; submission is retained without reposting")
        else:
            if state.get("publish_intent") and not state.get("post_id"):
                raise ValueError("Previous TikTok submission is uncertain; use read-only reconciliation")
            if not state.get("post_id"):
                text = caption(record["package"])
                output = artwork(store, date, record)
                urls = []
                for card in record["package"]["cards"]:
                    kind = card["kind"]
                    shared = record["state"]["cards"][kind]
                    stage = "TikTok storage"
                    if not shared.get("public_url"):
                        shared["public_url"] = store.expose(date, kind + "-card.jpg")
                        store.save(date, record)
                    if request("GET", shared["public_url"], raw=True) != (output / (kind + "-card.jpg")).read_bytes():
                        raise ValueError("TikTok image bytes differ from the reviewed renderer output")
                    urls.append(shared["public_url"])
                stage = "TikTok publishing"
                state.update(publish_intent=True, publish_intent_at=datetime.now(timezone.utc).isoformat(), image_urls=urls)
                store.save(date, record)
                actual = buffer.create(text, urls)
                state["post_id"] = identifier(actual["id"])
                # Save the returned ID even if later asset/content verification fails.
                store.save(date, record)
                checked_post(buffer, record, actual, capture=True)
                store.save(date, record)
            stage = "TikTok publication verification"
            # Read-only polling of one accepted submission is not a scheduled retry.
            for attempt in range(13):
                if verify_post(buffer, store, date, record, buffer.post(state["post_id"])):
                    break
                if attempt == 12:
                    raise ValueError("Buffer accepted the post but has not confirmed TikTok publication within four minutes; inspect the saved ID; no repost")
                time.sleep(20)
        state.pop("failed_stage", None); state.pop("last_error", None)
        state["status"] = "Buffer-confirmed TikTok publication"
        store.save(date, record)
        write_json(ROOT / "build" / date / "tiktok-result.json", {"batch": date, "status": state["status"],
                   "post_id": state["post_id"], "permalink": state["permalink"], "verified_by": state["verified_by"]})
        return state
    except Exception as error:
        stage = getattr(error, "stage", None) or stage
        state = record["state"].get("platforms", {}).get("tiktok", {}) if record else {}
        status = "Buffer-confirmed published" if state.get("verified") else "Buffer accepted; TikTok publication unconfirmed" if state.get("post_id") else "uncertain submission" if state.get("publish_intent") else "nothing submitted to TikTok"
        message = redact(error)
        if record:
            state.update(failed_stage=stage, last_error=message)
            try: store.save(date, record)
            except Exception: pass
        report = failure(date, stage, message, status, os.getenv("GITHUB_RUN_URL"))
        try: store.call("POST", "/v1/events", {"date": date, "stage": stage, "error": message, "publication": status, "run_url": os.getenv("GITHUB_RUN_URL")})
        except Exception: pass
        write_json(ROOT / "build" / date / "tiktok-result.json", {"batch": date, "status": status,
                   "failed_stage": stage, "post_id": state.get("post_id"), "error": message})
        print(report)
        raise RuntimeError("TikTok pipeline failed at " + stage) from None

"""Inspect or reconcile an existing Buffer submission; never create a post."""
import argparse
import hashlib
import io
import json
from urllib.parse import urlparse

from PIL import Image

from easybosnian.buffer import Buffer, caption, pipeline_tiktok
from easybosnian.core import ROOT, verify_repository, write_json
from easybosnian.facebook import checked_batch
from easybosnian.http import request
from easybosnian.store import Store


def inspect(date):
    verify_repository(remote=True)
    store = Store()
    record = checked_batch(store, date)
    state = record["state"].get("platforms", {}).get("tiktok", {})
    if not state.get("post_id"):
        raise ValueError("No accepted Buffer post ID exists; inspection cannot submit a post")
    buffer = Buffer()
    buffer.verify_channel()
    actual = buffer.post(state["post_id"])
    assets = []
    expected = [hashlib.sha256(store.get_file(date, c["kind"] + "-card.jpg")).hexdigest()
                for c in record["package"]["cards"]]
    for asset in actual.get("assets", []):
        source = urlparse(asset["source"])
        body = request("GET", asset["source"], raw=True)
        decoded = Image.open(io.BytesIO(body))
        assets.append({"id": asset.get("id"), "source_host": source.hostname,
                       "source_path": source.path, "source_has_query": bool(source.query),
                       "sha256": hashlib.sha256(body).hexdigest(), "size": decoded.size})
    result = {"date": date, "post_id": state["post_id"], "status": actual.get("status"),
              "channel_matches": actual.get("channelId") == buffer.channel_id,
              "caption_matches": actual.get("text") == caption(record["package"]),
              "scheduling_type": actual.get("schedulingType"), "sent_at": actual.get("sentAt"),
              "permalink": actual.get("externalLink"), "assets": assets,
              "expected_sha256": expected,
              "exact_ordered_bytes_match": [a["sha256"] for a in assets] == expected,
              "operation": "read-only; no post created or edited"}
    write_json(ROOT / "build" / date / "tiktok-inspection.json", result)
    print(json.dumps(result, indent=2))


def capabilities(date):
    """Read the confirmed channel's content types; never submit a Story probe."""
    verify_repository(remote=True)
    buffer = Buffer()
    buffer.verify_channel()
    config = buffer.call(
        "query($input: ConfigurationInput!) { configuration(input:$input) { channels { "
        "channelId service channelType content { configurationContentTypes supportedProperties } "
        "} } }", {"input": {"organizationId": buffer.organization_id}})["configuration"]
    matches = [c for c in config["channels"] if c.get("channelId") == buffer.channel_id]
    if len(matches) != 1 or matches[0].get("service") != "tiktok":
        raise ValueError("Buffer configuration did not identify the confirmed TikTok channel")
    channel = matches[0]
    types = sorted({t for c in channel["content"] for t in c["configurationContentTypes"]})
    result = {"date": date, "account": "@easy.bosnian", "channel_id": buffer.channel_id,
              "channel_type": channel["channelType"], "content_types": types,
              "content": channel["content"], "story_configuration_exposed": "story" in types,
              "feed_post_configuration_exposed": "post" in types,
              "note": "Experimental catalog can omit working feed publishing; absence alone does not prove API support or non-support.",
              "operation": "read-only capability query; no post created or edited"}
    write_json(ROOT / "build" / date / "tiktok-capabilities.json", result)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["inspect", "reconcile", "capabilities"])
    parser.add_argument("date")
    args = parser.parse_args()
    if args.mode == "inspect":
        inspect(args.date)
    elif args.mode == "capabilities":
        capabilities(args.date)
    else:
        pipeline_tiktok(args.date, "reconcile")

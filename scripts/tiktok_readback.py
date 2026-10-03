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


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["inspect", "reconcile"])
    parser.add_argument("date")
    args = parser.parse_args()
    if args.mode == "inspect":
        inspect(args.date)
    else:
        pipeline_tiktok(args.date, "reconcile")

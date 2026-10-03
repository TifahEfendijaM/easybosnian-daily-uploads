"""One handoff, sequential cache writers, independent platform outcomes."""
import os

from .core import ROOT, today, write_json
from .facebook import pipeline_facebook, export_tiktok
from .http import redact
from .pipeline import pipeline
from .stories import pipeline_stories
from .buffer import pipeline_tiktok


def daily(date=None, mode="preview"):
    date = date or today()
    if mode != "live":
        return pipeline(date, mode)
    results, failed = {}, []
    operations = [("instagram", lambda: pipeline(date, "live"))]
    if os.getenv("FACEBOOK_POSTING_ENABLED") == "true":
        operations.append(("facebook", lambda: pipeline_facebook(date, "live")))
    else:
        results["facebook"] = {"status": "disabled pending Page authorization", "published": False}
    if os.getenv("TIKTOK_POSTING_ENABLED") == "true":
        operations.append(("tiktok", lambda: pipeline_tiktok(date, "live")))
    elif os.getenv("TIKTOK_EXPORT_ENABLED") == "true":
        operations.append(("tiktok", lambda: export_tiktok(date)))
    else:
        results["tiktok"] = {"status": "export disabled", "published": False}
    for name, operation in operations:
        try:
            state = operation()
            results[name] = {"status": state.get("status", "confirmed published" if state.get("verified") else "completed"), "permalink": state.get("permalink"), "published": state.get("verified", False)}
        except Exception as error:
            failed.append(name)
            results[name] = {"status": "failed; inspect platform diagnostics", "error": redact(error)}
    if os.getenv("INSTAGRAM_STORIES_ENABLED") == "true":
        if results["instagram"].get("published"):
            try:
                state = pipeline_stories(date, "live")
                results["instagram_stories"] = {"status": state["status"], "published": state["verified"], "highlights": "manual addition required"}
            except Exception as error:
                failed.append("instagram_stories")
                results["instagram_stories"] = {"status": "failed; inspect saved Story IDs", "error": redact(error)}
        else:
            results["instagram_stories"] = {"status": "waiting for verified Instagram carousel", "published": False}
    write_json(ROOT / "build" / date / "platforms-result.json", {"batch": date, "platforms": results})
    if failed:
        raise RuntimeError("Daily batch failed for: " + ", ".join(failed) + "; inspect each independent platform outcome")
    return results

"""Allow only a real reviewed daily package to start the completion-based publisher."""
import os
import re
from pathlib import Path

from .core import REPO, ROOT, read_json, today, verify_repository


def reviewed_result(result, date):
    # Connection checks and already-published batches deliberately have no handoff.
    if result.get("status") == "already verified published; preparation unchanged":
        return None
    if result.get("status") != "reviewed JSON saved and read back":
        raise ValueError("No real reviewed preparation result exists; publishing is not due")
    if result.get("date") != date or not re.fullmatch(r"\d{4}-\d{2}-\d{2}",date):
        raise ValueError("Automatic handoff must use today's Sarajevo batch")
    if result.get("scheduled_pipeline_enabled") is not True:
        raise ValueError("The verified daily publication gate is not enabled")
    package_hash=result.get("package_hash", "")
    if not isinstance(package_hash,str) or not re.fullmatch(r"[a-f0-9]{64}",package_hash):
        raise ValueError("Preparation did not return a valid immutable package hash")
    if result.get("queue_url") != f"https://github.com/{REPO}/blob/main/queue/{date}.json":
        raise ValueError("Preparation queue proof belongs to a different repository or date")
    return {"batch_date":date,"package_hash":package_hash}


def main():
    verify_repository(remote=True)
    if os.getenv("GITHUB_ACTIONS") != "true" or os.getenv("GITHUB_EVENT_NAME") != "schedule":
        raise ValueError("Only successful scheduled preparation can approve an automatic handoff")
    event=read_json(os.environ["GITHUB_EVENT_PATH"])
    if event.get("schedule") != "0 20 * * *":
        raise ValueError("Preparation schedule does not match the current daily authorization")
    approved=reviewed_result(read_json(ROOT/"build/preparation-result.json"),today())
    if approved is None:
        print("This batch is already verified published; no second pipeline is due")
        return
    with Path(os.environ["GITHUB_OUTPUT"]).open("a",encoding="utf-8") as output:
        for key,value in approved.items():
            output.write(f"{key}={value}\n")
    print(f"Batch {approved['batch_date']} saved and read back; publication follows successful preparation and a three-minute wait")


if __name__=="__main__":
    main()

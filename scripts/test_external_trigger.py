"""Manually verify the deployed Worker dispatch path; cannot prepare or publish."""
import json
from easybosnian.cli import load_env
from easybosnian.core import verify_repository
from easybosnian.store import Store


if __name__ == "__main__":
    load_env()
    verify_repository(remote=True)
    result = Store().call("POST", "/v1/scheduler/verify", {})
    if result.get("github_status") != 204 or result.get("mode") != "verify":
        raise RuntimeError("Worker did not confirm the expected verify-only dispatch")
    print(json.dumps(result, indent=2))
    print("Request accepted, not workflow completion. Check the new verify run in this exact repository; the render/publish step must be skipped.")

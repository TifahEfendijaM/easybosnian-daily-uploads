import json
import os
import re
import time
from datetime import datetime, timezone
from urllib.parse import urlencode

from .core import REPO, gh, verify_repository
from .http import request


class Instagram:
    def __init__(self, token=None, user_id=None):
        self.token = token or os.environ["INSTAGRAM_ACCESS_TOKEN"]
        self.user_id = user_id if user_id is not None else os.environ["INSTAGRAM_USER_ID"]
        version = os.environ["META_GRAPH_VERSION"]
        if not re.fullmatch(r"v\d+\.0", version):
            raise ValueError("META_GRAPH_VERSION must be a verified supported API version")
        self.base = f"https://graph.instagram.com/{version}"

    def call(self, method, path, values=None):
        url = self.base + "/" + path
        headers = {"Authorization": "Bearer " + self.token}
        if method == "GET":
            return request(method, url + "?" + urlencode(values or {}), headers=headers)
        return request(method, url, headers=headers, form=values or {})

    def verify_account(self):
        info = self.call("GET", "me", {"fields": "user_id,username,account_type"})
        if "data" in info:
            if len(info["data"]) != 1: raise ValueError("Expected exactly one authorized Instagram account")
            info = info["data"][0]
        account_id = str(info.get("user_id", info.get("id", "")))
        if info.get("username", "").casefold() != "easy_bosnian" or not account_id or (self.user_id and account_id != str(self.user_id)):
            raise ValueError("Authorized Instagram account is not the expected @easy_bosnian and user ID")
        if info.get("account_type", "").upper() not in ("BUSINESS", "MEDIA_CREATOR"):
            raise ValueError("Instagram account must be a professional Business or Creator account")
        self.user_id = account_id
        return info

    def refresh_if_needed(self):
        issued = datetime.fromisoformat(os.environ["INSTAGRAM_TOKEN_ISSUED_AT"].replace("Z", "+00:00"))
        age = (datetime.now(timezone.utc) - issued).total_seconds()
        if age < 0:
            raise ValueError("Invalid token issuance date")
        if age >= 60 * 86400:
            raise ValueError("Instagram token expired or too near expiry; reauthorize before posting")
        if age < 40 * 86400:
            return
        if not os.getenv("GH_SECRETS_TOKEN"):
            raise ValueError("Token refresh is due; configure the repository-scoped secrets writer")
        # Meta requires an unexpired long-lived token that is at least 24 hours old.
        refreshed = request("GET", "https://graph.instagram.com/refresh_access_token?" + urlencode({"grant_type": "ig_refresh_token", "access_token": self.token}))
        new_token = refreshed["access_token"]
        # Persist immediately, without ever printing the new token. gh encrypts GitHub secrets.
        original = os.environ.get("GH_TOKEN")
        os.environ["GH_TOKEN"] = os.environ["GH_SECRETS_TOKEN"]
        try:
            gh("secret", "set", "INSTAGRAM_ACCESS_TOKEN", "--repo", REPO, input_text=new_token)
            stamp = datetime.now(timezone.utc).isoformat()
            gh("secret", "set", "INSTAGRAM_TOKEN_ISSUED_AT", "--repo", REPO, input_text=stamp)
        finally:
            if original is None:
                os.environ.pop("GH_TOKEN", None)
            else:
                os.environ["GH_TOKEN"] = original
        self.token = new_token

    def child(self, url, alt):
        return self.call("POST", self.user_id + "/media", {"image_url": url, "is_carousel_item": "true", "alt_text": alt})["id"]

    def ready(self, container):
        # Read-only status polling within one run, never another scheduled attempt.
        for _ in range(12):
            result = self.call("GET", container, {"fields": "status_code"})
            status = result.get("status_code")
            if status in ("FINISHED", "PUBLISHED"):
                return status
            if status in ("ERROR", "EXPIRED"):
                raise ValueError(f"Instagram media container is {status}; inspect the saved container ID")
            time.sleep(5)
        raise ValueError("Instagram container is still processing; deliberately rerun later after inspecting state")

    def carousel(self, children, caption):
        return self.call("POST", self.user_id + "/media", {"media_type": "CAROUSEL", "children": ",".join(children), "caption": caption})["id"]

    def publish(self, container):
        return self.call("POST", self.user_id + "/media_publish", {"creation_id": container})["id"]

    def media(self, media_id):
        return self.call("GET", media_id, {"fields": "id,permalink,caption,media_type,children{id,media_type}"})

    def recent(self):
        return self.call("GET", self.user_id + "/media", {"fields": "id,caption,permalink,timestamp,media_type", "limit": 50})["data"]


class Facebook:
    """Independent Pages authorization, deliberately unused by the Instagram pipeline."""
    def __init__(self):
        self.token = os.environ["FACEBOOK_PAGE_TOKEN"]
        self.page_id = os.environ["FACEBOOK_PAGE_ID"]
        self.base = "https://graph.facebook.com/" + os.environ["META_GRAPH_VERSION"]

    def verify_page(self):
        page = request("GET", self.base + "/" + self.page_id + "?fields=id,name", headers={"Authorization": "Bearer " + self.token})
        if page["id"] != self.page_id or page["name"] != "EasyBosnian":
            raise ValueError("Facebook token does not authorize the exact selected EasyBosnian Page")
        return page

import os
from urllib.parse import urlparse

from .http import request


class Store:
    def __init__(self):
        self.url = os.environ["EASYBOSNIAN_WORKER_URL"].rstrip("/")
        if urlparse(self.url).scheme != "https":
            raise ValueError("Cloudflare endpoint must use HTTPS")
        self.headers = {"Authorization": "Bearer " + os.environ["EASYBOSNIAN_ADMIN_TOKEN"]}

    def call(self, method, path, data=None, raw=False, headers=None):
        return request(method, self.url + path, data, {**self.headers, **(headers or {})}, raw=raw)

    def history(self):
        return self.call("GET", "/v1/history")

    def batch(self, date):
        return self.call("GET", f"/v1/batches/{date}")

    def save(self, date, record):
        result = self.call("PATCH", f"/v1/batches/{date}", {"revision": record["revision"], "state": record["state"]})
        record["revision"] = result["revision"]

    def get_file(self, date, name):
        return self.call("GET", f"/v1/private/{date}/{name}", raw=True)

    def put_file(self, date, name, body):
        return self.call("PUT", f"/v1/private/{date}/{name}", body, headers={"Content-Type": "image/jpeg"})

    def expose(self, date, name):
        return self.call("POST", f"/v1/expose/{date}/{name}")["url"]


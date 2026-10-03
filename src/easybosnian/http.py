import json
import os
import re
import ssl
import certifi
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class SafeError(RuntimeError):
    def __init__(self,message,stage=None):
        super().__init__(message)
        self.stage=stage


def redact(message):
    message = str(message)
    for name, value in os.environ.items():
        if value and any(k in name for k in ("TOKEN", "SECRET", "PASSWORD", "API_KEY")):
            message = message.replace(value, "[REDACTED]")
    return re.sub(r"(?i)(access_token|client_secret|authorization)[=:\s]+[^\s&,]+", r"\1=[REDACTED]", message)[:900]


def request(method, url, data=None, headers=None, form=None, raw=False, timeout=90):
    headers = {"User-Agent": "EasyBosnian/1.0", **(headers or {})}
    if form is not None:
        data = urlencode(form).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    elif isinstance(data, (dict, list)):
        data = json.dumps(data, ensure_ascii=False).encode()
        headers["Content-Type"] = "application/json"
    try:
        with urlopen(Request(url, data=data, method=method, headers=headers), timeout=timeout, context=ssl.create_default_context(cafile=certifi.where())) as response:
            body = response.read()
    except HTTPError as error:
        # Never dump error bodies: providers can echo tokens, payloads or query strings.
        try:
            payload = json.loads(error.read())
            code = payload.get("error", {}).get("code") if isinstance(payload.get("error"), dict) else None
            stage = payload.get("stage") if payload.get("stage") in ("FLUX generation","storage") else None
        except Exception:
            code = None; stage = None
        raise SafeError(f"HTTP {error.code}; provider code {code or 'unavailable'}; inspect provider permissions/status",stage) from None
    except (URLError, TimeoutError, OSError):
        raise SafeError("Network request failed or timed out; remote outcome may be uncertain") from None
    if raw:
        return body
    try:
        result = json.loads(body)
    except (ValueError, UnicodeError):
        raise SafeError("Provider returned an invalid JSON response") from None
    if isinstance(result, dict) and (result.get("error") or result.get("success") is False):
        raise SafeError("Provider rejected the request; inspect its permissions and service status")
    return result

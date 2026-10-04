import json
import os
import re
import ssl
import certifi
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class SafeError(RuntimeError):
    def __init__(self,message,stage=None,http_status=None):
        super().__init__(message)
        self.stage=stage
        self.http_status=http_status


STORAGE_REASONS={
    'asset_invalid':'rendered image is not a supported JPEG',
    'asset_write_failed':'private image storage failed',
    'asset_not_visible':'uploaded image is not visible in KV yet',
    'asset_read_failed':'private image read failed',
    'asset_exposure_failed':'public image storage failed',
}


def provider_codes(payload):
    error = payload.get('error') if isinstance(payload, dict) else None
    error = error if isinstance(error, dict) else {}
    # Do not log provider prose, payloads, trace IDs or token-shaped strings.
    def number(key):
        value = error.get(key)
        return str(value) if type(value) is int else 'unavailable'
    return f"provider code {number('code')}; provider subcode {number('error_subcode')}"


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
            codes = provider_codes(payload)
            stage = payload.get("stage") if payload.get("stage") in ("FLUX generation","storage") else None
            reason = STORAGE_REASONS.get(payload.get('reason'),'') if stage=='storage' else ''
        except Exception:
            codes = provider_codes(None); stage = None; reason = ''
        detail = reason or 'inspect provider permissions/status'
        raise SafeError(f"HTTP {error.code}; {codes}; {detail}",stage,error.code) from None
    except (URLError, TimeoutError, OSError):
        raise SafeError("Network request failed or timed out; remote outcome may be uncertain") from None
    if raw:
        return body
    try:
        result = json.loads(body)
    except (ValueError, UnicodeError):
        raise SafeError("Provider returned an invalid JSON response") from None
    if isinstance(result, dict) and result.get('error'):
        raise SafeError(f"Provider rejected the request; {provider_codes(result)}; inspect provider permissions/status")
    if isinstance(result, dict) and result.get('success') is False:
        raise SafeError('Provider returned success=false; the operation was not confirmed')
    return result

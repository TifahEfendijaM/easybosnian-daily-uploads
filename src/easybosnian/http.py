import json
import os
import re
import ssl
import certifi
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class SafeError(RuntimeError):
    def __init__(self,message,stage=None,http_status=None,*,reason=None,provider_code=None,provider_http_status=None,diagnostic_saved=False):
        super().__init__(message)
        self.stage=stage
        self.http_status=http_status
        self.reason=reason
        self.provider_code=provider_code
        self.provider_http_status=provider_http_status
        self.diagnostic_saved=diagnostic_saved is True


STORAGE_REASONS={
    'asset_invalid':'rendered image is not a supported JPEG',
    'asset_write_failed':'private image storage failed',
    'asset_not_visible':'uploaded image is not visible in KV yet',
    'asset_read_failed':'private image read failed',
    'asset_exposure_failed':'public image storage failed',
}

FLUX_REASONS={
    'cache_read_failed':'private background cache read failed',
    'ai_binding_missing':'Cloudflare Workers AI binding is missing',
    'ai_call_failed':'Cloudflare Workers AI inference failed',
    'ai_response_invalid':'Cloudflare Workers AI returned an invalid response',
    'ai_image_missing':'Cloudflare Workers AI returned no image',
    'cache_write_failed':'private background cache write failed',
}
# Documented classifications; unknown bounded numeric codes remain visible, never prose.
FLUX_CODES=frozenset((5007,5004,3039,3003,5018,5016,3023,3041,5035,5019,5005,3042,3006,3007,3008,3036,3040))


def safe_response_error(payload,http_status=None):
    payload=payload if isinstance(payload,dict) else {}
    stage=payload.get('stage') if payload.get('stage') in ('FLUX generation','storage') else None
    reason=payload.get('reason')
    reason=reason if isinstance(reason,str) else None
    detail='inspect provider permissions/status'
    codes=provider_codes(payload)
    code=status=None
    if stage=='FLUX generation':
        value=payload.get('code')
        code=value if type(value) is int and 0<value<=99999 else None
        value=payload.get('provider_http_status')
        status=value if type(value) is int and 100<=value<=599 else None
        codes=f"provider code {code if code is not None else 'unavailable'}; provider HTTP {status if status is not None else 'unavailable'}"
        detail=FLUX_REASONS.get(reason,detail)
        reason=reason if reason in FLUX_REASONS else None
    elif stage=='storage':
        detail=STORAGE_REASONS.get(reason,detail)
        reason=reason if reason in STORAGE_REASONS else None
    else:
        reason=None
        meta=payload.get('error')
        if (isinstance(meta,dict) and type(meta.get('code')) is int and meta['code']==9
                and type(meta.get('error_subcode')) is int and meta['error_subcode']==2207042):
            reason='instagram_publishing_limit'
            detail='Instagram publishing-limit refusal; inspect current quota; no automatic retry'
        elif (isinstance(meta,dict) and type(meta.get('code')) is int and meta['code']==9
                and type(meta.get('error_subcode')) is int and meta['error_subcode']==2207074):
            reason='instagram_deletion_refused'
            detail='Instagram deletion refused; exact restriction/window unverified; no automatic retry'
    prefix=f'HTTP {http_status}' if http_status is not None else 'Provider rejected the request'
    return SafeError(f'{prefix}; {codes}; {detail}',stage,http_status,
                     reason=reason,provider_code=code,provider_http_status=status,diagnostic_saved=stage=='FLUX generation' and payload.get('diagnostic_saved') is True)


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
        except Exception:
            payload = None
        raise safe_response_error(payload,error.code) from None
    except (URLError, TimeoutError, OSError):
        raise SafeError("Network request failed or timed out; remote outcome may be uncertain") from None
    if raw:
        return body
    try:
        result = json.loads(body)
    except (ValueError, UnicodeError):
        raise SafeError("Provider returned an invalid JSON response") from None
    if isinstance(result, dict) and result.get('error'):
        raise safe_response_error(result)
    if isinstance(result, dict) and result.get('success') is False:
        raise SafeError('Provider returned success=false; the operation was not confirmed')
    return result

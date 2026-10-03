"""TikTok publishing through the user's Free Buffer account; no TikTok app/client."""
import hashlib
import os
import re
import time
from urllib.parse import urlparse

from .core import ROOT, require_publishing, write_json
from .http import SafeError, redact, request
from .notify import failure


TARGET = "easy.bosnian"
CHANNEL_FIELDS = """id name service serviceId organizationId externalLink scopes
    isDisconnected isLocked isQueuePaused
    metadata { ... on TiktokMetadata { defaultToReminders } }"""
POST_FIELDS = """id channelId channelService text status schedulingType externalLink createdAt sentAt
    assets { id mimeType source }"""


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r"[a-f0-9]{24}", value):
        raise ValueError("Buffer requires a confirmed 24-character channel/organization/post ID")
    return value


def caption(package):
    # TikTok allows five hashtags. Select only already-reviewed public hashtags.
    text = package["caption"] + "\n\n" + " ".join(package["hashtags"][:5])
    if len(text) > 2200:
        raise ValueError("Reviewed TikTok caption exceeds 2200 characters; do not truncate it")
    return text


class Buffer:
    def __init__(self, key=None, channel_id=None, organization_id=None):
        self.key = key or os.environ["BUFFER_API_KEY"]
        self.channel_id = channel_id or os.getenv("BUFFER_TIKTOK_CHANNEL_ID", "")
        self.organization_id = organization_id or os.getenv("BUFFER_ORGANIZATION_ID", "")
        if not self.key.strip():
            raise ValueError("Missing protected Buffer API key")

    def call(self, query, variables=None):
        result = request("POST", "https://api.buffer.com", {"query": query, "variables": variables or {}},
                         headers={"Authorization": "Bearer " + self.key}, timeout=45)
        # GraphQL errors can echo credentials or public/private content. Never print them.
        if not isinstance(result, dict) or result.get("errors") or not isinstance(result.get("data"), dict):
            raise SafeError("Buffer API rejected the operation; inspect API access, quota and channel permissions")
        return result["data"]

    def discover(self):
        orgs = self.call("query { account { organizations { id } } }")["account"]["organizations"]
        matches = []
        for org in orgs:
            org_id = identifier(org["id"])
            channels = self.call("query($input: ChannelsInput!) { channels(input:$input) { " + CHANNEL_FIELDS + " } }",
                                 {"input": {"organizationId": org_id}})["channels"]
            matches.extend(c for c in channels if c.get("service") == "tiktok" and c.get("name", "").lstrip("@").lower() == TARGET)
        if len(matches) != 1:
            raise ValueError("Buffer must contain exactly one connected @easy.bosnian TikTok channel")
        self.channel_id = identifier(matches[0]["id"])
        self.organization_id = identifier(matches[0]["organizationId"])
        return self.verify_channel()

    def verify_channel(self):
        identifier(self.channel_id); identifier(self.organization_id)
        actual = self.call("query($input: ChannelInput!) { channel(input:$input) { " + CHANNEL_FIELDS + " } }",
                           {"input": {"id": self.channel_id}})["channel"]
        if (actual.get("id") != self.channel_id or actual.get("organizationId") != self.organization_id
                or actual.get("service") != "tiktok" or actual.get("name", "").lstrip("@").lower() != TARGET
                or not actual.get("serviceId")):
            raise ValueError("Buffer channel does not match the confirmed @easy.bosnian TikTok identity")
        if any(actual.get(k) is not False for k in ("isDisconnected", "isLocked", "isQueuePaused")):
            raise ValueError("Buffer TikTok channel is disconnected, locked or paused; repair the connection in Buffer")
        if (actual.get("metadata") or {}).get("defaultToReminders") is not False:
            raise ValueError("Disable default notification publishing in Buffer before automatic TikTok publishing")
        if not {"user.info.basic", "user.info.username", "video.publish", "video.list"}.issubset(set(actual.get("scopes", []))):
            raise ValueError("Buffer has not confirmed TikTok identity, direct publishing and public-post permissions")
        return actual

    def create(self, text, urls):
        if len(urls) != 3 or len(set(urls)) != 3:
            raise ValueError("TikTok requires the three distinct reviewed images in order")
        result = self.call("mutation($input: CreatePostInput!) { createPost(input:$input) { __typename "
                           "... on PostActionSuccess { post { " + POST_FIELDS + " } } "
                           "... on MutationError { __typename } } }", {"input": {
                               "channelId": self.channel_id, "text": text, "schedulingType": "automatic",
                               "mode": "shareNow", "needsApproval": False, "saveToDraft": False, "aiAssisted": True,
                               "assets": [{"image": {"url": url}} for url in urls]}})["createPost"]
        if result.get("__typename") != "PostActionSuccess" or not result.get("post", {}).get("id"):
            raise SafeError("Buffer did not accept automatic TikTok publishing; inspect its channel/plan restrictions; no retry")
        return result["post"]

    def post(self, post_id):
        identifier(post_id)
        return self.call("query($input: PostInput!) { post(input:$input) { " + POST_FIELDS + " } }",
                         {"input": {"id": post_id}})["post"]



def checked_post(buffer, package, post_id, actual, assets):
    if (actual.get('id')!=post_id or actual.get('channelId')!=buffer.channel_id
            or actual.get('channelService')!='tiktok' or actual.get('text')!=caption(package)
            or actual.get('schedulingType')!='automatic'):
        raise ValueError('Buffer post identity, caption or publishing type differs from reviewed content')
    actual_assets=actual.get('assets',[])
    if len(actual_assets)!=3 or any(not a.get('mimeType','').startswith('image/') or not a.get('source') for a in actual_assets):
        raise ValueError('Buffer post must contain three image assets')
    expected=[hashlib.sha256(assets[c['kind']]['path'].read_bytes()).hexdigest() for c in package['cards']]
    received=[hashlib.sha256(request('GET',a['source'],raw=True)).hexdigest() for a in actual_assets]
    if received!=expected: raise ValueError('Buffer image bytes or order differ from the reviewed cards')
    status=actual.get('status')
    if status not in ('scheduled','sending','sent'): raise ValueError('Buffer reports a failed, draft or approval-only post')
    if status!='sent' or not actual.get('externalLink'): return None
    parsed=urlparse(actual['externalLink'])
    if parsed.scheme!='https' or parsed.hostname not in ('www.tiktok.com','tiktok.com') or not re.fullmatch(r'/@easy\.bosnian/(photo|video)/[0-9]+/?',parsed.path) or not actual.get('sentAt'):
        raise ValueError('Buffer returned no actual @easy.bosnian publication permalink')
    return actual['externalLink']


def publish_tiktok(package, assets, record=None):
    date=package['date'];stage='TikTok authorization';result={'batch':date,'published':False}
    publication='nothing submitted to TikTok'
    try:
        require_publishing()
        if os.getenv('TIKTOK_POSTING_ENABLED')!='true': raise ValueError('TikTok publisher is disabled')
        buffer=Buffer();buffer.verify_channel();stage='TikTok publishing';require_publishing()
        publication='Buffer submission outcome uncertain'
        accepted=buffer.create(caption(package),[assets[c['kind']]['url'] for c in package['cards']])
        post_id=identifier(accepted['id']);result['post_id']=post_id
        if record: record('feed',post_id,buffer.channel_id)
        # Diagnostic artifacts are not a durable gate or a recovery state machine.
        publication='Buffer accepted; TikTok publication unconfirmed'
        write_json(ROOT/'build'/date/'tiktok-result.json',{**result,'status':publication})
        stage='TikTok publication verification'
        for attempt in range(13):
            permalink=checked_post(buffer,package,post_id,buffer.post(post_id),assets)
            if permalink: break
            if attempt==12: raise ValueError('Buffer has not confirmed publication within four minutes; inspect the returned post ID')
            time.sleep(20)  # Read-only polling of this request, not another publication.
        result.update(published=True,permalink=permalink,status='Buffer-confirmed TikTok publication')
        write_json(ROOT/'build'/date/'tiktok-result.json',result);return result
    except Exception as error:
        result.update(status=publication,failed_stage=stage)
        write_json(ROOT/'build'/date/'tiktok-result.json',result)
        print(failure(date,stage,error,publication,os.getenv('GITHUB_RUN_URL')))
        raise SafeError('TikTok failed at '+stage,stage) from None

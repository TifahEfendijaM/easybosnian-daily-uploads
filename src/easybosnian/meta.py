import json
import os
import re
import time
from datetime import datetime, timezone
from urllib.parse import urlencode

from .core import REPO, gh, verify_repository, require_publishing
from .http import request, SafeError


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
        os.environ["INSTAGRAM_ACCESS_TOKEN"] = new_token
        os.environ["INSTAGRAM_TOKEN_ISSUED_AT"] = stamp

    def child(self, url, alt):
        return self.call("POST", self.user_id + "/media", {"image_url": url, "is_carousel_item": "true", "alt_text": alt})["id"]

    def ready(self, container, stable=False):
        # Read-only status polling within one run, never another scheduled attempt.
        finished = 0
        for attempt in range(12):
            result = self.call("GET", container, {"fields": "status_code"})
            status = result.get("status_code")
            if status == "FINISHED":
                finished += 1
                if not stable or finished >= 2:
                    return status
            elif status == "PUBLISHED":
                raise ValueError('Instagram container is already published; no second publish request')
            else:
                finished = 0
            if status in ("ERROR", "EXPIRED"):
                raise ValueError(f"Instagram media container is {status}; inspect the current run’s container ID")
            if attempt < 11:
                time.sleep(5)
        raise ValueError("Instagram container is still processing; inspect the platform before another manual daily run")

    def carousel(self, children, caption):
        return self.call("POST", self.user_id + "/media", {"media_type": "CAROUSEL", "children": ",".join(children), "caption": caption})["id"]

    def publish(self, container):
        return self.call("POST", self.user_id + "/media_publish", {"creation_id": container})["id"]

    def media(self, media_id):
        return self.call("GET", media_id, {"fields": "id,permalink,caption,media_type,children{id,media_type}"})

    def story(self, url):
        return self.call("POST", self.user_id + "/media", {"image_url": url, "media_type": "STORIES"})["id"]

    def story_media(self, media_id):
        return self.call("GET", media_id, {"fields": "id,media_type,media_product_type,permalink,timestamp"})

    def stories(self):
        return self.call("GET", self.user_id + "/stories", {"fields": "id", "limit": 100})

    def publishing_limit(self):
        return self.call('GET', self.user_id+'/content_publishing_limit',{'fields':'quota_usage,config'})


class Facebook:
    """Independent Pages token and photo-feed publishing."""
    def __init__(self, token=None, page_id=None):
        self.token = token or os.environ["FACEBOOK_PAGE_TOKEN"]
        self.page_id = page_id or os.environ["FACEBOOK_PAGE_ID"]
        version = os.environ["META_GRAPH_VERSION"]
        if not re.fullmatch(r"v\d+\.0", version) or not re.fullmatch(r"\d+", self.page_id):
            raise ValueError("Invalid Facebook Page ID or supported Graph version")
        self.base = "https://graph.facebook.com/" + version

    def call(self, method, path, values=None):
        headers = {"Authorization": "Bearer " + self.token}
        url = self.base + "/" + path
        if method == "GET":
            return request(method, url + "?" + urlencode(values or {}), headers=headers)
        return request(method, url, headers=headers, form=values or {})

    def verify_page(self):
        page = self.call("GET", "me", {"fields": "id,name,can_post"})
        if page["id"] != self.page_id or page["name"] != "Easy Bosnian":
            raise ValueError("Facebook token does not authorize the exact selected EasyBosnian Page")
        if page.get('can_post') is not True:
            raise ValueError('Facebook Page posting capability is unavailable; renew the existing Page publishing authorization')
        return page

    def photo(self, url, alt):
        return self.call("POST", self.page_id + "/photos", {"url": url, "published": "false", "alt_text_custom": alt})["id"]

    def publish(self, photos, caption):
        if len(photos) != 3 or len(set(photos)) != 3:
            raise ValueError("Facebook requires the three distinct reviewed photos")
        return self.call("POST", self.page_id + "/feed", {"message": caption, "published": "true", "attached_media": json.dumps([{"media_fbid": p} for p in photos])})["id"]

    def post(self, post_id):
        return self.call("GET", post_id, {"fields": "id,from,message,is_published,permalink_url,attachments{type,target,subattachments{type,target}}"})

    def story(self, photo_id):
        result = self.call("POST", self.page_id + "/photo_stories", {"photo_id": photo_id})
        post_id = str(result.get('post_id', ''))
        if result.get('success') is not True or not re.fullmatch(r"\d+(?:_\d+)?", post_id):
            raise ValueError('Facebook did not confirm acceptance of the photo Story')
        return post_id

    def stories(self, after=None):
        values = {"limit": 100}
        if after:
            values['after'] = after
        return self.call("GET", self.page_id + "/stories", values)

    def owned_ids(self, kind):
        edge = {'feed':'published_posts', 'photo':'photos', 'story':'stories'}[kind]
        values = {'limit':100}
        if kind != 'story': values['fields'] = 'id'
        if kind == 'photo': values['type'] = 'uploaded'
        return owned_ids(self, self.page_id+'/'+edge, values, 'post_id' if kind == 'story' else 'id')

    def story_photos(self):
        """Complete owned edge: Story nodes cannot themselves be deleted."""
        result = {}; after = None
        for _ in range(50):
            page = self.stories(after)
            if not isinstance(page.get('data'), list):
                raise ValueError('Facebook Story ownership listing is incomplete')
            for item in page['data']:
                post_id = str(item.get('post_id', ''))
                media_id = str(item.get('media_id', ''))
                if not re.fullmatch(r'\d+(?:_\d+)?', post_id) or not re.fullmatch(r'\d+', media_id):
                    raise ValueError('Facebook Story ownership identifiers are incomplete')
                media_type = str(item.get('media_type', '')).casefold()
                if media_type not in ('photo', 'video'):
                    raise ValueError('Facebook Story ownership media type is incomplete')
                if media_type == 'video':
                    result[post_id] = None
                    continue
                if post_id in result and result[post_id] != media_id:
                    raise ValueError('Facebook Story photo ownership is inconsistent')
                result[post_id] = media_id
            if not page.get('paging', {}).get('next'): return result
            cursor = page.get('paging', {}).get('cursors', {}).get('after')
            if not cursor or cursor == after:
                raise ValueError('Facebook Story ownership pagination is incomplete')
            after = cursor
        raise ValueError('Facebook Story ownership exceeded the bounded listing')

    def delete(self, object_id):
        if not re.fullmatch(r'\d+(?:_\d+)?', object_id): raise ValueError('Invalid Facebook media identifier')
        try:
            result = self.call('DELETE', object_id)
        except SafeError as error:
            raise SafeError(f'Facebook DELETE of recorded object {object_id} failed: {error}') from None
        if result.get('success') is not True:
            raise ValueError('Facebook did not confirm deletion; old content may remain')


def owned_ids(provider, path, values, field='id'):
    result = set(); after = None
    for _ in range(50):
        page = provider.call('GET', path, {**values, **({'after':after} if after else {})})
        if not isinstance(page.get('data'), list) or any(not x.get(field) for x in page['data']):
            raise ValueError('Owned media listing is incomplete; refusing to infer deletion')
        result.update(str(x[field]) for x in page['data'])
        if not page.get('paging', {}).get('next'): return result
        cursor = page.get('paging', {}).get('cursors', {}).get('after')
        if not cursor or cursor == after: raise ValueError('Owned media pagination is incomplete')
        after = cursor
    raise ValueError('Owned media exceeded the bounded listing; replacement requires manual cleanup')


class InstagramDeletion:
    """Separate Facebook Login user token; never replaces Instagram Login."""
    def __init__(self, token=None, user_id=None):
        self.token = token or os.getenv('INSTAGRAM_DELETE_ACCESS_TOKEN')
        self.user_id = user_id or os.getenv('INSTAGRAM_DELETE_USER_ID')
        if not self.token or not self.user_id:
            raise ValueError('Instagram deletion needs Facebook Login authorization for the linked Easy Bosnian Page')
        if not re.fullmatch(r'\d+', self.user_id): raise ValueError('Invalid Instagram deletion account identifier')
        version = os.environ['META_GRAPH_VERSION']
        if not re.fullmatch(r'v\d+\.0', version): raise ValueError('Invalid Graph version')
        self.base = 'https://graph.facebook.com/'+version

    call = Facebook.call

    def verify_account(self):
        permissions = self.call('GET', 'me/permissions')
        granted = {p['permission'] for p in permissions['data'] if p['status']=='granted'}
        if not {'instagram_basic','instagram_manage_contents','pages_read_engagement','pages_show_list'} <= granted:
            raise ValueError('Instagram deletion authorization is missing its required permissions')
        page = self.call('GET', '1284422991426579', {'fields':'id,name,instagram_business_account{id,username}'})
        ig = page.get('instagram_business_account') or {}
        if page.get('id')!='1284422991426579' or page.get('name')!='Easy Bosnian' or ig.get('id')!=self.user_id or ig.get('username','').casefold()!='easy_bosnian':
            raise ValueError('Instagram deletion does not authorize @easy_bosnian through the exact Easy Bosnian Page')
        return ig

    def owned_ids(self, kind):
        if kind not in ('feed','story'): raise ValueError('Invalid Instagram media kind')
        return owned_ids(self, self.user_id+('/media' if kind=='feed' else '/stories'), {'fields':'id','limit':100})

    def delete(self, object_id):
        if not re.fullmatch(r'\d+', object_id): raise ValueError('Invalid Instagram media identifier')
        result = self.call('DELETE', object_id)
        if result.get('success') is not True or str(result.get('deleted_id')) != object_id:
            raise ValueError('Instagram did not confirm deletion of the expected media; replacement stopped')


class InstagramFacebook(Instagram):
    """Facebook Login feed/polls only. Instagram Login still owns Stories/refresh."""
    required_scopes = frozenset(('instagram_basic', 'instagram_content_publish',
                                 'pages_read_engagement', 'pages_show_list', 'ads_read',
                                 'business_management'))

    def __init__(self, token=None, user_id=None, expires_at=None):
        self.token = token or os.getenv('INSTAGRAM_FACEBOOK_ACCESS_TOKEN')
        self.user_id = user_id or os.getenv('INSTAGRAM_FACEBOOK_USER_ID')
        expiry = expires_at if expires_at is not None else os.getenv('INSTAGRAM_FACEBOOK_EXPIRES_AT')
        if not self.token or not self.user_id or not expiry:
            raise ValueError('Native Instagram polls need separate Facebook Login publishing authorization')
        if not re.fullmatch(r'\d+', self.user_id) or not str(expiry).isdigit():
            raise ValueError('Invalid Facebook Login Instagram publishing identity/expiry')
        self.expires_at = int(expiry)
        if self.expires_at <= datetime.now(timezone.utc).timestamp():
            raise ValueError('Facebook Login Instagram publishing access expired; renew it privately before posting')
        version = os.environ['META_GRAPH_VERSION']
        if not re.fullmatch(r'v\d+\.0', version):
            raise ValueError('Invalid supported Graph version')
        self.base = 'https://graph.facebook.com/' + version

    call = Facebook.call

    def verify_account(self):
        granted = {item.get('permission') for item in self.call('GET', 'me/permissions')['data']
                   if item.get('status') == 'granted'}
        if not self.required_scopes <= granted:
            raise ValueError('Facebook Login Instagram publishing is missing required poll/feed scopes')
        page_id = '1284422991426579'
        page = self.call('GET', page_id, {'fields': 'id,name,instagram_business_account{id,username}'})
        info = page.get('instagram_business_account') or {}
        if (page.get('id') != page_id or page.get('name') != 'Easy Bosnian'
                or str(info.get('id')) != self.user_id or info.get('username', '').casefold() != 'easy_bosnian'):
            raise ValueError('Facebook Login publishing does not authorize the exact linked Easy Bosnian Page/@easy_bosnian')
        after = None
        for _ in range(50):
            pages = self.call('GET', 'me/accounts', {'fields': 'id,tasks', 'limit': 100,
                                                   **({'after': after} if after else {})})
            for item in pages.get('data', []):
                if item.get('id') == page_id:
                    if not {'MANAGE', 'CREATE_CONTENT'} & set(item.get('tasks', [])):
                        raise ValueError('Facebook Login user lacks MANAGE/CREATE_CONTENT on the exact linked Page')
                    return info
            if not pages.get('paging', {}).get('next'):
                break
            cursor = pages.get('paging', {}).get('cursors', {}).get('after')
            if not cursor or cursor == after:
                raise ValueError('Facebook Login Page task pagination is incomplete')
            after = cursor
        raise ValueError('Facebook Login did not confirm content tasks on the exact linked Page')

    def carousel(self, children, caption, poll=None):
        from .instagram_poll import serialize_poll
        if not caption.strip():
            raise ValueError('Instagram caption add-ons need a non-empty caption')
        values = {'media_type': 'CAROUSEL', 'children': ','.join(children), 'caption': caption}
        if poll is not None:
            values['poll_attachment'] = serialize_poll(poll)
        return self.call('POST', self.user_id + '/media', values)['id']

    def publish_with_addon(self, container):
        # Exactly one publish request; retain the attachment outcome, unlike
        # the unchanged Instagram Login Story publisher's ID-only return.
        return self.call('POST', self.user_id + '/media_publish', {'creation_id': container})

    def poll_attachment(self, media_id):
        return self.call('GET', media_id + '/poll_attachment')


def instagram_facebook_token(user_token, app_secret):
    """Separate long-lived Facebook User publishing credential, never a Page token."""
    app_id = '1987873818544936'; version = os.environ['META_GRAPH_VERSION']
    if not re.fullmatch(r'v\d+\.0', version):
        raise ValueError('Invalid Graph version')
    base = 'https://graph.facebook.com/' + version
    exchanged = request('GET', base + '/oauth/access_token?' + urlencode({
        'grant_type': 'fb_exchange_token', 'client_id': app_id,
        'client_secret': app_secret, 'fb_exchange_token': user_token}))
    token = exchanged['access_token']
    debug = request('GET', base + '/debug_token?' + urlencode({'input_token': token}),
                    headers={'Authorization': 'Bearer ' + app_id + '|' + app_secret})['data']
    if (debug.get('is_valid') is not True or debug.get('app_id') != app_id
            or debug.get('type') != 'USER'
            or not InstagramFacebook.required_scopes <= set(debug.get('scopes', []))):
        raise ValueError('Facebook Login publishing token failed app/type/scope validation')
    expiry_values = [int(debug.get(name) or 0) for name in ('expires_at', 'data_access_expires_at')]
    expiry = min((value for value in expiry_values if value > 0), default=0)
    if expiry <= datetime.now(timezone.utc).timestamp() + 40 * 86400:
        raise ValueError('Facebook Login publishing access is not valid for at least 40 days')
    page = request('GET', base + '/1284422991426579?' + urlencode({
        'fields': 'id,name,instagram_business_account{id,username}'}), headers={'Authorization': 'Bearer ' + token})
    info = page.get('instagram_business_account') or {}
    client = InstagramFacebook(token, str(info.get('id', '')), expiry)
    client.verify_account()
    return token, {'app_id': app_id, 'page_id': '1284422991426579',
                   'instagram_id': client.user_id, 'instagram_username': 'easy_bosnian',
                   'expires_at': expiry, 'token_expires_at': expiry_values[0],
                   'data_access_expires_at': expiry_values[1],
                   'scopes': sorted(InstagramFacebook.required_scopes),
                   'verified_at': datetime.now(timezone.utc).isoformat(),
                   'publication': 'No container, post, poll or Story created during authorization'}


def instagram_deletion_token(user_token, app_secret):
    """Long-lived Facebook User token for this app and only the linked target."""
    app_id = '1987873818544936'; version = os.environ['META_GRAPH_VERSION']
    if not re.fullmatch(r'v\d+\.0',version): raise ValueError('Invalid Graph version')
    base = 'https://graph.facebook.com/'+version
    exchanged = request('GET',base+'/oauth/access_token?'+urlencode({
        'grant_type':'fb_exchange_token','client_id':app_id,'client_secret':app_secret,'fb_exchange_token':user_token}))
    token = exchanged['access_token']
    headers = {'Authorization':'Bearer '+token}
    page = request('GET',base+'/1284422991426579?'+urlencode({'fields':'id,name,instagram_business_account{id,username}'}),headers=headers)
    ig = page.get('instagram_business_account') or {}
    if ig.get('username','').casefold()!='easy_bosnian' or not re.fullmatch(r'\d+',str(ig.get('id',''))):
        raise ValueError('Link @easy_bosnian to the exact Easy Bosnian Page before deletion authorization')
    InstagramDeletion(token,ig['id']).verify_account()
    debug = request('GET',base+'/debug_token?'+urlencode({'input_token':token}),headers={'Authorization':'Bearer '+app_id+'|'+app_secret})['data']
    required = {'instagram_basic','instagram_manage_contents','pages_read_engagement','pages_show_list'}
    if debug.get('is_valid') is not True or str(debug.get('app_id'))!=app_id or debug.get('type')!='USER' or not required <= set(debug.get('scopes',[])):
        raise ValueError('Meta did not verify the correct app and required deletion scopes')
    # Meta may report expires_at=0 for an app administrator's User token.
    # Its positive data-access expiry still limits how long authorization works.
    expiries = [x for x in (debug.get('expires_at'),debug.get('data_access_expires_at')) if isinstance(x,int) and x>0]
    expiry = min(expiries) if expiries else 0
    if not expiry or expiry-time.time()<40*86400: raise ValueError('Deletion token is not a long-lived Facebook User token')
    return token, {'app_id':app_id,'page_id':'1284422991426579','instagram_id':ig['id'],'instagram_username':'easy_bosnian','expires_at':expiry,'token_expires_at':debug.get('expires_at'),'data_access_expires_at':debug.get('data_access_expires_at'),'verified_at':datetime.now(timezone.utc).isoformat(),'scopes':sorted(required),'publication':'No post was created or deleted during authorization'}



def facebook_page_token(user_token, app_id, app_secret, page_id):
    """Exchange once; discover the exact Page. Never return/print other Pages."""
    version = os.environ["META_GRAPH_VERSION"]
    if not re.fullmatch(r"v\d+\.0", version) or not re.fullmatch(r"\d+", app_id) or not re.fullmatch(r"\d+", page_id):
        raise ValueError("Invalid Facebook authorization identifiers")
    base = "https://graph.facebook.com/" + version
    exchange = request("GET", base + "/oauth/access_token?" + urlencode({"grant_type": "fb_exchange_token", "client_id": app_id, "client_secret": app_secret, "fb_exchange_token": user_token}))
    token = exchange["access_token"]
    headers = {"Authorization": "Bearer " + token}
    permissions = request("GET", base + "/me/permissions", headers=headers)
    granted = {p["permission"] for p in permissions["data"] if p["status"] == "granted"}
    if not {"pages_show_list", "pages_read_engagement", "pages_manage_posts"} <= granted:
        raise ValueError("Facebook login is missing one of the three required Page permissions")
    after = None
    for _ in range(20):
        values = {"fields": "id,name,tasks,access_token", "limit": 100}
        if after: values["after"] = after
        pages = request("GET", base + "/me/accounts?" + urlencode(values), headers=headers)
        for page in pages["data"]:
            if str(page["id"]) == page_id:
                if page["name"] != "Easy Bosnian" or not {"CREATE_CONTENT", "MANAGE"}.intersection(page.get("tasks", [])):
                    raise ValueError("Selected Page is not EasyBosnian or its publishing task is unavailable")
                result = Facebook(page["access_token"], page_id)
                result.verify_page()
                debug = request("GET", base + "/debug_token?" + urlencode({"input_token": page["access_token"]}), headers={"Authorization": "Bearer " + app_id + "|" + app_secret})["data"]
                if debug.get("is_valid") is not True or str(debug.get("app_id")) != app_id or debug.get("type") != "PAGE":
                    raise ValueError("Meta did not verify an independent Page token for this app")
                expires = debug.get("expires_at", 0)
                if expires and expires - time.time() < 40 * 86400:
                    raise ValueError("Page token is short-lived; complete the long-lived authorization flow")
                return page["access_token"], {"page_id": page_id, "page_name": "Easy Bosnian", "app_id": app_id, "expires_at": expires, "data_access_expires_at": debug.get("data_access_expires_at", 0)}
        if not pages.get("paging", {}).get("next"): break
        cursor = pages.get("paging", {}).get("cursors", {}).get("after")
        if not cursor or cursor == after: raise ValueError("Facebook Page discovery pagination is incomplete")
        after = cursor
    raise ValueError("The exact selected EasyBosnian Page is not authorized")

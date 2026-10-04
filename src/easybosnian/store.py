import os
import re
import time
from urllib.parse import urlparse
from .http import SafeError, request
from .batches import BATCH_ID
from .core import PROJECT


def scope_path(key):
    if BATCH_ID.fullmatch(key):return 'batches/'+key
    if re.fullmatch(r'\d{4}-\d{2}-\d{2}',key):return key
    raise ValueError('Invalid batch storage identity')


def wait_for_image(url,expected,fetch=None):
    """Read only: wait at most three minutes for this one freshly written URL.

    A KV negative cache can outlive the write. Never resubmit a write, exposure,
    generation or social publish; only an explicit 404 is eligible for polling.
    """
    fetch=fetch or request
    deadline=time.monotonic()+180
    while True:
        remaining=deadline-time.monotonic()
        if remaining<=0:
            raise SafeError('Public image remained unavailable after 180 seconds; no write or publication was repeated','storage')
        try:
            body=fetch('GET',url,raw=True,timeout=min(10,remaining))
        except SafeError as error:
            if error.http_status!=404: raise
        else:
            if body!=expected:
                raise SafeError('Public image bytes differ from the reviewed renderer output','storage')
            return
        remaining=deadline-time.monotonic()
        if remaining>0: time.sleep(min(5,remaining))


class Store:
    def __init__(self):
        self.url=os.environ['EASYBOSNIAN_WORKER_URL'].rstrip('/')
        if urlparse(self.url).scheme!='https': raise ValueError('Cloudflare endpoint must use HTTPS')
        self.headers={'Authorization':'Bearer '+os.environ['EASYBOSNIAN_ADMIN_TOKEN']}

    def call(self,method,path,data=None,raw=False,headers=None):
        return request(method,self.url+path,data,{**self.headers,**(headers or {})},raw=raw)

    def history(self): return self.call('GET','/v1/history')
    def content(self,key): return self.call('GET',f'/v1/history/{scope_path(key)}')
    def save_content(self,package): return self.call('PUT',f'/v1/history/{scope_path(package.get("batch_id") or package["date"])}',package)
    def delete_content(self,key,date):
        if not BATCH_ID.fullmatch(key) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}',date):raise ValueError('Explicit batch/date required for history removal')
        return self.call('DELETE',f'/v1/history/batches/{key}',{'date':date})
    def publications_for_date(self,date):
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}',date):raise ValueError('Invalid publication date')
        result=self.call('GET',f'/v1/publications/dates/{date}')
        if (result.get('project')!=PROJECT or result.get('date')!=date
                or any(item.get('date')!=date or not BATCH_ID.fullmatch(item.get('batch_id','')) for item in result['items'])):
            raise ValueError('Publication date scope does not match this project')
        return result['items']
    def publications(self,key): return self.call('GET',f'/v1/publications/{scope_path(key)}')['items']
    def remember(self,key,platform,kind,object_id,account_id):
        return self.call('POST',f'/v1/publications/{scope_path(key)}',{'platform':platform,'kind':kind,'object_id':str(object_id),'account_id':str(account_id)})
    def forget(self,key,platform,object_id): return self.call('DELETE',f'/v1/publications/{scope_path(key)}/{platform}/{object_id}')
    def get_file(self,key,name): return self.call('GET',f'/v1/private/{scope_path(key)}/{name}',raw=True)
    def put_file(self,key,name,body): return self.call('PUT',f'/v1/private/{scope_path(key)}/{name}',body,headers={'Content-Type':'image/jpeg'})
    def expose(self,key,name,body=None):
        # Send the exact rendered bytes; do not depend on an immediate KV read
        # of the preceding private upload. Empty legacy requests remain valid.
        result=self.call('POST',f'/v1/expose/{scope_path(key)}/{name}',body,
                         headers={'Content-Type':'image/jpeg'} if body is not None else None)
        url=result['url']
        if body is not None and not re.fullmatch(re.escape(self.url)+r'/images/[a-f0-9]{64}\.jpg',url):
            raise SafeError('Worker returned an unexpected public image URL','storage')
        return url

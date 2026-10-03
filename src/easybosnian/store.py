import os
import re
from urllib.parse import urlparse
from .http import request
from .batches import BATCH_ID


def scope_path(key):
    if BATCH_ID.fullmatch(key):return 'batches/'+key
    if re.fullmatch(r'\d{4}-\d{2}-\d{2}',key):return key
    raise ValueError('Invalid batch storage identity')


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
    def publications(self,key): return self.call('GET',f'/v1/publications/{scope_path(key)}')['items']
    def remember(self,key,platform,kind,object_id,account_id):
        return self.call('POST',f'/v1/publications/{scope_path(key)}',{'platform':platform,'kind':kind,'object_id':str(object_id),'account_id':str(account_id)})
    def forget(self,key,platform,object_id): return self.call('DELETE',f'/v1/publications/{scope_path(key)}/{platform}/{object_id}')
    def get_file(self,key,name): return self.call('GET',f'/v1/private/{scope_path(key)}/{name}',raw=True)
    def put_file(self,key,name,body): return self.call('PUT',f'/v1/private/{scope_path(key)}/{name}',body,headers={'Content-Type':'image/jpeg'})
    def expose(self,key,name): return self.call('POST',f'/v1/expose/{scope_path(key)}/{name}')['url']

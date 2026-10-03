import os
from urllib.parse import urlparse
from .http import request


class Store:
    def __init__(self):
        self.url=os.environ['EASYBOSNIAN_WORKER_URL'].rstrip('/')
        if urlparse(self.url).scheme!='https': raise ValueError('Cloudflare endpoint must use HTTPS')
        self.headers={'Authorization':'Bearer '+os.environ['EASYBOSNIAN_ADMIN_TOKEN']}

    def call(self,method,path,data=None,raw=False,headers=None):
        return request(method,self.url+path,data,{**self.headers,**(headers or {})},raw=raw)

    def history(self): return self.call('GET','/v1/history')
    def content(self,date): return self.call('GET',f'/v1/history/{date}')
    def save_content(self,package): return self.call('PUT',f'/v1/history/{package["date"]}',package)
    def get_file(self,date,name): return self.call('GET',f'/v1/private/{date}/{name}',raw=True)
    def put_file(self,date,name,body): return self.call('PUT',f'/v1/private/{date}/{name}',body,headers={'Content-Type':'image/jpeg'})
    def expose(self,date,name): return self.call('POST',f'/v1/expose/{date}/{name}')['url']

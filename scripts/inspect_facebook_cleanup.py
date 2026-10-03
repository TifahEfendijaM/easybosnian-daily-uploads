"""Temporary read-only diagnosis; outputs only identity and response status."""
import json
import ssl
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import certifi

from easybosnian.core import ROOT, today, write_json
from easybosnian.meta import Facebook
from easybosnian.store import Store


facebook = Facebook()
facebook.verify_page()
items = [x for x in Store().publications(today()) if x['platform'] == 'facebook']
result = {'batch': today(), 'read_only': True, 'probes': []}


def probe(label, path, values):
    entry = {'probe': label}
    url = facebook.base + '/' + path + '?' + urlencode(values)
    headers = {'Authorization': 'Bearer ' + facebook.token, 'User-Agent': 'EasyBosnian/1.0'}
    try:
        with urlopen(Request(url, headers=headers, method='GET'), timeout=45,
                     context=ssl.create_default_context(cafile=certifi.where())) as response:
            data = json.loads(response.read())
            entry['http_status'] = response.status
            if isinstance(data.get('data'), list):
                entry['ids'] = [{k: row[k] for k in ('id', 'post_id', 'media_id', 'status') if k in row}
                                for row in data['data']]
            else:
                entry['identity'] = {k: data[k] for k in ('id', 'page_story_id', 'can_delete') if k in data}
                if 'from' in data: entry['owner_id'] = data['from'].get('id')
                entry['node_type'] = data.get('metadata', {}).get('type')
    except HTTPError as error:
        body = json.loads(error.read()).get('error', {})
        entry.update(http_status=error.code, provider_code=body.get('code'),
                     provider_subcode=body.get('error_subcode'))
        message = body.get('message', '').casefold()
        entry['unsupported_operation'] = 'unsupported' in message
        entry['invalid_field'] = 'nonexisting field' in message or 'non-existing field' in message
    result['probes'].append(entry)


for kind, edge in [('story', 'stories'), ('feed', 'published_posts'), ('photo', 'photos')]:
    values = {'limit': 100}
    if kind != 'story': values['fields'] = 'id'
    if kind == 'photo': values['type'] = 'uploaded'
    probe('owned_' + kind, facebook.page_id + '/' + edge, values)
for item in items:
    if item['kind'] == 'story':
        probe('bare_story', item['object_id'], {'fields': 'id', 'metadata': '1'})
        probe('page_scoped_story', facebook.page_id + '_' + item['object_id'], {'fields': 'id', 'metadata': '1'})
    elif item['kind'] == 'photo':
        probe('photo_' + item['object_id'], item['object_id'], {'fields': 'id,page_story_id,from{id},can_delete'})
write_json(ROOT / 'build' / today() / 'facebook-cleanup-result.json', result)
print(json.dumps(result, separators=(',', ':')))

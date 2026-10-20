"""Read only known publication IDs on this project's verified accounts."""
import argparse
import json

from easybosnian.core import ROOT, PROJECT, verify_repository, today, write_json
from easybosnian.meta import Facebook, Instagram, InstagramFacebook
from easybosnian.instagram_quota import publishing_quota
from easybosnian.store import Store
from easybosnian.http import redact


def diagnose_publishing_quota():
    verify_repository(remote=True)
    quotas={}
    for name,client in (('instagram_login',Instagram()),('facebook_login',InstagramFacebook())):
        client.verify_account()
        quotas[name]=publishing_quota(client,required=3)
    return {'date':today(),'instagram_publishing_quotas':quotas,
            'publication':'Read-only; no deletion, preparation, rendering or publication'}


def diagnose():
    verify_repository(remote=True)
    store = Store()
    if store.call('GET', '/health').get('project') != PROJECT:
        raise ValueError('Wrong project')
    date = today()
    items = [item for row in store.history()['days'] if row['date']==date for item in store.publications(row['batch_id'])]
    facebook = Facebook(); facebook.verify_page()
    instagram = Instagram(); instagram.verify_account()
    owned_stories = facebook.story_photos()
    rows = []
    for item in items:
        if item['platform'] != 'facebook':
            continue
        if item['account_id'] != facebook.page_id:
            raise ValueError('Wrong recorded Page')
        object_id = item['object_id']
        row = {'kind': item['kind'], 'object_id': object_id}
        try:
            if item['kind'] == 'story':
                row.update(current_story=object_id in owned_stories, backing_photo_id=owned_stories.get(object_id))
                full_id = object_id if '_' in object_id else facebook.page_id + '_' + object_id
                try:
                    post = facebook.call('GET', full_id, {'fields': 'id,from{id},is_published'})
                    row.update(full_post_id=post.get('id'), full_post_owner_matches=post.get('from', {}).get('id') == facebook.page_id,
                               full_post_is_published=post.get('is_published'))
                except Exception as error:
                    row['full_post_read_error'] = redact(error)
            elif item['kind'] == 'photo':
                photo = facebook.call('GET', object_id, {'fields': 'id,from{id},page_story_id,can_delete'})
                row.update(id_matches=photo.get('id') == object_id,
                           owner_matches=photo.get('from', {}).get('id') == facebook.page_id,
                           page_story_id=photo.get('page_story_id'), can_delete=photo.get('can_delete'))
            else:
                post = facebook.call('GET', object_id, {'fields': 'id,from{id},is_published'})
                row.update(id_matches=post.get('id') == object_id,
                           owner_matches=post.get('from', {}).get('id') == facebook.page_id,
                           is_published=post.get('is_published'))
        except Exception as error:
            row.update(read_error_type=type(error).__name__, read_error=redact(error))
        rows.append(row)
    return {'date': date, 'facebook_recorded_objects': rows,
            'instagram_current_story_count': len(instagram.stories().get('data', [])),
            'publication': 'Read-only; no deletion, preparation, rendering or publication'}


if __name__ == '__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--publishing-quota-only',action='store_true')
    result = diagnose_publishing_quota() if parser.parse_args().publishing_quota_only else diagnose()
    write_json(ROOT/'build'/result['date']/'meta-diagnostics-result.json', result)
    print(json.dumps(result, indent=2))

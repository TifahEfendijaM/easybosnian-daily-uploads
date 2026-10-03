"""Publish this run's exact cards as Facebook Page photo Stories."""
import os
import time
from urllib.parse import urlparse

from .core import ROOT, read_json, require_publishing, write_json
from .http import SafeError, request
from .meta import Facebook
from .notify import failure
from .stories import story_image


def verify_story(facebook, post_id, photo_id):
    # Poll only this submission. Follow opaque cursors, never provider next URLs.
    for attempt in range(6):
        after = None
        for _ in range(5):
            result = facebook.stories(after)
            if not isinstance(result.get('data'), list):
                raise ValueError('Facebook Stories read-back did not return a list')
            for story in result['data']:
                if str(story.get('post_id', '')) != post_id:
                    continue
                if str(story.get('media_id', '')) != photo_id or story.get('media_type') != 'photo':
                    raise ValueError('Facebook Story differs from the submitted photo')
                if story.get('status') == 'ARCHIVED':
                    raise ValueError('Facebook Story is archived rather than currently published')
                if story.get('status') != 'PUBLISHED':
                    continue
                url = urlparse(story.get('url', ''))
                if url.scheme != 'https' or url.hostname not in ('facebook.com', 'www.facebook.com', 'm.facebook.com') or not url.path.startswith('/stories/'):
                    raise ValueError('Facebook returned no actual Story permalink')
                return story['url']
            cursor = result.get('paging', {}).get('cursors', {}).get('after')
            if not result.get('paging', {}).get('next') or not cursor or cursor == after:
                break
            after = cursor
        if attempt < 5:
            time.sleep(3)
    raise ValueError('Facebook did not confirm this Story on the selected Page; no retry')


def publish_facebook_stories(store, package, assets, record=None):
    date = package['date']; stage = 'Facebook Stories authorization'; stories = []
    publication = 'nothing published to Facebook Stories'
    try:
        require_publishing()
        if os.getenv('FACEBOOK_POSTING_ENABLED') != 'true' or os.getenv('FACEBOOK_STORIES_ENABLED') != 'true':
            raise ValueError('Facebook Stories publisher is disabled')
        facebook = Facebook(); facebook.verify_page()
        palette = read_json(ROOT/'data/design-palettes.json')[package['design_palette']]
        for card in package['cards']:
            kind = card['kind']; stage = 'Facebook Stories rendering'
            path = ROOT/'build'/date/f'{kind}-story.jpg'
            story_image(assets[kind]['path'], path, palette)
            body = path.read_bytes()
            if len(body) > 10_000_000:
                raise ValueError('Facebook Story exceeds the 10 MB photo limit')
            store.put_file(date, path.name, body); url = store.expose(date, path.name)
            if request('GET', url, raw=True) != body:
                raise ValueError('Facebook Story bytes differ from the padded card')
            stage = 'Facebook Stories photo upload'; require_publishing()
            # Meta forbids reusing a photo already used in a published feed post.
            photo_id = str(facebook.photo(url, card['alt_text']))
            if record: record('photo',photo_id,facebook.page_id)
            stage = 'Facebook Stories publishing'; require_publishing()
            publication = 'partial or uncertain Facebook Story publication'
            post_id = facebook.story(photo_id)
            if record: record('story',post_id,facebook.page_id)
            item = {'slide': kind, 'photo_id': photo_id, 'post_id': post_id}; stories.append(item)
            stage = 'Facebook Stories verification'
            item['permalink'] = verify_story(facebook, post_id, photo_id)
        result = {'batch': date, 'published': True, 'status': 'three Facebook image Stories confirmed published', 'stories': stories}
        write_json(ROOT/'build'/date/'facebook-stories-result.json', result); return result
    except Exception as error:
        write_json(ROOT/'build'/date/'facebook-stories-result.json', {'batch': date, 'published': False, 'status': publication, 'stories': stories, 'failed_stage': stage})
        print(failure(date, stage, error, publication, os.getenv('GITHUB_RUN_URL')))
        raise SafeError('Facebook Stories failed at '+stage, stage) from None

"""Best-effort cleanup of known same-date supported objects; posting is independent."""
import os

from .core import require_publishing
from .meta import Facebook, InstagramDeletion
from .batches import BATCH_ID


def recorder(store, date, platform):
    def record(kind, object_id, account_id):
        store.remember(date, platform, kind, object_id, account_id)
    return record



def latest_batch(items):
    """Only the last recorded feed and its following up-to-three Story IDs.

    The Worker exposes D1 insertion order; no content state, intent or generation
    record is needed. Never infer recency from provider IDs or an unordered list.
    """
    if any(type(x.get('recorded_order')) is not int or x['recorded_order'] <= 0 for x in items):
        raise ValueError('Publication recording order is unavailable; skip cleanup rather than guess the latest batch')
    ordered = sorted(items, key=lambda x: x['recorded_order'])
    feeds = [x for x in ordered if x['kind']=='feed']
    feed = feeds[-1] if feeds else None
    stories = [x for x in ordered if x['kind']=='story' and (feed is None or x['recorded_order']>feed['recorded_order'])][-3:]
    return ([feed] if feed else []) + stories


def cleanup(store, date, platform,all_known=False,expected_date=None):
    require_publishing()
    items = [x for x in store.publications(date) if x['platform'] == platform]
    if BATCH_ID.fullmatch(date) and any(x.get('batch_id')!=date for x in items):
        raise ValueError('Publication identifiers belong to a different batch; refusing cleanup')
    if expected_date is not None and any(x.get('date')!=expected_date for x in items):
        raise ValueError('Publication identifiers belong to a different content date; refusing cleanup')
    if not items: return {'removed':0, 'already_absent':0}
    if platform == 'tiktok':
        from .buffer import Buffer
        provider = Buffer(); provider.verify_channel()
        if any(x['account_id'] != provider.channel_id for x in items):
            raise ValueError('Recorded TikTok items belong to a different channel')
        # Buffer cannot delete these upstream posts. Preserve known IDs without
        # claiming manual deletion or making the next upload depend on a checkbox.
        return {'removed':0, 'previous_posts_recorded':len(items),
                'deletion':'manual; not checked or performed'}
    all_items = items
    items = items if all_known else latest_batch(items)
    if not items: return {'removed':0, 'already_absent':0}
    provider = InstagramDeletion() if platform == 'instagram' else Facebook()
    provider.verify_account() if platform == 'instagram' else provider.verify_page()
    # Instagram Login and Facebook Login can identify this verified profile
    # differently. Accept only its verified publishing ID or linked deletion ID.
    expected = {os.environ['INSTAGRAM_USER_ID'], provider.user_id} if platform == 'instagram' else {provider.page_id}
    if any(x['account_id'] not in expected for x in items):
        raise ValueError('Recorded media belong to a different publishing account')
    result = {'removed':0, 'already_absent':0}
    if platform == 'facebook':
        # Page Stories expose publish/read, not a supported Story DELETE. Never
        # delete their backing photos as a workaround. Existing photo IDs mix
        # feed and Story uploads, so leave them intact and delete feed posts only.
        result.update(stories_recorded=sum(x['kind']=='story' for x in all_items),
                      photos_preserved=sum(x['kind']=='photo' for x in all_items),
                      story_deletion='manual; not checked or performed')
    kinds = ('story', 'feed') if platform == 'instagram' else ('feed',)
    for kind in kinds:
        selected = [x for x in items if x['kind'] == kind]
        if not selected: continue
        # A complete authenticated edge distinguishes absence from a read error.
        # Errors stop this cleanup attempt, never the independently checked post.
        owned = provider.owned_ids(kind)
        for item in selected:
            object_id = item['object_id']; require_publishing()
            if object_id in owned:
                provider.delete(object_id); result['removed'] += 1
            else: result['already_absent'] += 1
            # Retain identifiers after ambiguous deletion/storage failure.
            store.forget(date, platform, object_id)
    return result


def cleanup_day(store,batch_ids,date,platform):
    """Attempt every frozen, current-date batch once; retain uncertain IDs."""
    result={'scope':'all_today','batches_targeted':len(batch_ids),'removed':0,'already_absent':0};errors=[]
    if platform=='tiktok':
        return {**result,'status':'manual; TikTok deletion not checked or performed'},errors
    for batch_id in batch_ids:
        try:
            one=cleanup(store,batch_id,platform,all_known=True,expected_date=date)
            for key in ('removed','already_absent'):result[key]+=one.get(key,0)
        except Exception as error:errors.append(error)
    result['status']='failed; some earlier content may remain' if errors else 'supported current-date cleanup attempted'
    if platform=='facebook':result['story_deletion']='manual; not checked or performed'
    return result,errors

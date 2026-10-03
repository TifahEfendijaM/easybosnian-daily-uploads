"""Delete only known same-date provider objects before deliberate replacement."""
import os

from .core import require_publishing
from .meta import Facebook, InstagramDeletion


def recorder(store, date, platform):
    def record(kind, object_id, account_id):
        store.remember(date, platform, kind, object_id, account_id)
    return record


def cleanup(store, date, platform):
    require_publishing()
    items = [x for x in store.publications(date) if x['platform'] == platform]
    if not items: return {'removed':0, 'already_absent':0}
    if platform == 'tiktok':
        if os.getenv('TIKTOK_PREVIOUS_REMOVED') != 'true':
            raise ValueError('Delete today\'s previous TikTok post in TikTok, then select tiktok_previous_removed; Buffer cannot delete published TikTok posts')
        from .buffer import Buffer
        provider = Buffer(); provider.verify_channel()
        if any(x['account_id'] != provider.channel_id for x in items):
            raise ValueError('Recorded TikTok items belong to a different channel')
        # This is the user's explicit manual-deletion acknowledgement, never an
        # API claim that deleting a Buffer record deletes an upstream social post.
        for x in items: store.forget(date, platform, x['object_id'])
        return {'removed':0, 'manually_removed':len(items)}
    provider = InstagramDeletion() if platform == 'instagram' else Facebook()
    provider.verify_account() if platform == 'instagram' else provider.verify_page()
    # Instagram Login and Facebook Login can identify this verified profile
    # differently. Accept only its verified publishing ID or linked deletion ID.
    expected = {os.environ['INSTAGRAM_USER_ID'], provider.user_id} if platform == 'instagram' else {provider.page_id}
    if any(x['account_id'] not in expected for x in items):
        raise ValueError('Recorded media belong to a different publishing account')
    result = {'removed':0, 'already_absent':0}
    # Read the authenticated account's complete owned-media edge. Missing here
    # is distinct from a permission/network failure; those errors stop cleanup.
    for kind in ('story', 'feed', 'photo'):
        selected = [x for x in items if x['kind'] == kind]
        if not selected: continue
        owned = provider.owned_ids(kind)
        for item in selected:
            object_id = item['object_id']; require_publishing()
            if object_id in owned:
                provider.delete(object_id)
                result['removed'] += 1
            else: result['already_absent'] += 1
            # Keep identifiers on any ambiguous deletion/storage failure. A later
            # deliberate invocation checks ownership again; nothing retries here.
            store.forget(date, platform, object_id)
    return result

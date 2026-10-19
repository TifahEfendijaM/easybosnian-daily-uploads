"""One Instagram publication per invocation, with immediate content read-back."""
from .batches import output_key
import os
from urllib.parse import urlparse
from .core import ROOT, require_publishing, write_json
from .http import SafeError
from .meta import Instagram, InstagramFacebook
from .instagram_poll import instagram_caption, quiz_poll, poll_readback, POLL_MESSAGES
from .notify import failure


def verify_media(ig, package, media_id, caption=None):
    actual=ig.media(media_id)
    expected=caption if caption is not None else package['caption']+'\n\n'+' '.join(package['hashtags'])
    if actual.get('id')!=media_id or actual.get('caption','')!=expected or actual.get('media_type')!='CAROUSEL_ALBUM':
        raise ValueError('Instagram post identity, caption or carousel type differs from reviewed content')
    children=actual.get('children',{}).get('data',[])
    if len(children)!=3 or any(c.get('media_type')!='IMAGE' for c in children):
        raise ValueError('Instagram post must contain three image slides')
    url=urlparse(actual.get('permalink',''))
    if url.scheme!='https' or url.hostname!='www.instagram.com' or not url.path.startswith('/p/'):
        raise ValueError('Instagram returned no actual carousel permalink')
    return actual['permalink']


def publish_instagram(package, assets, record=None):
    date=package['date']; stage='authorization'; result={'batch':date,'batch_id':package.get('batch_id'),'published':False}
    publication='nothing published to Instagram'
    try:
        require_publishing()
        # Preserve the independently managed Instagram Login/Story credential.
        stories_account=Instagram(); stories_account.refresh_if_needed(); stories_account.verify_account()
        ig=InstagramFacebook(); ig.verify_account()
        stage='Instagram poll validation'
        caption=instagram_caption(package); poll, poll_result=quiz_poll(package)
        result['poll']=poll_result
        stage='publishing'; children=[]
        for card in package['cards']:
            child=ig.child(assets[card['kind']]['url'],card['alt_text']);children.append(child);ig.ready(child,stable=True)
        carousel=ig.carousel(children,caption,poll=poll)
        result.update(child_ids=children,container_id=carousel)
        ig.ready(carousel,stable=True);result['ready_status']='FINISHED'
        require_publishing()
        publication='Instagram publish request outcome uncertain'
        response=ig.publish_with_addon(carousel)
        media_id=response['id'];result['media_id']=media_id
        if record: record('feed',media_id,ig.user_id)
        status=response.get('caption_add_on_attachment_status')
        if status not in (None,'POLL_CREATION_FAILURE','PROMPT_CREATION_FAILURE'):
            status='UNRECOGNIZED'
        result['caption_add_on_attachment_status']=status
        publication='published to Instagram; content read-back pending';stage='publication verification'
        if poll is not None:
            # Status omission is documented success, but still confirm exact
            # ordered options via the separate edge. Never retry or republish.
            try:
                result['poll']=poll_readback(ig.poll_attachment(media_id),poll,status)
                result['poll']['readback']='completed'
            except Exception:
                reason=('creation_failure' if status=='POLL_CREATION_FAILURE' else
                        'unexpected_status' if status is not None else 'read_failed')
                result['poll']={'requested':True,'attached':False,'failed':True,
                                'reason':reason,'status':POLL_MESSAGES[reason],'readback':'failed'}
        # Keep the poll outcome even if independent feed read-back fails.
        result.update(permalink=verify_media(ig,package,media_id,caption),published=True,status='confirmed Instagram publication')
        if poll is not None:
            if result['poll']['failed']:
                result['status']='confirmed Instagram publication; native poll failed or unconfirmed; no republish'
                print(failure(date,'Instagram poll attachment',ValueError(result['poll']['status']),
                              'carousel published at '+result['permalink']+'; no automatic retry or republish',os.getenv('GITHUB_RUN_URL')))
        else:
            result['status']='confirmed Instagram publication; native poll omitted under approved limit policy'
            print('::warning::'+result['poll']['status'])
        write_json(ROOT/'build'/output_key(package)/'instagram-result.json',result)
        return result
    except Exception as error:
        if stage=='publishing' and result.get('container_id'):
            try:
                state=ig.call('GET',result['container_id'],{'fields':'status_code'}).get('status_code')
                if state in ('IN_PROGRESS','FINISHED','PUBLISHED','ERROR','EXPIRED'):
                    result['container_status_after_failure']=state
            except Exception:
                result['container_status_after_failure']='unavailable'
        result.update(status=publication,failed_stage=stage)
        write_json(ROOT/'build'/output_key(package)/'instagram-result.json',result)
        print(failure(date,stage,error,publication,os.getenv('GITHUB_RUN_URL')))
        raise SafeError('Instagram failed at '+stage,stage) from None

import copy
import os
import unittest
from unittest.mock import MagicMock, patch
from test_project import reviewed_fixture
from easybosnian.replacement import cleanup, recorder
from easybosnian.selection import selection_context, check_selection, novelty_history
from easybosnian.validate import validate
from easybosnian.meta import owned_ids, InstagramDeletion, Facebook, instagram_deletion_token


class SelectionTests(unittest.TestCase):
    def setUp(self):
        self.old=reviewed_fixture();self.history={'days':[{'date':self.old['date'],'content':self.old}]}

    def test_reuse_needs_today_and_the_exact_pinned_metadata(self):
        for choice in ('same_theme','same_words'):
            with self.assertRaises(ValueError):selection_context({'days':[]},self.old['date'],choice)
        chosen=selection_context(self.history,self.old['date'],'same_theme')
        wrong=copy.deepcopy(self.old);wrong['theme']['name']='renamed'
        with self.assertRaises(ValueError):check_selection(wrong,chosen)
        chosen=selection_context(self.history,self.old['date'],'same_words')
        wrong=copy.deepcopy(self.old);wrong['words'][0]['equivalence_keys'].append('changed')
        with self.assertRaises(ValueError):check_selection(wrong,chosen)

    def test_same_words_requires_fresh_copy_and_prompts(self):
        chosen=selection_context(self.history,self.old['date'],'same_words')
        with self.assertRaises(ValueError):check_selection(self.old,chosen)
        new=copy.deepcopy(self.old)
        for c in new['cards']:
            c['background_prompt']+=' New light.'
            key='question' if c['kind']=='quiz' else 'body'
            c[key]+=' Danas.'
        check_selection(new,chosen)
        validate(new,novelty_history(self.history,new['date'],chosen),include_today=True)
        # The exemption does not extend to an older day's reused words/theme.
        history=copy.deepcopy(self.history);history['days'].append({'date':'2026-10-01','content':self.old})
        with self.assertRaises(ValueError):validate(new,novelty_history(history,new['date'],chosen),include_today=True)

    def test_same_theme_does_not_exempt_previous_words_or_modify_history(self):
        chosen=selection_context(self.history,self.old['date'],'same_theme')
        filtered=novelty_history(self.history,self.old['date'],chosen)
        self.assertEqual(self.history['days'][0]['content']['theme'],self.old['theme'])
        with self.assertRaises(ValueError):validate(self.old,filtered,include_today=True)
        with self.assertRaises(ValueError):validate(self.old,self.history,include_today=True)


class ReplacementTests(unittest.TestCase):
    def item(self,kind='feed',id='123',platform='instagram'):
        return {'date':'2026-10-03','platform':platform,'kind':kind,'object_id':id,'account_id':'42'}

    def test_no_previous_ids_needs_no_deletion_authorization(self):
        store=MagicMock();store.publications.return_value=[]
        with patch('easybosnian.replacement.require_publishing'),patch('easybosnian.replacement.InstagramDeletion') as ig:
            self.assertEqual(cleanup(store,'2026-10-03','instagram')['removed'],0);ig.assert_not_called()

    def test_known_owned_items_deleted_and_manually_absent_items_skipped(self):
        store=MagicMock();store.publications.return_value=[self.item(id='123'),self.item(kind='story',id='456')]
        ig=MagicMock();ig.owned_ids.side_effect=lambda kind:{'123'} if kind=='feed' else set()
        with patch.dict(os.environ,{'INSTAGRAM_USER_ID':'42'}),patch('easybosnian.replacement.require_publishing'),patch('easybosnian.replacement.InstagramDeletion',return_value=ig):
            result=cleanup(store,'2026-10-03','instagram')
        self.assertEqual(result,{'removed':1,'already_absent':1});ig.delete.assert_called_once_with('123')
        self.assertEqual(store.forget.call_count,2)

    def test_wrong_account_permission_failure_and_uncertain_delete_keep_ids(self):
        for failure in ('account','listing','delete','kill'):
            store=MagicMock();store.publications.return_value=[self.item()];ig=MagicMock();ig.owned_ids.return_value={'123'}
            if failure=='account':store.publications.return_value[0]['account_id']='other'
            if failure=='listing':ig.owned_ids.side_effect=RuntimeError('permission denied')
            if failure=='delete':ig.delete.side_effect=RuntimeError('timeout')
            with patch.dict(os.environ,{'INSTAGRAM_USER_ID':'42'}),patch('easybosnian.replacement.require_publishing',side_effect=ValueError('off') if failure=='kill' else None),patch('easybosnian.replacement.InstagramDeletion',return_value=ig):
                with self.assertRaises((ValueError,RuntimeError)):cleanup(store,'2026-10-03','instagram')
            store.forget.assert_not_called()

    def test_tiktok_requires_explicit_manual_deletion_acknowledgement(self):
        store=MagicMock();store.publications.return_value=[self.item(platform='tiktok')]
        with patch.dict(os.environ,{'TIKTOK_PREVIOUS_REMOVED':'false'}),patch('easybosnian.replacement.require_publishing'):
            with self.assertRaisesRegex(ValueError,'Buffer cannot delete'):cleanup(store,'2026-10-03','tiktok')
        buffer=MagicMock();buffer.channel_id='42'
        with patch.dict(os.environ,{'TIKTOK_PREVIOUS_REMOVED':'true'}),patch('easybosnian.replacement.require_publishing'),patch('easybosnian.buffer.Buffer',return_value=buffer):
            self.assertEqual(cleanup(store,'2026-10-03','tiktok')['manually_removed'],1)
        buffer.call.assert_not_called();store.forget.assert_called_once()

    def test_recording_does_not_depend_on_verification(self):
        store=MagicMock();recorder(store,'2026-10-03','facebook')('feed','123','42')
        store.remember.assert_called_once_with('2026-10-03','facebook','feed','123','42')

    def test_complete_listing_uses_opaque_cursors_and_rejects_incomplete_reads(self):
        provider=MagicMock();provider.call.side_effect=[{'data':[{'id':'1'}],'paging':{'next':'untrusted url','cursors':{'after':'cursor'}}},{'data':[{'id':'2'}]}]
        self.assertEqual(owned_ids(provider,'42/media',{'fields':'id'}),{'1','2'})
        self.assertEqual(provider.call.call_args.args[1],'42/media')
        self.assertEqual(provider.call.call_args.args[2]['after'],'cursor')
        for data in ({}, {'data':[{}]}, {'data':[],'paging':{'next':'exists'}}):
            provider.call.side_effect=None;provider.call.return_value=data
            with self.assertRaises(ValueError):owned_ids(provider,'42/media',{})

    def test_instagram_delete_requires_exact_response_and_separate_token(self):
        with patch.dict(os.environ,{'INSTAGRAM_DELETE_ACCESS_TOKEN':'delete','INSTAGRAM_DELETE_USER_ID':'42','INSTAGRAM_ACCESS_TOKEN':'publish','META_GRAPH_VERSION':'v26.0'}):
            ig=InstagramDeletion();self.assertEqual(ig.token,'delete');self.assertIn('graph.facebook.com',ig.base)
            with patch.object(ig,'call',return_value={'success':True,'deleted_id':'123'}) as call:
                ig.delete('123');call.assert_called_once_with('DELETE','123')
            for result in ({'success':False},{'success':True,'deleted_id':'other'}):
                with patch.object(ig,'call',return_value=result),self.assertRaises(ValueError):ig.delete('123')

    def test_facebook_cleanup_includes_stories_posts_and_partial_photos(self):
        store=MagicMock();store.publications.return_value=[self.item(kind=kind,id=id,platform='facebook') for kind,id in [('feed','42_123'),('photo','456'),('story','42_789')]]
        fb=MagicMock();fb.page_id='42';fb.owned_ids.side_effect=lambda kind:{'42_123','456','42_789'}
        with patch('easybosnian.replacement.require_publishing'),patch('easybosnian.replacement.Facebook',return_value=fb):
            self.assertEqual(cleanup(store,'2026-10-03','facebook')['removed'],3)
        self.assertEqual([c.args[0] for c in fb.delete.call_args_list],['42_789','42_123','456'])
        self.assertEqual(store.forget.call_count,3)

    def test_returned_facebook_photo_id_is_recorded_before_later_upload_failure(self):
        from easybosnian.facebook import publish_facebook
        fb=MagicMock();fb.page_id='42';fb.photo.side_effect=['123',RuntimeError('network')]
        package=reviewed_fixture();assets={c['kind']:{'url':'https://example.test/'+c['kind']} for c in package['cards']};record=MagicMock()
        with patch.dict(os.environ,{'FACEBOOK_POSTING_ENABLED':'true'}),patch('easybosnian.facebook.Facebook',return_value=fb),patch('easybosnian.facebook.require_publishing'),patch('easybosnian.facebook.write_json'),patch('easybosnian.facebook.failure',return_value='failure'):
            with self.assertRaises(RuntimeError):publish_facebook(package,assets,record=record)
        record.assert_called_once_with('photo','123','42');fb.publish.assert_not_called()

    def test_long_lived_deletion_authorization_rejects_wrong_app_scope_or_expiry(self):
        import time
        debug={'is_valid':True,'app_id':'1987873818544936','type':'USER','scopes':['instagram_basic','instagram_manage_contents','pages_read_engagement','pages_show_list'],'expires_at':int(time.time())+60*86400}
        page={'instagram_business_account':{'id':'42','username':'easy_bosnian'}}
        with patch.dict(os.environ,{'META_GRAPH_VERSION':'v26.0'}),patch.object(InstagramDeletion,'verify_account'):
            for change in ({},{'app_id':'other'},{'scopes':['instagram_basic']},{'expires_at':int(time.time())+3600},{'type':'PAGE'}):
                with patch('easybosnian.meta.request',side_effect=[{'access_token':'private'},page,{'data':{**debug,**change}}]):
                    if change:
                        with self.assertRaises(ValueError):instagram_deletion_token('short','secret')
                    else:
                        token,info=instagram_deletion_token('short','secret')
                        self.assertEqual(token,'private');self.assertEqual(info['instagram_id'],'42');self.assertNotIn('private',str(info))

    def test_new_assets_render_before_any_cleanup_and_failed_cleanup_blocks_that_platform(self):
        from easybosnian.daily import daily
        sequence=[];store=MagicMock();store.content.return_value=reviewed_fixture();store.history.return_value={'days':[]}
        def deletion(*args):sequence.append('cleanup');raise ValueError('authorization missing')
        with patch.dict(os.environ,{'FACEBOOK_POSTING_ENABLED':'false','TIKTOK_POSTING_ENABLED':'false'}),patch('easybosnian.daily.verify_repository'),patch('easybosnian.daily.require_publishing'),patch('easybosnian.daily.Store',return_value=store),patch('easybosnian.daily.validate'),patch('easybosnian.daily.artwork',side_effect=lambda *a,**k:sequence.append('render') or {}),patch('easybosnian.daily.cleanup',side_effect=deletion),patch('easybosnian.daily.publish_instagram') as publish,patch('easybosnian.daily.write_json'),patch('easybosnian.daily.failure',return_value='failure'):
            with self.assertRaises(RuntimeError):daily('2026-10-03','daily')
        self.assertEqual(sequence,['render','cleanup']);publish.assert_not_called()

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

    def test_same_words_retains_words_but_requires_fresh_copy_and_allows_new_design(self):
        chosen=selection_context(self.history,self.old['date'],'same_words')
        with self.assertRaises(ValueError):check_selection(self.old,chosen)
        new=copy.deepcopy(self.old);new['caption']+=' Danas.'
        new['design_palette']='gold-cream'
        for c in new['cards']:
            c['background_prompt']+=' New light.'
            c['design_template']='minimal'
            c['question' if c['kind']=='quiz' else 'body']+=' Danas.'
        check_selection(new,chosen)
        for change in ('caption','body','prompt','word','theme'):
            wrong=copy.deepcopy(new)
            if change=='caption':wrong['caption']=self.old['caption']
            if change=='body':wrong['cards'][1]=copy.deepcopy(self.old['cards'][1]);wrong['cards'][1]['background_prompt']+=' New light.'
            if change=='prompt':wrong['cards'][0]['background_prompt']=self.old['cards'][0]['background_prompt']
            if change=='word':wrong['words'][0]['lemma']='kaput'
            if change=='theme':wrong['theme']['name']='renamed'
            with self.subTest(change=change),self.assertRaises(ValueError):check_selection(wrong,chosen)
        validate(new,novelty_history(self.history,new['date'],chosen),include_today=True)
        history=copy.deepcopy(self.history);history['days'].append({'date':'2026-10-01','content':self.old})
        with self.assertRaises(ValueError):validate(new,novelty_history(history,new['date'],chosen),include_today=True)

    def test_same_theme_does_not_exempt_previous_words_or_modify_history(self):
        chosen=selection_context(self.history,self.old['date'],'same_theme')
        filtered=novelty_history(self.history,self.old['date'],chosen)
        self.assertEqual(self.history['days'][0]['content']['theme'],self.old['theme'])
        with self.assertRaises(ValueError):validate(self.old,filtered,include_today=True)
        with self.assertRaises(ValueError):validate(self.old,self.history,include_today=True)

    def test_non_custom_choices_ignore_every_custom_control(self):
        for choice in ('new','same_theme','same_words'):
            chosen=selection_context(self.history,self.old['date'],choice,'Unrelated theme',['x','x','x'],['unknown']*3)
            self.assertEqual(chosen,{'choice':choice,'previous':self.old})

    def test_custom_blank_defaults_preserve_metadata_but_require_fresh_text(self):
        chosen=selection_context(self.history,self.old['date'],'custom')
        self.assertEqual(chosen['requested_theme'],self.old['theme']['name'])
        self.assertEqual(chosen['requested_words'],[w['lemma'] for w in self.old['words']])
        with self.assertRaises(ValueError):check_selection(self.old,chosen)
        new=copy.deepcopy(self.old);new['caption']+=' Danas.'
        for c in new['cards']:
            c['background_prompt']+=' New light.'
            key='question' if c['kind']=='quiz' else 'body';c[key]+=' Danas.'
        check_selection(new,chosen)
        validate(new,novelty_history(self.history,new['date'],chosen),include_today=True)
        older=copy.deepcopy(self.history);older['days'].append({'date':'2026-10-01','content':self.old})
        with self.assertRaises(ValueError):validate(new,novelty_history(older,new['date'],chosen),include_today=True)

    def test_custom_partial_defaults_and_novelty_exempt_only_explicit_reuse(self):
        chosen=selection_context(self.history,self.old['date'],'custom','',['','vjetar',''])
        self.assertIsNone(chosen['pinned_words'][1]);self.assertEqual(chosen['requested_words'][1],'vjetar')
        remaining=novelty_history(self.history,self.old['date'],chosen)['days'][0]['content']['words']
        self.assertEqual(remaining,[self.old['words'][1]])
        chosen=selection_context(self.history,self.old['date'],'custom','Zimska šetnja',['','',''])
        self.assertIsNone(chosen['pinned_theme'])
        self.assertEqual(novelty_history(self.history,self.old['date'],chosen)['days'][0]['content']['theme'],self.old['theme'])
        with self.assertRaises(ValueError):check_selection(self.old,chosen)

    def test_custom_first_run_requires_all_fields_and_distinct_words(self):
        history={'days':[]}
        for theme,words in (('',None),('Kišni dan',['kap','','oblak']),('Kišni dan',['kap','kap','oblak'])):
            with self.assertRaises(ValueError):selection_context(history,self.old['date'],'custom',theme,words)
        chosen=selection_context(history,self.old['date'],'custom','Kišni dan',['kišobran','oblak','kap'])
        check_selection(self.old,chosen)
        self.assertEqual(chosen['pinned_words'],[None]*3)


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

    def test_verified_facebook_login_id_can_record_pre_feature_instagram_media(self):
        store=MagicMock();store.publications.return_value=[self.item(id='123')]
        ig=MagicMock();ig.user_id='42';ig.owned_ids.return_value={'123'}
        with patch.dict(os.environ,{'INSTAGRAM_USER_ID':'different-scoped-publishing-id'}),patch('easybosnian.replacement.require_publishing'),patch('easybosnian.replacement.InstagramDeletion',return_value=ig):
            self.assertEqual(cleanup(store,'2026-10-03','instagram')['removed'],1)
        ig.verify_account.assert_called_once();ig.delete.assert_called_once_with('123')
        store.publications.return_value[0]['account_id']='unrelated'
        with patch.dict(os.environ,{'INSTAGRAM_USER_ID':'different-scoped-publishing-id'}),patch('easybosnian.replacement.require_publishing'),patch('easybosnian.replacement.InstagramDeletion',return_value=ig):
            with self.assertRaises(ValueError):cleanup(store,'2026-10-03','instagram')

    def test_wrong_account_permission_failure_and_uncertain_delete_keep_ids(self):
        for failure in ('account','listing','delete','kill'):
            store=MagicMock();store.publications.return_value=[self.item()];ig=MagicMock();ig.owned_ids.return_value={'123'}
            if failure=='account':store.publications.return_value[0]['account_id']='other'
            if failure=='listing':ig.owned_ids.side_effect=RuntimeError('permission denied')
            if failure=='delete':ig.delete.side_effect=RuntimeError('timeout')
            with patch.dict(os.environ,{'INSTAGRAM_USER_ID':'42'}),patch('easybosnian.replacement.require_publishing',side_effect=ValueError('off') if failure=='kill' else None),patch('easybosnian.replacement.InstagramDeletion',return_value=ig):
                with self.assertRaises((ValueError,RuntimeError)):cleanup(store,'2026-10-03','instagram')
            store.forget.assert_not_called()

    def test_tiktok_rerun_needs_no_acknowledgement_and_never_claims_or_performs_deletion(self):
        store=MagicMock();store.publications.return_value=[self.item(platform='tiktok')]
        buffer=MagicMock();buffer.channel_id='42'
        with patch.dict(os.environ,{},clear=True),patch('easybosnian.replacement.require_publishing'),patch('easybosnian.buffer.Buffer',return_value=buffer):
            result=cleanup(store,'2026-10-03','tiktok')
        self.assertEqual(result,{'removed':0,'previous_posts_recorded':1,'deletion':'manual; not checked or performed'})
        buffer.verify_channel.assert_called_once();buffer.call.assert_not_called();store.forget.assert_not_called()
        store.publications.return_value[0]['account_id']='wrong'
        with patch('easybosnian.replacement.require_publishing'),patch('easybosnian.buffer.Buffer',return_value=buffer),self.assertRaisesRegex(ValueError,'different channel'):
            cleanup(store,'2026-10-03','tiktok')
        store.forget.assert_not_called()

    def test_daily_submits_new_tiktok_content_when_previous_posts_remain_recorded(self):
        from easybosnian.daily import daily
        store=MagicMock();store.content.return_value=reviewed_fixture();store.history.return_value={'days':[]}
        store.publications.return_value=[self.item(platform='tiktok')]
        buffer=MagicMock();buffer.channel_id='42'
        env={'GITHUB_ACTIONS':'true','DAILY_POSTING_ENABLED':'true','TIKTOK_POSTING_ENABLED':'true'}
        with patch.dict(os.environ,env,clear=True),patch('easybosnian.daily.verify_repository'),patch('easybosnian.daily.Store',return_value=store),patch('easybosnian.daily.artwork',return_value={}),patch('easybosnian.daily.publish_instagram',return_value={'published':True,'status':'published'}),patch('easybosnian.daily.publish_tiktok',return_value={'published':True,'status':'published'}) as submit,patch('easybosnian.buffer.Buffer',return_value=buffer),patch('easybosnian.daily.write_json'):
            result=daily('2026-10-03','daily')
        submit.assert_called_once()
        self.assertTrue(result['tiktok']['published'])
        self.assertEqual(result['tiktok']['replacement_cleanup']['previous_posts_recorded'],1)
        self.assertEqual(result['tiktok']['replacement_cleanup']['removed'],0)
        store.forget.assert_not_called();buffer.call.assert_not_called()

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
        fb.story_photos.return_value={'42_789':'456'}
        with patch('easybosnian.replacement.require_publishing'),patch('easybosnian.replacement.Facebook',return_value=fb):
            self.assertEqual(cleanup(store,'2026-10-03','facebook')['removed'],3)
        fb.delete_story_photo.assert_called_once_with('42_789','456')
        self.assertEqual([c.args[0] for c in fb.delete.call_args_list],['42_123'])
        self.assertEqual(store.forget.call_count,3)

    def test_facebook_story_photo_must_be_recorded_for_the_same_date(self):
        store=MagicMock();store.publications.return_value=[self.item(kind='story',id='789',platform='facebook')]
        fb=MagicMock();fb.page_id='42';fb.story_photos.return_value={'789':'456'}
        with patch('easybosnian.replacement.require_publishing'),patch('easybosnian.replacement.Facebook',return_value=fb):
            with self.assertRaisesRegex(ValueError,'not recorded'):cleanup(store,'2026-10-03','facebook')
        fb.delete_story_photo.assert_not_called();store.forget.assert_not_called()

    def test_facebook_story_mapping_completes_cursor_reads_and_keeps_video_identity(self):
        with patch.dict(os.environ,{'META_GRAPH_VERSION':'v26.0'}):fb=Facebook(token='test',page_id='42')
        first={'post_id':'789','media_id':'456','media_type':'photo'}
        fb.stories=MagicMock(side_effect=[{'data':[first],'paging':{'next':'untrusted','cursors':{'after':'opaque'}}},{'data':[{'post_id':'790','media_id':'457','media_type':'video'}]}])
        self.assertEqual(fb.story_photos(),{'789':'456','790':None})
        self.assertEqual(fb.stories.call_args.args,('opaque',))
        for response in ({}, {'data':[{}]}, {'data':[first],'paging':{'next':'untrusted'}}, {'data':[first,{**first,'media_id':'999'}]}):
            fb.stories=MagicMock(return_value=response)
            with self.assertRaises(ValueError):fb.story_photos()

    def test_facebook_story_deletes_its_owned_photo_once_and_requires_removal(self):
        with patch.dict(os.environ,{'META_GRAPH_VERSION':'v26.0'}):fb=Facebook(token='test',page_id='42')
        photo={'id':'456','from':{'id':'42'},'page_story_id':'42_789','can_delete':True}
        fb.call=MagicMock(return_value=photo);fb.delete=MagicMock();fb.story_photos=MagicMock(return_value={})
        with patch('easybosnian.meta.require_publishing'):
            fb.delete_story_photo('789','456')
        fb.delete.assert_called_once_with('456')
        for change in ({'id':'wrong'},{'from':{'id':'other'}},{'page_story_id':'42_999'},{'can_delete':False}):
            fb.call.return_value={**photo,**change};fb.delete.reset_mock()
            with patch('easybosnian.meta.require_publishing'),self.assertRaises(ValueError):fb.delete_story_photo('789','456')
            fb.delete.assert_not_called()
        fb.call.return_value=photo;fb.story_photos.return_value={'789':'456'};fb.delete.reset_mock()
        with patch('easybosnian.meta.require_publishing'),patch('easybosnian.meta.time.sleep'),self.assertRaisesRegex(ValueError,'no second deletion'):
            fb.delete_story_photo('789','456')
        fb.delete.assert_called_once_with('456')

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

    def test_zero_token_expiry_still_honours_meta_data_access_expiry(self):
        import time
        expiry=int(time.time())+90*86400
        debug={'is_valid':True,'app_id':'1987873818544936','type':'USER','scopes':['instagram_basic','instagram_manage_contents','pages_read_engagement','pages_show_list'],'expires_at':0,'data_access_expires_at':expiry}
        page={'instagram_business_account':{'id':'42','username':'easy_bosnian'}}
        with patch.dict(os.environ,{'META_GRAPH_VERSION':'v26.0'}),patch.object(InstagramDeletion,'verify_account'):
            with patch('easybosnian.meta.request',side_effect=[{'access_token':'private'},page,{'data':debug}]):
                token,info=instagram_deletion_token('short','secret')
                self.assertEqual(info['expires_at'],expiry);self.assertEqual(info['token_expires_at'],0)
            for access_expiry in (0,int(time.time())+3600):
                with patch('easybosnian.meta.request',side_effect=[{'access_token':'private'},page,{'data':{**debug,'data_access_expires_at':access_expiry}}]):
                    with self.assertRaises(ValueError):instagram_deletion_token('short','secret')

    def test_new_assets_render_before_any_cleanup_and_failed_cleanup_blocks_that_platform(self):
        from easybosnian.daily import daily
        sequence=[];store=MagicMock();store.content.return_value=reviewed_fixture();store.history.return_value={'days':[]}
        def deletion(*args):sequence.append('cleanup');raise ValueError('authorization missing')
        with patch.dict(os.environ,{'FACEBOOK_POSTING_ENABLED':'false','TIKTOK_POSTING_ENABLED':'false'}),patch('easybosnian.daily.verify_repository'),patch('easybosnian.daily.require_publishing'),patch('easybosnian.daily.Store',return_value=store),patch('easybosnian.daily.validate'),patch('easybosnian.daily.artwork',side_effect=lambda *a,**k:sequence.append('render') or {}),patch('easybosnian.daily.cleanup',side_effect=deletion),patch('easybosnian.daily.publish_instagram') as publish,patch('easybosnian.daily.write_json'),patch('easybosnian.daily.failure',return_value='failure'):
            with self.assertRaises(RuntimeError):daily('2026-10-03','daily')
        self.assertEqual(sequence,['render','cleanup']);publish.assert_not_called()

import copy
import os
import unittest
from unittest.mock import MagicMock, patch
from test_project import reviewed_fixture
from easybosnian.replacement import cleanup, recorder, latest_batch
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
        return {'recorded_order':int(id.split('_')[-1]) if id.isdigit() or '_' in id else 1,'date':'2026-10-03','platform':platform,'kind':kind,'object_id':id,'account_id':'42'}

    def test_only_latest_feed_and_its_three_stories_are_deleted(self):
        items=[self.item(kind=kind,id=str(index)) for index,kind in [(10,'feed'),(11,'story'),(12,'story'),(13,'story'),(20,'feed'),(21,'story'),(22,'story'),(23,'story')]]
        store=MagicMock();store.publications.return_value=list(reversed(items))
        ig=MagicMock();ig.user_id='42';ig.owned_ids.return_value={x['object_id'] for x in items}
        with patch.dict(os.environ,{'INSTAGRAM_USER_ID':'42'}),patch('easybosnian.replacement.require_publishing'),patch('easybosnian.replacement.InstagramDeletion',return_value=ig):
            result=cleanup(store,'2026-10-03','instagram')
        self.assertEqual(result['removed'],4)
        self.assertEqual([call.args[0] for call in ig.delete.call_args_list],['21','22','23','20'])
        self.assertEqual({call.args[2] for call in store.forget.call_args_list},{'20','21','22','23'})

    def test_latest_partial_batch_never_deletes_older_stories_to_make_three(self):
        items=[self.item(kind=kind,id=str(index)) for index,kind in [(10,'feed'),(11,'story'),(12,'story'),(13,'story'),(20,'feed'),(21,'story')]]
        self.assertEqual([x['object_id'] for x in latest_batch(items)],['20','21'])
        items[-1].pop('recorded_order')
        with self.assertRaisesRegex(ValueError,'skip cleanup'):latest_batch(items)

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

    def test_facebook_deletes_only_feed_and_never_story_or_backing_photos(self):
        store=MagicMock();store.publications.return_value=[self.item(kind=kind,id=id,platform='facebook') for kind,id in [('feed','42_123'),('photo','456'),('story','42_789')]]
        fb=MagicMock();fb.page_id='42';fb.owned_ids.return_value={'42_123'}
        with patch('easybosnian.replacement.require_publishing'),patch('easybosnian.replacement.Facebook',return_value=fb):
            result=cleanup(store,'2026-10-03','facebook')
        self.assertEqual(result['removed'],1)
        self.assertEqual(result['stories_recorded'],1);self.assertEqual(result['photos_preserved'],1)
        fb.owned_ids.assert_called_once_with('feed');fb.delete.assert_called_once_with('42_123')
        fb.story_photos.assert_not_called();store.forget.assert_called_once_with('2026-10-03','facebook','42_123')

    def test_facebook_only_story_ids_never_request_deletion_or_story_listing(self):
        store=MagicMock();store.publications.return_value=[self.item(kind='story',id='789',platform='facebook'),self.item(kind='photo',id='456',platform='facebook')]
        fb=MagicMock();fb.page_id='42'
        with patch('easybosnian.replacement.require_publishing'),patch('easybosnian.replacement.Facebook',return_value=fb):
            result=cleanup(store,'2026-10-03','facebook')
        self.assertEqual(result['removed'],0);self.assertEqual(result['story_deletion'],'manual; not checked or performed')
        fb.delete.assert_not_called();fb.owned_ids.assert_not_called();fb.story_photos.assert_not_called();store.forget.assert_not_called()

    def test_facebook_story_mapping_completes_cursor_reads_and_keeps_video_identity(self):
        with patch.dict(os.environ,{'META_GRAPH_VERSION':'v26.0'}):fb=Facebook(token='test',page_id='42')
        first={'post_id':'789','media_id':'456','media_type':'photo'}
        fb.stories=MagicMock(side_effect=[{'data':[first],'paging':{'next':'untrusted','cursors':{'after':'opaque'}}},{'data':[{'post_id':'790','media_id':'457','media_type':'video'}]}])
        self.assertEqual(fb.story_photos(),{'789':'456','790':None})
        self.assertEqual(fb.stories.call_args.args,('opaque',))
        for response in ({}, {'data':[{}]}, {'data':[first],'paging':{'next':'untrusted'}}, {'data':[first,{**first,'media_id':'999'}]}):
            fb.stories=MagicMock(return_value=response)
            with self.assertRaises(ValueError):fb.story_photos()

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

    def test_failed_meta_cleanup_does_not_block_feed_or_story_publishing(self):
        from easybosnian.daily import daily
        from contextlib import ExitStack
        sequence=[];store=MagicMock();store.content.return_value=reviewed_fixture();store.history.return_value={'days':[]}
        def deletion(*args):sequence.append('cleanup '+args[-1]);raise ValueError('authorization missing')
        env={'GITHUB_ACTIONS':'true','DAILY_POSTING_ENABLED':'true','FACEBOOK_POSTING_ENABLED':'true','TIKTOK_POSTING_ENABLED':'false','INSTAGRAM_STORIES_ENABLED':'true','FACEBOOK_STORIES_ENABLED':'true'}
        with patch.dict(os.environ,env,clear=True),ExitStack() as stack:
            for name in ('verify_repository','write_json'):
                stack.enter_context(patch('easybosnian.daily.'+name))
            stack.enter_context(patch('easybosnian.daily.Store',return_value=store))
            stack.enter_context(patch('easybosnian.daily.artwork',side_effect=lambda *a,**k:sequence.append('render') or {}))
            stack.enter_context(patch('easybosnian.daily.cleanup',side_effect=deletion))
            publishers={}
            for name in ('publish_instagram','publish_facebook','publish_stories','publish_facebook_stories'):
                publishers[name]=stack.enter_context(patch('easybosnian.daily.'+name,return_value={'published':True}))
            notice=stack.enter_context(patch('easybosnian.daily.failure',return_value='safe cleanup warning'))
            result=daily('2026-10-03','daily')
        self.assertEqual(sequence,['render','cleanup instagram','cleanup facebook'])
        for publisher in publishers.values():publisher.assert_called_once()
        for platform in ('instagram','facebook'):
            self.assertTrue(result[platform]['published'])
            self.assertIn('failed',result[platform]['replacement_cleanup']['status'])
        self.assertEqual(notice.call_count,2)
        self.assertTrue(all('new feed publication confirmed' in call.args[3] for call in notice.call_args_list))

    def test_cleanup_failure_never_bypasses_live_publishing_kill_switch(self):
        from easybosnian.daily import daily
        with patch.dict(os.environ,{'GITHUB_ACTIONS':'true','DAILY_POSTING_ENABLED':'false'},clear=True),patch('easybosnian.daily.verify_repository'),patch('easybosnian.daily.Store') as store,patch('easybosnian.daily.cleanup') as clean,patch('easybosnian.daily.publish_instagram') as submit,patch('easybosnian.daily.failure',return_value='disabled'):
            with self.assertRaises(RuntimeError):daily('2026-10-03','daily')
        store.assert_not_called();clean.assert_not_called();submit.assert_not_called()

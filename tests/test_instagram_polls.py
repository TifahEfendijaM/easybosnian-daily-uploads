import copy
import json
import os
import time
import unittest
from unittest.mock import MagicMock, patch

from easybosnian.instagram_poll import (characters, instagram_caption, quiz_poll,
                                        serialize_poll, poll_readback, PollLimit)
from easybosnian.meta import Instagram, InstagramFacebook, instagram_facebook_token
from easybosnian.pipeline import publish_instagram
from easybosnian.success_report import publication_data
from easybosnian.http import SafeError
from test_project import reviewed_fixture


class PollContentTests(unittest.TestCase):
    def test_exact_two_three_four_options_in_order_without_private_answer(self):
        for count in (2, 3, 4):
            package=reviewed_fixture()
            texts=['Čaša','Šolja','Đezva','Tanjir'][:count]
            package['cards'][0]['options']=[{'label':label,'text':text} for label,text in zip('ABCD',texts)]
            before=copy.deepcopy(package)
            poll,status=quiz_poll(package)
            self.assertEqual(list(poll.values()),texts)
            self.assertEqual(list(poll),['option_'+letter for letter in 'abcd'[:count]])
            self.assertEqual(json.loads(serialize_poll(poll)),poll)
            self.assertTrue(status['requested']);self.assertEqual(package,before)
            self.assertNotIn('correct',serialize_poll(poll));self.assertNotIn('private_review',serialize_poll(poll))

    def test_emoji_and_decomposed_accents_are_single_characters_without_rewriting(self):
        for text in ('Š'*25,'s\u030c'*25,'👨‍👩‍👧‍👦'*25):
            self.assertEqual(characters(text),25)
        text='s\u030c'*24+'👍🏽'
        poll={'option_a':text,'option_b':'Ne'}
        self.assertEqual(characters(text),25)
        self.assertEqual(json.loads(serialize_poll(poll))['option_a'],text)

    def test_limits_omit_only_native_poll_and_never_shorten_answers(self):
        for value,reason in [('Š'*26,'option_length'),(' Da','option_whitespace'),('', 'option_length')]:
            package=reviewed_fixture();package['cards'][0]['options'][0]['text']=value
            before=copy.deepcopy(package);poll,status=quiz_poll(package)
            self.assertIsNone(poll);self.assertEqual(status['reason'],reason)
            self.assertFalse(status['failed']);self.assertEqual(package,before)
        poll={key:'"'*25 for key in ('option_a','option_b','option_c','option_d')}
        with self.assertRaises(PollLimit) as error:serialize_poll(poll)
        self.assertEqual(error.exception.reason,'payload_length')
        for size in range(1,26):
            candidate={'option_a':'"'*size,'option_b':'"'*size,'option_c':'"'*size,'option_d':'"'*size}
            raw=json.dumps(candidate,ensure_ascii=False,separators=(',',':'))
            if len(raw)<=200:self.assertEqual(serialize_poll(candidate),raw)
            else:
                with self.assertRaises(PollLimit):serialize_poll(candidate)

    def test_missing_out_of_order_extra_private_keys_and_discontinuous_options_rejected(self):
        for poll in ({'option_a':'Da'},{'option_a':'Da','option_d':'Ne'},
                     {'option_b':'Ne','option_a':'Da'},
                     {'option_a':'Da','option_b':'Ne','correct_option':'A'}):
            with self.assertRaises(ValueError):serialize_poll(poll)
        package=reviewed_fixture();package['cards'][0]['options'].reverse()
        with self.assertRaises(ValueError):quiz_poll(package)

    def test_caption_preserves_question_difficulty_invitation_and_final_website(self):
        package=reviewed_fixture()
        package['caption']='U ovoj situaciji vježbamo bosanski na nivou A2.\n\nZa lakši razgovor nastavite učiti s nama.\n👉easybosnian.com'
        value=instagram_caption(package)
        self.assertTrue(value.startswith('Pitanje dana: '+package['cards'][0]['question']))
        self.assertIn('bosanski na nivou A2.',value)
        self.assertTrue(value.endswith('Za lakši razgovor nastavite učiti s nama.\n👉easybosnian.com'))
        self.assertIn(' '.join(package['hashtags']),value)
        self.assertNotIn(package['private_review']['correct_text'],value)
        package['caption']=value
        self.assertEqual(instagram_caption(package).count(package['cards'][0]['question']),1)

    def test_caption_limits_fail_without_creating_or_truncating_content(self):
        package=reviewed_fixture();package['caption']='č'*2200
        with self.assertRaisesRegex(ValueError,'2200'):instagram_caption(package)
        package=reviewed_fixture();package['hashtags']=['#x']*31
        with self.assertRaises(ValueError):instagram_caption(package)
        package=reviewed_fixture();package['caption']='@x '*21
        with self.assertRaises(ValueError):instagram_caption(package)

    def test_readback_ignores_votes_but_compares_exact_choices_and_status(self):
        expected={'option_a':'Da','option_b':'Ne'}
        read={'poll_attachment':{**expected,'option_a_votes_percentage':1,'total_votes':1}}
        self.assertTrue(poll_readback(read,expected)['attached'])
        for actual,reason in [({'poll_attachment':None},'missing'),
                              ({'poll_attachment':{'option_a':'Ne','option_b':'Da'}},'options_mismatch'),
                              ({'poll_attachment':{**expected,'option_c':'Možda'}},'options_mismatch')]:
            self.assertEqual(poll_readback(actual,expected)['reason'],reason)
        self.assertEqual(poll_readback({'poll_attachment':None},expected,'POLL_CREATION_FAILURE')['reason'],'creation_failure')
        self.assertEqual(poll_readback(read,expected,'POLL_CREATION_FAILURE')['reason'],'status_read_conflict')


class FacebookLoginPollTests(unittest.TestCase):
    def client(self):
        with patch.dict(os.environ,{'META_GRAPH_VERSION':'v26.0'}):
            return InstagramFacebook('protected-user-token','17841429077454658',int(time.time())+60*86400)

    def authorization(self, client, scopes=None, tasks=None, username='easy_bosnian', page='1284422991426579'):
        return [{'data':[{'permission':scope,'status':'granted'} for scope in (scopes if scopes is not None else client.required_scopes)]},
                {'id':page,'name':'Easy Bosnian','instagram_business_account':{'id':client.user_id,'username':username}},
                {'data':[{'id':page,'tasks':tasks if tasks is not None else ['CREATE_CONTENT']}]}]

    def test_exact_linked_page_profile_scope_and_content_task_checked_read_only(self):
        client=self.client()
        with patch.object(client,'call',side_effect=self.authorization(client)) as call:
            self.assertEqual(client.verify_account()['username'],'easy_bosnian')
            self.assertTrue(all(item.args[0]=='GET' for item in call.call_args_list))
        for params in ([{'scopes':['instagram_basic']},{'tasks':['ANALYZE']},{'username':'wrong'},{'page':'999'}]
                       +[{'scopes':list(client.required_scopes-{scope})} for scope in ('ads_read','business_management')]):
            with self.subTest(params=params),patch.object(client,'call',side_effect=self.authorization(client,**params)),self.assertRaises(ValueError):
                client.verify_account()
        with patch.dict(os.environ,{'META_GRAPH_VERSION':'v26.0'}),self.assertRaises(ValueError):
            InstagramFacebook('protected','17841429077454658',int(time.time())-1)

    def test_parent_only_payload_and_single_publish_retains_attachment_status(self):
        client=self.client();poll={'option_a':'Da','option_b':'Ne'}
        with patch.object(client,'call',side_effect=[{'id':'1'},{'id':'2'},{'id':'3','caption_add_on_attachment_status':'POLL_CREATION_FAILURE'},{'poll_attachment':poll}]) as call:
            client.child('https://example.com/photo.jpg','Fotografija.')
            client.carousel(['1','4','5'],'Pitanje dana?',poll)
            reply=client.publish_with_addon('2');client.poll_attachment('3')
        self.assertNotIn('poll_attachment',call.call_args_list[0].args[2])
        values=call.call_args_list[1].args[2]
        self.assertEqual(values['media_type'],'CAROUSEL');self.assertEqual(json.loads(values['poll_attachment']),poll)
        self.assertEqual(reply['caption_add_on_attachment_status'],'POLL_CREATION_FAILURE')
        self.assertEqual(call.call_args_list[-1].args,('GET','3/poll_attachment'))
        self.assertEqual(client.base,'https://graph.facebook.com/v26.0')

    def test_original_instagram_login_story_client_has_no_poll_payload(self):
        with patch.dict(os.environ,{'META_GRAPH_VERSION':'v26.0'}):client=Instagram('original','123')
        with patch.object(client,'call',return_value={'id':'1'}) as call:
            client.story('https://example.com/story.jpg');client.publish('1')
        self.assertEqual(call.call_args_list[0].args[2],{'image_url':'https://example.com/story.jpg','media_type':'STORIES'})
        self.assertEqual(call.call_count,2);self.assertEqual(client.base,'https://graph.instagram.com/v26.0')

    def test_exchange_rejects_page_tokens_wrong_app_and_missing_publishing_scope(self):
        client=self.client()
        debug={'is_valid':True,'app_id':'1987873818544936','type':'USER',
               'scopes':list(client.required_scopes),'expires_at':int(time.time())+60*86400,
               'data_access_expires_at':int(time.time())+90*86400}
        for changes in ({'type':'PAGE'},{'app_id':'999'},{'scopes':['instagram_basic']},{'expires_at':int(time.time())+86400}):
            with self.subTest(changes=changes),patch.dict(os.environ,{'META_GRAPH_VERSION':'v26.0'}),patch('easybosnian.meta.request',side_effect=[{'access_token':'protected'}, {'data':{**debug,**changes}}]) as request,self.assertRaises(ValueError):
                instagram_facebook_token('protected-input','protected-secret')
            self.assertEqual(request.call_count,2)


class PollPublishingTests(unittest.TestCase):
    def publish(self,status=None,read=None,error=None,long_option=False):
        package=reviewed_fixture();assets={card['kind']:{'url':card['kind']} for card in package['cards']}
        if long_option:package['cards'][0]['options'][0]['text']='č'*26
        ig=MagicMock();ig.user_id='17841429077454658'
        ig.child.side_effect=['11','12','13'];ig.carousel.return_value='14'
        ig.publish_with_addon.return_value={'id':'123',**({'caption_add_on_attachment_status':status} if status is not None else {})}
        if error:ig.publish_with_addon.side_effect=error
        ig.media.return_value={'id':'123','caption':instagram_caption(package),'media_type':'CAROUSEL_ALBUM',
                               'children':{'data':[{'media_type':'IMAGE'}]*3},'permalink':'https://www.instagram.com/p/test/'}
        poll,_=quiz_poll(package)
        if isinstance(read,Exception):ig.poll_attachment.side_effect=read
        else:ig.poll_attachment.return_value=read if read is not None else {'poll_attachment':poll}
        events=[]
        ig.poll_attachment.side_effect=(lambda *args: events.append('read') or ig.poll_attachment.return_value) if not isinstance(read,Exception) else read
        with patch('easybosnian.pipeline.require_publishing'),patch('easybosnian.pipeline.Instagram') as original,patch('easybosnian.pipeline.InstagramFacebook',return_value=ig),patch('easybosnian.pipeline.write_json') as save,patch('easybosnian.pipeline.failure',return_value='safe poll failure') as failure:
            if error:
                with self.assertRaises(SafeError):publish_instagram(package,assets)
                result=None
            else:result=publish_instagram(package,assets,record=lambda *args:events.append('record'))
        return result,ig,original,save,failure,events

    def test_attached_poll_records_feed_before_read_and_keeps_original_refresh(self):
        result,ig,original,_,failure,events=self.publish()
        self.assertTrue(result['published']);self.assertTrue(result['poll']['attached'])
        self.assertEqual(events,['record','read']);failure.assert_not_called()
        original.return_value.refresh_if_needed.assert_called_once()
        ig.publish_with_addon.assert_called_once();self.assertEqual(ig.child.call_count,3)
        self.assertEqual(ig.carousel.call_args.kwargs['poll'],{'option_a':'torba','option_b':'kišobran','option_c':'knjiga'})

    def test_failure_status_missing_mismatch_or_read_error_never_republishes(self):
        for args,reason in [({'status':'POLL_CREATION_FAILURE','read':{'poll_attachment':None}},'creation_failure'),
                            ({'read':{'poll_attachment':None}},'missing'),
                            ({'read':{'poll_attachment':{'option_a':'wrong','option_b':'wrong'}}},'options_mismatch'),
                            ({'read':SafeError('read failed')},'read_failed'),
                            ({'status':'raw secret-like provider prose'},'status_read_conflict')]:
            with self.subTest(args=args):
                result,ig,_,save,failure,_=self.publish(**args)
                self.assertTrue(result['published']);self.assertTrue(result['poll']['failed'])
                self.assertEqual(result['poll']['reason'],reason)
                ig.publish_with_addon.assert_called_once();ig.poll_attachment.assert_called_once()
                failure.assert_called_once();save.assert_called_once()
                self.assertNotIn('raw secret-like',json.dumps(result))

    def test_limit_omission_publishes_once_without_poll_or_poll_read(self):
        result,ig,_,_,failure,_=self.publish(long_option=True)
        self.assertTrue(result['published']);self.assertFalse(result['poll']['failed'])
        self.assertFalse(result['poll']['requested']);self.assertIsNone(ig.carousel.call_args.kwargs['poll'])
        ig.publish_with_addon.assert_called_once();ig.poll_attachment.assert_not_called();failure.assert_not_called()

    def test_publish_timeout_is_never_retried_or_interpreted_as_poll_failure(self):
        result,ig,_,_,failure,_=self.publish(error=SafeError('ambiguous timeout'))
        self.assertIsNone(result);ig.publish_with_addon.assert_called_once();ig.poll_attachment.assert_not_called()
        self.assertEqual(failure.call_args.args[3],'Instagram publish request outcome uncertain')

    def test_poll_failure_still_attempts_stories_and_other_platforms_then_fails_run(self):
        from easybosnian.daily import daily
        with patch.dict(os.environ,{'FACEBOOK_POSTING_ENABLED':'true','TIKTOK_POSTING_ENABLED':'true','INSTAGRAM_STORIES_ENABLED':'true','FACEBOOK_STORIES_ENABLED':'true'}),patch('easybosnian.daily.verify_repository'),patch('easybosnian.daily.require_publishing'),patch('easybosnian.daily.Store') as store,patch('easybosnian.daily.artwork',return_value={}),patch('easybosnian.daily.cleanup'),patch('easybosnian.daily.publish_instagram',return_value={'published':True,'poll':{'failed':True}}),patch('easybosnian.daily.publish_facebook',return_value={'published':True}) as facebook,patch('easybosnian.daily.publish_tiktok',return_value={'published':True}) as tiktok,patch('easybosnian.daily.publish_stories',return_value={'published':True}) as stories,patch('easybosnian.daily.publish_facebook_stories',return_value={'published':True}) as fb_stories,patch('easybosnian.daily.write_json') as save:
            store.return_value.content.return_value=reviewed_fixture()
            with self.assertRaisesRegex(RuntimeError,'instagram_poll'):daily('2026-10-02','daily')
            for operation in (facebook,tiktok,stories,fb_stories):operation.assert_called_once()
            self.assertTrue(save.call_args.args[1]['platforms']['instagram']['published'])

    def test_success_report_exposes_omission_but_refuses_attachment_failure(self):
        from test_success_report import results
        outcome=results();outcome['instagram']['poll']={'reason':'option_length','failed':False}
        self.assertIn('omitted',publication_data(outcome)[0]['poll_status'])
        outcome['instagram']['poll']={'reason':'missing','failed':True}
        with self.assertRaisesRegex(ValueError,'Native poll failed'):publication_data(outcome)


if __name__=='__main__':unittest.main()

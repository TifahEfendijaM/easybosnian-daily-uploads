from test_project import accepted_photo_review
import contextlib
import copy
import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock,patch

from PIL import Image
from easybosnian.core import ROOT as CODE_ROOT,read_json
from easybosnian.frozen_cards import snapshot,prepare_cards,loaded_cards,digest,checked_source
from easybosnian.hybrid import default_plan,render_hybrid
from easybosnian.visual_policy import policy_metadata
from easybosnian.story_layouts import tall_story_image
from easybosnian.selection import selection_context,check_selection
from easybosnian.artwork import artwork
from test_project import reviewed_fixture

A='b-'+'a'*32
B='b-'+'b'*32


class FrozenCardTests(unittest.TestCase):
    def fixture(self,root,kind='word'):
        package=reviewed_fixture();package['batch_id']=A
        card=next(c for c in package['cards'] if c['kind']==kind);photo=root/'photo.jpg';Image.new('RGB',(1024,1024),'#888888').save(photo)
        plan=default_plan(card);plan.update(confidence='high',palette='gold-cream')
        path=root/f'{kind}-card.jpg';metrics=render_hybrid(card,'gold-cream',photo,path,plan)
        story=root/f'{kind}-story.jpg';tall_story_image(card,photo,story,read_json(CODE_ROOT/'data/design-palettes.json')['gold-cream'])
        cache={};store=MagicMock()
        def call(method,url,body=None,**kwargs):
            if method=='PUT':cache[url]=body;return {'stored':True}
            if method=='GET':return cache[url]
            self.fail('snapshot must not publish, infer or save history')
        store.call.side_effect=call
        source=snapshot(store,package,card,{'path':path,'story_path':story,'metrics':metrics},policy_metadata(plan,panel_opacity=100))
        package['rendered_sources']={kind:source}
        return package,store,cache,photo

    def test_snapshot_reuse_keeps_exact_feed_story_and_text_without_new_writes(self):
        with tempfile.TemporaryDirectory() as temp,patch.dict(os.environ,{'GITHUB_RUN_URL':'run-one'}):
            root=Path(temp)
            with patch('easybosnian.frozen_cards.ROOT',root):
                old,store,cache,photo=self.fixture(root)
                before=dict(cache);sources=prepare_cards(store,old,A,B,old['date'],('word',),{'word':photo})
                package=copy.deepcopy(old);package.update(batch_id=B,rendered_sources=sources)
                entry=loaded_cards(package)['word']
                self.assertEqual(entry['card'].read_bytes(),(root/'word-card.jpg').read_bytes())
                self.assertEqual(entry['story'].read_bytes(),(root/'word-story.jpg').read_bytes())
                self.assertEqual(cache,before)
                self.assertEqual(sum(c.args[0]=='PUT' for c in store.call.call_args_list),2)
                store.save_content.assert_not_called();store.expose.assert_not_called()
                entry['card'].write_bytes(b'changed by child')
                with self.assertRaisesRegex(ValueError,'format|size|changed'):loaded_cards(package)

    def test_reference_is_bound_to_copy_and_run_and_missing_bytes_never_regenerate(self):
        with tempfile.TemporaryDirectory() as temp,patch.dict(os.environ,{'GITHUB_RUN_URL':'run-one'}):
            root=Path(temp)
            with patch('easybosnian.frozen_cards.ROOT',root):
                old,store,cache,photo=self.fixture(root)
                changed=copy.deepcopy(old['cards'][2]);changed['body']+=' Changed.'
                with self.assertRaisesRegex(ValueError,'exact source text'):checked_source(old['rendered_sources']['word'],changed)
                source=old['rendered_sources']['word'];cache[f"/v1/private/batches/{source['cache_id']}/word-card.jpg"]=b'wrong card'
                with self.assertRaises(ValueError):prepare_cards(store,old,A,B,old['date'],('word',),{'word':photo})
                self.assertTrue(all(c.args[0] in ('GET','PUT') and '/v1/private/batches/' in c.args[1] for c in store.call.call_args_list))

    def test_custom_action_preserves_only_selected_card_while_other_copy_changes(self):
        old=reviewed_fixture();old['batch_id']=A
        history={'days':[{'batch_id':A,'date':old['date'],'content':old}]}
        selection=selection_context(history,old['date'],'custom','',['','',''],['chatgpt','keep_today','same_image&design'],source_batch_id=A)
        package=copy.deepcopy(old);package['caption']+=' Danas.'
        package['cards'][0]['question']+=' Danas.';package['cards'][0]['background_prompt']+=' New scene.'
        package['cards'][1]['body']+=' Danas.';package['cards'][1]['background_prompt']+=' New scene.'
        check_selection(package,selection)
        package['cards'][2]['example']+=' Danas.'
        with self.assertRaisesRegex(ValueError,'exact saved card'):check_selection(package,selection)

    def test_mixed_artwork_reuse_excludes_frozen_card_from_flux_and_visual_choices(self):
        with tempfile.TemporaryDirectory() as temp,contextlib.ExitStack() as stack:
            root=Path(temp);old,store,cache,photo=self.fixture(root)
            source=old['rendered_sources']['word'];package=copy.deepcopy(old);package['batch_id']=B
            package['background_sources']={'word':{'batch_id':A,'artwork_id':'r-'+'1'*32}}
            fixed={'word':{'source':source,'card':root/'word-card.jpg','story':root/'word-story.jpg'}}
            stream=io.BytesIO();Image.new('RGB',(1024,1024),'#888888').save(stream,'JPEG')
            generator=stack.enter_context(patch('easybosnian.artwork.provider'));generator.return_value.generate.return_value=stream.getvalue()
            stack.enter_context(patch('easybosnian.artwork.ROOT',root))
            stack.enter_context(patch('easybosnian.photo_quality.inspect_photos',side_effect=accepted_photo_review))
            stack.enter_context(patch('easybosnian.visual_history.recent_choices',return_value=([],'available')))
            plans={'cards':{c['kind']:dict(default_plan(c),confidence='high',palette='gold-cream') for c in package['cards'] if c['kind']!='word'}}
            review=stack.enter_context(patch('easybosnian.visual_placement.review_compositions',return_value=(plans,'reviewed')))
            assets=artwork(store,package,review_images=True,reused_backgrounds={'word':photo},frozen_cards=fixed)
            self.assertEqual(generator.return_value.generate.call_count,2)
            self.assertEqual(set(review.call_args.args[1]),{'quiz','lesson'})
            self.assertEqual(digest(assets['word']['path'].read_bytes()),source['card_sha256'])
            self.assertEqual(digest(assets['word']['story_path'].read_bytes()),source['story_sha256'])
            placement=read_json(root/'build'/B/'image-placement-result.json')['cards']['word']
            self.assertEqual(placement['provenance']['layout']['source'],'reused')
            store.expose.assert_not_called()

    def test_saved_preview_does_not_retain_stale_finished_card_fingerprints(self):
        with tempfile.TemporaryDirectory() as tmp,contextlib.ExitStack() as stack:
            root=Path(tmp);package,store,_,_=self.fixture(root)
            stream=io.BytesIO();Image.new('RGB',(1024,1024),'#728192').save(stream,'JPEG')
            provider=MagicMock();provider.generate.return_value=stream.getvalue()
            stack.enter_context(patch.dict(os.environ,{'MODE':'preview'}))
            stack.enter_context(patch('easybosnian.artwork.ROOT',root))
            stack.enter_context(patch('easybosnian.artwork.provider',return_value=provider))
            stack.enter_context(patch('easybosnian.photo_quality.inspect_photos',side_effect=accepted_photo_review))
            stack.enter_context(patch('easybosnian.visual_history.recent_choices',return_value=([],'available')))
            plans={'cards':{c['kind']:dict(default_plan(c),confidence='high',palette='gold-cream') for c in package['cards']}}
            stack.enter_context(patch('easybosnian.visual_placement.review_compositions',return_value=(plans,'reviewed')))
            artwork(store,package,review_images=True)
            self.assertNotIn('rendered_sources',package)
            assets=artwork(store,package,require_prepared=True)
            self.assertEqual(set(assets),{'quiz','lesson','word'})


    def test_cloud_parent_seals_frozen_copy_and_quiz_metadata_before_staging(self):
        from easybosnian.cloud_prepare import cloud_run
        from easybosnian.core import PROJECT,write_json
        from test_photo_reuse import fresh
        for index,kind in enumerate(('quiz','lesson','word')):
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as tmp,contextlib.ExitStack() as stack:
                root=Path(tmp);(root/'docs').mkdir();(root/'docs/cloud-agent-task.md').write_text('Prepare {{DATE}}')
                old,store,cache,photo=self.fixture(root,kind)
                old['bosnian_level']='A2'
                store.history.return_value={'project':PROJECT,'days':[{'batch_id':A,'date':old['date'],'content':old}]}
                store.publications_for_date.return_value=[]
                def agent(prompt,**kwargs):
                    context=read_json(root/'build/preparation-context.json')
                    self.assertEqual(context['frozen_card_kinds'],[kind])
                    self.assertNotIn('rendered_sources',context['selection']['previous'])
                    self.assertTrue(all('rendered_sources' not in row['content'] for row in context['history']['days']))
                    draft=fresh(old);draft.pop('rendered_sources',None)
                    draft['date']=context['batch_date'];draft['batch_id']=context['batch']['batch_id']
                    if kind=='quiz':draft['private_review']['correct_option']='D'  # Parent restores the pinned key.
                    for c in draft['cards']:
                        if c['kind']!=kind:c['background_prompt']=c['background_prompt'].replace('No text, no lettering, no logos.','Bright natural light. No text, no lettering, no logos.')
                    write_json(root/f'build/preparation/{draft["date"]}.json',draft)
                    return '{"status":"ready","reason":"none"}'
                for module in ('cloud_prepare','cli','frozen_cards'):
                    stack.enter_context(patch('easybosnian.'+module+'.ROOT',root))
                stack.enter_context(patch('easybosnian.cloud_prepare.failure',return_value='test-only'))
                stack.enter_context(patch('easybosnian.cloud_prepare.Store',return_value=store))
                stack.enter_context(patch('easybosnian.cloud_prepare.today',return_value=old['date']))
                stack.enter_context(patch('easybosnian.cloud_prepare.select_run_level',return_value='A2'))
                stack.enter_context(patch('easybosnian.cloud_prepare.secrets.choice',return_value=3))
                stack.enter_context(patch('easybosnian.cloud_prepare.run_codex',side_effect=agent))
                stack.enter_context(patch('easybosnian.photo_reuse.prepare_photos',return_value={'paths':{kind:photo}}))
                stack.enter_context(patch('easybosnian.photo_reuse.seal_photos',return_value={'background_sources':{kind:{'batch_id':A,'artwork_id':'r-'+'1'*32}}}))
                for name in ('check_infrastructure','require_publishing','validate','fit_check','prepare'):
                    stack.enter_context(patch('easybosnian.cloud_prepare.'+name))
                actions=['keep_today']*3;actions[index]='same_image&design'
                cloud_run('daily','custom',custom_actions=actions,batch_target='none')
                staged=read_json(root/'build/reviewed-content.secret')['content']
                self.assertEqual(staged['cards'][index],old['cards'][index])
                self.assertEqual(staged['rendered_sources'],old['rendered_sources'])
                if kind=='quiz':self.assertEqual(staged['private_review']['correct_option'],old['private_review']['correct_option'])
                store.save_content.assert_not_called();store.expose.assert_not_called()

    def test_legacy_reuse_requires_confirmed_artifact_and_exact_byte_reproduction(self):
        import json
        import zipfile
        from easybosnian.frozen_cards import legacy_artifact
        with tempfile.TemporaryDirectory() as tmp,patch('easybosnian.frozen_cards.ROOT',Path(tmp)):
            root=Path(tmp);old,store,cache,photo=self.fixture(root)
            choice={'palette':'gold-cream','composition':old['rendered_sources']['word']['metrics']['composition'],
                    'render_policy':old['rendered_sources']['word']['policy']}
            old.pop('rendered_sources')
            store.publications.return_value=[{'kind':'feed','platform':'facebook','object_id':'page_feed'}]
            def archive(published):
                data=io.BytesIO()
                with zipfile.ZipFile(data,'w') as z:
                    z.writestr(A+'/facebook-result.json',json.dumps({'published':published,'post_id':'page_feed'}))
                    z.writestr(A+'/image-placement-result.json',json.dumps({'batch_id':A,'cards':{'word':choice}}))
                    z.writestr(A+'/word-card.jpg',(root/'word-card.jpg').read_bytes())
                    z.writestr(A+'/word-story.jpg',(root/'word-story.jpg').read_bytes())
                return data.getvalue()
            def gh(*args):
                return json.dumps([{'databaseId':7,'status':'completed','displayTitle':'EasyBosnian (daily)'}] if args[0]=='run'
                    else {'artifacts':[{'id':8,'name':'easybosnian-daily-7','expired':False,'size_in_bytes':1000000}]})
            with patch('easybosnian.frozen_cards.gh',side_effect=gh),patch('easybosnian.frozen_cards.gh_binary',return_value=archive(True)):
                source,files=legacy_artifact(store,old,A,old['cards'][2],photo)
                self.assertEqual(source['card_sha256'],digest((root/'word-card.jpg').read_bytes()))
                self.assertEqual(files['story'].read_bytes(),(root/'word-story.jpg').read_bytes())
            with patch('easybosnian.frozen_cards.gh',side_effect=gh),patch('easybosnian.frozen_cards.gh_binary',return_value=archive(False)):
                with self.assertRaisesRegex(ValueError,'could not be proven'):legacy_artifact(store,old,A,old['cards'][2],photo)

"""Actual rendered-card inspection shares the design budget and locks siblings."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock,patch
from PIL import Image
from easybosnian.hybrid import default_plan,render_hybrid
from easybosnian.rendered_harmony import improve,inspect,safe_harmony
from easybosnian.cloud_prepare import AgentIntegrityError
from test_project import reviewed_fixture

ACCEPT={'verdict':'accept','reason':'harmonious','elements':[],'composition':None}
def revision(metrics,colour='#145638',strength='medium',can_revise=True):
    plan=copy.deepcopy(metrics['composition'])
    plan['blocks'][-1].update(backing_colour=colour,shade_strength=strength)
    return {'verdict':'revise','reason':'poor_palette_harmony','elements':['example'],
            'composition':plan if can_revise else None}

class RenderedHarmonyTests(unittest.TestCase):
    def fixture(self,root):
        card=copy.deepcopy(reviewed_fixture()['cards'][2]);plan=default_plan(card)
        plan.update(confidence='high',palette='forest-cream')
        plan['blocks'][-1].update(photo_tone='paper_dark',backing_colour='#493020')
        photo=root/'photo.jpg';Image.new('RGB',(1080,1350),'#999999').save(photo)
        path=root/'card.jpg'
        def draw(p):return render_hybrid(card,'forest-cream',photo,path,p)
        return card,path,draw(plan),draw

    def test_inspector_sees_actual_card_in_read_only_strict_contract_without_private_package(self):
        with tempfile.TemporaryDirectory() as tmp:
            card,path,metrics,_=self.fixture(Path(tmp));card.update(private_review='SECRET',answer_key='SECRET')
            original=path.read_bytes()
            with patch('easybosnian.cloud_prepare.run_codex',return_value=json.dumps(ACCEPT)) as child:
                self.assertEqual(inspect(card,path,metrics,can_revise=True),ACCEPT)
            prompt=child.call_args.args[0];kwargs=child.call_args.kwargs
            self.assertNotIn('SECRET',prompt);self.assertIn('ACTUAL Pillow-rendered card',prompt)
            self.assertEqual(kwargs['images'][0],path);self.assertEqual(len(kwargs['images']),2)
            phone_path=kwargs['images'][1]
            with Image.open(phone_path) as phone:
                self.assertEqual(phone.size,(432,540))
                self.assertEqual(phone.mode,'RGB')
            self.assertEqual(path.read_bytes(),original);self.assertTrue(kwargs['read_only'])
            self.assertFalse(kwargs['result_contract']['additionalProperties'])
            self.assertIn('actual opacity',prompt);self.assertIn('EXACT',prompt)
            # A subsequent inspection must see the newly rendered card at both sizes.
            Image.new('RGB',(1080,1350),'#123456').save(path)
            with patch('easybosnian.cloud_prepare.run_codex',return_value=json.dumps(ACCEPT)) as child:
                inspect(card,path,metrics,can_revise=False)
            child.assert_called_once()
            with Image.open(phone_path) as phone:
                self.assertLess(max(abs(a-b) for a,b in zip(phone.getpixel((216,270)),(18,52,86))),3)

    def test_revision_changes_only_backing_and_strength_then_inspects_new_render(self):
        with tempfile.TemporaryDirectory() as tmp:
            card,path,metrics,draw=self.fixture(Path(tmp));before=copy.deepcopy(metrics);pixels=path.read_bytes();seen=[]
            def review(*args,**kwargs):
                seen.append(path.read_bytes());return revision(metrics) if len(seen)==1 else ACCEPT
            actual,detail=improve(card,path,metrics,draw,review=review)
            expected=copy.deepcopy(before['composition']);expected['blocks'][-1].update(backing_colour='#145638',shade_strength='medium')
            self.assertEqual(actual['composition'],expected);self.assertEqual(metrics,before)
            self.assertEqual(seen[0],pixels);self.assertNotEqual(seen[0],seen[1])
            self.assertEqual(detail['status'],'refined');self.assertEqual(detail['design_proposals'],2)
            self.assertGreaterEqual(actual['example_contrast'],4.5)

    def test_layout_repairs_and_harmony_share_three_proposals_with_no_fourth(self):
        with tempfile.TemporaryDirectory() as tmp:
            card,path,metrics,draw=self.fixture(Path(tmp));seen=[]
            def review(*args,**kwargs):
                seen.append(kwargs['can_revise'])
                return revision(metrics,can_revise=kwargs['can_revise'])
            actual,detail=improve(card,path,metrics,draw,used=2,review=review)
            self.assertEqual(seen,[True,False]);self.assertEqual(detail['design_proposals'],3)
            self.assertEqual(detail['status'],'budget_exhausted')
            self.assertEqual(actual['composition']['blocks'][-1]['backing_colour'],'#145638')

    def test_rejected_colour_restores_last_readable_bytes_and_siblings(self):
        with tempfile.TemporaryDirectory() as tmp:
            card,path,metrics,draw=self.fixture(Path(tmp));before=path.read_bytes();seen=[]
            def bad_draw(plan):
                if plan['blocks'][-1]['backing_colour']=='#145638':
                    path.write_bytes(b'rejected candidate');raise ValueError('Actual photographic text contrast fails; never publish unreadable copy')
                return draw(plan)
            def review(*args,**kwargs):
                seen.append(path.read_bytes());return revision(metrics) if len(seen)==1 else ACCEPT
            actual,detail=improve(card,path,metrics,bad_draw,review=review)
            self.assertEqual(path.read_bytes(),before);self.assertTrue(seen==[before,before])
            self.assertEqual(actual['composition'],metrics['composition'])
            self.assertEqual(detail['checks'][0]['result'],'rejected');self.assertEqual(detail['design_proposals'],2)

    def test_services_and_invalid_model_responses_do_not_retry_or_edit(self):
        with tempfile.TemporaryDirectory() as tmp:
            card,path,metrics,draw=self.fixture(Path(tmp));before=path.read_bytes()
            for value in ({**ACCEPT,'elements':['invalid']},{**ACCEPT,'private':'SECRET'},{**ACCEPT,'verdict':'revise'}):
                review=Mock(return_value=value);actual,detail=improve(card,path,metrics,draw,review=review)
                review.assert_called_once();self.assertEqual(detail['status'],'unavailable');self.assertEqual(actual,metrics)
                self.assertNotIn('SECRET',str(detail));self.assertEqual(path.read_bytes(),before)
            review=Mock(side_effect=RuntimeError('SECRET auth error'))
            actual,detail=improve(card,path,metrics,draw,review=review);review.assert_called_once()
            self.assertEqual(actual,metrics);self.assertNotIn('SECRET',str(detail))
            with self.assertRaises(AgentIntegrityError):improve(card,path,metrics,draw,review=Mock(side_effect=AgentIntegrityError('changed')))

    def test_quiz_and_unshaded_cards_are_inspected_but_unavailable_review_skips(self):
        with tempfile.TemporaryDirectory() as tmp:
            card,path,metrics,draw=self.fixture(Path(tmp))
            for kind,style in (('quiz','italic_photo_fade'),('word','italic_photo')):
                c=copy.deepcopy(card);c['kind']=kind;m=copy.deepcopy(metrics);m['composition']['blocks'][-1]['style']=style
                review=Mock(return_value=ACCEPT)
                _,detail=improve(c,path,m,draw,review=review)
                self.assertEqual(detail['status'],'accepted');review.assert_called_once()
            review=Mock();_,detail=improve(card,path,metrics,draw,review=review,available=False)
            self.assertEqual(detail['status'],'skipped_review_unavailable');review.assert_not_called()
            for bad in ({'status':'secret'}, {'status':'accepted','design_proposals':4,'checks':[]},
                {'status':'accepted','design_proposals':1,'checks':[{'check':1,'result':'accepted','reason':'SECRET'}]}):
                with self.assertRaises(ValueError):safe_harmony(bad)

    def test_whole_card_revisions_preserve_unflagged_siblings_and_use_new_palette(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);card,path,metrics,_=self.fixture(root);before=copy.deepcopy(metrics['composition'])
            def draw(plan):return render_hybrid(card,plan['palette'],root/'photo.jpg',path,plan)
            plan=copy.deepcopy(before);plan['palette']='blue-ice';plan['blocks'][0]['surface_richness']=75
            proposal={'verdict':'revise','reason':'poor_palette_harmony','elements':['palette','body'],'composition':plan}
            result,detail=improve(card,path,metrics,draw,review=Mock(side_effect=[proposal,ACCEPT]))
            self.assertEqual(detail['status'],'refined');self.assertEqual(result['palette'],'blue-ice')
            self.assertEqual(result['composition'],plan);self.assertEqual(plan['blocks'][1],before['blocks'][1])
            # A changed title is rejected unless explicitly identified as a defect.
            plan['heading_tone']='paper_dark';proposal['elements']=['body']
            result,detail=improve(card,path,metrics,draw,review=Mock(side_effect=[proposal,ACCEPT]))
            self.assertEqual(result['composition'],before);self.assertEqual(detail['checks'][0]['result'],'rejected')

    def test_artwork_stores_only_final_revised_card_and_prepared_reuse_skips_review(self):
        import contextlib,io
        from unittest.mock import MagicMock
        from easybosnian.artwork import artwork
        from easybosnian.core import read_json
        from test_project import accepted_photo_review
        package=reviewed_fixture();package['batch_id']='b-'+'a'*32
        plans={'cards':{c['kind']:dict(default_plan(c),confidence='high',palette='forest-cream') for c in package['cards']}}
        plans['cards']['word']['blocks'][-1]['photo_tone']='paper_dark'
        stream=io.BytesIO();Image.new('RGB',(1024,1024),'#888888').save(stream,'JPEG')
        provider=MagicMock();provider.generate.return_value=stream.getvalue();store=MagicMock();seen=[]
        def review(card,path,metrics,**kwargs):
            seen.append((card['kind'],path.read_bytes()))
            return revision(metrics) if card['kind']=='word' and len([k for k,_ in seen if k=='word'])==1 else ACCEPT
        with tempfile.TemporaryDirectory() as tmp,contextlib.ExitStack() as stack:
            root=Path(tmp)
            for target,value in (('easybosnian.artwork.ROOT',root),('easybosnian.artwork.provider',provider),):
                stack.enter_context(patch(target,return_value=value) if target.endswith('provider') else patch(target,value))
            stack.enter_context(patch('easybosnian.photo_quality.inspect_photos',side_effect=accepted_photo_review))
            stack.enter_context(patch('easybosnian.visual_history.recent_choices',return_value=([],'available')))
            stack.enter_context(patch('easybosnian.visual_placement.review_compositions',return_value=(plans,'reviewed')))
            checker=stack.enter_context(patch('easybosnian.rendered_harmony.inspect',side_effect=review))
            with contextlib.redirect_stdout(io.StringIO()):assets=artwork(store,package,review_images=True)
            self.assertEqual([k for k,_ in seen],['quiz','lesson','word','word'])
            selected=assets['word']['path'].read_bytes();self.assertNotEqual(seen[-2][1],selected)
            stored=[c.args[2] for c in store.put_file.call_args_list if c.args[1]=='word-card.jpg']
            self.assertEqual(stored,[selected])
            report=read_json(root/'build'/package['batch_id']/'image-placement-result.json')
            self.assertEqual(report['cards']['word']['design_harmony']['status'],'refined')
            from easybosnian.success_report import report_data,with_rendering,render_report
            from test_success_report import RUN,results
            public=with_rendering(report_data(package,results(),RUN),report)
            self.assertTrue(all('Rendered whole-card design review: refined' in text.replace(chr(92),'') for text in render_report(public)))
            checker.reset_mock()
            with contextlib.redirect_stdout(io.StringIO()):reused=artwork(store,package,require_prepared=True)
            checker.assert_not_called();self.assertEqual(reused['word']['path'].read_bytes(),selected)

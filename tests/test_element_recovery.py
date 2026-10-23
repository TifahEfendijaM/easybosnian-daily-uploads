import copy
import tempfile
import unittest
from pathlib import Path

from PIL import Image
from easybosnian.hybrid import default_plan,render_hybrid,measured_plan
from easybosnian.element_recovery import recover_elements,safe_recovery
from test_project import reviewed_fixture


class ElementRecoveryTests(unittest.TestCase):
    def test_contained_photo_example_repairs_only_example_preserving_the_rest(self):
        card=reviewed_fixture()['cards'][1]
        card.update(body='A short explanation with exact Bosnian letters č, ć, š, ž and đ.',example='Ovo je naš primjer.')
        plan=default_plan(card);plan.update(confidence='high',palette='burgundy-oat',category_style='outlined',
            category_tone='ink_paper',photo_window={'fit':'contain','y':500,'height':520})
        plan['blocks'][0].update(style='minimal_rule',font_size=36,y=277,max_lines=3,panel_tone='ink_paper')
        plan['blocks'][1].update(x=64,y=1060,width=952,max_lines=1,photo_tone='paper_ink')
        original=copy.deepcopy(plan);copy_before=copy.deepcopy(card)
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);photo=root/'photo.jpg';Image.new('RGB',(1024,1024),'#888888').save(photo)
            def render(candidate):return render_hybrid(card,'burgundy-oat',photo,root/'card.jpg',candidate)
            with self.assertRaisesRegex(ValueError,'inside the complete photograph'):render(plan)
            metrics,recovery=recover_elements(card,plan,photo,render)
            self.assertEqual(recovery['fallback'],['example'])
            self.assertEqual(metrics['composition']['blocks'][0],original['blocks'][0])
            for field in ('category_style','category_tone','photo_window','heading_tone','design'):
                self.assertEqual(metrics['composition'][field],original[field])
            self.assertEqual(measured_plan(card,metrics['composition'])[1]['rows'].reconstructed(),card['example'])
            self.assertGreaterEqual(metrics['example_contrast'],4.5)
            self.assertEqual(card,copy_before);self.assertEqual(plan,original)

    def test_failed_example_never_moves_or_overlaps_an_accepted_body(self):
        card=reviewed_fixture()['cards'][2]
        card.update(body='A short explanation.',example='Ovo je primjer.')
        plan=default_plan(card);plan.update(confidence='high',palette='gold-cream')
        plan['blocks'][0].update(y=930,style='outlined')
        plan['blocks'][1].update(y=930)
        before=copy.deepcopy(plan)
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);photo=root/'photo.jpg';Image.new('RGB',(1024,1024),'#888888').save(photo)
            result=recover_elements(card,plan,photo,lambda p:render_hybrid(card,'gold-cream',photo,root/'card.jpg',p))
            self.assertIsNotNone(result)
            metrics,recovery=result
            # Either member of an otherwise-valid colliding pair may be moved,
            # but the smallest selected failed set must leave its sibling exact.
            self.assertEqual(len(recovery['fallback']),1)
            for role in ('body','example'):
                if role not in recovery['fallback']:
                    self.assertEqual(next(b for b in metrics['composition']['blocks'] if b['role']==role),next(b for b in before['blocks'] if b['role']==role))
            measured_plan(card,metrics['composition'])

    def test_unknown_root_fields_and_untrusted_metadata_are_not_silently_accepted(self):
        card=reviewed_fixture()['cards'][2];plan=default_plan(card);plan.update(confidence='high',css='private prose')
        self.assertIsNone(recover_elements(card,plan,None,lambda p:self.fail('must not render')))
        with self.assertRaises(ValueError):safe_recovery({'reason':'private prose','preserved':['body'],'fallback':['example']})

    def test_incompatible_overall_family_replaces_only_family_and_keeps_valid_answers(self):
        card=reviewed_fixture()['cards'][0]
        plan=dict(default_plan(card),confidence='high',palette='gold-cream',design='editorial')
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);photo=root/'photo.jpg';Image.new('RGB',(1024,1024),'#888888').save(photo)
            metrics,detail=recover_elements(card,plan,photo,lambda p:render_hybrid(card,'gold-cream',photo,root/'card.jpg',p))
            self.assertEqual(detail['fallback'],['design'])
            self.assertEqual(metrics['composition']['blocks'],plan['blocks'])
            self.assertEqual(metrics['composition']['category_style'],plan['category_style'])
            self.assertEqual(metrics['composition']['design'],'hybrid')

"""Fresh reviews choose fade colours only; geometry and strength remain renderer-owned."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image
from jsonschema import Draft202012Validator
from easybosnian.designs import REVIEW_PHOTO_TONES, PANEL_OPACITIES
from easybosnian.hybrid import default_plan, render_hybrid, measured_plan
from easybosnian.visual_placement import MODEL_CARD_SCHEMA, CARD_SCHEMA, review_compositions
from easybosnian.visual_history import accepted_choices
from easybosnian.success_report import with_rendering, report_data, render_report
from test_project import reviewed_fixture
from test_success_report import RUN, results


class FixedFadeTests(unittest.TestCase):
    def proposal(self):
        package=reviewed_fixture()
        return package,{'cards':{c['kind']:dict(default_plan(c),confidence='high',palette='forest-cream') for c in package['cards']}}

    def test_new_model_allows_colour_pairs_but_cannot_choose_fade_shapes_or_strength(self):
        package,base=self.proposal();model=Draft202012Validator(MODEL_CARD_SCHEMA)
        self.assertIn('paper_dark',REVIEW_PHOTO_TONES);self.assertIn('ink_light',REVIEW_PHOTO_TONES)
        for tone in REVIEW_PHOTO_TONES:
            plan=copy.deepcopy(base['cards']['word'])
            plan['heading_tone']=tone;plan['blocks'][-1]['photo_tone']=tone
            self.assertFalse(list(model.iter_errors(plan)),tone)
        self.assertFalse(list(model.iter_errors(base['cards']['word'])))
        for scope,key,value in [('card','heading_fade','soft'),('card','heading_fade','standard'),
                                ('example','fade_style','soft'),('example','fade_style','standard')]:
            plan=copy.deepcopy(base['cards']['word'])
            target=plan if scope=='card' else next(b for b in plan['blocks'] if b['role']=='example')
            target[key]=value
            self.assertTrue(list(model.iter_errors(plan)),(scope,key,value))
            # Historical metadata is still understood rather than corrupting old reports.
            self.assertFalse(list(Draft202012Validator(CARD_SCHEMA).iter_errors(plan)))
        self.assertEqual(PANEL_OPACITIES['translucent'],191)
        for scope,key,value in [('card','fade_opacity',50),('example','fade_width',400),
                                ('example','photo_tone','#559966')]:
            plan=copy.deepcopy(base['cards']['word'])
            (plan if scope=='card' else plan['blocks'][-1])[key]=value
            self.assertTrue(list(model.iter_errors(plan)))

    def test_actual_current_fades_are_white_on_black_or_black_on_white(self):
        card=reviewed_fixture()['cards'][2];original=copy.deepcopy(card)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);photo=root/'photo.jpg';Image.new('RGB',(1080,1350),'#828282').save(photo)
            images=[]
            for tone,colour in [('paper_dark','#ffffff'),('ink_light','#000000')]:
                plan=default_plan(card);plan['heading_tone']=tone;plan['blocks'][-1]['photo_tone']=tone
                plan['blocks'][0].update(panel_tone='ink_accent',panel_opacity=75)
                metrics=render_hybrid(card,'forest-cream',photo,root/f'{tone}.jpg',plan)
                self.assertEqual(metrics['heading_colour'],colour);self.assertEqual(metrics['example_colour'],colour)
                self.assertGreaterEqual(metrics['heading_contrast'],3)
                self.assertGreaterEqual(metrics['example_contrast'],4.5)
                self.assertEqual(measured_plan(card,plan)[0]['rows'].reconstructed(),card['body'])
                self.assertNotIn('heading_fade',plan)
                self.assertNotIn('fade_style',plan['blocks'][-1])
                images.append((root/f'{tone}.jpg').read_bytes())
            self.assertNotEqual(*images);self.assertEqual(card,original)

    def test_removed_fade_fields_cannot_bypass_model_contract_through_position_adjustment(self):
        package,base=self.proposal();proposal=copy.deepcopy(base)
        proposal['cards']['word']['heading_fade']='soft'
        proposal['cards']['word']['blocks'][0]['x']=30
        with patch('easybosnian.cloud_prepare.run_codex',return_value=json.dumps(proposal)) as child:
            reviewed,status=review_compositions(package,{k:{'sheet':Path(k+'.jpg')} for k in proposal['cards']})
        child.assert_called_once();self.assertEqual(status,'reviewed')
        self.assertEqual(reviewed['card_failures'],{'word':'review violated the declarative schema'})
        self.assertEqual(reviewed['cards']['word']['confidence'],'uncertain')
        self.assertNotIn('heading_fade',reviewed['cards']['word'])
        self.assertEqual(reviewed['cards']['quiz'],base['cards']['quiz'])
        self.assertEqual(reviewed['palette_decisions']['word']['source'],'chatgpt')
        prompt=child.call_args.args[0]
        for text in ('Catalogue order is not a ranking','Compare EVERY approved palette',
                     'do not stop at the first acceptable','review ALL compatible',
                     'Do not supply heading_fade or fade_style', 'Only the text/fade COLOURS may change'):
            self.assertIn(text,prompt)
        shown=prompt.split(' Photo-colour catalogue: ',1)[1].split(' Palette repetition policy:',1)[0]
        self.assertEqual(set(json.loads(shown)),set(REVIEW_PHOTO_TONES))

    def test_recent_accepted_colours_are_whitelisted_but_fade_controls_are_not_recommended(self):
        placement={'cards':{'word':{'status':'accepted','palette':'forest-cream','design':'hybrid',
                   'block_styles':{'body':'soft_corner','example':'italic_photo_fade'},
                   'heading_tone':'accent_dark','example_tone':'ink_paper',
                   'palette_outcome':{'source':'chatgpt','reason':'ChatGPT selected this approved palette'}}}}
        safe=accepted_choices(placement)['word']
        self.assertEqual(safe['heading_tone'],'accent_dark');self.assertEqual(safe['example_tone'],'ink_paper')
        self.assertNotIn('heading_fade',safe)
        placement['cards']['word']['heading_tone']='arbitrary prose'
        self.assertNotIn('heading_tone',accepted_choices(placement)['word'])
        self.assertEqual(safe['block_styles']['body'],'soft_corner')
        self.assertEqual(safe['palette'],'forest-cream')

    def test_private_legacy_reports_with_former_fade_choices_stay_readable(self):
        package,plans=self.proposal()
        placement={'batch':package['date'],'batch_id':package.get('batch_id',package['date']),'cards':{}}
        for card in package['cards']:
            plan=plans['cards'][card['kind']]
            plan.update(heading_tone='accent_dark',heading_fade='soft')
            for b in plan['blocks']:
                if b['role']=='example':b.update(photo_tone='paper_ink',fade_style='soft')
            placement['cards'][card['kind']]={'status':'accepted','position':'free','palette':'forest-cream',
                'design':plan['design'],'composition':plan,'block_styles':{b['role']:b['style'] for b in plan['blocks']},
                'answer_badges':{},'heading_tone':'accent_dark',
                'example_tone':'paper_ink' if card.get('example') else None}
        report=with_rendering(report_data(package,results(),RUN),placement)
        text,markup=render_report(report)
        self.assertIn('Title fade: soft',text);self.assertIn('Title fade: soft',markup)

"""Photo-first exceptions, optional category hues and isolated light-panel rules."""
import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image,ImageChops
from jsonschema import Draft202012Validator
from easybosnian.core import ROOT,read_json
from easybosnian.designs import category_colours,panel_rule_colour
from easybosnian.hybrid import category_label,default_plan,measured_plan,draw_panel,render_hybrid
from easybosnian.visual_placement import CARD_SCHEMA,review_compositions
from easybosnian.visual_history import accepted_choices
from test_project import reviewed_fixture

class PaletteCompatibilityControlTests(unittest.TestCase):
    def test_all_category_additions_are_legible_and_do_not_change_archived_category_pixels(self):
        catalogue=read_json(ROOT/'data/design-palettes.json')
        self.assertEqual(sum('category_secondary' in p for p in catalogue.values()),18)
        for name,p in catalogue.items():
            with self.subTest(palette=name):
                bare={k:v for k,v in p.items() if k not in ('category_secondary','light_rule')}
                old=Image.new('RGBA',(500,180),'#808080');new=old.copy()
                category_label(old,'RIJEČ DANA',bare,'pill');category_label(new,'RIJEČ DANA',p,'pill')
                self.assertIsNone(ImageChops.difference(old,new).convert('RGB').getbbox())
                if 'category_secondary' in p:
                    result=category_label(new,'RIJEČ DANA',p,'pill',tone='ink_secondary')
                    self.assertGreaterEqual(result['contrast'],4.5)
                    self.assertEqual(category_colours(p,'ink_secondary'),(p['ink'],p['category_secondary']))
                else:
                    with self.assertRaisesRegex(ValueError,'unavailable'):category_colours(p,'ink_secondary')
        card=reviewed_fixture()['cards'][2];plan=default_plan(card)
        plan['blocks'][0]['panel_tone']='ink_secondary'
        self.assertTrue(list(Draft202012Validator(CARD_SCHEMA).iter_errors(plan)))
        plan=default_plan(card);plan['heading_tone']='ink_secondary'
        self.assertTrue(list(Draft202012Validator(CARD_SCHEMA).iter_errors(plan)))

    def test_new_rule_pixels_are_isolated_and_missing_control_is_exactly_legacy(self):
        p=read_json(ROOT/'data/design-palettes.json')['lavender-pearl'];card=reviewed_fixture()['cards'][2]
        plan=default_plan(card);plan['blocks'][0].update(style='corner_brackets',panel_tone='ink_paper')
        block=measured_plan(card,plan)[0];canvas=Image.new('RGBA',(1080,1350),'#808080')
        original=canvas.copy();before=copy.deepcopy({k:v for k,v in block.items() if k!='face'})
        foreground=draw_panel(original,block,p)
        legacy=copy.deepcopy(block);legacy.pop('rule_tone')
        archived=canvas.copy();draw_panel(archived,legacy,p)
        self.assertIsNone(ImageChops.difference(original,archived).convert('RGB').getbbox())
        changed=copy.deepcopy(block);changed['rule_tone']='contrast';refined=canvas.copy()
        self.assertEqual(draw_panel(refined,changed,p),foreground)
        delta=ImageChops.difference(original,refined).convert('RGB').getbbox();self.assertIsNotNone(delta)
        x,y,right,bottom=block['bounds'];self.assertTrue(x<=delta[0]<delta[2]<=right+1 and y<=delta[1]<delta[3]<=bottom+1)
        self.assertEqual(original.getpixel((x+100,y+50)),refined.getpixel((x+100,y+50)))
        self.assertEqual({k:v for k,v in block.items() if k!='face'},before)
        # An existing answer badge retains exact fill and lettering.
        from easybosnian.hybrid import declared_block,block_spec
        quiz=reviewed_fixture()['cards'][0];answer=declared_block(quiz,'A',width=400,style='corner_brackets',x=64,y=600)
        spec=block_spec(quiz,'A',400,answer['style'],answer['font_size'],answer['line_spacing'],answer['max_lines'])
        answer={**answer,**spec,'bounds':[64,600,464,600+spec['height']]}
        a=canvas.copy();b=canvas.copy();draw_panel(a,answer,p);draw_panel(b,dict(answer,rule_tone='contrast'),p)
        badge=(85,round(600+(spec['height']-52)/2)+1,135,round(600+(spec['height']+52)/2)-1)
        self.assertEqual(a.crop(badge).tobytes(),b.crop(badge).tobytes())

    def test_rule_choices_are_clearer_only_for_eligible_light_decorations(self):
        from easybosnian.render import contrast
        catalogue=read_json(ROOT/'data/design-palettes.json')
        self.assertEqual(sum('light_rule' in p for p in catalogue.values()),27)
        block={'role':'body','style':'corner_brackets','panel_tone':'ink_paper','surface_richness':100,'rule_tone':'contrast'}
        for p in catalogue.values():
            if 'light_rule' not in p:continue
            self.assertEqual(panel_rule_colour(p,block),p['light_rule'])
            self.assertGreater(contrast(p['light_rule'],p['panel']),contrast(p['accent'],p['panel']))
        p=catalogue['lavender-pearl']
        for change in ({'panel_tone':'paper_ink'},{'style':'rounded_plain'},{'style':'split_panel'},{'style':'plain'}, {'role':'A','style':'rounded'}):
            with self.assertRaisesRegex(ValueError,'light decorated'):panel_rule_colour(p,{**block,**change})
        with self.assertRaisesRegex(ValueError,'unavailable'):panel_rule_colour(catalogue['coral-cream'],block)
        with self.assertRaisesRegex(ValueError,'clearer'):panel_rule_colour(dict(p,light_rule=p['panel']),block)
        self.assertEqual(panel_rule_colour(p,{**block,'rule_tone':'accent','panel_tone':'paper_ink'}),p['accent'])

    def test_photo_fit_exception_survives_repetition_gate_and_reaches_public_report_and_history(self):
        import test_visual_provenance as harness
        from easybosnian.success_report import report_data,with_rendering,render_report
        from test_success_report import RUN,results
        h=harness.VisualProvenanceTests();h.setUp();proposal=h.proposal(h.package)
        proposal['cards']['quiz'].update(palette='plum-blush',palette_exception='none')
        proposal['cards']['lesson'].update(palette='forest-cream',palette_exception='none')
        proposal['cards']['word'].update(palette='plum-blush',palette_exception='photo_compatibility_priority',category_tone='ink_secondary')
        proposal['cards']['word']['blocks'][0].update(style='corner_brackets',panel_tone='ink_paper',rule_tone='contrast')
        with patch('easybosnian.cloud_prepare.run_codex',return_value=json.dumps(proposal)) as child:
            result,status=review_compositions(h.package,{k:{'sheet':k+'.jpg'} for k in proposal['cards']})
        self.assertEqual(status,'reviewed');self.assertNotIn('card_failures',result)
        self.assertEqual(result['palette_decisions']['word']['source'],'chatgpt')
        prompt=child.call_args.args[0]
        for phrase in ('PHOTO/PALETTE COMPATIBILITY is the PRIMARY','NEVER promote a weaker colour fit','photo_compatibility_priority',
            'category_tone=ink_secondary','rule_tone=contrast','Dark panels, unboxed copy and undecorated styles require inactive accent'):
            self.assertIn(phrase,prompt)
        placement,_=h.render(h.package,proposal)
        recent=accepted_choices(placement)['word'];self.assertEqual(recent['category_tone'],'ink_secondary');self.assertEqual(recent['panel_rules']['body'],'contrast')
        public=with_rendering(report_data(h.package,results(),RUN),placement)
        for text in render_report(public):
            text=text.replace(chr(92),'')
            self.assertIn('better photographic colour fit',text)
            self.assertIn('Category secondary surface: #92d8b8',text)
            self.assertIn('decorative rule: contrasting #418c71',text)
        bad=copy.deepcopy(proposal);bad['cards']['word']['palette_exception']='secret unapproved text'
        with patch('easybosnian.cloud_prepare.run_codex',return_value=json.dumps(bad)):
            value,_=review_compositions(h.package,{k:{'sheet':k+'.jpg'} for k in bad['cards']})
        self.assertEqual(value['palette_decisions']['word']['source'],'fallback')

    def test_invalid_new_rule_recovers_only_that_field(self):
        from easybosnian.element_recovery import recover_elements
        card=reviewed_fixture()['cards'][2];plan=dict(default_plan(card),confidence='high',palette='lavender-pearl',category_tone='ink_secondary')
        plan['blocks'][0].update(style='corner_brackets',panel_tone='paper_ink',rule_tone='contrast')
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);photo=root/'photo.jpg';Image.new('RGB',(1080,1350),'#888888').save(photo)
            result=recover_elements(card,plan,photo,lambda p:render_hybrid(card,'lavender-pearl',photo,root/'card.jpg',p),reason='Contrasting rules require a light decorated panel')
        self.assertIsNotNone(result);actual,detail=result;expected=copy.deepcopy(plan);expected['blocks'][0]['rule_tone']='accent'
        self.assertEqual(actual['composition'],expected);self.assertEqual(detail['fallback'],['body'])

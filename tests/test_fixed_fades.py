"""Fresh reviews choose approved colours/presets; geometry and strength stay trusted."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image, ImageChops
from jsonschema import Draft202012Validator
from easybosnian.designs import REVIEW_PHOTO_TONES, REVIEW_TITLE_TONES, PANEL_OPACITIES
from easybosnian.hybrid import default_plan, render_hybrid, measured_plan, protect_text, serif, photo_colours
from easybosnian.render import font, measure
from easybosnian.core import ROOT, read_json
from easybosnian.visual_placement import MODEL_CARD_SCHEMA, CARD_SCHEMA, review_compositions
from easybosnian.visual_history import accepted_choices
from easybosnian.success_report import with_rendering, report_data, render_report
from test_project import reviewed_fixture
from test_success_report import RUN, results


class FixedFadeTests(unittest.TestCase):
    def proposal(self):
        package=reviewed_fixture()
        return package,{'cards':{c['kind']:dict(default_plan(c),confidence='high',palette=p) for c,p in zip(package['cards'],('gold-cream','blue-ice','forest-cream'))}}

    def test_new_model_allows_colour_pairs_and_two_presets_but_no_free_shape_or_strength(self):
        package,base=self.proposal();model=Draft202012Validator(MODEL_CARD_SCHEMA)
        self.assertIn('paper_dark',REVIEW_PHOTO_TONES);self.assertIn('ink_light',REVIEW_PHOTO_TONES)
        for tone in REVIEW_PHOTO_TONES:
            plan=copy.deepcopy(base['cards']['word'])
            plan['blocks'][-1]['photo_tone']=tone
            self.assertFalse(list(model.iter_errors(plan)),tone)
        for tone in REVIEW_TITLE_TONES:
            plan=copy.deepcopy(base['cards']['word']);plan['heading_tone']=tone
            self.assertFalse(list(model.iter_errors(plan)),tone)
        self.assertFalse(list(model.iter_errors(base['cards']['word'])))
        for preset in ('standard','defined'):
            plan=copy.deepcopy(base['cards']['word'])
            plan['heading_fade']=preset;plan['blocks'][-1]['fade_style']='standard'
            self.assertFalse(list(model.iter_errors(plan)))
        for scope,key,value in [('card','heading_fade','soft'),('example','fade_style','soft'),('example','fade_style','defined')]:
            plan=copy.deepcopy(base['cards']['word'])
            target=plan if scope=='card' else next(b for b in plan['blocks'] if b['role']=='example')
            target[key]=value
            self.assertTrue(list(model.iter_errors(plan)),(scope,key,value))
            # Historical metadata is still understood rather than corrupting old reports.
            self.assertFalse(list(Draft202012Validator(CARD_SCHEMA).iter_errors(plan)))
        self.assertEqual(PANEL_OPACITIES['translucent'],191)
        for scope,key,value in [('card','fade_opacity',50),('example','fade_width',400),
                                ('card','heading_feather',100),('example','fade_padding',100),
                                ('card','shade_levels',[54,78]),('card','feather_power',1.75),
                                ('card','surround_opacity',.35),
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
                self.assertEqual(plan['heading_fade'],'standard')
                self.assertEqual(plan['blocks'][-1]['fade_style'],'standard')
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
        self.assertEqual(reviewed['cards']['word']['confidence'],'high')
        self.assertEqual(reviewed['card_invalid_elements']['word'],['body','heading'])
        # These values remain rejected, pending element repair; they are not rendered.
        self.assertEqual(reviewed['cards']['word']['heading_fade'],'soft')
        self.assertEqual(reviewed['cards']['quiz'],base['cards']['quiz'])
        self.assertEqual(reviewed['palette_decisions']['word']['source'],'chatgpt')
        prompt=child.call_args.args[0]
        for text in ('Catalogue order is not a ranking','Compare EVERY approved palette',
                     'do not stop at the first acceptable','review ALL compatible',
                     'For the TITLE specifically, keep a softly shaded appearance',
                     'Favour a gentle fade over a pronounced dark band',
                     'Do not select a worse-fitting colour pair simply to avoid shading',
                     'Pillow first tries very light title strengths and a more transparent outer fade',
                     'stronger protection is reserved for the actual glyph area',
                     'Pillow lightens the surrounding photograph',
                     'Pillow alone controls strength',
                     'This title preference does not change PRIMJER treatment',
                     'Choose heading_fade for photographic titles from exactly two approved presets',
                     'standard has smoothly eased edges; defined preserves the earlier',
                     'with EVERY shade treatment and EVERY design',
                     'Only the approved preset ID and text/fade COLOURS are selectable'):
            self.assertIn(text,prompt)
        self.assertNotIn('favour one that is clearly readable with little or no added shading',prompt)
        shown=prompt.split(' PRIMJER photo-colour catalogue: ',1)[1].split(' Palette repetition policy for EVERY palette:',1)[0]
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
            placement['cards'][card['kind']]={'status':'accepted','position':'free','palette':plan['palette'],
                'design':plan['design'],'composition':plan,'block_styles':{b['role']:b['style'] for b in plan['blocks']},
                'answer_badges':{},'heading_tone':'accent_dark',
                'example_tone':'paper_ink' if card.get('example') else None}
        report=with_rendering(report_data(package,results(),RUN),placement)
        text,markup=render_report(report)
        self.assertIn('Title fade: soft',text);self.assertIn('Title fade: soft',markup)

    def test_standard_fade_support_stays_within_48px_of_measured_text_by_default(self):
        palette=read_json(ROOT/'data/design-palettes.json')['gold-cream']
        label_face=font(21,'SemiBold')
        example_y=500+measure(['PRIMJER'],label_face)[0]+16
        cases=[((64,155),['Čuvaj svoju riječ.'],serif(74),None,(),3),
               ((64,example_y),['Moje vunene rukavice su pored jakne.'],serif(34,True),1.35,
                (((64,500),['PRIMJER'],label_face),),4.5),
               ((64,example_y),['Čuvaj svoju riječ i đakovu torbu.',
                                'Šetnja će prijati cijeloj porodici.'],serif(34,True),1.55,
                (((64,500),['PRIMJER'],label_face),),4.5)]
        for tone,background in [('paper_dark','#b0b0b0'),('ink_light','#303030'),
                                ('paper_ink','#b0b0b0'),('ink_paper','#303030')]:
            for xy,rows,face,leading,extra,threshold in cases:
                with self.subTest(tone=tone,rows=len(rows),size=face.size):
                    original=Image.new('RGBA',(1080,1350),background);image=original.copy()
                    colours,backings=photo_colours(palette,tone)
                    colour,score,alpha=protect_text(image,xy,rows,face,colours,threshold,
                        extra=extra,line_spacing=leading,backings=backings)
                    self.assertEqual(colour,colours[0]);self.assertGreaterEqual(score,threshold)
                    self.assertGreater(alpha,0)
                    changed=ImageChops.difference(image.convert('RGB'),original.convert('RGB')).getbbox()
                    top=min([xy[1],*(item[0][1] for item in extra)])
                    bottom=max([xy[1]+measure(rows,face,leading)[0],
                                *(p[1]+measure(r,f)[0] for p,r,f in extra)])
                    self.assertGreaterEqual(changed[1],top-48)
                    self.assertLessEqual(changed[3],bottom+48)
                    self.assertLess(changed[1],top);self.assertGreater(changed[3],bottom)
                    self.assertEqual(image.getpixel((540,top-64)),original.getpixel((540,top-64)))
                    self.assertEqual(image.getpixel((540,bottom+64)),original.getpixel((540,bottom+64)))

    def test_compact_fade_respects_photo_limits_and_existing_no_shade_rules(self):
        original=Image.new('RGBA',(420,300),'#b0b0b0');image=original.copy()
        face=serif(28,True);label=font(21,'SemiBold')
        colour,score,alpha=protect_text(image,(48,110),['Čuvaj riječ.'],face,['#ffffff'],4.5,
            (20,50,400,200),extra=[((48,65),['PRIMJER'],label)])
        self.assertEqual(colour,'#ffffff');self.assertGreaterEqual(score,4.5);self.assertGreater(alpha,0)
        bounds=ImageChops.difference(image.convert('RGB'),original.convert('RGB')).getbbox()
        self.assertGreaterEqual(bounds[0],20);self.assertGreaterEqual(bounds[1],50)
        self.assertLessEqual(bounds[2],400);self.assertLessEqual(bounds[3],200)
        readable=Image.new('RGBA',(420,300),'#000000');before=readable.tobytes()
        self.assertEqual(protect_text(readable,(48,110),['Čuvaj riječ.'],face,['#ffffff'],4.5)[2],0)
        self.assertEqual(readable.tobytes(),before)
        untouched=original.copy()
        with self.assertRaisesRegex(ValueError,'Unshaded photo text fails'):
            protect_text(untouched,(48,110),['Čuvaj riječ.'],face,['#ffffff'],4.5,allow_fade=False)
        self.assertEqual(untouched.tobytes(),original.tobytes())

    def test_real_card_keeps_model_choices_exact_with_narrower_fades(self):
        card=reviewed_fixture()['cards'][2];source=copy.deepcopy(card)
        plan=default_plan(card);plan.update(confidence='high',heading_tone='paper_ink')
        plan['blocks'][-1]['photo_tone']='paper_ink'
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);photo=root/'photo.jpg';Image.new('RGB',(1080,1350),'#b0b0b0').save(photo)
            with patch('easybosnian.hybrid.PHOTO_FADE_FEATHER',100):
                old=render_hybrid(card,'gold-cream',photo,root/'old.jpg',plan)
            new=render_hybrid(card,'gold-cream',photo,root/'new.jpg',plan)
            self.assertNotEqual((root/'old.jpg').read_bytes(),(root/'new.jpg').read_bytes())
            self.assertEqual(new['composition'],plan);self.assertEqual(old['composition'],plan)
            for key in ('heading_colour','example_colour','heading_shading','example_shading',
                        'panel_bounds','example_bounds','block_styles','block_typography'):
                self.assertEqual(new[key],old[key],key)
            self.assertGreaterEqual(new['heading_contrast'],3)
            self.assertGreaterEqual(new['example_contrast'],4.5)
            self.assertGreaterEqual(new['body_contrast'],4.5)
            self.assertEqual(measured_plan(card,plan)[0]['rows'].reconstructed(),card['body'])
            self.assertEqual(card,source)

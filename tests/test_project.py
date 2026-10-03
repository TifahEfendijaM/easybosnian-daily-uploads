import copy
import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from easybosnian.core import ROOT, LAYOUTS, verify_repository
from easybosnian.render import density, font, render, wrap
from easybosnian.validate import validate, normalise
from easybosnian.pipeline import verify_media
from easybosnian.http import redact

spec=importlib.util.spec_from_file_location('preview',ROOT / 'scripts/preview.py')
preview=importlib.util.module_from_spec(spec); spec.loader.exec_module(preview)


def reviewed_fixture():
    p=preview.package()
    # Test-only flags: source and semantic checks must be done by the real scheduled reviewer.
    for k in ('standard_bosnian_checked','sources_checked','semantic_history_checked','no_answer_leak_checked'): p['private_review'][k]=True
    return p


class ContentTests(unittest.TestCase):
    def test_valid_and_draft_rejected(self):
        validate(reviewed_fixture())
        with self.assertRaises(ValueError): validate(preview.package())

    def test_leaks_and_answer_letters_rejected(self):
        for field,value in [('caption','Tačan odgovor je B.'),('caption','Ponijeli smo kišobran.'),('hashtags',['#EasyBosnian','#Kišobran','#Bosanski'])]:
            p=reviewed_fixture(); p[field]=value
            with self.assertRaises(ValueError): validate(p)
        p=reviewed_fixture(); p['cards'][1]['body']='Kišobran je dobar primjer.'
        with self.assertRaises(ValueError): validate(p)
        p=reviewed_fixture(); p['cards'][0]['alt_text']='Correct answer: umbrella.'
        with self.assertRaises(ValueError): validate(p)

    def test_repeats_aliases_and_missing_artwork_exclusions_rejected(self):
        p=reviewed_fixture()
        history={'days':[{'date':'2026-10-01','content':p}]}
        with self.assertRaises(ValueError): validate(p,history)
        history={'days':[{'date':'2026-10-01','content':p}]}
        with self.assertRaises(ValueError): validate(p,history)
        for exclusion in ('No text', 'no lettering', 'no logos'):
            p=reviewed_fixture()
            p['cards'][0]['background_prompt']=p['cards'][0]['background_prompt'].replace(exclusion,'')
            with self.subTest(exclusion=exclusion), self.assertRaises(ValueError): validate(p)

    def test_natural_scene_prompt_passes_without_renderer_instructions(self):
        p=reviewed_fixture()
        scene='A natural photograph of soft clouds above distant mountains. Gentle daylight, cool blue and grey tones, realistic atmospheric detail. No text, no lettering, no logos.'
        for card in p['cards']:
            card['background_prompt']=scene
        validate(p)
        # Schema still requires approved renderer metadata independently of FLUX prose.
        for field, value in (('design_palette','invented'),('design_template','invented')):
            invalid=copy.deepcopy(p)
            if field=='design_palette': invalid[field]=value
            else: invalid['cards'][0][field]=value
            with self.subTest(field=field), self.assertRaises(ValueError): validate(invalid)

    def test_schema_failure_does_not_echo_private_answer_or_model_prose(self):
        p=reviewed_fixture()
        p['private_review']['correct_text']='private-answer-'+('x'*200)
        with self.assertRaises(ValueError) as failure: validate(p)
        self.assertNotIn('private-answer',str(failure.exception))
        self.assertIn('schema check failed',str(failure.exception))

    def test_validated_legacy_prompt_can_be_migrated(self):
        p=reviewed_fixture()
        p['cards'][0]['background_prompt']='A quiet rainy window. framed layout: top x64..1016 y64..900 uncluttered for three answer boxes. Deep slate-blue #041625, misty #f0f8fc, ice-blue #a8dcf2, muted #10324b. No text, no lettering, no logos.'
        validate(p)

    def test_diatrics_alias_normalization(self):
        self.assertEqual(normalise(' KIŠOBRAN! '),normalise('kisobran'))
        self.assertEqual(normalise('Đak'),normalise('dak'))

    def test_template_example_label_cannot_leak_the_quiz_answer(self):
        p=reviewed_fixture();p['words'][0]={'lemma':'primjer','equivalence_keys':['example']}
        p['cards'][0]['word']='primjer';p['cards'][0]['options'][1]['text']='primjer'
        p['private_review']['correct_text']='primjer'
        with self.assertRaises(ValueError):validate(p)

    def test_marker_and_mismatched_private_answer(self):
        p=reviewed_fixture(); p['cards'][0]['options'][0]['text']='A) torba'
        with self.assertRaises(ValueError): validate(p)
        p=reviewed_fixture(); p['private_review']['correct_option']='A'
        with self.assertRaises(ValueError): validate(p)


class RendererTests(unittest.TestCase):
    def test_density_boundaries(self):
        p=preview.package()['cards'][1]
        for n,size,padding in [(160,44,38),(161,38,30),(240,38,30),(241,34,24)]:
            p['body']='a'*n
            self.assertEqual(density(p),(size,padding))

    def test_every_layout_card_and_density(self):
        with tempfile.TemporaryDirectory() as directory:
            background=Path(directory)/'bg.jpg'; Image.new('RGB',(1080,1350),'#648699').save(background)
            seen=set()
            for style in LAYOUTS:
                for original in preview.package()['cards']:
                    for variant in ('short','long'):
                        c=copy.deepcopy(original); c['design_template']=style
                        if c['kind']=='quiz' and variant=='long':
                            c['question']='Koji predmet koristimo tokom kišnog dana da se zaštitimo od kiše?'
                            c['options'][0]['text']='torba koju nosimo preko ramena'
                        if c['kind']=='lesson' and variant=='long':
                            c['body']='Od riječi „oblak“ nastaje pridjev „oblačan“. Kada opisujemo vrijeme, često kažemo: „Danas je oblačno.“ To znači da na nebu ima oblaka. Obrati pažnju na oblik pridjeva: oblačan dan, oblačno jutro i oblačna noć. Tako pridjev usklađujemo s imenicom.'
                        output=Path(directory)/f'{style}-{c["kind"]}-{variant}.jpg'
                        metrics=render(c,'blue-ice',background,output)
                        with Image.open(output) as image: self.assertEqual(image.size,(1080,1350))
                        self.assertLess(metrics['panel_area_ratio'],.49)
                        self.assertLess(metrics['panel_bounds'][-1][3],1050)
                        seen.add(output.read_bytes())
            self.assertGreater(len(seen),24)

    def test_palettes_and_exact_wrapping(self):
        with tempfile.TemporaryDirectory() as directory:
            bg=Path(directory)/'bg.jpg'; Image.new('RGB',(1080,1350),'#728192').save(bg)
            for palette in json.loads((ROOT/'data/design-palettes.json').read_text()):
                render(preview.package()['cards'][2],palette,bg,Path(directory)/f'{palette}.jpg')
        text='Često čujemo: ćilim, šuma, žaba i đak.'
        self.assertEqual(' '.join(wrap(text,font(44),400)),text)

    def test_overlong_copy_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            bg=Path(directory)/'bg.jpg'; Image.new('RGB',(1080,1350)).save(bg)
            c=preview.package()['cards'][1]; c['body']='Duga rečenica. '*100
            with self.assertRaises(ValueError): render(c,'blue-ice',bg,Path(directory)/'bad.jpg')

    def test_logo_original_preserved(self):
        with Image.open(ROOT/'assets/watermark.png') as logo:
            self.assertEqual(logo.mode,'RGBA')
            self.assertEqual(logo.getextrema()[3][0],0)
            self.assertGreater(logo.getextrema()[3][1],0)


class PublishingTests(unittest.TestCase):
    def test_wrong_repo_is_rejected(self):
        with patch.dict(os.environ,{'GITHUB_REPOSITORY':'other/repository'}):
            with self.assertRaises(RuntimeError): verify_repository()

    def test_verification_requires_actual_three_card_permalink(self):
        p=reviewed_fixture()
        class FakeIG:
            def media(self,id):
                return {'id':'123','caption':p['caption']+'\n\n'+' '.join(p['hashtags']),'media_type':'CAROUSEL_ALBUM','children':{'data':[{'media_type':'IMAGE'}]*3},'permalink':'https://www.instagram.com/p/test/'}
        self.assertTrue(verify_media(FakeIG(),p,'123').startswith('https://'))
        class Wrong(FakeIG):
            def media(self,id): r=super().media(id); r.pop('permalink'); return r
        with self.assertRaises(ValueError): verify_media(Wrong(),p,'123')

    def test_secrets_are_redacted(self):
        with patch.dict(os.environ,{'INSTAGRAM_ACCESS_TOKEN':'secret-value'}):
            self.assertNotIn('secret-value',redact('Error secret-value'))


if __name__=='__main__': unittest.main()

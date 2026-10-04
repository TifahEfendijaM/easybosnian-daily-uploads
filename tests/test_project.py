import copy
import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from easybosnian.core import ROOT, verify_repository
from easybosnian.render import density, font, wrap
from easybosnian.hybrid import render_hybrid as render, default_plan
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

    def test_foreign_word_translation_questions_rejected_without_echoing_copy(self):
        for question in ('Kako se na bosanskom kaže „button” na odjeći?',
                         'Kako se kaže „button” na bosanskom?',
                         'Koji je prijevod engleske riječi „button”?'):
            p=reviewed_fixture(); p['cards'][0]['question']=question
            with self.subTest(question=question), self.assertRaises(ValueError) as failure:
                validate(p)
            self.assertIn('foreign-word translation',str(failure.exception))
            self.assertNotIn('button',str(failure.exception))

    def test_bosnian_description_and_visual_naming_quizzes_remain_valid(self):
        p=reviewed_fixture()
        p['cards'][0]['question']='Kako kažemo za predmet kojim se štitimo od kiše?'
        validate(p)
        p['cards'][0]['question']='Kako se zove predmet na slici?'
        p['cards'][0]['background_prompt']='Photorealistic photograph of a closed blue umbrella resting on a wooden bench beside a rainy window. Soft overcast daylight, realistic fabric and wood textures. An off-centre close-up with softly blurred surroundings. No text, no lettering, no logos.'
        validate(p)
        # Permission to depict the referent does not expose the answer in other copy.
        for field in ('caption','alt_text'):
            leaked=copy.deepcopy(p)
            if field=='caption': leaked[field]='Predmet na slici je kišobran.'
            else: leaked['cards'][0][field]='Na slici je kišobran.'
            with self.subTest(field=field), self.assertRaises(ValueError): validate(leaked)

    def test_four_options_allow_d_and_reject_missing_duplicate_or_leaked_answers(self):
        p=reviewed_fixture();q=p['cards'][0]
        q['options'].append({'label':'D','text':'kišobran'})
        q['options'][1]['text']='šešir';p['private_review']['correct_option']='D'
        validate(p)
        for change in ('gap','duplicate','leak','missing'):
            bad=copy.deepcopy(p)
            if change=='gap':bad['cards'][0]['options'][2]['label']='D'
            if change=='duplicate':bad['cards'][0]['options'][0]['text']='kišobran'
            if change=='leak':bad['caption']='Tačan odgovor je D.'
            if change=='missing':bad['cards'][0]['options'].pop()
            with self.subTest(change=change),self.assertRaises(ValueError):validate(bad)

    def test_yes_no_quiz_allows_ordinary_da_ne_prose_but_not_explicit_answer(self):
        p=reviewed_fixture();q=p['cards'][0]
        q['question']='Da li je predmet na slici koristan za zaštitu od kiše?'
        q['options']=[{'label':'A','text':'Da'},{'label':'B','text':'Ne'}]
        p['private_review'].update(correct_option='A',correct_text='Da',answer_aliases=['da'],identifying_hints=['tačan odgovor je da'])
        p['cards'][1]['body']='Ne zaboravi da pogledaš nebo prije izlaska. Oblaci mogu najaviti promjenu vremena.'
        validate(p)
        for field in ('caption','body'):
            bad=copy.deepcopy(p)
            if field=='caption':bad[field]='Tačan odgovor je Da.'
            else:bad['cards'][1][field]='Odgovor je Da, pogledaj nebo.'
            with self.subTest(field=field),self.assertRaises(ValueError):validate(bad)

    def test_captions_cannot_reference_deleted_content_or_corrections(self):
        for text in ('Mala ispravka: danas biramo odgovor.', 'Ovo je nova verzija objave.', 'Umjesto prethodne objave, pogledaj pitanje.'):
            p=reviewed_fixture();p['caption']=text
            with self.subTest(text=text),self.assertRaises(ValueError):validate(p)

    def test_new_caption_footer_is_required_without_invalidating_saved_history(self):
        p=reviewed_fixture()
        validate(p)  # Previously saved content remains renderable without rewriting it.
        with self.assertRaisesRegex(ValueError,'final line'):
            validate(p,require_website_footer=True)
        p['caption']+='\n\nDa ti razgovor ne zapne na prvoj rečenici, nastavi učiti bosanski uz EasyBosnian.\n👉easybosnian.com'
        validate(p,require_website_footer=True)
        for suffix in ('\nJoš nešto.', '\n', ''):
            bad=copy.deepcopy(p)
            if suffix=='\n':bad['caption']=bad['caption'].replace('\n👉easybosnian.com','\n\n👉easybosnian.com')
            elif not suffix:bad['caption']=bad['caption'].replace('easybosnian.com','easybosnian.example')
            else:bad['caption']+=suffix
            with self.subTest(suffix=suffix),self.assertRaises(ValueError):validate(bad,require_website_footer=True)
        bad=copy.deepcopy(p);bad['caption']='easybosnian.com\n'+bad['caption']
        with self.assertRaises(ValueError):validate(bad,require_website_footer=True)
        for ending in ('easybosnian.com','👇\neasybosnian.com','👉 easybosnian.com'):
            bad=copy.deepcopy(p);bad['caption']=bad['caption'].replace('👉easybosnian.com',ending)
            with self.subTest(ending=ending),self.assertRaises(ValueError):validate(bad,require_website_footer=True)
        bad=copy.deepcopy(p);bad['caption']=bad['caption'].replace('Da ti razgovor','Da ti kišobran')
        with self.assertRaisesRegex(ValueError,'leaks'):
            validate(bad,require_website_footer=True)

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

    def test_new_batches_need_no_planning_layout_and_legacy_layouts_are_readable(self):
        package=reviewed_fixture();self.assertTrue(all('design_template' not in c for c in package['cards']))
        validate(package)
        for style in ('editorial','framed','notebook','ribbon','split-cards','minimal','rounded','poster'):
            legacy=copy.deepcopy(package)
            for card in legacy['cards']:card['design_template']=style
            validate(legacy)
        schema=json.loads((ROOT/'data/content.schema.json').read_text())
        self.assertNotIn('design_template',schema['$defs']['card']['required'])
        self.assertFalse((ROOT/'data/design-layouts.json').exists())

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
            for style in ('rounded','outlined'):
                for original in preview.package()['cards']:
                    for variant in ('short','long'):
                        c=copy.deepcopy(original)
                        if c['kind']=='quiz' and variant=='long':
                            c['question']='Koji predmet koristimo tokom kišnog dana da se zaštitimo od kiše?'
                            c['options'][0]['text']='torba koju nosimo preko ramena'
                        if c['kind']=='lesson' and variant=='long':
                            c['body']='Od riječi „oblak“ nastaje pridjev „oblačan“. Kada opisujemo vrijeme, često kažemo: „Danas je oblačno.“ To znači da na nebu ima oblaka. Obrati pažnju na oblik pridjeva: oblačan dan, oblačno jutro i oblačna noć. Tako pridjev usklađujemo s imenicom.'
                        output=Path(directory)/f'{style}-{c["kind"]}-{variant}.jpg'
                        plan=default_plan(c)
                        for block in plan['blocks']:
                            if block['role']!='example':block['style']=style
                        metrics=render(c,'blue-ice',background,output,plan)
                        with Image.open(output) as image: self.assertEqual(image.size,(1080,1350))
                        self.assertLess(sum((b[2]-b[0])*(b[3]-b[1]) for b in metrics['panel_bounds'])/(1080*1350),.49)
                        self.assertLess(metrics['panel_bounds'][-1][3],1170)
                        seen.add(output.read_bytes())
            self.assertGreater(len(seen),6)

    def test_accents_and_descenders_keep_uniform_paragraph_baselines(self):
        from easybosnian.render import draw_rows,measure
        from unittest.mock import MagicMock
        face=font(44);rows=['Rasparan šav ne znači da odjeću','moramo baciti. Šiti možemo i kada','popravljamo nešto staro, a ne samo','kada pravimo nešto novo.']
        draw=MagicMock();draw.textbbox.side_effect=lambda xy,text,font:font.getbbox(text)
        height=draw_rows(draw,(64,200),rows,face,'#000000')
        positions=[c.args[0][1] for c in draw.text.call_args_list]
        step=measure(rows,face)[1]
        self.assertEqual([positions[i+1]-positions[i] for i in range(len(positions)-1)],[step]*3)
        boxes=[face.getbbox(row) for row in rows]
        self.assertGreaterEqual(height,max(positions[i]+box[3]-200 for i,box in enumerate(boxes)))

    def test_balanced_paragraph_preserves_exact_text_without_an_orphan_line(self):
        face=font(44);text='Rasparan šav ne znači da odjeću moramo baciti. Šiti možemo i kada popravljamo nešto staro, a ne samo kada pravimo nešto novo.'
        rows=wrap(text,face,852)
        self.assertEqual(' '.join(rows),text)
        self.assertTrue(all(face.getlength(row)<=852 for row in rows))
        self.assertGreater(face.getlength(rows[-1]),852*.35)

    def test_two_and_four_options_fit_every_retained_layout(self):
        with tempfile.TemporaryDirectory() as directory:
            bg=Path(directory)/'bg.jpg';Image.new('RGB',(1080,1350),'#728192').save(bg)
            for n in (2,4):
                for style in ('rounded','outlined'):
                    c=copy.deepcopy(preview.package()['cards'][0])
                    c['options']=[{'label':label,'text':text} for label,text in zip('ABCD',['Da','Ne','Možda','Nikada'])][:n]
                    plan=default_plan(c)
                    for block in plan['blocks']:block['style']=style
                    result=render(c,'blue-ice',bg,Path(directory)/f'{n}-{style}.jpg',plan)
                    self.assertEqual(len(result['panel_bounds']),n)
                    self.assertLess(result['panel_bounds'][-1][3],1170)

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

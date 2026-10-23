"""Independent visual fallback using real Pillow renders and mocked external calls."""
import contextlib
import copy
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from PIL import Image
from easybosnian.artwork import artwork
from easybosnian.hybrid import default_plan, render_hybrid
from easybosnian.visual_diagnostics import select_palette, rendering_provenance
from easybosnian.visual_placement import review_compositions
from easybosnian.visual_history import accepted_choices
from easybosnian.success_report import content_data, report_data, with_rendering, render_report, visual_summary
from test_project import reviewed_fixture
from test_success_report import RUN, results


class VisualProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.package=reviewed_fixture();self.package['batch_id']='b-'+'a'*32

    def proposal(self,package):
        return {'cards':{c['kind']:dict(default_plan(c),confidence='high',palette='terracotta-sand',
                                      category_style='ribbon',palette_exception='no_other_suitable_palette')
                         for c in package['cards']}}

    def render(self,package,proposal,render_override=None,photo=None):
        stream=io.BytesIO();(photo if photo is not None else Image.new('RGB',(1024,1024),'#728192')).save(stream,'JPEG')
        provider=MagicMock();provider.generate.return_value=stream.getvalue()
        store=MagicMock()
        with contextlib.ExitStack() as stack:
            root=Path(stack.enter_context(tempfile.TemporaryDirectory()))
            stack.enter_context(patch('easybosnian.artwork.ROOT',root))
            stack.enter_context(patch('easybosnian.artwork.provider',return_value=provider))
            stack.enter_context(patch('easybosnian.visual_history.recent_choices',return_value=([],'available')))
            shade_draw=stack.enter_context(patch('secrets.choice',side_effect=AssertionError('no visual draw expected')))
            opacity_draw=stack.enter_context(patch('secrets.randbelow',side_effect=AssertionError('no opacity draw expected')))
            child=stack.enter_context(patch('easybosnian.cloud_prepare.run_codex',return_value=json.dumps(proposal)))
            if render_override:stack.enter_context(patch('easybosnian.artwork.render_hybrid',side_effect=render_override))
            stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
            assets=artwork(store,package,review_images=True)
            placement=json.loads((root/'build'/package['batch_id']/'image-placement-result.json').read_text())
            metrics={kind:asset['metrics'] for kind,asset in assets.items()}
            child.assert_called_once();self.assertEqual(provider.generate.call_count,3)
            shade_draw.assert_not_called()
            opacity_draw.assert_not_called()
            self.assertEqual(store.put_file.call_count,3);store.expose.assert_not_called()
        return placement,metrics

    def test_real_render_preserves_layout_on_bad_palette_and_palette_on_bad_layout(self):
        package=copy.deepcopy(self.package);proposal=self.proposal(package)
        proposal['cards']['lesson']['palette']={'untrusted':'private model prose'}
        proposal['cards']['lesson']['blocks'][0]['style']='outlined'
        proposal['cards']['word']['blocks'][0].update(style='outlined',max_lines=1)
        placement,metrics=self.render(package,proposal)
        quiz,lesson,word=(placement['cards'][kind] for kind in ('quiz','lesson','word'))
        self.assertEqual([quiz['provenance'][key]['source'] for key in ('layout','palette')],['chatgpt','chatgpt'])
        self.assertEqual([lesson['provenance'][key]['source'] for key in ('layout','palette')],['chatgpt','fallback'])
        self.assertEqual(lesson['palette'],package['design_palette'])
        self.assertEqual(lesson['category_style'],'ribbon');self.assertEqual(lesson['block_styles']['body'],'outlined')
        expected=copy.deepcopy(proposal['cards']['lesson']);expected['palette']=package['design_palette']
        self.assertEqual(metrics['lesson']['composition'],expected)
        self.assertEqual([word['provenance'][key]['source'] for key in ('layout','palette')],['fallback','chatgpt'])
        self.assertEqual(word['palette'],'terracotta-sand');self.assertEqual(word['block_styles']['body'],'rounded')
        self.assertNotIn('private model prose',str(placement))
        # Recent context must not claim a fallback palette was a model decision.
        recent=accepted_choices(placement)
        self.assertIn('quiz',recent);self.assertIn('lesson',recent);self.assertNotIn('word',recent)
        self.assertNotIn('palette',recent['lesson']);self.assertEqual(recent['lesson']['category_style'],'ribbon')

    def test_missing_invalid_and_low_contrast_palettes_are_isolated_from_layout_contract(self):
        package=copy.deepcopy(self.package);base=self.proposal(package)
        candidates={k:{'sheet':Path(k+'.jpg')} for k in base['cards']}
        for value in (None,'unknown','#123456',45,{'private':'do not log'}):
            proposal=copy.deepcopy(base)
            if value is None:del proposal['cards']['word']['palette']
            else:proposal['cards']['word']['palette']=value
            with patch('easybosnian.cloud_prepare.run_codex',return_value=json.dumps(proposal)) as child:
                reviewed,status=review_compositions(package,candidates)
            child.assert_called_once();self.assertEqual(status,'reviewed')
            self.assertEqual(reviewed['cards']['word']['palette'],package['design_palette'])
            self.assertEqual(reviewed['palette_decisions']['word']['source'],'fallback')
            self.assertEqual(reviewed['cards']['quiz'],base['cards']['quiz'])
        with patch('easybosnian.render.contrast',return_value=1):
            selected,outcome=select_palette(base['cards']['word'],package['design_palette'])
        self.assertEqual(selected,package['design_palette'])
        self.assertEqual(outcome,{'source':'fallback','reason':'ChatGPT palette fails text contrast'})
        # Isolating palette does not relax any other required property or enum.
        for field in ('heading_tone','category_style'):
            bad=copy.deepcopy(base);del bad['cards']['word'][field]
            with patch('easybosnian.cloud_prepare.run_codex',return_value=json.dumps(bad)) as child,contextlib.redirect_stdout(io.StringIO()):
                reviewed,status=review_compositions(package,candidates)
            self.assertEqual(status,'reviewed');child.assert_called_once()
            self.assertEqual(reviewed['cards']['quiz'],base['cards']['quiz'])
            self.assertEqual(reviewed['cards']['lesson'],base['cards']['lesson'])
            self.assertEqual(reviewed['cards']['word']['confidence'],'uncertain')
            self.assertEqual(reviewed['card_failures'],{'word':'review violated the declarative schema'})
            self.assertTrue(all(p['source']=='chatgpt' for p in reviewed['palette_decisions'].values()))

    def test_photographic_palette_rejection_preserves_every_layout_parameter(self):
        package=copy.deepcopy(self.package);proposal=self.proposal(package)
        proposal['cards']['word']['blocks'][0]['style']='outlined'
        seen=[]
        def render(card,palette,background,path,plan=None):
            if card['kind']=='word' and plan and plan['confidence']=='high':
                seen.append((palette,copy.deepcopy(plan)))
                if palette=='terracotta-sand':raise ValueError('Unshaded photo text fails measured contrast')
            return render_hybrid(card,palette,background,path,plan)
        placement,metrics=self.render(package,proposal,render)
        word=placement['cards']['word']
        self.assertEqual([word['provenance'][key]['source'] for key in ('layout','palette')],['chatgpt','fallback'])
        self.assertEqual(len(seen),2)
        expected=copy.deepcopy(seen[0][1]);expected['palette']=package['design_palette']
        self.assertEqual(seen[1][1],expected);self.assertEqual(metrics['word']['composition'],expected)
        self.assertEqual(word['palette_rejection']['proposal'],seen[0][1])
        self.assertNotIn('rejection',word)

    def test_both_fields_fall_back_when_layout_is_invalid_too(self):
        package=copy.deepcopy(self.package);proposal=self.proposal(package)
        proposal['cards']['word']['palette']='invalid';proposal['cards']['word']['blocks'][0]['max_lines']=1
        placement,_=self.render(package,proposal)
        word=placement['cards']['word']
        self.assertEqual([word['provenance'][key]['source'] for key in ('layout','palette')],['fallback','fallback'])
        self.assertEqual(word['palette'],package['design_palette'])

    def test_fallback_layout_can_also_require_a_palette_fallback(self):
        package=copy.deepcopy(self.package);proposal=self.proposal(package)
        proposal['cards']['word']['blocks'][0]['max_lines']=1
        def render(card,palette,background,path,plan=None):
            if card['kind']=='word' and plan and plan['confidence']=='uncertain' and palette=='terracotta-sand':
                raise ValueError('Unshaded photo text fails measured contrast')
            return render_hybrid(card,palette,background,path,plan)
        placement,_=self.render(package,proposal,render)
        word=placement['cards']['word']
        self.assertEqual([word['provenance'][key]['source'] for key in ('layout','palette')],['fallback','fallback'])
        self.assertIn('rejection',word);self.assertIn('palette_rejection',word)

    def test_palette_fallback_still_requires_measured_layout_and_failures_remain_fatal(self):
        from easybosnian.http import SafeError
        package=copy.deepcopy(self.package);proposal=self.proposal(package)
        seen=[]
        def render(card,palette,background,path,plan=None):
            if card['kind']=='word' and plan:
                seen.append((palette,plan['confidence']))
                if plan['confidence']=='high':raise ValueError('Unshaded photo text fails measured contrast')
            return render_hybrid(card,palette,background,path,plan)
        placement,_=self.render(package,proposal,render)
        self.assertEqual([placement['cards']['word']['provenance'][key]['source'] for key in ('layout','palette')],['fallback','fallback'])
        self.assertEqual(seen,[('terracotta-sand','high'),(package['design_palette'],'high'),(package['design_palette'],'uncertain')])
        def unreadable(card,palette,background,path,plan=None):
            if card['kind']=='word' and plan:raise ValueError('Unshaded photo text fails measured contrast')
            return render_hybrid(card,palette,background,path,plan)
        with self.assertRaises(SafeError):self.render(package,proposal,unreadable)

    def test_equal_palette_ids_do_not_determine_source_and_uncertainty_keeps_palette(self):
        package=copy.deepcopy(self.package);proposal=self.proposal(package)
        proposal['cards']['quiz']['palette']=package['design_palette']
        proposal['cards']['lesson']['confidence']='uncertain'
        placement,_=self.render(package,proposal)
        self.assertEqual(placement['cards']['quiz']['palette_outcome']['source'],'chatgpt')
        self.assertEqual(placement['cards']['lesson']['provenance']['layout']['source'],'fallback')
        self.assertEqual(placement['cards']['lesson']['provenance']['palette']['source'],'chatgpt')

    def test_summaries_and_markdown_html_json_reports_show_both_sources(self):
        package=copy.deepcopy(self.package);proposal=self.proposal(package)
        proposal['cards']['lesson']['palette']='invalid'
        proposal['cards']['word']['blocks'][0]['max_lines']=1
        placement,_=self.render(package,proposal)
        data=with_rendering(report_data(package,results(),RUN),placement)
        text,markup=render_report(data);summary=visual_summary(content_data(package,RUN),placement)
        for body in (text,markup,summary):
            for phrase in ('Layout source: chatgpt','Layout source: fallback',
                           'Palette source: chatgpt','Palette source: fallback','ChatGPT palette not approved'):
                self.assertIn(phrase,body)
            self.assertNotIn('Photo-reviewed final palette',body)
        self.assertEqual(data['cards'][1]['rendering']['provenance']['palette']['source'],'fallback')
        bad=copy.deepcopy(placement)
        bad['cards']['lesson']['palette_outcome']['reason']='private arbitrary model prose'
        with self.assertRaises(ValueError):with_rendering(report_data(package,results(),RUN),bad)
        # Historical fallback palettes cannot be attributed from IDs alone.
        legacy=copy.deepcopy(placement)
        for card in legacy['cards'].values():
            card.pop('palette_outcome');card.pop('provenance')
        old=with_rendering(report_data(package,results(),RUN),legacy)
        self.assertTrue(all(c['rendering']['provenance']['palette']['source']=='unknown' for c in old['cards']))
        self.assertIn('Palette source not recorded in this older run',render_report(old)[0])

    def test_palette_provenance_rejects_arbitrary_sources_reasons_and_fields(self):
        for bad in ({'source':'model','reason':'ChatGPT palette missing'},
                    {'source':'chatgpt','reason':'private prose'},
                    {'source':'chatgpt','reason':'ChatGPT selected this approved palette','extra':'private'},
                    {'source':[],'reason':'private'}):
            with self.assertRaises(ValueError):rendering_provenance({'status':'accepted','palette_outcome':bad},'reviewed')


if __name__=='__main__':unittest.main()

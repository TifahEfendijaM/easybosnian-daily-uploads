import copy
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch, MagicMock
from PIL import Image

from easybosnian.artwork import artwork
from easybosnian.visual_history import accepted_choices, recent_choices
from easybosnian.visual_diagnostics import rendering_outcome, review_failure
from easybosnian.hybrid import default_plan
from easybosnian.visual_placement import review_compositions
from easybosnian.success_report import with_rendering, report_data, render_report
from test_project import reviewed_fixture
from test_success_report import results, RUN


class VisualOutcomeTests(unittest.TestCase):
    def placement(self):
        return {'status':'reviewed','cards':{kind:{'status':'accepted','palette':'terracotta-sand',
                'design':'hybrid','position':'free','block_styles':{'A':'pill'} if kind=='quiz' else {'body':'minimal_rule','example':'italic_photo_fade'},
                'category_style':'pill','answer_badges':{},'arbitrary':'private prose'} for kind in ('quiz','lesson','word')}}

    def test_recent_context_excludes_fallbacks_copy_geometry_and_unknown_enums(self):
        data=self.placement();data['cards']['lesson']['status']='default'
        data['cards']['word']['palette']='arbitrary'
        safe=accepted_choices(data)
        self.assertEqual(set(safe),{'quiz'});self.assertNotIn('private',str(safe))
        self.assertNotIn('status',str(safe));self.assertNotIn('position',str(safe))

    def test_artifact_reads_are_bounded_exact_repository_and_never_extract_images(self):
        stream=io.BytesIO()
        with zipfile.ZipFile(stream,'w') as archive:
            archive.writestr('b-'+'a'*32+'/image-placement-result.json',json.dumps(self.placement()))
            archive.writestr('../private.txt','do not extract')
        runs=[{'databaseId':10,'status':'completed','displayTitle':'EasyBosnian (preview)','createdAt':'now'},
              {'databaseId':11,'status':'completed','displayTitle':'EasyBosnian (daily)','createdAt':'now'}]
        artifact={'artifacts':[{'id':12,'name':'easybosnian-daily-11','expired':False,'size_in_bytes':900}]}
        with patch('easybosnian.visual_history.gh',side_effect=[json.dumps(runs),json.dumps(artifact)]) as gh,patch('easybosnian.visual_history.gh_binary',return_value=stream.getvalue()) as binary:
            data,status=recent_choices()
        self.assertEqual(status,'available');self.assertEqual(data[0]['run_id'],11)
        self.assertEqual(gh.call_count,2)
        self.assertIn('TifahEfendijaM/easybosnian-daily-uploads',str(binary.call_args))
        self.assertNotIn('do not extract',str(data))
        with patch('easybosnian.visual_history.gh',side_effect=RuntimeError('secret provider prose')):
            self.assertEqual(recent_choices(),([],'unavailable'))

    def test_report_distinguishes_used_uncertain_and_unavailable_per_image(self):
        p=reviewed_fixture();placement=self.placement();placement.update(batch=p['date'],batch_id=p['date'])
        placement['cards']['lesson']['status']='default'
        placement['cards']['word'].update(status='default',review_failure='review timed out')
        data=with_rendering(report_data(p,results(),RUN),placement);text,markup=render_report(data)
        self.assertEqual([c['rendering']['outcome']['source'] for c in data['cards']],['chatgpt','fallback','fallback'])
        for message in ('Pillow validated and used','marked the proposal uncertain','review timed out'):
            self.assertIn(message,text);self.assertIn(message,markup)
        placement['cards']['word']['review_failure']='private model prose'
        self.assertNotIn('private model prose',str(with_rendering(report_data(p,results(),RUN),placement)))

    def test_no_second_call_on_review_failure_and_fixed_reason(self):
        p=reviewed_fixture();candidates={c['kind']:{'sheet':Path(c['kind']+'.jpg')} for c in p['cards']}
        error=ValueError('ChatGPT review exceeded its time allowance; inspect the run and reviewed content; no retry was dispatched')
        with patch('easybosnian.cloud_prepare.run_codex',side_effect=error) as child:
            proposal,status=review_compositions(p,candidates)
        child.assert_called_once();self.assertEqual(status,'unavailable')
        self.assertEqual(proposal['failure_reason'],'review timed out')
        self.assertEqual(review_failure(ValueError('private token')),'review unavailable; exact cause not recorded')

    def test_uncertainty_and_unavailable_cannot_be_mislabeled_accepted(self):
        p=reviewed_fixture();stream=io.BytesIO();Image.new('RGB',(1024,1024),'#728192').save(stream,'JPEG')
        provider=MagicMock();provider.generate.return_value=stream.getvalue()
        for status in ('reviewed','unavailable'):
            proposal={'cards':{c['kind']:dict(default_plan(c),palette='terracotta-sand') for c in p['cards']}}
            if status=='unavailable':
                proposal['failure_reason']='invalid review JSON'
                # Even a high-confidence plan cannot come from a failed review.
                for plan in proposal['cards'].values():plan['confidence']='high'
            with tempfile.TemporaryDirectory() as tmp,patch('easybosnian.artwork.ROOT',Path(tmp)),patch('easybosnian.artwork.provider',return_value=provider),patch('easybosnian.visual_history.recent_choices',return_value=([],'available')),patch('easybosnian.visual_placement.review_compositions',return_value=(proposal,status)) as review:
                artwork(MagicMock(),p,review_images=True)
                saved=json.loads((Path(tmp)/'build'/p['date']/'image-placement-result.json').read_text())
            review.assert_called_once()
            self.assertTrue(all(c['outcome']['source']=='fallback' for c in saved['cards'].values()))
            self.assertTrue(all(c['status']=='default' for c in saved['cards'].values()))

    def test_model_gets_recent_choices_and_quality_constrained_variation(self):
        p=reviewed_fixture();proposal={'cards':{c['kind']:dict(default_plan(c),palette='terracotta-sand') for c in p['cards']}}
        candidates={c['kind']:{'sheet':Path(c['kind']+'.jpg')} for c in p['cards']}
        recent=[{'run_id':11,'cards':accepted_choices(self.placement())}]
        with patch('easybosnian.cloud_prepare.run_codex',return_value=json.dumps(proposal)) as child:
            review_compositions(p,candidates,recent)
        prompt=child.call_args.args[0]
        self.assertIn(json.dumps(recent,ensure_ascii=False),prompt)
        self.assertIn('still suitable, appealing, readable',prompt)
        self.assertIn('Never select a poor fit',prompt)
        self.assertIn('No rendered card, layout or style reference',prompt)


if __name__=='__main__':unittest.main()

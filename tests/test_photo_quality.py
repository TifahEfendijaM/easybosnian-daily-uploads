import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock,patch
from PIL import Image
from easybosnian.photo_quality import quality_gate,inspect_photos,revised_prompt
from test_project import reviewed_fixture


def verdict(status='accepted',score=90):
    return {'status':status,'reason':'acceptable' if status=='accepted' else 'major_anatomy_defect',
            'quality':score,'replacement_prompt':None}


class PhotoQualityTests(unittest.TestCase):
    def test_only_failed_photos_regenerate_and_best_rejected_candidate_survives_cap(self):
        package=reviewed_fixture()
        with tempfile.TemporaryDirectory() as tmp:
            paths={k:Path(tmp)/(k+'-background.jpg') for k in ('quiz','lesson')}
            for path in paths.values():Image.new('RGB',(1024,1024),'red').save(path,'JPEG')
            first=paths['lesson'].read_bytes()
            inspect=Mock(side_effect=[{'quiz':verdict(),'lesson':verdict('regenerate',80)},
                                      {'lesson':verdict('regenerate',20)},{'lesson':verdict('regenerate',70)}])
            generate=Mock(side_effect=lambda card,path:Image.new('RGB',(1024,1024),'blue').save(path,'JPEG'))
            result=quality_gate(package,paths,generate,inspect=inspect)
            self.assertEqual(generate.call_count,2);self.assertEqual(inspect.call_count,3)
            self.assertEqual([set(c.args[1]) for c in inspect.call_args_list],[{'quiz','lesson'},{'lesson'},{'lesson'}])
            self.assertEqual(result['lesson']['selected_attempt'],1);self.assertEqual(result['lesson']['status'],'best_effort')
            self.assertEqual(paths['lesson'].read_bytes(),first)
            self.assertEqual(result['quiz']['status'],'accepted')

    def test_acceptance_stops_retries_pinned_photo_never_regenerates_and_service_errors_do_not_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'lesson-background.jpg';Image.new('RGB',(1024,1024),'grey').save(path,'JPEG')
            package=reviewed_fixture();generate=Mock()
            inspect=Mock(side_effect=[{'lesson':verdict('regenerate')},{'lesson':verdict()}])
            result=quality_gate(package,{'lesson':path},generate,inspect=inspect)
            self.assertEqual(result['lesson']['selected_attempt'],2);generate.assert_called_once()
            inspect=Mock(return_value={'lesson':verdict('regenerate')});generate.reset_mock()
            self.assertEqual(quality_gate(package,{'lesson':path},generate,pinned=('lesson',),inspect=inspect)['lesson']['status'],'retained_pinned')
            generate.assert_not_called();inspect.assert_called_once()
            inspect=Mock(side_effect=TimeoutError())
            with self.assertRaises(TimeoutError):quality_gate(package,{'lesson':path},generate,inspect=inspect)
            inspect.assert_called_once();generate.assert_not_called()

    def test_quality_review_uses_actual_photo_crop_and_public_quiz_only(self):
        package=reviewed_fixture()
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'quiz.jpg';Image.new('RGB',(1024,1024),'grey').save(path,'JPEG')
            with patch('easybosnian.cloud_prepare.run_codex',return_value=json.dumps({'photos':{'quiz':verdict()}})) as child:
                self.assertEqual(inspect_photos(package,{'quiz':path})['quiz']['status'],'accepted')
            prompt=child.call_args.args[0]
            self.assertNotIn('correct_option',prompt);self.assertNotIn('private_review',prompt)
            self.assertIn('intentional cropping',prompt);self.assertEqual(len(child.call_args.kwargs['images']),1)
            self.assertTrue(child.call_args.kwargs['read_only'])
        with self.assertRaises(ValueError):revised_prompt('draw a layout #ff0000')

if __name__=='__main__':unittest.main()

class PhotoSelectionIntegrationTests(unittest.TestCase):
    def test_chosen_photo_retains_its_own_prompt_and_cache_namespace(self):
        import contextlib
        import io
        from unittest.mock import MagicMock
        from easybosnian.artwork import artwork
        from easybosnian.hybrid import default_plan
        from easybosnian.core import read_json
        package=reviewed_fixture();package['batch_id']='b-'+'a'*32
        stream=io.BytesIO();Image.new('RGB',(1024,1024),'#728192').save(stream,'JPEG')
        provider=MagicMock();provider.generate.return_value=stream.getvalue()
        replacement='Photorealistic photograph of wispy clouds above a mountain lake. Natural light, realistic textures and true-to-life colours. No text, no lettering, no logos.'
        first=verdict('regenerate',20);first['replacement_prompt']=replacement
        second=verdict('regenerate',90)
        third=verdict('regenerate',30)
        inspector=Mock(side_effect=[{'quiz':verdict(),'lesson':first,'word':verdict()},
                                    {'lesson':second},{'lesson':third}])
        plans={'cards':{c['kind']:dict(default_plan(c),confidence='high',palette='burgundy-oat') for c in package['cards']}}
        with tempfile.TemporaryDirectory() as tmp,contextlib.ExitStack() as stack:
            root=Path(tmp);store=MagicMock()
            stack.enter_context(patch('easybosnian.artwork.ROOT',root))
            stack.enter_context(patch('easybosnian.artwork.provider',return_value=provider))
            stack.enter_context(patch('easybosnian.photo_quality.inspect_photos',side_effect=inspector))
            stack.enter_context(patch('easybosnian.rendered_harmony.inspect',return_value={'verdict':'accept','reason':'harmonious','backing_colour':None,'shade_strength':None}))
            stack.enter_context(patch('easybosnian.visual_history.recent_choices',return_value=([],'available')))
            stack.enter_context(patch('easybosnian.visual_placement.review_compositions',return_value=(plans,'reviewed')))
            assets=artwork(store,package,review_images=True)
            self.assertEqual(provider.generate.call_count,5)
            calls=provider.generate.call_args_list
            self.assertNotEqual(calls[3].kwargs['artwork_id'],calls[4].kwargs['artwork_id'])
            self.assertEqual(package['background_sources']['lesson']['artwork_id'],calls[3].kwargs['artwork_id'])
            self.assertEqual(package['cards'][1]['background_prompt'],replacement)
            quality=read_json(root/'build'/package['batch_id']/'photo-quality-result.json')['cards']['lesson']
            self.assertEqual(quality['selected_attempt'],2);self.assertEqual(quality['status'],'best_effort')
            store.save_content.assert_not_called();store.expose.assert_not_called()

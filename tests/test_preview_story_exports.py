"""Preview exports remain private and cannot acquire publication/history state."""
import contextlib,io,json,os,tempfile,unittest
from pathlib import Path
from unittest.mock import MagicMock,patch
from PIL import Image
from easybosnian.artwork import artwork
from easybosnian.core import ROOT
from test_project import reviewed_fixture,accepted_photo_review
import test_visual_provenance as provenance_harness
from test_success_report import RUN

class PreviewStoryExportsTests(unittest.TestCase):
 def test_preview_exports_exact_three_feeds_and_stories_without_snapshots_or_history(self):
  h=provenance_harness.VisualProvenanceTests();h.setUp();package=h.package;proposal=h.proposal(package)
  photo=io.BytesIO();Image.new('RGB',(1024,1024),'#728192').save(photo,'JPEG')
  provider=MagicMock();provider.generate.return_value=photo.getvalue();store=MagicMock()
  with tempfile.TemporaryDirectory() as tmp,contextlib.ExitStack() as stack:
   root=Path(tmp)
   stack.enter_context(patch.dict(os.environ,MODE='preview'))
   stack.enter_context(patch('easybosnian.artwork.ROOT',root))
   stack.enter_context(patch('easybosnian.artwork.provider',return_value=provider))
   stack.enter_context(patch('easybosnian.photo_quality.inspect_photos',side_effect=accepted_photo_review))
   stack.enter_context(patch('easybosnian.visual_history.recent_choices',return_value=([],'available')))
   stack.enter_context(patch('easybosnian.cloud_prepare.run_codex',return_value=json.dumps(proposal)))
   snapshots=stack.enter_context(patch('easybosnian.frozen_cards.snapshot',side_effect=AssertionError('preview cannot snapshot')))
   assets=artwork(store,package,review_images=True,design_attempt_limit=1)
   names={call.args[1] for call in store.put_file.call_args_list}
   self.assertEqual(names,{f'{k}-{suffix}.jpg' for k in ('quiz','lesson','word') for suffix in ('card','story')})
   self.assertEqual(store.put_file.call_count,6)
   for kind,item in assets.items():
    with Image.open(item['story_path']) as im:self.assertEqual(im.size,(1080,1920))
    self.assertTrue(item['story_path'].is_file());self.assertNotIn('url',item)
   snapshots.assert_not_called();store.expose.assert_not_called();store.save_content.assert_not_called()
   self.assertNotIn('rendered_sources',package)
 def test_preview_saves_only_approved_report_source_fields_for_gallery_labels(self):
  from easybosnian.visual_placement import main
  package=reviewed_fixture();package['batch_id']='b-'+'a'*32
  with tempfile.TemporaryDirectory() as tmp,contextlib.ExitStack() as stack:
   root=Path(tmp);stack.enter_context(patch.dict(os.environ,MODE='preview',GITHUB_RUN_URL=RUN))
   stack.enter_context(patch('easybosnian.core.ROOT',root))
   stack.enter_context(patch('easybosnian.core.verify_repository'))
   stack.enter_context(patch('easybosnian.cli.prepared_batch',return_value=(package['date'],package['batch_id'],None)))
   stack.enter_context(patch('easybosnian.cli.prepared_content',return_value=package))
   stack.enter_context(patch('easybosnian.cli.stage_content'))
   stack.enter_context(patch('easybosnian.artwork.artwork'))
   stack.enter_context(patch('easybosnian.store.Store'))
   stack.enter_context(contextlib.redirect_stdout(io.StringIO()));main()
   source=json.loads((root/'build'/package['batch_id']/'report-source.json').read_text())
   self.assertEqual(source['batch_id'],package['batch_id']);self.assertEqual(len(source['cards']),3)
   self.assertTrue(all(set(c)=={'category','heading','prompt'} for c in source['cards']))
   self.assertNotIn('correct',json.dumps(source));self.assertNotIn('private_review',json.dumps(source))

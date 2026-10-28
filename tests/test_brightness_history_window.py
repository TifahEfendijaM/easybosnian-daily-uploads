import json,unittest
from unittest.mock import patch
from easybosnian.visual_history import brightness_history
from easybosnian.visual_placement import review_compositions
import test_visual_provenance as harness

def batch(n,value,quiz='light'):
 return {'batch_id':'b-'+format(n,'032x'),'panel_theme_observations':[quiz,value,value]}

class BrightnessHistoryWindowTests(unittest.TestCase):
 def test_only_four_newest_batches_and_newest_pair_outweighs_older_pair(self):
  recent=[batch(1,'dark'),batch(2,'dark'),batch(3,'light'),batch(4,'light'),batch(5,'light')]
  result=brightness_history(recent)
  self.assertEqual(len(result['batches']),4)
  self.assertEqual(result['weighted_counts'],{'dark':14,'light':6})
  self.assertEqual(result,brightness_history(recent[:4]))
 def test_duplicates_unknown_and_quiz_do_not_inflate_or_extend_window(self):
  recent=[batch(1,'unknown'),batch(1,'dark'),batch(2,'mixed'),batch(3,'light','dark'),batch(4,'dark'),batch(5,'dark')]
  result=brightness_history(recent)
  self.assertEqual([b['lesson'] for b in result['batches']],['unknown','mixed','light','dark'])
  self.assertEqual(result['weighted_counts'],{'light':4,'dark':2})
 def test_review_receives_dedicated_context_and_keeps_other_history(self):
  h=harness.VisualProvenanceTests();h.setUp();proposal=h.proposal(h.package)
  recent=[batch(i,'light') for i in range(1,6)]
  with patch('easybosnian.cloud_prepare.run_codex',return_value=json.dumps(proposal)) as child:
   review_compositions(h.package,{k:{'sheet':k+'.jpg'} for k in proposal['cards']},recent)
  prompt=child.call_args.args[0]
  for phrase in ('newest at most FOUR','newest ONE or TWO','NEVER additional brightness evidence','independent nine-image palette-repetition window','even if less optimal alone'):
   self.assertIn(phrase,prompt)
  self.assertIn(json.dumps(brightness_history(recent)),prompt)
  self.assertIn(json.dumps(recent,ensure_ascii=False),prompt)

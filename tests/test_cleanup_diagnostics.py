"""Report refusals/partial cleanup without extra writes or guessed Meta limits."""
import contextlib
import io
import json
import os
import runpy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock,patch

from easybosnian.core import ROOT
from easybosnian.http import safe_response_error
from easybosnian.notify import next_step
from easybosnian.replacement import cleanup,cleanup_day
import test_replacement as replacement_harness


def refusal():
    return safe_response_error({'error':{'code':9,'error_subcode':2207074,
        'message':'private provider prose','error_user_msg':'private token'}},400)


class CleanupDiagnosticsTests(unittest.TestCase):
    def test_deletion_refusal_is_distinct_from_publishing_limit_and_never_guesses_a_reset(self):
        error=refusal()
        self.assertEqual(error.reason,'instagram_deletion_refused')
        self.assertNotIn('private',str(error))
        guidance=next_step('instagram replacement cleanup',error)
        self.assertIn('exact deletion restriction/window is unverified',guidance)
        self.assertNotIn('following day',guidance)
        self.assertIsNone(error.provider_code)  # FLUX-only numeric attributes stay unchanged.
        for code,subcode in ((9,2207042),(10,2207074),('9',2207074),(True,2207074)):
            self.assertNotEqual(safe_response_error({'error':{'code':code,'error_subcode':subcode}},400).reason,
                                'instagram_deletion_refused')

    def test_story_delete_refusal_identifies_action_and_still_stops_without_deleting_feed_or_forgetting_ids(self):
        item=replacement_harness.ReplacementTests().item;store=MagicMock()
        store.publications.return_value=[item(id='20'),item('story','21'),item('story','22')]
        ig=MagicMock();ig.user_id='42';ig.owned_ids.return_value={'20','21','22'}
        ig.delete.side_effect=refusal()
        with patch.dict(os.environ,{'INSTAGRAM_USER_ID':'42'}),patch('easybosnian.replacement.require_publishing'), \
             patch('easybosnian.replacement.InstagramDeletion',return_value=ig),self.assertRaises(RuntimeError) as caught:
            cleanup(store,'2026-10-03','instagram')
        self.assertEqual(caught.exception.cleanup_diagnostic,
            {'operation':'delete','kind':'story','removed':0,'already_absent':0})
        ig.delete.assert_called_once_with('21');store.forget.assert_not_called()
        ig.owned_ids.assert_called_once_with('story')

    def test_all_today_counts_confirmed_partial_removals_and_keeps_other_batch_attempt_independent(self):
        item=replacement_harness.ReplacementTests().item;store=MagicMock()
        first='b-'+'a'*32;second='b-'+'b'*32
        store.publications.side_effect=[[
            {**row,'batch_id':first} for row in (item(id='20'),item('story','21'),item('story','22'))],[]]
        ig=MagicMock();ig.user_id='42';ig.owned_ids.side_effect=[{'21','22'},{'22'}]
        ig.delete.side_effect=[None,refusal()]
        with patch.dict(os.environ,{'INSTAGRAM_USER_ID':'42'}),patch('easybosnian.replacement.require_publishing'), \
             patch('easybosnian.replacement.InstagramDeletion',return_value=ig):
            result,errors=cleanup_day(store,[first,second],'2026-10-03','instagram')
        self.assertEqual(len(errors),1);self.assertEqual(result['removed'],1)
        self.assertEqual(result['failures'][0]['operation'],'delete')
        self.assertNotIn('private',json.dumps(result))
        self.assertEqual(store.publications.call_count,2)
        store.forget.assert_called_once_with(first,'instagram','21')
        self.assertEqual([c.args[0] for c in ig.delete.call_args_list],['21','22'])

    def test_post_delete_read_failure_is_reported_as_verification_without_claiming_removal(self):
        store=MagicMock();store.publications.return_value=[replacement_harness.ReplacementTests().item()]
        ig=MagicMock();ig.user_id='42';ig.owned_ids.side_effect=[{'123'},RuntimeError('read failed')]
        with patch.dict(os.environ,{'INSTAGRAM_USER_ID':'42'}),patch('easybosnian.replacement.require_publishing'), \
             patch('easybosnian.replacement.InstagramDeletion',return_value=ig),self.assertRaises(RuntimeError) as caught:
            cleanup(store,'2026-10-03','instagram')
        self.assertEqual(caught.exception.cleanup_diagnostic,
                         {'operation':'deletion_verification','kind':'feed','removed':0,'already_absent':0})
        ig.delete.assert_called_once();store.forget.assert_not_called()

    def test_github_summary_shows_latest_and_all_today_failures_not_only_last_failure_file(self):
        source=ROOT/'scripts/action_summary.py'
        with tempfile.TemporaryDirectory() as temp:
            previous=Path.cwd();os.chdir(temp)
            try:
                folder=Path('build/batch');folder.mkdir(parents=True)
                diagnostic={'operation':'delete','kind':'story','removed':1,'already_absent':0}
                latest={'status':'failed; new publication will still be attempted',
                        'error':str(refusal()),'diagnostic':diagnostic}
                all_today={'scope':'all_today','status':'failed; some earlier content may remain',
                    'removed':1,'already_absent':0,'failures':[{'batch_id':'saved-batch',
                    'error':str(refusal()),**diagnostic}]}
                for entry in (latest,all_today):
                    (folder/'platforms-result.json').write_text(json.dumps({'batch':'2026-10-03',
                        'platforms':{'instagram':{'status':'confirmed Instagram publication',
                        'replacement_cleanup':entry}}}))
                    with contextlib.redirect_stdout(io.StringIO()) as output,patch.dict(os.environ,{},clear=True):
                        runpy.run_path(str(source))
                    text=output.getvalue()
                    self.assertIn('2207074',text);self.assertIn('story/delete',text)
                    self.assertIn('1 confirmed removed',text)
                    self.assertNotIn('private',text)
            finally:os.chdir(previous)

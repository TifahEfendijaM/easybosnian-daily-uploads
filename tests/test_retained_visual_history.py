"""Only current retained publication metadata may influence future visuals."""
import copy,json,unittest
from unittest.mock import MagicMock,patch
from easybosnian.core import PROJECT
from easybosnian.hybrid import default_plan
from easybosnian.frozen_cards import card_digest
from easybosnian.visual_policy import policy_metadata
from easybosnian.visual_history import recent_choices,retained_designs,matching_published_design
from test_project import reviewed_fixture

BASE=reviewed_fixture()
PLANS={c['kind']:dict(default_plan(c),confidence='high') for c in BASE['cards']}

def fixture(n=1,palette='forest-cream'):
 package=copy.deepcopy(BASE);batch='b-'+format(n,'032x');package['batch_id']=batch
 sources={};choices={}
 for card in package['cards']:
  kind=card['kind'];plan=copy.deepcopy(PLANS[kind]);plan['palette']=palette
  policy=policy_metadata(plan)
  metrics={'size':[1080,1350],'palette':palette,'composition':plan,'design':'hybrid',
    'block_styles':{b['role']:b['style'] for b in plan['blocks']},'category_style':'rounded',
    'heading_tone':'auto','example_tone':'auto' if card.get('example') else None,
    'heading_contrast':3,'body_contrast':4.5,'example_contrast':4.5 if card.get('example') else None}
  sources[kind]={'cache_id':'b-'+'f'*32,'date':package['date'],'card_sha256':'a'*64,'story_sha256':'b'*64,
    'content_sha256':card_digest(card),'metrics':metrics,'policy':policy}
  choices[kind]={**copy.deepcopy(metrics),'status':'accepted','render_policy':policy,
    'palette_outcome':{'source':'chatgpt','reason':'ChatGPT selected this approved palette'}}
 package['rendered_sources']=sources
 row={'batch_id':batch,'date':package['date'],'created_at':f'2026-10-02T00:00:{n:02d}Z','created_order':n,'content':package}
 placement={'batch':package['date'],'batch_id':batch,'status':'reviewed','cards':choices}
 outcome={'batch':package['date'],'batch_id':batch,'history_saved':True,'platforms':{'instagram':{'published':True}}}
 files={batch+'/image-placement-result.json':json.dumps(placement),batch+'/platforms-result.json':json.dumps(outcome)}
 return row,placement,files

def run(n,title='EasyBosnian (daily)'):
 return {'id':n,'status':'completed','display_title':title}

class RetainedVisualHistoryTests(unittest.TestCase):
 def test_deleted_superseded_and_unpublished_reports_do_not_enrich_current_choices(self):
  row,placement,files=fixture(1)
  deleted=fixture(2)[2]
  superseded=copy.deepcopy(files);p=copy.deepcopy(placement);p['cards']['word']['composition']['blocks'][0]['style']='outlined'
  superseded[row['batch_id']+'/image-placement-result.json']=json.dumps(p)
  unpublished=copy.deepcopy(files);out=json.loads(unpublished[row['batch_id']+'/platforms-result.json']);out['platforms']['instagram']['published']=False
  unpublished[row['batch_id']+'/platforms-result.json']=json.dumps(out)
  reports={90:deleted,89:superseded,88:unpublished,87:files}
  store=MagicMock();store.history.return_value={'project':PROJECT,'days':[row]}
  with patch('easybosnian.store.Store',return_value=store),patch('easybosnian.visual_history.gh',return_value=json.dumps({'workflow_runs':[run(i) for i in reports]})),patch('easybosnian.run_reports.get_report',side_effect=lambda s,r:{'mode':'daily','files':reports[r]}):
   recent,status=recent_choices()
  self.assertEqual(status,'available');self.assertEqual(len(recent),1);self.assertEqual(recent[0]['run_id'],87)
  self.assertEqual(recent[0]['cards']['word']['block_styles'],placement['cards']['word']['block_styles'])
  self.assertEqual(recent[0]['palette_observations'],['forest-cream']*3)
  store.history.assert_called_once();store.save_content.assert_not_called();store.delete_content.assert_not_called()

 def test_many_previews_never_displace_retained_data_or_consume_daily_lookup(self):
  row,p,files=fixture();store=MagicMock();store.history.return_value={'project':PROJECT,'days':[row]}
  pages=[{'workflow_runs':[run(i,'EasyBosnian (preview)') for i in range(100,200)]},
         {'workflow_runs':[run(1,'EasyBosnian (verify)'),run(2)]}]
  with patch('easybosnian.store.Store',return_value=store),patch('easybosnian.visual_history.gh',side_effect=[json.dumps(x) for x in pages]) as github,patch('easybosnian.run_reports.get_report',return_value={'mode':'daily','files':files}) as report:
   recent,status=recent_choices()
  self.assertEqual(status,'available');self.assertEqual(recent[0]['run_id'],2);self.assertEqual(github.call_count,2)
  self.assertIn('page=2',github.call_args.args[-1]);report.assert_called_once_with(store,2)
  # Even without any report, the retained publication's applied colour evidence survives.
  with patch('easybosnian.store.Store',return_value=store),patch('easybosnian.visual_history.gh',return_value=json.dumps({'workflow_runs':[]})):
   no_reports,_=recent_choices()
  self.assertEqual(no_reports[0]['palette_observations'],recent[0]['palette_observations'])
  self.assertEqual(no_reports[0]['panel_theme_observations'],recent[0]['panel_theme_observations'])
  self.assertEqual(no_reports[0]['cards'],{})  # No guessed ChatGPT provenance.

 def test_newest_retained_batches_occupy_slots_and_missing_sources_stay_unknown(self):
  rows=[fixture(i)[0] for i in range(1,7)];rows[-1]['content'].pop('rendered_sources')
  store=MagicMock();store.history.return_value={'project':PROJECT,'days':rows}
  with patch('easybosnian.store.Store',return_value=store),patch('easybosnian.visual_history.gh',return_value=json.dumps({'workflow_runs':[]})):
   recent,status=recent_choices()
  self.assertEqual([x['batch_id'] for x in recent],[r['batch_id'] for r in rows[::-1][:5]])
  self.assertEqual(recent[0]['palette_observations'],[]);self.assertEqual(recent[0]['panel_theme_observations'],['unknown']*3)
  self.assertEqual(status,'available')

 def test_history_failure_or_bad_identity_does_not_admit_reports_or_retry(self):
  for value in ({'project':'other','days':[]},RuntimeError('private network details')):
   store=MagicMock()
   if isinstance(value,Exception):store.history.side_effect=value
   else:store.history.return_value=value
   with patch('easybosnian.store.Store',return_value=store),patch('easybosnian.visual_history.gh') as github:
    self.assertEqual(recent_choices(),([],'unavailable'))
   store.history.assert_called_once();github.assert_not_called()

"""Saved-photo design previews: fresh private identity, never inference/history."""
import copy
import json

from .batches import BATCH_ID, identity, plan_batch
from .core import PROJECT, ROOT, write_json
from .photo_reuse import prepare_photos, seal_photos
from .validate import validate


def stage_saved_preview(store, history, source_batch_id, run_date):
    if not isinstance(source_batch_id,str) or not BATCH_ID.fullmatch(source_batch_id):
        raise ValueError('Saved preview source requires an exact batch ID')
    records=[r for r in history['days'] if identity(r)==source_batch_id]
    if (len(records)!=1 or not isinstance(records[0].get('content'),dict)
            or records[0]['content'].get('schema_version')!=1 or records[0]['date']>run_date):
        raise ValueError('Saved preview source is missing, incomplete or ambiguous')
    previous=copy.deepcopy(records[0]['content'])
    if previous.get('batch_id',source_batch_id)!=source_batch_id or previous.get('date')!=records[0]['date']:
        raise ValueError('Saved preview source identity differs from its history row')
    previous.pop('rendered_sources',None)  # Finished-card cache is irrelevant to a redesign.
    validate(previous)
    plan=plan_batch(history,run_date,'none')
    prepared=prepare_photos(store,previous,source_batch_id,plan['batch_id'],run_date)
    package=copy.deepcopy(previous)
    package.update(date=run_date,batch_id=plan['batch_id'])
    package.pop('rendered_sources',None)  # Never freeze an earlier finished design.
    package.pop('background_source',None);package.pop('background_sources',None)
    package.update(seal_photos(prepared,metadata=True))
    validate(package)
    from .cli import fit_check, stage_content
    fit_check(package);stage_content(package,root=ROOT)
    result={'project':PROJECT,'mode':'preview','date':run_date,'run_date':run_date,
            'status':'reviewed content staged privately','batch_target':'none',
            'batch_id':plan['batch_id'],'cleanup_batch_id':None,
            'source_batch_id':source_batch_id,'backgrounds_reused':True,
            'target_cefr':package.get('bosnian_level'),
            'publication':'nothing published by preparation'}
    write_json(ROOT/'build/preparation-result.json',result)
    print(json.dumps(result,indent=2))
    return result

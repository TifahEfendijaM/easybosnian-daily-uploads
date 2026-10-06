"""Render the reviewed candidate, attempt publishers, save history on confirmed feed."""
import os
from .artwork import artwork
from .buffer import publish_tiktok
from .core import ROOT, require_publishing, today, verify_repository, write_json
from .facebook import publish_facebook
from .facebook_stories import publish_facebook_stories
from .http import redact
from .notify import failure
from .pipeline import publish_instagram
from .stories import publish_stories
from .store import Store
from .validate import validate
from .replacement import cleanup, cleanup_day, recorder
from .batches import BATCH_ID, output_key


def daily(date=None,mode='preview',batch_id=None,replace=True,cleanup_all=False,cleanup_batch_ids=None,prune_history_ids=None,package=None):
    if mode not in ('verify','preview','daily'): raise ValueError('Mode must be verify, preview or daily')
    if mode=='verify':
        from .readiness import check_infrastructure
        return check_infrastructure()
    verify_repository(remote=True);date=date or today();stage='storage'
    try:
        if mode=='daily': require_publishing()
        store=Store();package=package if package is not None else store.content(batch_id or date)
        if package.get('batch_id'):store.use_content(package)
        if batch_id and package.get('batch_id')!=batch_id:raise ValueError('Reviewed content has a different batch identity')
        if batch_id and package['date']!=date:raise ValueError('Reviewed content has a different content date')
        date=package['date'];key=output_key(package);stage='validation'
        if cleanup_all:
            targets=cleanup_batch_ids;prune=prune_history_ids
            if (not isinstance(targets,list) or not isinstance(prune,list)
                    or any(not isinstance(value,str) or not BATCH_ID.fullmatch(value) for value in targets+prune)
                    or len(set(targets))!=len(targets) or len(set(prune))!=len(prune)
                    or key in targets or not set(prune).issubset(targets)):
                raise ValueError('Invalid all-today cleanup scope')
        elif cleanup_batch_ids or prune_history_ids:raise ValueError('Multiple-batch cleanup requires all_today')
        # Novelty was checked against all history at trusted preparation. Independent
        # batches may deliberately reuse terms; keep full schema/editorial/secrecy checks.
        validate(package)
        if mode=='daily' and os.getenv('GITHUB_RUN_URL') and os.getenv('EASYBOSNIAN_PREPARED_ARTWORK')!='true':
            try:
                from .success_report import content_data
                write_json(ROOT/'build'/key/'report-source.json',content_data(package,os.environ['GITHUB_RUN_URL']))
            except Exception:
                print('::warning::Report metadata could not be captured; publication continues independently')
        stage='rendering';assets=artwork(store,package,expose=mode=='daily',
            require_prepared=os.getenv('EASYBOSNIAN_PREPARED_ARTWORK')=='true')
    except Exception as error:
        stage=getattr(error,'stage',None) or stage
        print(failure(date,stage,error,'nothing published by this run',os.getenv('GITHUB_RUN_URL')))
        raise RuntimeError('Daily run failed before publication at '+stage) from None
    if mode=='preview':
        result={'batch':date,'batch_id':package.get('batch_id'),'status':'unpublished preview','published':False}
        write_json(ROOT/'build'/key/'result.json',result);return result
    results={};failed=[];cleanup_warnings=[];history_warnings=[];history_cleanup=None
    history_saved=False;history_save_attempted=False
    operations=[('instagram',lambda:publish_instagram(package,assets,record=recorder(store,key,'instagram')))]
    for name,flag,publisher in [('facebook','FACEBOOK_POSTING_ENABLED',publish_facebook),('tiktok','TIKTOK_POSTING_ENABLED',publish_tiktok)]:
        if os.getenv(flag)=='true': operations.append((name,lambda fn=publisher,platform=name:fn(package,assets,record=recorder(store,key,platform))))
        else: results[name]={'status':'disabled','published':False}
    for name,operation in operations:
        try:
            if cleanup_all:
                removed,errors=cleanup_day(store,cleanup_batch_ids,date,name)
                cleanup_warnings.extend((name,error) for error in errors)
            else:removed=cleanup(store,key,name) if replace else {'status':'skipped; additional independent batch','removed':0}
        except Exception as error:
            removed={'status':'failed; new publication will still be attempted',
                     'error':redact(error), 'prior_content':'may remain or be partly removed'}
            cleanup_warnings.append((name, error))
            print(name+' replacement cleanup failed; continuing with independently verified publishing')
        try:
            results[name]=operation();results[name]['replacement_cleanup']=removed
            if results[name].get('published') is True and not history_save_attempted:
                # Persist only after a feed publication is actually confirmed.
                # A later platform/Story failure must not lose used vocabulary.
                history_save_attempted=True
                try:
                    store.save_content(package,preserve_artwork=True);history_saved=True
                except Exception as error:
                    failed.append('published content history');history_warnings.append(error)
                if history_saved and cleanup_all:
                    history_cleanup={'removed':0,'already_absent':0,'targeted':len(prune_history_ids)}
                    for old_id in prune_history_ids:
                        try:
                            require_publishing()
                            deleted=store.delete_content(old_id,date)
                            history_cleanup['removed' if deleted['removed'] else 'already_absent']+=1
                        except Exception as error:history_warnings.append(error)
                    history_cleanup['status']='failed; earlier history may remain' if history_warnings else 'earlier current-date history removed'

        except Exception as error:
            # Publishers already write their artifact and private failure issue.
            failed.append(name);results[name]={'status':'failed; inspect platform result artifact','error':redact(error),'published':False,'replacement_cleanup':removed}
    if os.getenv('INSTAGRAM_STORIES_ENABLED')=='true' and results['instagram'].get('published'):
        try: results['instagram_stories']=publish_stories(store,package,assets,record=recorder(store,key,'instagram'))
        except Exception as error:
            failed.append('instagram_stories');results['instagram_stories']={'status':'failed; inspect Story result artifact','error':redact(error),'published':False}
    else: results['instagram_stories']={'status':'disabled or Instagram feed publication not confirmed in this run','published':False}
    if os.getenv('FACEBOOK_STORIES_ENABLED')=='true' and results['facebook'].get('published'):
        try: results['facebook_stories']=publish_facebook_stories(store,package,assets,record=recorder(store,key,'facebook'))
        except Exception as error:
            failed.append('facebook_stories');results['facebook_stories']={'status':'failed; inspect Story result artifact','error':redact(error),'published':False}
    else: results['facebook_stories']={'status':'disabled or Facebook feed publication not confirmed in this run','published':False}
    results['tiktok_stories']={'status':'manual upload required; Buffer integration publishes feed posts only','published':False}
    for name,error in cleanup_warnings:
        published = results[name].get('published') is True
        story_result = results.get(name+'_stories', {})
        publication = ('new feed publication confirmed' if published else 'new feed outcome unconfirmed; inspect its artifact')
        publication += '; '+('new Stories confirmed' if story_result.get('published') else 'new Stories not confirmed')
        print(failure(date,name+' replacement cleanup',error,publication+'; old content may remain; no automatic retry',os.getenv('GITHUB_RUN_URL')))
    for error in history_warnings:
        publication='; '.join(name+': '+('confirmed' if outcome.get('published') else 'not confirmed') for name,outcome in results.items())
        print(failure(date,'published content history',error,publication+'; inspect saved history; no automatic retry',os.getenv('GITHUB_RUN_URL')))
    if cleanup_warnings and os.getenv('GITHUB_STEP_SUMMARY'):
        from pathlib import Path
        with Path(os.environ['GITHUB_STEP_SUMMARY']).open('a',encoding='utf-8') as summary:
            summary.write('\nReplacement cleanup warning: old content may remain. Cleanup failures did not block new publication.\n')
            for name,_ in cleanup_warnings:
                summary.write('- '+name+': '+('new feed confirmed' if results[name].get('published') else 'new feed unconfirmed; inspect its artifact')+'\n')
    outcome={'batch':date,'batch_id':package.get('batch_id'),'platforms':results,'history_saved':history_saved}
    if history_cleanup:outcome['history_cleanup']=history_cleanup
    write_json(ROOT/'build'/key/'platforms-result.json',outcome)
    if failed: raise RuntimeError('Daily run failed for: '+', '.join(failed))
    return results

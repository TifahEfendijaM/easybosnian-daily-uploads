"""Read today's history, render once, then attempt each enabled publisher."""
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
from .replacement import cleanup, recorder


def daily(date=None,mode='preview'):
    if mode not in ('verify','preview','daily'): raise ValueError('Mode must be verify, preview or daily')
    if mode=='verify':
        from .readiness import check_infrastructure
        return check_infrastructure()
    verify_repository(remote=True);date=date or today();stage='storage'
    try:
        if mode=='daily': require_publishing()
        store=Store();package=store.content(date);stage='validation';validate(package,store.history())
        stage='rendering';assets=artwork(store,package,expose=mode=='daily')
    except Exception as error:
        stage=getattr(error,'stage',None) or stage
        print(failure(date,stage,error,'nothing published by this run',os.getenv('GITHUB_RUN_URL')))
        raise RuntimeError('Daily run failed before publication at '+stage) from None
    if mode=='preview':
        result={'batch':date,'status':'unpublished preview','published':False}
        write_json(ROOT/'build'/date/'result.json',result);return result
    results={};failed=[];cleanup_warnings=[]
    operations=[('instagram',lambda:publish_instagram(package,assets,record=recorder(store,date,'instagram')))]
    for name,flag,publisher in [('facebook','FACEBOOK_POSTING_ENABLED',publish_facebook),('tiktok','TIKTOK_POSTING_ENABLED',publish_tiktok)]:
        if os.getenv(flag)=='true': operations.append((name,lambda fn=publisher,platform=name:fn(package,assets,record=recorder(store,date,platform))))
        else: results[name]={'status':'disabled','published':False}
    for name,operation in operations:
        try:
            removed=cleanup(store,date,name)
        except Exception as error:
            removed={'status':'failed; new publication will still be attempted',
                     'error':redact(error), 'prior_content':'may remain or be partly removed'}
            cleanup_warnings.append((name, error))
            print(name+' replacement cleanup failed; continuing with independently verified publishing')
        try:
            results[name]=operation();results[name]['replacement_cleanup']=removed
        except Exception as error:
            # Publishers already write their artifact and private failure issue.
            failed.append(name);results[name]={'status':'failed; inspect platform result artifact','error':redact(error),'published':False,'replacement_cleanup':removed}
    if os.getenv('INSTAGRAM_STORIES_ENABLED')=='true' and results['instagram'].get('published'):
        try: results['instagram_stories']=publish_stories(store,package,assets,record=recorder(store,date,'instagram'))
        except Exception as error:
            failed.append('instagram_stories');results['instagram_stories']={'status':'failed; inspect Story result artifact','error':redact(error),'published':False}
    else: results['instagram_stories']={'status':'disabled or Instagram feed publication not confirmed in this run','published':False}
    if os.getenv('FACEBOOK_STORIES_ENABLED')=='true' and results['facebook'].get('published'):
        try: results['facebook_stories']=publish_facebook_stories(store,package,assets,record=recorder(store,date,'facebook'))
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
    if cleanup_warnings and os.getenv('GITHUB_STEP_SUMMARY'):
        from pathlib import Path
        with Path(os.environ['GITHUB_STEP_SUMMARY']).open('a',encoding='utf-8') as summary:
            summary.write('\nReplacement cleanup warning: old content may remain. Cleanup failures did not block new publication.\n')
            for name,_ in cleanup_warnings:
                summary.write('- '+name+': '+('new feed confirmed' if results[name].get('published') else 'new feed unconfirmed; inspect its artifact')+'\n')
    write_json(ROOT/'build'/date/'platforms-result.json',{'batch':date,'platforms':results})
    if failed: raise RuntimeError('Daily run failed for: '+', '.join(failed))
    return results

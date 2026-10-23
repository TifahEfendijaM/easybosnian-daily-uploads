import json
import os
from pathlib import Path
from easybosnian.visual_diagnostics import safe_rejection, rendering_provenance
from easybosnian.success_report import visual_summary
from easybosnian.batches import output_key

context_path=Path('build/preparation-result.json')
level_summary=''
if context_path.is_file():
    level=json.loads(context_path.read_text()).get('target_cefr')
    if level in ('A1','A2','B1','B2','C1','C2'):level_summary=f'\nRun difficulty target: **{level}** (retained words keep their individual levels).\n'
text='This workflow has no confirmed publication result. Inspect failed steps and diagnostics.\n'
results=list(Path('build').glob('*/result.json'))
if results:
    r=json.loads(results[0].read_text())
    text=f"Batch: {r['batch']}\n\nStatus: **{r['status']}**\n"
    if r.get('permalink'): text+=f"\nPublication: {r['permalink']}\n"
if Path('build/failure.txt').exists(): text+='\n'+Path('build/failure.txt').read_text()
platforms=list(Path('build').glob('*/platforms-result.json'))
if platforms:
    all_results=json.loads(platforms[0].read_text())
    text=f"Content date: {all_results['batch']}\n\nBatch ID: {all_results.get('batch_id','legacy date')}\n\n"
    for platform,result in all_results['platforms'].items():
        text+=f"- **{platform}**: {result['status']}\n"
        if result.get('permalink'): text+=f"  Publication: {result['permalink']}\n"
        if result.get('error'): text+=f"  Error: {result['error']}\n"
        if platform=='instagram' and result.get('poll'):
            text+='  Native Pitanje dana poll: '+result['poll']['status']+'\n'
        cleanup=result.get('replacement_cleanup',{})
        if cleanup.get('scope')=='all_today':text+=f"  All-today cleanup: {cleanup['status']}; {cleanup['removed']} removed, {cleanup['already_absent']} already absent\n"
        elif cleanup.get('status'):text+='  Replacement cleanup: '+cleanup['status']+'\n'
        if cleanup.get('error'):text+='  Cleanup error: '+cleanup['error']+'\n'
        diagnostics=([cleanup['diagnostic']] if cleanup.get('diagnostic') else [])+cleanup.get('failures',[])
        for diagnostic in diagnostics:
            if diagnostic.get('error'):text+='  Cleanup batch error: '+diagnostic['error']+'\n'
            if diagnostic.get('operation'):
                text+=f"  Cleanup stopped at {diagnostic['kind']}/{diagnostic['operation']}; {diagnostic['removed']} confirmed removed, {diagnostic['already_absent']} already absent. Remaining cleanup was not completed.\n"
    if 'history_saved' in all_results:
        text+='\nPublished content history: '+('saved after confirmed feed publication' if all_results['history_saved'] else 'not saved; inspect publication/history failures')+'\n'
    if all_results.get('history_cleanup'):
        history=all_results['history_cleanup']
        text+=f"\nAll-today history: {history['status']}; {history['removed']} batches removed\n"
placements=list(Path('build').glob('*/image-placement-result.json'))
if placements:
    placement=json.loads(placements[0].read_text())
    text+='\nFeed text placement: '+placement['status']+'\n'
    text+='Recent design history: '+placement.get('recent_design_context','unknown')+'; accepted runs supplied: '+str(placement.get('recent_design_runs','unknown'))+'\n'
    for kind,result in placement['cards'].items():
        provenance=rendering_provenance(result,placement['status'])
        text+='- **'+kind+'**. Placement: '+result['position']+'\n'
        for label,key in (('Layout','layout'),('Palette','palette')):
            outcome=provenance[key]
            text+='  '+label+' source: '+outcome['source']+' — '+outcome['reason']+'\n'
        if result.get('rejection'):
            rejection=safe_rejection(result['rejection'])
            text+='  Pillow rejection before repair/recovery: '+rejection['reason']+'\n'
            text+='\n<details><summary>'+kind+' — rejected approved rendering parameters</summary>\n\n```json\n'+json.dumps(rejection['proposal'],ensure_ascii=False,indent=2)+'\n```\n\n</details>\n\n'
text+=level_summary
console_text=text  # Keep reviewed prompts/design detail in the private Summary, not step logs.
sources=list(Path('build').glob('*/report-source.json'))
if sources:
    source=json.loads(sources[0].read_text())
    try:
        matching=Path('build')/output_key(source)/'image-placement-result.json'
        placement=json.loads(matching.read_text()) if matching.is_file() else None
        text+=visual_summary(source,placement)
    except (ValueError,KeyError,TypeError):
        text+='\nImage design details unavailable: report identity or approved metadata validation failed.\n'
        try:text+=visual_summary(source)
        except (ValueError,KeyError,TypeError):
            text+='\nExact prompt details unavailable: report identity validation failed.\n'
if os.getenv('GITHUB_STEP_SUMMARY'):
    with open(os.environ['GITHUB_STEP_SUMMARY'],'a') as f: f.write(text)
print(console_text)

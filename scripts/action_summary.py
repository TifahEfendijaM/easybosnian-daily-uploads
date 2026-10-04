import json
import os
from pathlib import Path

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
        cleanup=result.get('replacement_cleanup',{})
        if cleanup.get('scope')=='all_today':text+=f"  All-today cleanup: {cleanup['status']}; {cleanup['removed']} removed, {cleanup['already_absent']} already absent\n"
    if all_results.get('history_cleanup'):
        history=all_results['history_cleanup']
        text+=f"\nAll-today history: {history['status']}; {history['removed']} batches removed\n"
if os.getenv('GITHUB_STEP_SUMMARY'):
    with open(os.environ['GITHUB_STEP_SUMMARY'],'a') as f: f.write(text)
print(text)

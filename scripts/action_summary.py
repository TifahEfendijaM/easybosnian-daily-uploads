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
    text=f"Batch: {all_results['batch']}\n\n"
    for platform,result in all_results['platforms'].items():
        text+=f"- **{platform}**: {result['status']}\n"
        if result.get('permalink'): text+=f"  Publication: {result['permalink']}\n"
        if result.get('error'): text+=f"  Error: {result['error']}\n"
if os.getenv('GITHUB_STEP_SUMMARY'):
    with open(os.environ['GITHUB_STEP_SUMMARY'],'a') as f: f.write(text)
print(text)

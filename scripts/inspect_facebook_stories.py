"""Read provider metadata for only today's recorded Facebook Stories; never post."""
from easybosnian.core import ROOT, today, write_json
from easybosnian.meta import Facebook
from easybosnian.store import Store


def main():
    date=today();recorded=[x for x in Store().publications(date) if x['platform']=='facebook' and x['kind']=='story']
    facebook=Facebook();facebook.verify_page()
    if any(x['account_id']!=facebook.page_id for x in recorded):raise ValueError('Recorded Story belongs to a different Page')
    expected={x['object_id'] for x in recorded};stories=[];after=None
    for _ in range(50):
        result=facebook.stories(after)
        if not isinstance(result.get('data'),list):raise ValueError('Invalid Facebook Stories response')
        stories.extend(result['data'])
        if not result.get('paging',{}).get('next'):break
        cursor=result.get('paging',{}).get('cursors',{}).get('after')
        if not cursor or cursor==after:raise ValueError('Incomplete Facebook Stories pagination')
        after=cursor
    else:raise ValueError('Facebook Stories pagination exceeded the bound')
    safe={'batch':date,'nothing_published_or_deleted':True,'recorded_story_ids':sorted(expected),
          'returned_fields':sorted({k for s in stories for k in s}),
          'returned_post_ids':[str(s.get('post_id','')) for s in stories],
          'matching_stories':[{k:s.get(k) for k in ('id','post_id','media_id','media_type','status','url')} for s in stories if str(s.get('post_id')) in expected or str(s.get('id')) in expected]}
    write_json(ROOT/'build'/date/'facebook-stories-inspection-result.json',safe)
    import json
    print(json.dumps(safe))


if __name__=='__main__':main()

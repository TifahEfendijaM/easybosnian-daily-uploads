"""Bounded local research reads; never a history store, summary or API client."""
import argparse
import copy
import json

from .core import PROJECT, ROOT, read_json

PAGE_BYTES = 8000
# Historical audit paperwork is not teaching content. Keep unknown fields, all
# semantic metadata/copy and the selected previous package in full. The original
# context remains unchanged for validation, exact retention and optional reads.
HISTORICAL_STORAGE = ('sources', 'rendered_sources', 'background_source', 'background_sources')
HISTORICAL_AUDIT = ('standard_bosnian_checked', 'sources_checked', 'semantic_history_checked',
                    'no_answer_leak_checked', 'language_policy_checked', 'history_checked_at',
                    'reviewed_at', 'reviewer', 'notes')


def review_context(context):
    result = copy.deepcopy(context)
    for row in result['history']['days']:
        content = row.get('content')
        if not isinstance(content, dict):
            continue
        for key in HISTORICAL_STORAGE:
            content.pop(key, None)
        review = content.get('private_review')
        if isinstance(review, dict):
            for key in HISTORICAL_AUDIT:
                review.pop(key, None)
    return result


def context_pages(context, *, full=False):
    # Bound UTF-8 bytes, not line/row counts. Preserve Bosnian letters and split
    # even an unusually long field without cutting a Unicode code point.
    document = json.dumps(context if full else review_context(context),
                          ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    pages = []
    start = 0
    while start < len(document):
        end = min(start+PAGE_BYTES, len(document))
        while end < len(document) and document[end] & 0xC0 == 0x80:
            end -= 1
        pages.append(document[start:end].decode('utf-8'))
        start = end
    return pages



def context_index(context):
    return {'history_batches': len(context['history']['days']),
            'review_pages': len(context_pages(context)),
            'full_pages': len(context_pages(context, full=True)),
            'page_bytes': PAGE_BYTES,
            'required_read': 'Every review page, in order; full pages for historical audit details if needed.'}


def reading_instructions(context):
    return ('\n\nTrusted local context index: '+json.dumps(context_index(context))+
            '\nRead with python -m easybosnian.research_context page N (one page per tool call, '
            'max_output_tokens=10000). Start at 1 and read through review_pages. '
            'Page boundaries may split JSON strings; continue on the next page. '
            'Do not cat the entire context or stop at a truncated tool response. '
            'The complete original stays at build/preparation-context.json for local validation; '
            'use page N --full for optional unabridged historical audit details.\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('index', 'page'))
    parser.add_argument('page', type=int, nargs='?')
    parser.add_argument('--full', action='store_true')
    args = parser.parse_args()
    context = read_json(ROOT/'build/preparation-context.json')
    if (not isinstance(context, dict) or not isinstance(context.get('history'), dict)
            or context['history'].get('project') != PROJECT
            or not isinstance(context['history'].get('days'), list)):
        parser.error('Invalid local research context')
    if args.action == 'index':
        if args.page is not None or args.full:
            parser.error('Use index without a page or --full')
        print(json.dumps(context_index(context)))
        return
    pages = context_pages(context, full=args.full)
    if args.page is None or not 1 <= args.page <= len(pages):
        parser.error('Choose a page from 1 through '+str(len(pages)))
    print(('FULL' if args.full else 'REVIEW')+' CONTEXT PAGE '+str(args.page)+'/'+str(len(pages)))
    print(pages[args.page-1])
    print('END PAGE '+str(args.page)+(' — read page '+str(args.page+1)+' next' if args.page < len(pages) else ' — final page'))


if __name__ == '__main__':
    main()

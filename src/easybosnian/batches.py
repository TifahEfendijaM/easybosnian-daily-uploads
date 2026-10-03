"""Content identity and creation order, without publication state or retry machinery."""
import re
from datetime import date as calendar_date, datetime, timezone
from uuid import uuid4

BATCH_ID=re.compile(r'(?:b-[a-f0-9]{32}|legacy-\d{4}-\d{2}-\d{2})\Z')


def identity(record):
    return record.get('batch_id') or record['content'].get('batch_id') or 'legacy-'+record['date']


def creation_order(record):
    # Migrated legacy timestamps are estimates; live creation time comes from D1.
    stamp=record.get('created_at') or record['date']+'T00:00:00Z'
    moment=datetime.fromisoformat(stamp.replace('Z','+00:00'))
    if moment.tzinfo is None: raise ValueError('Batch creation time needs a timezone')
    return moment.astimezone(timezone.utc),record.get('created_order',0),identity(record)


def latest_record(history,run_date):
    if calendar_date.fromisoformat(run_date).isoformat()!=run_date:raise ValueError('Invalid Sarajevo run date')
    complete=[]
    for record in history['days']:
        content=record.get('content')
        if not isinstance(content,dict) or content.get('schema_version')!=1:continue
        date=record['date']
        if calendar_date.fromisoformat(date).isoformat()!=date or content.get('date')!=date:
            raise ValueError('Saved batch date differs from its history row')
        if not BATCH_ID.fullmatch(identity(record)):raise ValueError('Invalid saved batch identity')
        if date<=run_date:complete.append(record)
    return max(complete,key=creation_order,default=None)


def plan_batch(history,run_date,target='latest'):
    if target not in ('latest','none','today'):raise ValueError('Batch target must be latest or none')
    previous=latest_record(history,run_date)
    replace=target=='latest' and previous is not None
    return {'batch_id':identity(previous) if replace else 'b-'+uuid4().hex,
            'date':previous['date'] if replace else run_date,
            'source_batch_id':identity(previous) if previous else None,
            'cleanup_batch_id':identity(previous) if replace else None}


def output_key(package):
    key=package.get('batch_id') or package['date']
    if not BATCH_ID.fullmatch(key) and not re.fullmatch(r'\d{4}-\d{2}-\d{2}',key):
        raise ValueError('Invalid batch output identity')
    return key

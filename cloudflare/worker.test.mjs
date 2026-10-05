import test from 'node:test';
import assert from 'node:assert/strict';
import worker,{PROJECT,REPO,dailyPreparationDispatch,dispatchPreparation} from './worker.mjs';

function dispatchFixture() {
  const records=new Map(),calls=[];
  const env={PROJECT_ID:PROJECT,GITHUB_REPOSITORY:REPO,GITHUB_DISPATCH_TOKEN:'private-test-token',PREPARATION_DISPATCH_ENABLED:'true',DB:{prepare(sql){
    return {bind(...args){this.args=args;return this;},first:async()=>({value:JSON.stringify({daily_authorized:true})}),
      async run(){
        if(sql.startsWith('INSERT')) {
          const [date,scheduled_at,status]=this.args;
          if(records.has(date)) return {meta:{changes:0}};
          records.set(date,{scheduled_at,status});return {meta:{changes:1}};
        }
        const [status,http_status,date]=this.args;Object.assign(records.get(date),{status,http_status});return {meta:{changes:1}};
      }};
  }}};
  const fetch=async(url,options={})=>{
    // Workers supports manual/follow, and credentials must never follow redirects.
    assert.equal(options.redirect,'manual');
    calls.push({url,options});
    if(url==='https://api.github.com/repos/'+REPO) return Response.json({full_name:REPO,private:true,default_branch:'main'});
    assert.equal(url,'https://api.github.com/repos/'+REPO+'/actions/workflows/preparation.yml/dispatches');
    return new Response(null,{status:204});
  };
  return {env,records,calls,fetch};
}

test('both UTC candidates select one 05:00 Sarajevo dispatch, including DST transition days',async t=>{
  const fixture=dispatchFixture();t.mock.method(globalThis,'fetch',fixture.fetch);
  for(const [date,summer] of [['2026-07-01',true],['2026-12-01',false],['2026-03-29',true],['2026-10-25',false]]) {
    for(const hour of ['03','04']) await dailyPreparationDispatch(fixture.env,new Date(date+'T'+hour+':00:00Z'));
    assert.equal(fixture.records.get(date).status,'accepted');
    assert.equal(fixture.records.get(date).scheduled_at,date+(summer?'T03':'T04')+':00:00.000Z');
  }
  const posts=fixture.calls.filter(c=>c.options.method==='POST');assert.equal(posts.length,4);
  for(const {options} of posts) {
    assert.deepEqual(JSON.parse(options.body),{ref:'main',inputs:{mode:'daily',batch_target:'none'}});
    assert.equal(options.headers.Accept,'application/vnd.github+json');
    assert.equal(options.headers.Authorization,'Bearer private-test-token');
    assert.equal(options.headers['X-GitHub-Api-Version'],'2022-11-28');
    assert.equal(options.headers['User-Agent'],PROJECT);
  }
});

test('duplicate or concurrent cron delivery cannot send a second request',async t=>{
  const fixture=dispatchFixture();t.mock.method(globalThis,'fetch',fixture.fetch);
  const when=new Date('2026-07-01T03:00:00Z');
  await Promise.all([dailyPreparationDispatch(fixture.env,when),dailyPreparationDispatch(fixture.env,when)]);
  await dailyPreparationDispatch(fixture.env,when);
  assert.equal(fixture.calls.filter(c=>c.options.method==='POST').length,1);
});

test('non-204 and network failures remain claimed and fail without retry',async t=>{
  for(const failure of [200,401,403,404,422,429,500,'network']) {
    const fixture=dispatchFixture();
    const mock=t.mock.method(globalThis,'fetch',async(url,options)=>{
      if(options?.method!=='POST') return fixture.fetch(url,options);
      fixture.calls.push({url,options});
      if(failure==='network') throw Error('private provider details must not enter logs');
      return new Response(null,{status:failure});
    });
    const when=new Date('2026-07-01T03:00:00Z');
    await assert.rejects(dailyPreparationDispatch(fixture.env,when),/no automatic retry/);
    await dailyPreparationDispatch(fixture.env,when);
    assert.equal(fixture.calls.filter(c=>c.options.method==='POST').length,1);
    const record=fixture.records.get('2026-07-01');
    assert.equal(record.status,[200,500,'network'].includes(failure)?'uncertain':'failed');
    assert.equal(record.http_status,failure==='network'?null:failure);
    mock.mock.restore();
  }
});

test('disabled scheduler and inactive hours never dispatch',async t=>{
  const fixture=dispatchFixture();t.mock.method(globalThis,'fetch',fixture.fetch);
  await dailyPreparationDispatch(fixture.env,new Date('2026-07-01T10:07:00Z'));
  await dailyPreparationDispatch(fixture.env,new Date('2026-07-01T10:00:00Z')); // former 12:00 local start stays inactive
  await dailyPreparationDispatch(fixture.env,new Date('2026-07-01T08:00:00Z')); // former 10:00 local start stays inactive
  await dailyPreparationDispatch(fixture.env,new Date('2026-07-01T11:30:00Z')); // former 13:30 local start stays inactive
  await dailyPreparationDispatch({...fixture.env,PREPARATION_DISPATCH_ENABLED:'false'},new Date('2026-07-01T03:00:00Z'));
  assert.equal(fixture.calls.length,0);assert.equal(fixture.records.size,0);
});

test('wrong repository, public visibility and missing secret fail before dispatch',async t=>{
  const fixture=dispatchFixture();
  const mocked=t.mock.method(globalThis,'fetch',fixture.fetch);
  await assert.rejects(dispatchPreparation({...fixture.env,GITHUB_REPOSITORY:'wrong/repo'},'daily'),/mismatch/);
  await assert.rejects(dispatchPreparation({...fixture.env,GITHUB_DISPATCH_TOKEN:''},'daily'),/missing/);
  assert.equal(fixture.calls.length,0);
  mocked.mock.restore();
  t.mock.method(globalThis,'fetch',async()=>Response.json({full_name:REPO,private:false,default_branch:'main'}));
  await assert.rejects(dispatchPreparation(fixture.env,'daily'),/exact private repository/);
});

test('manual Worker verification uses its stored token but cannot publish or consume a daily claim',async t=>{
  const fixture=dispatchFixture();fixture.env.ADMIN_TOKEN='private-admin';
  t.mock.method(globalThis,'fetch',fixture.fetch);
  const url='https://example.test/v1/scheduler/verify';
  assert.equal((await worker.fetch(new Request(url,{method:'POST'}),fixture.env)).status,401);
  const result=await worker.fetch(new Request(url,{method:'POST',headers:{Authorization:'Bearer private-admin'}}),fixture.env);
  assert.equal(result.status,200);assert.equal((await result.json()).github_status,204);
  assert.equal(fixture.records.size,0);
  assert.deepEqual(JSON.parse(fixture.calls.find(c=>c.options.method==='POST').options.body),{ref:'main',inputs:{mode:'verify'}});
});

test('repository redirects fail before sending a dispatch or following the destination',async t=>{
  const fixture=dispatchFixture();
  t.mock.method(globalThis,'fetch',async(url,options)=>{
    fixture.calls.push({url,options});
    assert.equal(options.redirect,'manual');
    return new Response(null,{status:301,headers:{Location:'https://example.test/redirect'}});
  });
  await assert.rejects(dispatchPreparation(fixture.env,'verify'),/repository check HTTP 301/);
  assert.equal(fixture.calls.length,1);
  assert.equal(fixture.calls[0].url,'https://api.github.com/repos/'+REPO);
});

test('late delivery uses scheduledTime and verify never consumes a daily claim',async t=>{
  const fixture=dispatchFixture();t.mock.method(globalThis,'fetch',fixture.fetch);
  t.mock.timers.enable({apis:['Date'],now:new Date('2026-07-01T03:05:00Z')});
  let pending;await worker.scheduled({scheduledTime:new Date('2026-07-01T03:00:00Z').getTime()},fixture.env,{waitUntil(p){pending=p;}});await pending;
  assert.equal(fixture.records.get('2026-07-01').status,'accepted');
});

test('private history requires authorization and no watchdog/config/state endpoints survive',async()=>{
  const env={PROJECT_ID:PROJECT,ADMIN_TOKEN:'private',DB:{prepare(){throw Error('Must not access DB');}}};
  assert.equal((await worker.fetch(new Request('https://example.test/v1/history'),env)).status,401);
  for(const path of ['/v1/config','/v1/queue','/v1/monitoring/check','/v1/batches/2026-10-03']) {
    assert.equal((await worker.fetch(new Request('https://example.test'+path,{headers:{Authorization:'Bearer private'}}),env)).status,404);
  }
  assert.equal((await worker.fetch(new Request('https://example.test/privacy'),env)).status,200);
});

const A='b-'+'a'.repeat(32),B='b-'+'b'.repeat(32),C='b-'+'c'.repeat(32);
function content(id,date='2026-10-04',prompt='reviewed prompt') {
  return {project:PROJECT,schema_version:1,batch_id:id,date,theme:{name:'one',equivalence_keys:['one']},words:['a','b','c'].map(lemma=>({lemma,equivalence_keys:[lemma]})),cards:['quiz','lesson','word'].map(kind=>({kind,background_prompt:prompt})),private_review:{standard_bosnian_checked:true,sources_checked:true,semantic_history_checked:true,no_answer_leak_checked:true}};
}
function batchFixture() {
  const history=new Map(),ids=new Map(),kv=new Map(),deleted=[];let nextOrder=0,generated=0;
  const env={PROJECT_ID:PROJECT,ADMIN_TOKEN:'private',DB:{prepare(sql){return {bind(...args){this.args=args;return this;},async first(){
    if(sql.includes('FROM history WHERE batch_id'))return history.get(this.args[0]) || null;
    if(sql.includes('FROM publication_ids WHERE platform'))return ids.get(this.args.join(':')) || null;
    throw Error('Unexpected first query');
  },async all(){
    if(sql.includes('FROM history')) {let rows=[...history.values()];if(sql.includes('WHERE date='))rows=rows.filter(x=>x.date===this.args[0]);rows.sort((a,b)=>a.created_at.localeCompare(b.created_at)||a.created_order-b.created_order);if(sql.includes('DESC'))rows.reverse();if(sql.includes('LIMIT 2'))rows=rows.slice(0,2);return {results:rows};}
    if(sql.includes('FROM publication_ids'))return {results:[...ids.values()].filter(x=>sql.includes('WHERE date=')?x.date===this.args[0]:x.batch_id===this.args[0])};
    throw Error('Unexpected list query');
  },async run(){
    if(sql.startsWith('INSERT INTO history')) {
      const [batch_id,date,created_at,theme_json,words_json,content_json]=this.args,old=history.get(batch_id);
      if(old && old.date!==date)return {meta:{changes:0}};
      history.set(batch_id,{batch_id,date,created_at:old?.created_at || created_at,created_order:old?.created_order || ++nextOrder,theme_json,words_json,content_json});
    } else if(sql.startsWith('INSERT INTO publication_ids')) {
      const [batch_id,date,platform,kind,object_id,account_id]=this.args,key=platform+':'+object_id;
      if(!ids.has(key))ids.set(key,{recorded_order:ids.size+1,batch_id,date,platform,kind,object_id,account_id});
    } else if(sql.startsWith('DELETE FROM history')) {
      const [batch_id,date]=this.args;if(history.get(batch_id)?.date!==date)return {meta:{changes:0}};history.delete(batch_id);
    } else if(sql.startsWith('DELETE FROM publication_ids')) {
      const [batch_id,platform,object_id]=this.args,key=platform+':'+object_id;if(ids.get(key)?.batch_id===batch_id)ids.delete(key);
    } else throw Error('Unexpected write query');
    return {meta:{changes:1}};
  }};}},IMAGES:{get:async key=>kv.get(key),delete:async key=>{deleted.push(key);kv.delete(key);},put:async(key,value,options)=>{assert.equal(options.expirationTtl,14*86400);kv.set(key,value);}},AI:{run:async(model,options)=>{generated++;assert.equal(model,'@cf/black-forest-labs/flux-1-schnell');assert.equal(options.steps,4);return {image:'image-'+options.prompt};}}};
  const send=(method,path,body)=>worker.fetch(new Request('https://example.test'+path,{method,headers:{Authorization:'Bearer private','Content-Type':'application/json'},...(body!==undefined?{body:JSON.stringify(body)}:{})}),env);
  const save=p=>send('PUT','/v1/history/batches/'+p.batch_id,p);
  return {env,history,ids,kv,deleted,send,save,get generated(){return generated;}};
}

test('same-date batches coexist; replacement preserves creation time and invalidates only its caches',async()=>{
  const f=batchFixture();assert.equal((await f.save(content(A))).status,200);assert.equal((await f.save(content(B))).status,200);
  const created=f.history.get(A).created_at;f.kv.set('private-ai:'+B+':quiz','other batch');
  const p=content(A);p.theme.name='replacement';assert.equal((await f.save(p)).status,200);
  assert.equal(f.history.size,2);assert.equal(f.history.get(A).created_at,created);assert.equal(f.kv.get('private-ai:'+B+':quiz'),'other batch');
  const history=await (await f.send('GET','/v1/history')).json();assert.equal(history.days.length,2);assert.equal(history.storage_version,2);
  p.private_review.sources_checked=false;assert.equal((await f.save(p)).status,409);
  assert.equal((await f.save(content(A,'2026-10-03'))).status,409);assert.equal(f.history.get(A).date,'2026-10-04');
});

test('date-bound history removal protects other dates/batches and retains unsupported or uncertain publication IDs',async()=>{
  const f=batchFixture();await f.save(content(A));await f.save(content(B));await f.save(content(C,'2026-10-03'));
  for(const [id,object_id] of [[A,'123'],[B,'456'],[C,'789']]) {
    await f.send('POST','/v1/publications/batches/'+id,{platform:'facebook',kind:'story',object_id,account_id:'42'});
    f.kv.set('private-ai:'+id+':quiz','background');
  }
  const path='/v1/history/batches/'+A;
  assert.equal((await worker.fetch(new Request('https://example.test'+path,{method:'DELETE',body:JSON.stringify({date:'2026-10-04'})}),f.env)).status,401);
  assert.equal((await f.send('DELETE',path,{date:'2026-10-03'})).status,409);assert.equal(f.history.size,3);
  assert.equal((await f.send('DELETE','/v1/history/2026-10-04',{date:'2026-10-04'})).status,409);
  assert.equal((await f.send('DELETE',path,{date:'2026-10-04',extra:true})).status,409);
  assert.equal((await f.send('DELETE',path,{date:'2026-10-04'})).status,200);
  assert.ok(!f.history.has(A));assert.ok(f.history.has(B));assert.ok(f.history.has(C));
  assert.ok(!f.kv.has('private-ai:'+A+':quiz'));assert.ok(f.kv.has('private-ai:'+B+':quiz'));assert.ok(f.kv.has('private-ai:'+C+':quiz'));
  assert.equal(f.ids.size,3);
  const kept=await (await f.send('GET','/v1/publications/dates/2026-10-04')).json();
  assert.deepEqual(kept.items.map(x=>x.batch_id),[A,B]);assert.equal(kept.date,'2026-10-04');
  assert.equal((await worker.fetch(new Request('https://example.test/v1/publications/dates/2026-10-04'),f.env)).status,401);
  assert.equal((await (await f.send('GET','/v1/publications/dates/2026-10-05')).json()).items.length,0);
});

test('FLUX prompt binding, cached background and private/public artwork are isolated by batch ID',async()=>{
  const f=batchFixture();await f.save(content(A,'2026-10-04','first prompt'));await f.save(content(B,'2026-10-04','second prompt'));
  const generate=(id,prompt)=>f.send('POST','/v1/generate',{batch_id:id,date:'2026-10-04',kind:'quiz',prompt});
  assert.equal((await generate(A,'second prompt')).status,409);assert.equal(f.generated,0);
  for(const [id,prompt] of [[A,'first prompt'],[B,'second prompt'],[A,'first prompt']])assert.equal((await generate(id,prompt)).status,200);
  assert.equal(f.generated,2);assert.notEqual(f.kv.get('private-ai:'+A+':quiz'),f.kv.get('private-ai:'+B+':quiz'));
  const jpeg=new Uint8Array(100);jpeg[0]=255;jpeg[1]=216;jpeg[2]=12;
  for(const id of [A,B]) {
    const result=await worker.fetch(new Request('https://example.test/v1/private/batches/'+id+'/quiz-card.jpg',{method:'PUT',headers:{Authorization:'Bearer private'},body:jpeg}),f.env);assert.equal(result.status,200);
    jpeg[2]++;
  }
  const one=await (await f.send('POST','/v1/expose/batches/'+A+'/quiz-card.jpg')).json(),two=await (await f.send('POST','/v1/expose/batches/'+B+'/quiz-card.jpg')).json();
  assert.notEqual(one.url,two.url);assert.match(one.url,/\/images\/[a-f0-9]{64}\.jpg$/);
  await f.save(content(A,'2026-10-04','replacement prompt'));
  assert.ok(f.kv.has('private:'+B+':quiz-card.jpg'));assert.ok(f.kv.has('public:'+new URL(two.url).pathname.split('/').pop().slice(0,-4)));
});

test('direct JPEG exposure never reads stale private KV and preserves exact bytes and TTL',async t=>{
  const f=batchFixture();await f.save(content(A));
  const read=t.mock.method(f.env.IMAGES,'get',async()=>null);
  const put=t.mock.method(f.env.IMAGES,'put',async(key,value,options)=>{
    assert.equal(options.expirationTtl,14*86400);f.kv.set(key,value);
  });
  for(const name of ['quiz-card.jpg','lesson-card.jpg','word-card.jpg','quiz-story.jpg','lesson-story.jpg','word-story.jpg']) {
    const bytes=new Uint8Array(100);bytes[0]=255;bytes[1]=216;bytes[2]=name.length;
    const result=await worker.fetch(new Request('https://example.test/v1/expose/batches/'+A+'/'+name,{method:'POST',headers:{Authorization:'Bearer private','Content-Type':'image/jpeg'},body:bytes}),f.env);
    assert.equal(result.status,200);const {url}=await result.json();assert.match(url,/^https:\/\/example.test\/images\/[a-f0-9]{64}\.jpg$/);
    const id=new URL(url).pathname.slice('/images/'.length,-4);
    assert.deepEqual(new Uint8Array(f.kv.get('public:'+id)),bytes);
  }
  assert.equal(read.mock.callCount(),0);assert.equal(put.mock.callCount(),6);assert.equal(f.generated,0);
});

test('exposure still checks authorization, batch scope, JPEG size/type and final-image names',async t=>{
  const f=batchFixture();await f.save(content(A));await f.save(content(B));
  const put=t.mock.method(f.env.IMAGES,'put',async()=>{throw Error('Must not store');});
  const jpeg=new Uint8Array(100);jpeg[0]=255;jpeg[1]=216;
  const send=(name,body=jpeg,headers={Authorization:'Bearer private','Content-Type':'image/jpeg'},id=A)=>worker.fetch(new Request('https://example.test/v1/expose/batches/'+id+'/'+name,{method:'POST',headers,body}),f.env);
  assert.equal((await send('quiz-card.jpg',jpeg,{})).status,401);
  assert.equal((await send('quiz-card.jpg',jpeg,undefined,C)).status,404);
  assert.equal((await send('quiz-background.jpg')).status,404);
  for(const bytes of [new Uint8Array(99),new Uint8Array(100),new Uint8Array(3_000_001)])assert.equal((await send('quiz-card.jpg',bytes)).status,400);
  assert.equal((await send('quiz-card.jpg',jpeg,{Authorization:'Bearer private','Content-Type':'application/json'})).status,400);
  assert.equal(put.mock.callCount(),0);
  // Empty-body compatibility reads legacy KV, but ambiguous dates still fail.
  const result=await f.send('POST','/v1/expose/batches/'+A+'/quiz-card.jpg');
  assert.equal(result.status,409);assert.equal((await result.json()).reason,'asset_not_visible');
  assert.equal((await f.send('POST','/v1/expose/2026-10-04/quiz-card.jpg')).status,409);
});

test('storage diagnostics never include provider exception prose or credentials and never repeat a write',async t=>{
  const f=batchFixture();await f.save(content(A));const logs=[];
  t.mock.method(console,'error',line=>logs.push(JSON.parse(line)));
  const put=t.mock.method(f.env.IMAGES,'put',async()=>{throw Error('secret-provider-details');});
  const jpeg=new Uint8Array(100);jpeg[0]=255;jpeg[1]=216;
  for(const [route,method,reason] of [['private','PUT','asset_write_failed'],['expose','POST','asset_exposure_failed']]) {
    const result=await worker.fetch(new Request('https://example.test/v1/'+route+'/batches/'+A+'/quiz-card.jpg',{method,headers:{Authorization:'Bearer private','Content-Type':'image/jpeg'},body:jpeg}),f.env);
    assert.equal(result.status,503);const body=await result.json();assert.equal(body.stage,'storage');assert.equal(body.reason,reason);
    assert.ok(!JSON.stringify(body).includes('secret-provider-details'));
  }
  assert.equal(put.mock.callCount(),2);assert.ok(!JSON.stringify(logs).includes('secret-provider-details'));
  assert.deepEqual(logs.map(x=>x.reason),['asset_write_failed','asset_exposure_failed']);
});

test('public availability checks keep negative responses uncached and bound KV cache lifetime',async t=>{
  const f=batchFixture(),key='a'.repeat(64),url='https://example.test/images/'+key+'.jpg';
  const read=t.mock.method(f.env.IMAGES,'get',async()=>null);
  const missing=await worker.fetch(new Request(url),f.env);assert.equal(missing.status,404);assert.equal(missing.headers.get('Cache-Control'),'no-store');
  assert.deepEqual(read.mock.calls[0].arguments,['public:'+key,{type:'arrayBuffer',cacheTtl:30}]);
  read.mock.restore();f.kv.set('public:'+key,new Uint8Array([255,216,1]).buffer);
  const ready=await worker.fetch(new Request(url),f.env);assert.equal(ready.status,200);
  assert.deepEqual(new Uint8Array(await ready.arrayBuffer()),new Uint8Array([255,216,1]));
  assert.equal(ready.headers.get('Content-Type'),'image/jpeg');
});

test('legacy date reads remain compatible; ambiguous date writes and generation refuse to guess',async()=>{
  const f=batchFixture(),legacy=content('legacy-2026-10-03','2026-10-03');
  await f.save(legacy);f.kv.set('private-ai:2026-10-03:quiz','legacy image');
  const old=await f.send('POST','/v1/generate',{date:'2026-10-03',kind:'quiz',prompt:'reviewed prompt'});assert.equal(old.status,200);assert.equal((await old.json()).image,'legacy image');
  await f.save(content(A,'2026-10-03'));
  assert.equal((await f.send('GET','/v1/history/2026-10-03')).status,200);
  assert.equal((await f.send('PUT','/v1/history/2026-10-03',legacy)).status,409);
  assert.equal((await f.send('GET','/v1/publications/2026-10-03')).status,409);
  assert.equal((await f.send('POST','/v1/generate',{date:'2026-10-03',kind:'quiz',prompt:'reviewed prompt'})).status,409);
  await f.save(legacy);assert.ok(f.deleted.includes('private-ai:2026-10-03:quiz'));
});

test('gate logs distinguish inactive delivery and disabled starts without secrets',async t=>{
  const fixture=dispatchFixture(),logs=[];
  t.mock.method(console,'log',value=>logs.push(JSON.parse(value)));
  await dailyPreparationDispatch(fixture.env,new Date('2026-10-03T10:00:00Z'));
  await dailyPreparationDispatch({...fixture.env,PREPARATION_DISPATCH_ENABLED:'false'},new Date('2026-10-03T03:00:00Z'));
  assert.deepEqual(logs.map(x=>x.decision),['outside_local_start','disabled']);
  assert.equal(logs[0].sarajevo_time,'2026-10-03 12:00');
  assert.equal(fixture.records.size,0);assert.equal(fixture.calls.length,0);
  assert.ok(!JSON.stringify(logs).includes(fixture.env.GITHUB_DISPATCH_TOKEN));
});

test('pre-claim scheduled failures are visible and do not reveal provider details',async t=>{
  const fixture=dispatchFixture(),logs=[];
  fixture.env.DB.prepare=()=>{throw Error('private provider details');};
  t.mock.method(console,'error',value=>logs.push(JSON.parse(value)));
  let pending;
  await worker.scheduled({scheduledTime:new Date('2026-10-03T03:00:00Z').getTime()},fixture.env,{waitUntil(p){pending=p;}});
  await assert.rejects(pending,/Scheduled preparation failed/);
  assert.deepEqual(logs,[{event:'preparation_cron_failed'}]);
  assert.equal(fixture.records.size,0);assert.equal(fixture.calls.length,0);
});

test('publication identifiers are protected and cleanup cannot cross batches on the same date',async()=>{
  const f=batchFixture();await f.save(content(A));await f.save(content(B));
  const path=id=>'/v1/publications/batches/'+id;
  const item={platform:'instagram',kind:'feed',object_id:'123',account_id:'42'};
  assert.equal((await worker.fetch(new Request('https://example.test'+path(A)),f.env)).status,401);
  assert.equal((await f.send('POST',path(A),item)).status,200);
  assert.equal((await f.send('POST',path(A),item)).status,200);
  assert.equal((await f.send('POST',path(B),item)).status,409);
  assert.equal((await f.send('POST',path(B),{...item,object_id:'456'})).status,200);
  assert.equal((await f.send('POST',path(C),{...item,object_id:'789'})).status,409);
  for(const change of [{object_id:'../../anything'},{account_id:'43'},{published:true}])assert.equal((await f.send('POST',path(A),{...item,...change})).status,409);
  let listed=await (await f.send('GET',path(A))).json();assert.equal(listed.items.length,1);assert.equal(listed.items[0].batch_id,A);
  assert.equal((await f.send('DELETE',path(B)+'/instagram/123')).status,200);assert.ok(f.ids.has('instagram:123'));
  await f.send('DELETE',path(A)+'/instagram/123');assert.ok(f.ids.has('instagram:456'));assert.equal(f.ids.size,1);
  await f.save(content(B));listed=await (await f.send('GET',path(B))).json();assert.equal(listed.items[0].object_id,'456');
});


test('generation failures expose only fixed stages and known codes without a second AI call',async t=>{
  const logs=[];t.mock.method(console,'error',line=>logs.push(JSON.parse(line)));
  for(const fault of ['cache_read_failed','ai_binding_missing','ai_call_failed','ai_image_missing','cache_write_failed']) {
    const f=batchFixture();await f.save(content(A));let calls=0;
    if(fault==='cache_read_failed')f.env.IMAGES.get=async()=>{throw Error('private cache token');};
    if(fault==='ai_binding_missing')delete f.env.AI;
    else f.env.AI.run=async()=>{calls++;if(fault==='ai_call_failed')throw Error('AiError: 3040: private prompt and token');return fault==='ai_image_missing'?{}:{image:'image'};};
    if(fault==='cache_write_failed')f.env.IMAGES.put=async()=>{throw Error('private cache token');};
    const r=await f.send('POST','/v1/generate',{batch_id:A,date:'2026-10-04',kind:'quiz',prompt:'reviewed prompt'});
    assert.equal(r.status,409);const value=await r.json();assert.equal(value.reason,fault);
    assert.equal(value.code,fault==='ai_call_failed'?3040:null);
    assert.equal(value.stage,'FLUX generation');assert.ok(calls<=1);
    assert.ok(!JSON.stringify(value).includes('private'));assert.ok(!JSON.stringify(logs).includes('private'));
  }
});

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

test('both UTC candidates select one 13:30 Sarajevo dispatch, including DST transition days',async t=>{
  const fixture=dispatchFixture();t.mock.method(globalThis,'fetch',fixture.fetch);
  for(const [date,summer] of [['2026-07-01',true],['2026-12-01',false],['2026-03-29',true],['2026-10-25',false]]) {
    for(const hour of ['11','12']) await dailyPreparationDispatch(fixture.env,new Date(date+'T'+hour+':30:00Z'));
    assert.equal(fixture.records.get(date).status,'accepted');
    assert.equal(fixture.records.get(date).scheduled_at,date+(summer?'T11':'T12')+':30:00.000Z');
  }
  const posts=fixture.calls.filter(c=>c.options.method==='POST');assert.equal(posts.length,4);
  for(const {options} of posts) {
    assert.deepEqual(JSON.parse(options.body),{ref:'main',inputs:{mode:'daily'}});
    assert.equal(options.headers.Accept,'application/vnd.github+json');
    assert.equal(options.headers.Authorization,'Bearer private-test-token');
    assert.equal(options.headers['X-GitHub-Api-Version'],'2022-11-28');
    assert.equal(options.headers['User-Agent'],PROJECT);
  }
});

test('duplicate or concurrent cron delivery cannot send a second request',async t=>{
  const fixture=dispatchFixture();t.mock.method(globalThis,'fetch',fixture.fetch);
  const when=new Date('2026-07-01T11:30:00Z');
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
    const when=new Date('2026-07-01T11:30:00Z');
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
  await dailyPreparationDispatch(fixture.env,new Date('2026-07-01T03:00:00Z')); // former 05:00 local start stays inactive
  await dailyPreparationDispatch({...fixture.env,PREPARATION_DISPATCH_ENABLED:'false'},new Date('2026-07-01T11:30:00Z'));
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
  t.mock.timers.enable({apis:['Date'],now:new Date('2026-07-01T11:35:00Z')});
  let pending;await worker.scheduled({scheduledTime:new Date('2026-07-01T11:30:00Z').getTime()},fixture.env,{waitUntil(p){pending=p;}});await pending;
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

test('same-date reviewed replacements are allowed and invalidate artwork caches',async()=>{
  const writes=[],deleted=[];
  const env={PROJECT_ID:PROJECT,ADMIN_TOKEN:'private',DB:{prepare(sql){assert.ok(sql.startsWith('INSERT INTO history'));return {bind(...args){writes.push(args);return this;},run:async()=>({meta:{changes:1}})};}},IMAGES:{delete:async key=>deleted.push(key)}};
  const p={project:PROJECT,schema_version:1,date:'2026-10-03',theme:{name:'one',equivalence_keys:['one']},words:['a','b','c'].map(lemma=>({lemma,equivalence_keys:[lemma]})),cards:['quiz','lesson','word'].map(kind=>({kind})),private_review:{standard_bosnian_checked:true,sources_checked:true,semantic_history_checked:true,no_answer_leak_checked:true}};
  const send=async()=>worker.fetch(new Request('https://example.test/v1/history/'+p.date,{method:'PUT',headers:{Authorization:'Bearer private','Content-Type':'application/json'},body:JSON.stringify(p)}),env);
  assert.equal((await send()).status,200);p.theme.name='replacement';assert.equal((await send()).status,200);
  assert.equal(writes.length,2);assert.equal(deleted.length,24);
  assert.ok(deleted.includes('private-ai:2026-10-03:quiz'));
  p.private_review.sources_checked=false;assert.equal((await send()).status,409);assert.equal(writes.length,2);
});

test('FLUX uses reviewed prompt and cache without a generation intent table',async()=>{
  const p={cards:[{kind:'quiz',background_prompt:'reviewed prompt'}]};let generated=0,saved;
  const env={PROJECT_ID:PROJECT,ADMIN_TOKEN:'private',DB:{prepare(sql){assert.ok(sql.includes('FROM history'));return {bind(){return this;},first:async()=>({content_json:JSON.stringify(p)})};}},IMAGES:{get:async()=>saved,put:async(key,value,options)=>{assert.equal(options.expirationTtl,14*86400);saved=value;}},AI:{run:async(model,options)=>{generated++;assert.equal(model,'@cf/black-forest-labs/flux-1-schnell');assert.equal(options.prompt,'reviewed prompt');return {image:'image-data'};}}};
  const send=async prompt=>worker.fetch(new Request('https://example.test/v1/generate',{method:'POST',headers:{Authorization:'Bearer private','Content-Type':'application/json'},body:JSON.stringify({date:'2026-10-03',kind:'quiz',prompt})}),env);
  assert.equal((await send('wrong')).status,409);assert.equal(generated,0);
  assert.equal((await send('reviewed prompt')).status,200);assert.equal((await send('reviewed prompt')).status,200);assert.equal(generated,1);
});

test('gate logs distinguish inactive delivery and disabled starts without secrets',async t=>{
  const fixture=dispatchFixture(),logs=[];
  t.mock.method(console,'log',value=>logs.push(JSON.parse(value)));
  await dailyPreparationDispatch(fixture.env,new Date('2026-10-03T10:30:00Z'));
  await dailyPreparationDispatch({...fixture.env,PREPARATION_DISPATCH_ENABLED:'false'},new Date('2026-10-03T11:30:00Z'));
  assert.deepEqual(logs.map(x=>x.decision),['outside_local_start','disabled']);
  assert.equal(logs[0].sarajevo_time,'2026-10-03 12:30');
  assert.equal(fixture.records.size,0);assert.equal(fixture.calls.length,0);
  assert.ok(!JSON.stringify(logs).includes(fixture.env.GITHUB_DISPATCH_TOKEN));
});

test('pre-claim scheduled failures are visible and do not reveal provider details',async t=>{
  const fixture=dispatchFixture(),logs=[];
  fixture.env.DB.prepare=()=>{throw Error('private provider details');};
  t.mock.method(console,'error',value=>logs.push(JSON.parse(value)));
  let pending;
  await worker.scheduled({scheduledTime:new Date('2026-10-03T11:30:00Z').getTime()},fixture.env,{waitUntil(p){pending=p;}});
  await assert.rejects(pending,/Scheduled preparation failed/);
  assert.deepEqual(logs,[{event:'preparation_cron_failed'}]);
  assert.equal(fixture.records.size,0);assert.equal(fixture.calls.length,0);
});

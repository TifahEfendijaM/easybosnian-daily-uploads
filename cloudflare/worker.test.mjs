import test from 'node:test';
import assert from 'node:assert/strict';
import worker,{canonical,reservationKeys,watchdog,PROJECT,REPO,publicationMonitoringReady,dailyPreparationDispatch,dispatchPreparation} from './worker.mjs';

test('public privacy page never reads private storage and does not open history',async()=>{
  const env={PROJECT_ID:PROJECT,ADMIN_TOKEN:'private',DB:{prepare(){throw Error('Privacy must not read private storage');}}};
  const get=await worker.fetch(new Request('https://example.test/privacy'),env);
  assert.equal(get.status,200);
  assert.match(get.headers.get('Content-Type'),/text\/html/);
  assert.match(await get.text(),/Privacy policy/);
  const head=await worker.fetch(new Request('https://example.test/privacy',{method:'HEAD'}),env);
  assert.equal(await head.text(),'');
  assert.equal((await worker.fetch(new Request('https://example.test/v1/history'),env)).status,401);
});

test('Facebook and Story publication uncertainty cannot be erased by Instagram state updates',async()=>{
  const before={platforms:{facebook:{publish_intent:true,cards:{quiz:{upload_intent:true,photo_id:'123'}}},instagram_stories:{publish_intent:true,cards:{quiz:{publish_intent:true,media_id:'456',verified:true}}}}};
  let writes=0;
  const env={PROJECT_ID:PROJECT,ADMIN_TOKEN:'private',DB:{prepare(sql){return {bind(){return this;},first:async()=>({state:JSON.stringify(before),revision:0}),run:async()=>{writes++;return {meta:{changes:1}};}};}}};
  const send=async state=>worker.fetch(new Request('https://example.test/v1/batches/2026-10-03',{method:'PATCH',headers:{Authorization:'Bearer private','Content-Type':'application/json'},body:JSON.stringify({revision:0,state})}),env);
  for(const mutate of [s=>delete s.platforms.facebook,s=>s.platforms.facebook.cards.quiz.photo_id='different',s=>delete s.platforms.instagram_stories.cards.quiz.publish_intent,s=>s.platforms.instagram_stories.cards.quiz.media_id='different',s=>s.platforms.instagram_stories.cards.quiz.verified=false]) {
    const next=structuredClone(before);mutate(next);
    assert.equal((await send(next)).status,409);
  }
  assert.equal(writes,0);
  const next=structuredClone(before);next.media_id='instagram-feed';next.verified=true;
  assert.equal((await send(next)).status,200);
  assert.equal(writes,1);
});

test('only final card and Story JPEGs can be exposed, not private backgrounds or TikTok exports',async()=>{
  const env={PROJECT_ID:PROJECT,ADMIN_TOKEN:'private',DB:{prepare(){return {bind(){return this;},first:async()=>({})};}},IMAGES:{get:async()=>new Uint8Array(100),put:async()=>{}}};
  for(const [name,status] of [['quiz-card.jpg',200],['quiz-story.jpg',200],['quiz-tiktok.jpg',404],['quiz-background.jpg',404]]) {
    const r=await worker.fetch(new Request('https://example.test/v1/expose/2026-10-03/'+name,{method:'POST',headers:{Authorization:'Bearer private'}}),env);
    assert.equal(r.status,status);
  }
});

test('Buffer TikTok account, submission and ordered images cannot change after intent',async()=>{
  const before={platforms:{tiktok:{publish_intent:true,channel_id:'channel',service_id:'account',post_id:'accepted',image_urls:['one','two','three'],asset_ids:['a','b','c'],asset_sha256:['hash-a','hash-b','hash-c']}}};
  let writes=0;
  const env={PROJECT_ID:PROJECT,ADMIN_TOKEN:'private',DB:{prepare(){return {bind(){return this;},first:async()=>({state:JSON.stringify(before),revision:0}),run:async()=>{writes++;return {meta:{changes:1}};}};}}};
  const send=async state=>worker.fetch(new Request('https://example.test/v1/batches/2026-10-03',{method:'PATCH',headers:{Authorization:'Bearer private','Content-Type':'application/json'},body:JSON.stringify({revision:0,state})}),env);
  for(const mutate of [s=>delete s.platforms.tiktok.publish_intent,s=>s.platforms.tiktok.channel_id='other',s=>s.platforms.tiktok.service_id='other',s=>s.platforms.tiktok.post_id='other',s=>s.platforms.tiktok.image_urls.reverse(),s=>s.platforms.tiktok.asset_ids.reverse(),s=>s.platforms.tiktok.asset_sha256.reverse(),s=>delete s.platforms.tiktok.asset_sha256]) {
    const next=structuredClone(before);mutate(next);assert.equal((await send(next)).status,409);
  }
  assert.equal(writes,0);
  const next=structuredClone(before);next.platforms.tiktok.verified=true;
  assert.equal((await send(next)).status,200);
});

test('aliases normalize and reserve distinctly',()=>{
  assert.equal(canonical('Kišobran'),canonical('kisobran'));
  const keys=reservationKeys({theme:{equivalence_keys:['Kišni dan']},words:[{lemma:'kišobran',equivalence_keys:['umbrella','kišobran']}]});
  assert.deepEqual(keys,['theme:kisni dan','word:kisobran','word:umbrella']);
});
test('private history never bypasses bearer auth',async()=>{
  const r=await worker.fetch(new Request('https://example.test/v1/history'),{PROJECT_ID:PROJECT,ADMIN_TOKEN:'private'});
  assert.equal(r.status,401);
});
test('private endpoints stay closed until the deployment credential exists',async()=>{
  for(const token of ['Bearer undefined','Bearer null','Bearer ']) {
    const r=await worker.fetch(new Request('https://example.test/v1/history',{headers:{Authorization:token}}),{PROJECT_ID:PROJECT});
    assert.equal(r.status,401);
  }
});
test('project identity rejects cross-project binding',async()=>{
  const r=await worker.fetch(new Request('https://example.test/health'),{PROJECT_ID:'wrong'});
  assert.equal(r.status,503);
});
test('watchdog only runs at Sarajevo 06:59 in both seasons',async()=>{
  let reads=0;
  const env={DB:{prepare(){reads++;return{first:async()=>({value:'{"daily_enabled":false}'})};}}};
  await watchdog(env,new Date('2026-07-01T04:59:00Z')); assert.equal(reads,1);
  await watchdog(env,new Date('2026-07-01T05:59:00Z')); assert.equal(reads,1);
  await watchdog(env,new Date('2026-12-01T05:59:00Z')); assert.equal(reads,2);
  await watchdog(env,new Date('2026-12-01T04:59:00Z')); assert.equal(reads,2);
});

test('late cron delivery still runs the intended Sarajevo monitoring check',async t=>{
  t.mock.timers.enable({apis:['Date'],now:new Date('2026-10-03T05:01:00Z')});
  let reads=0, pending;
  const env={DB:{prepare(){reads++;return{first:async()=>({value:'{"daily_authorized":false}'})};}}};
  await worker.scheduled({scheduledTime:new Date('2026-10-03T04:59:00Z').getTime()},env,{waitUntil(p){pending=p;}});
  await pending;
  assert.equal(reads,1);
  await worker.scheduled({scheduledTime:new Date('2026-10-03T05:59:00Z').getTime()},env,{waitUntil(p){pending=p;}});
  await pending;
  assert.equal(reads,1,'the other-season trigger must remain inactive');
});

test('email deferral requires verified GitHub reporting',()=>{
  assert.equal(publicationMonitoringReady({healthchecks_deferred:true}),false);
  assert.equal(publicationMonitoringReady({healthchecks_deferred:'true',github_monitoring_ready:true}),false);
  assert.equal(publicationMonitoringReady({healthchecks_deferred:true,github_monitoring_ready:true}),true);
});

test('Worker still requires a real queue save with deferred email',async()=>{
  let written;
  const env={PROJECT_ID:PROJECT,ADMIN_TOKEN:'private',DB:{prepare(){return {bind(value){written=value;return this;},run:async()=>({})};}}};
  const send=async p=>worker.fetch(new Request('https://example.test/v1/config',{method:'PUT',headers:{Authorization:'Bearer private','Content-Type':'application/json'},body:JSON.stringify(p)}),env);
  assert.equal((await send({daily_enabled:true,daily_authorized:true,preparation_verified:false,healthchecks_deferred:true,github_monitoring_ready:true})).status,409);
  assert.equal(written,undefined);
  assert.equal((await send({daily_enabled:true,daily_authorized:true,preparation_verified:true,healthchecks_deferred:true,github_monitoring_ready:true,monitoring_ready:false})).status,200);
  assert.equal(JSON.parse(written).monitoring_ready,false);
  assert.equal((await send({healthchecks_deferred:'true'})).status,400);
});

test('GitHub-only monitoring check does not ping Healthchecks or publish',async()=>{
  const calls=[];
  const original=globalThis.fetch;
  globalThis.fetch=async(url,options={})=>{
    calls.push({url,method:options.method||'GET'});
    assert.ok(url.startsWith('https://api.github.com/repos/'+REPO));
    if(url==='https://api.github.com/repos/'+REPO) return Response.json({full_name:REPO,private:true});
    if(url.includes('/actions/workflows/daily.yml/runs')) return Response.json({workflow_runs:[]});
    if(url.endsWith('/issues')) return Response.json({number:1});
    throw Error('Unexpected external operation');
  };
  try {
    const env={PROJECT_ID:PROJECT,GITHUB_REPOSITORY:REPO,ADMIN_TOKEN:'private',NOTIFY_GITHUB_TOKEN:'private',DB:{prepare(){return {bind(){return this;},run:async()=>({meta:{changes:1}})};}}};
    const r=await worker.fetch(new Request('https://example.test/v1/monitoring/check',{method:'POST',headers:{Authorization:'Bearer private','Content-Type':'application/json'},body:JSON.stringify({healthchecks:false})}),env);
    assert.equal(r.status,200);
    assert.equal((await r.json()).healthchecks_check,'deferred');
    assert.equal(calls.filter(x=>x.method==='POST').length,1);
    assert.ok(calls.at(-1).url.endsWith('/issues'));
  } finally {globalThis.fetch=original;}
});

test('armed cloud schedule reports missing first preparation while publication is disabled',async()=>{
  const original=globalThis.fetch;
  const issues=[];
  globalThis.fetch=async(url,options={})=>{
    assert.ok(url.startsWith('https://api.github.com/repos/'+REPO));
    if(url==='https://api.github.com/repos/'+REPO) return Response.json({full_name:REPO,private:true});
    if(url.includes('/actions/workflows/')) return Response.json({workflow_runs:[]});
    if(url.endsWith('/issues')) {issues.push(JSON.parse(options.body)); return Response.json({number:1});}
    throw Error('Unexpected external operation');
  };
  try {
    const config={daily_enabled:false,daily_authorized:true,active_since:'2026-10-02',healthchecks_deferred:true};
    const env={GITHUB_REPOSITORY:REPO,NOTIFY_GITHUB_TOKEN:'private',DB:{prepare(sql){return{
      bind(){return this;},first:async()=>sql.includes('settings')?{value:JSON.stringify(config)}:null,
      run:async()=>({meta:{changes:1}})
    };}}};
    await watchdog(env,new Date('2026-10-02T04:59:00Z'));
    assert.equal(issues.length,2);
    assert.ok(issues.some(x=>x.title.includes('cloud preparation scheduling')));
    assert.ok(issues.every(x=>x.body.includes('nothing published')));
  } finally {globalThis.fetch=original;}
});

test('confirmed reusable publication does not require a separate pipeline cron run',async()=>{
  const original=globalThis.fetch;
  const issues=[];
  globalThis.fetch=async(url,options={})=>{
    assert.ok(url.startsWith('https://api.github.com/repos/'+REPO));
    if(url==='https://api.github.com/repos/'+REPO) return Response.json({full_name:REPO,private:true});
    if(url.includes('/actions/workflows/preparation.yml/runs')) return Response.json({workflow_runs:[{event:'workflow_dispatch',head_branch:'main',display_title:'EasyBosnian preparation (recover_today)',created_at:'2026-10-02T03:00:00Z',status:'completed',conclusion:'success',html_url:'https://github.com/'+REPO+'/actions/runs/123'}]});
    if(url.endsWith('/issues')) {issues.push(JSON.parse(options.body));return Response.json({number:1});}
    throw Error('A separate scheduled publisher must not be queried');
  };
  try {
    const config={daily_enabled:true,daily_authorized:true,healthchecks_deferred:true};
    const env={GITHUB_REPOSITORY:REPO,NOTIFY_GITHUB_TOKEN:'private',DB:{prepare(sql){return{
      bind(){return this;},first:async()=>sql.includes('settings')?{value:JSON.stringify(config)}:sql.includes('preparation_dispatches')?{status:'accepted',http_status:204,scheduled_at:'2026-10-02T03:00:00Z'}:{state:JSON.stringify({verified:true})},
      run:async()=>({meta:{changes:1}})
    };}}};
    await watchdog(env,new Date('2026-10-02T04:59:00Z'));
    assert.equal(issues.length,0);
  } finally {globalThis.fetch=original;}
});

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
    assert.deepEqual(JSON.parse(options.body),{ref:'main',inputs:{mode:'recover_today'}});
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

test('disabled scheduler, inactive hours and unauthorized daily publishing never dispatch',async t=>{
  const fixture=dispatchFixture();t.mock.method(globalThis,'fetch',fixture.fetch);
  await dailyPreparationDispatch(fixture.env,new Date('2026-07-01T03:07:00Z'));
  await dailyPreparationDispatch({...fixture.env,PREPARATION_DISPATCH_ENABLED:'false'},new Date('2026-07-01T03:00:00Z'));
  const paused={...fixture.env,DB:{prepare(){return {first:async()=>({value:'{"daily_authorized":false}'})};}}};
  await dailyPreparationDispatch(paused,new Date('2026-07-01T03:00:00Z'));
  assert.equal(fixture.calls.length,0);assert.equal(fixture.records.size,0);
});

test('wrong repository, public visibility and missing secret fail before dispatch',async t=>{
  const fixture=dispatchFixture();
  const mocked=t.mock.method(globalThis,'fetch',fixture.fetch);
  await assert.rejects(dispatchPreparation({...fixture.env,GITHUB_REPOSITORY:'wrong/repo'},'recover_today'),/mismatch/);
  await assert.rejects(dispatchPreparation({...fixture.env,GITHUB_DISPATCH_TOKEN:''},'recover_today'),/missing/);
  assert.equal(fixture.calls.length,0);
  mocked.mock.restore();
  t.mock.method(globalThis,'fetch',async()=>Response.json({full_name:REPO,private:false,default_branch:'main'}));
  await assert.rejects(dispatchPreparation(fixture.env,'recover_today'),/exact private repository/);
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

test('manual verify runs cannot satisfy the missing daily-run check',async t=>{
  const issues=[];
  t.mock.method(globalThis,'fetch',async(url,options={})=>{
    if(url==='https://api.github.com/repos/'+REPO) return Response.json({full_name:REPO,private:true});
    if(url.includes('runs?event=workflow_dispatch')) return Response.json({workflow_runs:[{event:'workflow_dispatch',head_branch:'main',display_title:'EasyBosnian preparation (verify)',created_at:'2026-07-01T03:01:00Z'}]});
    if(url.endsWith('/issues')) {issues.push(JSON.parse(options.body));return Response.json({number:1});}
    throw Error('Unexpected request');
  });
  const env={GITHUB_REPOSITORY:REPO,NOTIFY_GITHUB_TOKEN:'private',DB:{prepare(sql){return {
    bind(){return this;},first:async()=>sql.includes('settings')?{value:'{"daily_authorized":true,"daily_enabled":true,"healthchecks_deferred":true}'}:sql.includes('preparation_dispatches')?{status:'accepted',scheduled_at:'2026-07-01T03:00:00Z'}:{state:'{"verified":true}'},run:async()=>({meta:{changes:1}})
  };}}};
  await watchdog(env,new Date('2026-07-01T04:59:00Z'));
  assert.equal(issues.length,1);assert.match(issues[0].body,/no matching recover_today run/);
});

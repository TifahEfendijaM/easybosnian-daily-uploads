import test from 'node:test';
import assert from 'node:assert/strict';
import worker,{canonical,reservationKeys,watchdog,PROJECT,REPO,publicationMonitoringReady} from './worker.mjs';

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
  const before={platforms:{tiktok:{publish_intent:true,channel_id:'channel',service_id:'account',post_id:'accepted',image_urls:['one','two','three'],asset_ids:['a','b','c']}}};
  let writes=0;
  const env={PROJECT_ID:PROJECT,ADMIN_TOKEN:'private',DB:{prepare(){return {bind(){return this;},first:async()=>({state:JSON.stringify(before),revision:0}),run:async()=>{writes++;return {meta:{changes:1}};}};}}};
  const send=async state=>worker.fetch(new Request('https://example.test/v1/batches/2026-10-03',{method:'PATCH',headers:{Authorization:'Bearer private','Content-Type':'application/json'},body:JSON.stringify({revision:0,state})}),env);
  for(const mutate of [s=>delete s.platforms.tiktok.publish_intent,s=>s.platforms.tiktok.channel_id='other',s=>s.platforms.tiktok.service_id='other',s=>s.platforms.tiktok.post_id='other',s=>s.platforms.tiktok.image_urls.reverse(),s=>s.platforms.tiktok.asset_ids.reverse()]) {
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
    if(url.includes('/actions/workflows/preparation.yml/runs')) return Response.json({workflow_runs:[{created_at:'2026-10-02T03:00:00Z',status:'completed',conclusion:'success',html_url:'https://github.com/'+REPO+'/actions/runs/123'}]});
    if(url.endsWith('/issues')) {issues.push(JSON.parse(options.body));return Response.json({number:1});}
    throw Error('A separate scheduled publisher must not be queried');
  };
  try {
    const config={daily_enabled:true,daily_authorized:true,healthchecks_deferred:true};
    const env={GITHUB_REPOSITORY:REPO,NOTIFY_GITHUB_TOKEN:'private',DB:{prepare(sql){return{
      bind(){return this;},first:async()=>sql.includes('settings')?{value:JSON.stringify(config)}:{state:JSON.stringify({verified:true})},
      run:async()=>({meta:{changes:1}})
    };}}};
    await watchdog(env,new Date('2026-10-02T04:59:00Z'));
    assert.equal(issues.length,0);
  } finally {globalThis.fetch=original;}
});

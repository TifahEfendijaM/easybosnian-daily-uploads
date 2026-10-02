import test from 'node:test';
import assert from 'node:assert/strict';
import worker,{canonical,reservationKeys,watchdog,PROJECT,REPO,publicationMonitoringReady} from './worker.mjs';

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
test('watchdog only runs at Sarajevo 19:59 in both seasons',async()=>{
  let reads=0;
  const env={DB:{prepare(){reads++;return{first:async()=>({value:'{"daily_enabled":false}'})};}}};
  await watchdog(env,new Date('2026-07-01T17:59:00Z')); assert.equal(reads,1);
  await watchdog(env,new Date('2026-07-01T18:59:00Z')); assert.equal(reads,1);
  await watchdog(env,new Date('2026-12-01T18:59:00Z')); assert.equal(reads,2);
  await watchdog(env,new Date('2026-12-01T17:59:00Z')); assert.equal(reads,2);
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

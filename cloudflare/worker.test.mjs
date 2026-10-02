import test from 'node:test';
import assert from 'node:assert/strict';
import worker,{canonical,reservationKeys,watchdog,PROJECT} from './worker.mjs';

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
test('watchdog only runs at Sarajevo 17:50 in both seasons',async()=>{
  let reads=0;
  const env={DB:{prepare(){reads++;return{first:async()=>({value:'{"daily_enabled":false}'})};}}};
  await watchdog(env,new Date('2026-07-01T15:50:00Z')); assert.equal(reads,1);
  await watchdog(env,new Date('2026-07-01T16:50:00Z')); assert.equal(reads,1);
  await watchdog(env,new Date('2026-12-01T16:50:00Z')); assert.equal(reads,2);
  await watchdog(env,new Date('2026-12-01T15:50:00Z')); assert.equal(reads,2);
});

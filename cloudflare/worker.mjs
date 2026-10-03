import {privacy} from './privacy.mjs';
export const REPO = 'TifahEfendijaM/easybosnian-daily-uploads';
export const PROJECT = 'tifahefendijam-easybosnian-daily-uploads-v1';
const DATE = /^\d{4}-\d{2}-\d{2}$/;
const NAME = /^(quiz|lesson|word)-(background|card|tiktok|story)\.jpg$/;
const response = (data, status=200) => Response.json(data, {status, headers:{'Cache-Control':'no-store'}});
export const canonical = s => s.toLowerCase().replaceAll('đ','d').normalize('NFKD').replace(/[\u0300-\u036f]/g,'').replace(/[^a-z0-9 ]/g,' ').trim().replace(/\s+/g,' ');
export function reservationKeys(p) {
  return [...new Set([
    ...p.theme.equivalence_keys.map(k=>'theme:'+canonical(k)),
    ...p.words.flatMap(w=>[w.lemma,...w.equivalence_keys].map(k=>'word:'+canonical(k)))
  ])].sort();
}
function safePackage(p) {
  if (p.project!==PROJECT || p.schema_version!==1 || !DATE.test(p.date) || p.cards?.length!==3 || p.words?.length!==3) throw Error('Invalid package identity');
  if (p.cards.map(c=>c.kind).join(',')!=='quiz,lesson,word') throw Error('Invalid cards');
  const r=p.private_review;
  for (const check of ['standard_bosnian_checked','sources_checked','semantic_history_checked','no_answer_leak_checked']) if (r?.[check]!==true) throw Error('Editorial checks incomplete');
  if (!p.theme.equivalence_keys?.length || !p.words.every(w=>w.equivalence_keys?.length)) throw Error('Reservation keys missing');
  if (p.cards.some(c=>!['editorial','framed','notebook','ribbon','split-cards','minimal','rounded','poster'].includes(c.design_template))) throw Error('Invalid layout');
}
async function equalToken(a,b) {
  if (!a || !b) return false;
  const h=async s=>new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(s)));
  const x=await h(a),y=await h(b); let diff=0;
  for(let i=0;i<x.length;i++) diff|=x[i]^y[i];
  return diff===0;
}
async function row(env,date) { return env.DB.prepare('SELECT * FROM batches WHERE date=?').bind(date).first(); }
function unpack(r) {return {date:r.date,hash:r.package_hash,package:JSON.parse(r.package_json),reservation_keys:JSON.parse(r.reservation_keys),state:JSON.parse(r.state),revision:r.revision};}
async function settings(env) {return JSON.parse((await env.DB.prepare('SELECT value FROM settings WHERE id=1').first()).value);}
async function github(env,path,method='GET',body) {
  // All operations are anchored to one fixed private repository.
  if (env.GITHUB_REPOSITORY!==REPO) throw Error('Repository identity mismatch');
  const headers={Authorization:`Bearer ${env.NOTIFY_GITHUB_TOKEN}`,Accept:'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28','User-Agent':PROJECT,'Content-Type':'application/json'};
  const base=`https://api.github.com/repos/${REPO}`;
  const identity=await fetch(base,{headers});
  if(!identity.ok) throw Error(`GitHub ${identity.status}; check notification token access`);
  const repository=await identity.json();
  if(repository.full_name!==REPO || repository.private!==true) throw Error('Target repository is not exact/private');
  if(!path && method==='GET') return repository;
  const r=await fetch(base+path,{method,headers,body:body ? JSON.stringify(body):undefined});
  if(!r.ok) throw Error(`GitHub ${r.status}; check notification token access`);
  return r.json();
}
export function publicationMonitoringReady(config) {
  return config.monitoring_ready===true || (config.healthchecks_deferred===true && config.github_monitoring_ready===true);
}
async function monitorPing(url, suffix='',body='') {
  if(!url || !url.startsWith('https://hc-ping.com/')) throw Error('External monitor missing');
  const r=await fetch(url+suffix,{method:'POST',body});
  if(!r.ok) throw Error('External monitor failed');
}
async function alert(env,date,stage,error,publication,run) {
  const inserted=await env.DB.prepare('INSERT OR IGNORE INTO alerts(date,stage) VALUES(?,?)').bind(date,stage).run();
  if(!inserted.meta.changes) return;
  try {
    await github(env,'/issues','POST',{title:`EasyBosnian ${date}: ${stage} failed`,body:`Batch: ${date}\nStage: ${stage}\nError: ${error}\nPublication: ${publication}\nRun/logs: ${run || 'No GitHub run exists. Inspect the 05:00 cloud preparation schedule and account authorization.'}\nNext: Inspect schedules, account authorizations and free quotas. Reconcile saved publishing state before a deliberate rerun. No scheduled retry exists.`});
  } catch(e) {
    await env.DB.prepare('DELETE FROM alerts WHERE date=? AND stage=?').bind(date,stage).run();
    throw e;
  }
}
export async function watchdog(env, now=new Date()) {
  // UTC triggers in both seasons; only one executes the Sarajevo 06:59 health check.
  // This function has no generation, workflow-dispatch, or publication capability.
  const fields=Object.fromEntries(new Intl.DateTimeFormat('en-CA',{timeZone:'Europe/Sarajevo',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).formatToParts(now).map(x=>[x.type,x.value]));
  if(fields.hour!=='06' || fields.minute!=='59') return;
  const config=await settings(env);
  // Monitor an armed cloud schedule even before its first package can enable publication.
  if(!config.daily_authorized || (!config.daily_enabled && !config.active_since)) return;
  const date=`${fields.year}-${fields.month}-${fields.day}`;
  const r=await row(env,date);
  const state=r?JSON.parse(r.state):{};
  const publication=state.publish_intent && !state.verified ? 'uncertain' : state.verified ? 'confirmed published' : state.media_id ? 'published; verification pending' : 'nothing published';
  const repository=await github(env,'');
  if(repository.full_name!==REPO || !repository.private) throw Error('Target repository is not exact/private');
  const preparationRuns=await github(env,'/actions/workflows/preparation.yml/runs?event=schedule&per_page=20');
  const preparationDay=preparationRuns.workflow_runs.filter(x=>new Date(x.created_at).toLocaleDateString('en-CA',{timeZone:'Europe/Sarajevo'})===date);
  const dailyRun=preparationDay[0];
  if(!preparationDay.length) await alert(env,date,'cloud preparation scheduling','No scheduled cloud preparation run started by 06:59 Europe/Sarajevo. It may still start late.',publication,null);
  if(!r) await alert(env,date,'ChatGPT preparation/queue save','No reviewed package is reserved in private Cloudflare history.',publication,dailyRun?.html_url);
  // The reusable publisher is a job within preparation's run, not a second cron run.
  if(r && dailyRun && !state.verified) {
    const stage=state.failed_stage || (state.run_url ? 'publication verification' : 'preparation/publication handoff');
    await alert(env,date,stage,'The daily preparation and completion-based pipeline have not confirmed an actual Instagram publication by 06:59. Inspect the preparation and publication jobs.',publication,dailyRun.html_url);
  }
  if(config.healthchecks_deferred!==true) await monitorPing(env.HC_WATCHDOG_URL);
}
export default {
  async fetch(req,env) {
    const url=new URL(req.url), path=url.pathname;
    if(env.PROJECT_ID!==PROJECT) return response({error:'Project identifier mismatch'},503);
    if(path==='/health' && req.method==='GET') return response({project:PROJECT,status:'ok'});
    if(path==='/privacy' && ['GET','HEAD'].includes(req.method)) return new Response(req.method==='HEAD'?null:privacy,{headers:{'Content-Type':'text/html; charset=utf-8','Cache-Control':'public, max-age=300','X-Content-Type-Options':'nosniff','Content-Security-Policy':"default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; frame-ancestors 'none'"}});
    const publicAsset=path.match(/^\/images\/([a-f0-9]{64})\.jpg$/);
    if(publicAsset && ['GET','HEAD'].includes(req.method)) {
      const data=await env.IMAGES.get('public:'+publicAsset[1],{type:'arrayBuffer'});
      if(!data) return new Response('Not found',{status:404,headers:{'Cache-Control':'no-store'}});
      return new Response(req.method==='HEAD'?null:data,{headers:{'Content-Type':'image/jpeg','Cache-Control':'public, max-age=300','X-Content-Type-Options':'nosniff'}});
    }
    if(!env.ADMIN_TOKEN || !await equalToken(req.headers.get('Authorization'),`Bearer ${env.ADMIN_TOKEN}`)) return response({error:'Unauthorized'},401);
    try {
      if(path==='/v1/history' && req.method==='GET') {
        const result=await env.DB.prepare('SELECT date,package_json,reservation_keys,state FROM batches ORDER BY date').all();
        return response({project:PROJECT,batches:result.results.map(x=>({date:x.date,theme:JSON.parse(x.package_json).theme,words:JSON.parse(x.package_json).words,reservation_keys:JSON.parse(x.reservation_keys),state:JSON.parse(x.state)}))});
      }
      if(path==='/v1/monitoring/check' && req.method==='POST') {
        const options=req.headers.get('Content-Type')?.includes('application/json') ? await req.json() : {};
        if(Object.keys(options).some(k=>k!=='healthchecks') || (options.healthchecks!==undefined && typeof options.healthchecks!=='boolean')) return response({error:'Invalid monitoring check option'},400);
        const checkHealthchecks=options.healthchecks!==false;
        const repository=await github(env,'');
        if(repository.full_name!==REPO || !repository.private) throw Error('Target repository is not exact/private');
        await github(env,'/actions/workflows/daily.yml/runs?per_page=1');
        await alert(env,new Date().toLocaleDateString('en-CA',{timeZone:'Europe/Sarajevo'}),checkHealthchecks?'monitoring setup':'GitHub monitoring setup','Notification self-test; no pipeline failure and no post.','nothing published',null);
        if(checkHealthchecks) await monitorPing(env.HC_WATCHDOG_URL,'/fail','EasyBosnian monitoring self-test; nothing published.');
        return response({repository:REPO,github_notification_check:'accepted',healthchecks_check:checkHealthchecks?'accepted':'deferred',email_receipt:checkHealthchecks?'check your verified Healthchecks and GitHub email inboxes':'Healthchecks email setup deferred by user; private GitHub issue reporting tested'});
      }
      if(path==='/v1/config') {
        if(req.method==='GET') return response(await settings(env));
        if(req.method==='PUT') {
          const p=await req.json();
          const allowed=['daily_enabled','daily_authorized','preparation_verified','monitoring_ready','github_monitoring_ready','healthchecks_deferred','active_since'];
          if(Object.keys(p).some(k=>!allowed.includes(k))) return response({error:'Unknown activation field'},400);
          if(Object.entries(p).some(([k,v])=>k==='active_since' ? typeof v!=='string' || (v!=='' && !DATE.test(v)) : typeof v!=='boolean')) return response({error:'Invalid activation field type'},400);
          if(p.daily_enabled) {
            if(p.daily_authorized!==true || p.preparation_verified!==true || !publicationMonitoringReady(p)) return response({error:'Account, preparation or monitoring setup incomplete'},409);
          }
          await env.DB.prepare('UPDATE settings SET value=? WHERE id=1').bind(JSON.stringify(p)).run();
          return response(p);
        }
      }
      if(path==='/v1/queue' && req.method==='POST') {
        const p=await req.json(); safePackage(p.package);
        if(!/^[a-f0-9]{64}$/.test(p.hash)) throw Error('Invalid package hash');
        const keys=reservationKeys(p.package);
        if(JSON.stringify(keys)!==JSON.stringify(p.reservation_keys)) throw Error('Reservation keys do not match package');
        const existing=await row(env,p.package.date);
        if(existing) return existing.package_hash===p.hash ? response(unpack(existing)) : response({error:'Date already reserved for a different immutable package'},409);
        const stmts=[env.DB.prepare('INSERT INTO batches(date,package_hash,package_json,reservation_keys) VALUES(?,?,?,?)').bind(p.package.date,p.hash,JSON.stringify(p.package),JSON.stringify(keys)), ...keys.map(k=>env.DB.prepare('INSERT INTO reservations(key,batch_date) VALUES(?,?)').bind(k,p.package.date))];
        // D1 batch is transactional; a repeated alias rolls back the entire reservation.
        await env.DB.batch(stmts);
        return response(unpack(await row(env,p.package.date)),201);
      }
      if(path==='/v1/generate' && req.method==='POST') {
        const p=await req.json();
        if(!DATE.test(p.date) || !['quiz','lesson','word'].includes(p.kind)) throw Error('Invalid artwork identity');
        const r=await row(env,p.date);
        if(!r) throw Error('Batch not reserved');
        const c=JSON.parse(r.package_json).cards.find(c=>c.kind===p.kind);
        if(c.background_prompt!==p.prompt) throw Error('Prompt does not match reviewed package');
        const key=`private-ai:${p.date}:${p.kind}`;
        const cached=await env.IMAGES.get(key);
        if(cached) return response({image:cached});
        const existing=await env.DB.prepare('SELECT status FROM generations WHERE date=? AND kind=?').bind(p.date,p.kind).first();
        if(existing) return response({error:'Generation already started/completed; inspect cache and reconcile before generating again'},409);
        const intent=await env.DB.prepare("INSERT OR IGNORE INTO generations(date,kind,status) VALUES(?,?,'started')").bind(p.date,p.kind).run();
        if(!intent.meta.changes) throw Error('Generation is already in progress');
        let generationStage='FLUX generation';
        try {
          const result=await env.AI.run('@cf/black-forest-labs/flux-1-schnell',{prompt:p.prompt,steps:4});
          if(!result.image) throw Error('No image returned');
          generationStage='storage';
          // Keep the base64 result unchanged to avoid large per-byte CPU work on Workers Free.
          // Python decodes it, normalizes JPEG, renders and uploads the final asset.
          await env.IMAGES.put(key,result.image,{expirationTtl:14*86400});
          await env.DB.prepare("UPDATE generations SET status='done' WHERE date=? AND kind=?").bind(p.date,p.kind).run();
          return response({image:result.image});
        } catch(e) {
          // The intent stays durable: an uncertain model response must not be silently retried.
          await env.DB.prepare("UPDATE generations SET status='uncertain' WHERE date=? AND kind=?").bind(p.date,p.kind).run();
          return response({error:'Generation state preserved for reconciliation',stage:generationStage},502);
        }
      }
      const batch=path.match(/^\/v1\/batches\/(\d{4}-\d{2}-\d{2})$/);
      if(batch) {
        const r=await row(env,batch[1]);
        if(!r) return response({error:'No reviewed package for this date'},404);
        if(req.method==='GET') return response(unpack(r));
        if(req.method==='PATCH') {
          const p=await req.json(),before=JSON.parse(r.state);
          // Publication uncertainty is durable and cannot be erased by an ordinary rerun.
          if(before.publish_intent && !p.state.publish_intent) throw Error('Publish intent cannot be erased');
          if(before.verified && (!p.state.verified || p.state.media_id!==before.media_id)) throw Error('Verified publication is immutable');
          for(const [platform,old] of Object.entries(before.platforms||{})) {
            const next=p.state.platforms?.[platform];
            if(old.publish_intent && !next?.publish_intent) throw Error('Platform publication intent cannot be erased');
            if(old.verified && (!next?.verified || next.post_id!==old.post_id)) throw Error('Verified platform publication is immutable');
            if(old.page_id && next?.page_id!==old.page_id) throw Error('Platform Page identity is immutable');
            if(old.channel_id && next?.channel_id!==old.channel_id) throw Error('Platform channel identity is immutable');
            if(old.service_id && next?.service_id!==old.service_id) throw Error('Platform account identity is immutable');
            if(old.post_id && next?.post_id!==old.post_id) throw Error('Platform post identity is immutable');
            if(old.image_urls && JSON.stringify(next?.image_urls)!==JSON.stringify(old.image_urls)) throw Error('Submitted platform images are immutable');
            if(old.asset_ids && JSON.stringify(next?.asset_ids)!==JSON.stringify(old.asset_ids)) throw Error('Platform image identities are immutable');
            if(old.asset_sha256 && JSON.stringify(next?.asset_sha256)!==JSON.stringify(old.asset_sha256)) throw Error('Platform image content hashes are immutable');
            for(const [kind,item] of Object.entries(old.cards||{})) {
              const updated=next?.cards?.[kind];
              if(item.upload_intent && !updated?.upload_intent) throw Error('Platform upload intent cannot be erased');
              if(item.photo_id && updated?.photo_id!==item.photo_id) throw Error('Platform photo identity is immutable');
              if(item.publish_intent && !updated?.publish_intent) throw Error('Story publication intent cannot be erased');
              if(item.media_id && updated?.media_id!==item.media_id) throw Error('Story publication identity is immutable');
              if(item.verified && !updated?.verified) throw Error('Verified Story is immutable');
            }
          }
          const saved=await env.DB.prepare('UPDATE batches SET state=?,revision=revision+1 WHERE date=? AND revision=?').bind(JSON.stringify(p.state),batch[1],p.revision).run();
          if(!saved.meta.changes) return response({error:'Revision conflict; reload saved state'},409);
          return response({revision:p.revision+1});
        }
      }
      const asset=path.match(/^\/v1\/(private|expose)\/(\d{4}-\d{2}-\d{2})\/(.+)$/);
      if(asset && NAME.test(asset[3])) {
        const [,kind,date,name]=asset;
        if(!await row(env,date)) return response({error:'Batch not reserved'},404);
        const key=`private:${date}:${name}`;
        if(kind==='private' && req.method==='GET') {
          const data=await env.IMAGES.get(key,{type:'arrayBuffer'});
          return data ? new Response(data,{headers:{'Content-Type':'image/jpeg','Cache-Control':'no-store'}}) : response({error:'Asset not found'},404);
        }
        if(kind==='private' && req.method==='PUT') {
          const data=await req.arrayBuffer();
          if(data.byteLength>3_000_000 || data.byteLength<100 || new Uint8Array(data)[0]!==255 || new Uint8Array(data)[1]!==216) throw Error('Asset must be a JPEG below 3MB');
          await env.IMAGES.put(key,data,{expirationTtl:14*86400});
          return response({stored:true});
        }
        if(kind==='expose' && req.method==='POST' && (name.endsWith('-card.jpg') || name.endsWith('-story.jpg'))) {
          const data=await env.IMAGES.get(key,{type:'arrayBuffer'});
          if(!data) return response({error:'Rendered asset not visible in KV yet; wait and deliberately rerun'},409);
          const id=Array.from(crypto.getRandomValues(new Uint8Array(32)),x=>x.toString(16).padStart(2,'0')).join('');
          await env.IMAGES.put('public:'+id,data,{expirationTtl:14*86400});
          return response({url:url.origin+'/images/'+id+'.jpg'});
        }
      }
      if(path==='/v1/events' && req.method==='POST') {
        const p=await req.json();
        await env.DB.prepare('INSERT INTO events(date,stage,error,publication,run_url) VALUES(?,?,?,?,?)').bind(p.date,p.stage,p.error.slice(0,900),p.publication,p.run_url||null).run();
        return response({saved:true});
      }
      return response({error:'Not found'},404);
    } catch(e) {
      // Do not expose SQL, raw packages or provider credentials in public diagnostics.
      return response({error:'Operation rejected; inspect package validity, reservations, state and free limits'},409);
    }
  },
  async scheduled(controller,env,ctx) {ctx.waitUntil(watchdog(env));}
};

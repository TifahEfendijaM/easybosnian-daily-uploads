import {privacy} from './privacy.mjs';
export const REPO='TifahEfendijaM/easybosnian-daily-uploads';
export const PROJECT='tifahefendijam-easybosnian-daily-uploads-v1';
const DATE=/^\d{4}-\d{2}-\d{2}$/,BATCH=/^(b-[a-f0-9]{32}|legacy-\d{4}-\d{2}-\d{2})$/,KINDS=['quiz','lesson','word'],NAME=/^(quiz|lesson|word)-(background|card|story)\.jpg$/;
const response=(data,status=200)=>Response.json(data,{status,headers:{'Cache-Control':'no-store'}});
const validJpeg=data=>data.byteLength>=100 && data.byteLength<=3_000_000 && new Uint8Array(data)[0]===255 && new Uint8Array(data)[1]===216;
function storageFailure(reason,status,name) {
  // Only fixed diagnostics: never exception prose, bodies, tokens or URLs.
  console.error(JSON.stringify({event:'image_storage_failed',reason,http_status:status,asset:name}));
  return response({error:'Image storage operation failed',stage:'storage',reason},status);
}
function generationFailure(reason,error=null,providerStatus=null,diagnosticSaved=false) {
  // Bounded numeric codes (including undocumented ones) and fixed reasons only.
  // Upstream error envelopes vary; never echo provider prose/prompts/tokens.
  const match=typeof error?.message==='string'?error.message.match(/(?:^|[ :])([0-9]{4})(?=:)/):null;
  const value=error?.internalCode ?? error?.code ?? error?.errors?.[0]?.code ?? error?.error?.code ?? error?.result?.error?.code ?? (match?Number(match[1]):null);
  const numeric=typeof value==='string' && /^[0-9]{1,5}$/.test(value)?Number(value):value;
  const provider_code=Number.isInteger(numeric) && numeric>0 && numeric<=99999?numeric:null;
  const provider_http_status=Number.isInteger(providerStatus) && providerStatus>=100 && providerStatus<=599?providerStatus:null;
  console.error(JSON.stringify({event:'flux_generation_failed',reason,http_status:409,provider_code,provider_http_status}));
  return response({error:'FLUX generation failed; inspect fixed reason and provider code',stage:'FLUX generation',reason,code:provider_code,provider_http_status,diagnostic_saved:diagnosticSaved},409);
}
async function captureGenerationError(env,p,body) {
  // Private diagnostics, never a retry/intent/history record. Do not retain
  // successful image payloads or echo provider prose into logs/issues.
  if(!BATCH.test(p.batch_id) || !/^r-[a-f0-9]{32}$/.test(p.artwork_id) || !body || body.length>65536) return false;
  let safe=body;
  for(const token of [env.ADMIN_TOKEN,env.GITHUB_DISPATCH_TOKEN]) if(token) safe=safe.split(token).join('[REDACTED]');
  safe=safe.replace(/(access_token|client_secret|authorization)["'\s:=]+[^\s",&}]+/gi,'$1=[REDACTED]');
  try {await env.IMAGES.put(`private-error:${p.batch_id}:${p.artwork_id}:${p.kind}`,safe,{expirationTtl:14*86400});return true;}
  catch {return false;}
}
async function row(env,id) {return env.DB.prepare('SELECT batch_id,date,created_at,content_json FROM history WHERE batch_id=?').bind(id).first();}
async function legacyScope(env,date,write=false) {
  const r=await env.DB.prepare('SELECT batch_id,date,created_at,content_json FROM history WHERE date=? ORDER BY created_at DESC,rowid DESC LIMIT 2').bind(date).all();
  if(write && r.results.length>1) throw Error('Date is ambiguous; use an explicit batch ID');
  return r.results[0] || null;
}
async function scope(env,key,write=false) {return DATE.test(key)?legacyScope(env,key,write):row(env,key);}
async function stagedScope(env,key,req) {
  const r=await scope(env,key,true),date=req.headers.get('X-EasyBosnian-Content-Date');
  if(date!==null && (!BATCH.test(key) || !DATE.test(date) || (r && r.date!==date))) throw Error('Invalid staged scope');
  return r || (date!==null?{batch_id:key,date}:null);
}
async function saveHistory(env,p,id,preserveArtwork=false) {
  safePackage(p,p.date);if(!BATCH.test(id) || p.batch_id!==id) throw Error('Invalid batch identity');
  const result=await env.DB.prepare('INSERT INTO history(batch_id,date,created_at,theme_json,words_json,content_json) VALUES(?,?,?,?,?,?) ON CONFLICT(batch_id) DO UPDATE SET theme_json=excluded.theme_json,words_json=excluded.words_json,content_json=excluded.content_json WHERE history.date=excluded.date').bind(id,p.date,new Date().toISOString(),JSON.stringify(p.theme),JSON.stringify(p.words),JSON.stringify(p)).run();
  if(!result.meta.changes) throw Error('Existing batch date differs');
  if(!preserveArtwork) await clearArtwork(env,id,p.date);
}
async function clearArtwork(env,id,date) {
  const namespaces=[id,...(id==='legacy-'+date?[date]:[])];
  for(const key of namespaces) for(const kind of KINDS) {await env.IMAGES.delete(`private-ai:${key}:${kind}`);for(const suffix of ['background','card','story']) await env.IMAGES.delete(`private:${key}:${kind}-${suffix}.jpg`);}
}
async function imageValue(env,key,id,date,options) {
  return await env.IMAGES.get(key,options) || (id==='legacy-'+date?await env.IMAGES.get(key.replace(id,date),options):null);
}
function safePackage(p,date) {
  if(p.project!==PROJECT || p.schema_version!==1 || !DATE.test(date) || p.date!==date || p.cards?.length!==3 || p.words?.length!==3) throw Error('Invalid content identity');
  if(p.cards.map(c=>c.kind).join(',')!=='quiz,lesson,word') throw Error('Invalid cards');
  for(const flag of ['standard_bosnian_checked','sources_checked','semantic_history_checked','no_answer_leak_checked']) if(p.private_review?.[flag]!==true) throw Error('Editorial checks incomplete');
  if(!p.theme.equivalence_keys?.length || !p.words.every(w=>w.equivalence_keys?.length)) throw Error('Equivalence metadata missing');
  if(p.background_source!==undefined && !validPhotoSource(p.background_source)) throw Error('Invalid photograph provenance');
}
function validPhotoSource(source) {
  return source && Object.keys(source).sort().join(',')==='artwork_id,batch_id' && BATCH.test(source.batch_id) &&
    (source.artwork_id===null || /^r-[a-f0-9]{32}$/.test(source.artwork_id));
}
async function savedBackground(env,id,kind) {
  const record=await row(env,id);if(!record) return response({error:'No saved batch'},404);
  const p=JSON.parse(record.content_json);let source=p.background_source;
  // A cache listing cannot prove publication provenance: a lone surviving
  // namespace may belong to a failed rerun after the published originals expired.
  if(source===undefined) return response({error:'Legacy photograph source was not recorded; verified source annotation required'},409);
  if(!validPhotoSource(source)) throw Error('Invalid saved photograph source');
  const key=`private-ai:${source.batch_id}:${source.artwork_id?source.artwork_id+':':''}${kind}`;
  const image=await imageValue(env,key,source.batch_id,record.date);
  return image?response({image,source,prompt:p.cards.find(c=>c.kind===kind).background_prompt}):response({error:'Saved original photograph expired'},404);
}
async function equalToken(a,b) {
  if(!a || !b) return false;
  const hash=async s=>new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(s)));
  const x=await hash(a),y=await hash(b);let diff=0;for(let i=0;i<x.length;i++) diff|=x[i]^y[i];return diff===0;
}
function sarajevoTime(when) {return Object.fromEntries(new Intl.DateTimeFormat('en-CA',{timeZone:'Europe/Sarajevo',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).formatToParts(when).map(x=>[x.type,x.value]));}
function dispatchError(message,httpStatus=null,uncertain=false) {return Object.assign(new Error(message),{httpStatus,uncertain});}
export async function dispatchPreparation(env,mode) {
  if(env.PROJECT_ID!==PROJECT || env.GITHUB_REPOSITORY!==REPO) throw dispatchError('Dispatch repository/project mismatch');
  if(!['verify','preview','daily'].includes(mode)) throw dispatchError('Unsupported workflow mode');
  if(!env.GITHUB_DISPATCH_TOKEN) throw dispatchError('GITHUB_DISPATCH_TOKEN Worker secret is missing');
  const base=`https://api.github.com/repos/${REPO}`;
  const headers={Authorization:`Bearer ${env.GITHUB_DISPATCH_TOKEN}`,Accept:'application/vnd.github+json','User-Agent':PROJECT,'X-GitHub-Api-Version':'2022-11-28','Content-Type':'application/json'};
  let identity;
  try {identity=await fetch(base,{headers,redirect:'manual',signal:AbortSignal.timeout(15000)});}
  catch {throw dispatchError('GitHub repository check failed; no dispatch was sent');}
  console.log(JSON.stringify({event:'preparation_repository_check',mode,http_status:identity.status}));
  if(identity.status!==200) throw dispatchError(`GitHub repository check HTTP ${identity.status}; check token access`,identity.status);
  const repository=await identity.json();
  if(repository.full_name!==REPO || repository.private!==true || repository.default_branch!=='main') throw dispatchError('Dispatch target must be the exact private repository with default branch main');
  let result;
  try {result=await fetch(base+'/actions/workflows/preparation.yml/dispatches',{method:'POST',headers,redirect:'manual',signal:AbortSignal.timeout(15000),body:JSON.stringify({ref:'main',inputs:{mode,...(mode==='daily'?{batch_target:'none'}:{})}})});}
  catch {throw dispatchError('GitHub dispatch network failure; acceptance is uncertain; no automatic retry',null,true);}
  console.log(JSON.stringify({event:'preparation_dispatch_response',mode,http_status:result.status}));
  if(result.status!==204) throw dispatchError(`GitHub dispatch HTTP ${result.status}; expected 204; no automatic retry`,result.status,result.status>=500 || (result.status>=200 && result.status<300));
  return {github_status:204,mode,status:'accepted; inspect the GitHub run for completion'};
}
export async function dailyPreparationDispatch(env,when) {
  const f=sarajevoTime(when);
  const enabled=env.PREPARATION_DISPATCH_ENABLED==='true',matches=!(f.hour!=='05' || f.minute!=='00');
  console.log(JSON.stringify({event:'preparation_cron_gate',scheduled_at:when.toISOString(),sarajevo_time:`${f.year}-${f.month}-${f.day} ${f.hour}:${f.minute}`,dispatch_enabled:enabled,decision:!matches?'outside_local_start':!enabled?'disabled':'eligible'}));
  if(!matches || !enabled) return;
  if(env.PROJECT_ID!==PROJECT || env.GITHUB_REPOSITORY!==REPO) throw Error('Dispatch repository/project mismatch');
  const date=`${f.year}-${f.month}-${f.day}`;
  // This claim deduplicates cron deliveries only; no publication state is kept.
  const claim=await env.DB.prepare('INSERT OR IGNORE INTO preparation_dispatches(date,scheduled_at,status) VALUES(?,?,?)').bind(date,when.toISOString(),'claimed').run();
  if(!claim.meta.changes) {console.log(JSON.stringify({event:'preparation_dispatch_skipped',date,reason:'date already claimed; no retry'}));return;}
  let accepted=false;
  try {const result=await dispatchPreparation(env,'daily');accepted=true;await env.DB.prepare('UPDATE preparation_dispatches SET status=?,http_status=? WHERE date=?').bind('accepted',204,date).run();return result;}
  catch(error) {
    const status=accepted || error.uncertain?'uncertain':'failed',httpStatus=accepted?204:error.httpStatus??null;
    try {await env.DB.prepare('UPDATE preparation_dispatches SET status=?,http_status=? WHERE date=?').bind(status,httpStatus,date).run();}
    catch {console.error(JSON.stringify({event:'preparation_dispatch_record_failed',date,status}));}
    console.error(JSON.stringify({event:'preparation_dispatch_failed',date,status,http_status:httpStatus}));
    throw Error('Daily GitHub dispatch failed; inspect status logs and private dispatch record; no automatic retry');
  }
}
export default {
  async fetch(req,env) {
    const url=new URL(req.url),path=url.pathname;
    if(env.PROJECT_ID!==PROJECT) return response({error:'Project identifier mismatch'},503);
    if(path==='/health' && req.method==='GET') return response({project:PROJECT,status:'ok'});
    if(path==='/privacy' && ['GET','HEAD'].includes(req.method)) return new Response(req.method==='HEAD'?null:privacy,{headers:{'Content-Type':'text/html; charset=utf-8','Cache-Control':'public, max-age=300','X-Content-Type-Options':'nosniff','Content-Security-Policy':"default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; frame-ancestors 'none'"}});
    const publicAsset=path.match(/^\/images\/([a-f0-9]{64})\.jpg$/);
    if(publicAsset && ['GET','HEAD'].includes(req.method)) {
      const data=await env.IMAGES.get('public:'+publicAsset[1],{type:'arrayBuffer',cacheTtl:30});
      return data?new Response(req.method==='HEAD'?null:data,{headers:{'Content-Type':'image/jpeg','Cache-Control':'public, max-age=300','X-Content-Type-Options':'nosniff'}}):new Response('Not found',{status:404,headers:{'Cache-Control':'no-store'}});
    }
    if(!env.ADMIN_TOKEN || !await equalToken(req.headers.get('Authorization'),`Bearer ${env.ADMIN_TOKEN}`)) return response({error:'Unauthorized'},401);
    try {
      if(path==='/v1/scheduler/verify' && req.method==='POST') {
        try {return response(await dispatchPreparation(env,'verify'));}
        catch(error) {console.error(JSON.stringify({event:'preparation_dispatch_verify_failed',http_status:error.httpStatus??null}));return response({error:'GitHub verify dispatch failed; inspect status logs and access'},502);}
      }
      if(path==='/v1/scheduler/status' && req.method==='GET') {const r=await env.DB.prepare('SELECT date,scheduled_at,status,http_status FROM preparation_dispatches ORDER BY date DESC LIMIT 14').all();return response({project:PROJECT,dispatches:r.results});}
      if(path==='/v1/history' && req.method==='GET') {
        const r=await env.DB.prepare('SELECT rowid AS created_order,batch_id,date,created_at,theme_json,words_json,content_json FROM history ORDER BY created_at,rowid').all();
        return response({project:PROJECT,storage_version:2,days:r.results.map(x=>({batch_id:x.batch_id,date:x.date,created_at:x.created_at,created_order:x.created_order,theme:JSON.parse(x.theme_json),words:JSON.parse(x.words_json),content:JSON.parse(x.content_json)}))});
      }
      const publicationDate=path.match(/^\/v1\/publications\/dates\/(\d{4}-\d{2}-\d{2})$/);
      if(publicationDate && req.method==='GET') {
        const date=publicationDate[1];
        const result=await env.DB.prepare('SELECT rowid AS recorded_order,batch_id,date,platform,kind,object_id,account_id FROM publication_ids WHERE date=? ORDER BY rowid').bind(date).all();
        return response({project:PROJECT,date,items:result.results});
      }
      const publications=path.match(/^\/v1\/publications\/(?:batches\/)?(b-[a-f0-9]{32}|legacy-\d{4}-\d{2}-\d{2}|\d{4}-\d{2}-\d{2})(?:\/(instagram|facebook|tiktok)\/([a-z0-9_]+))?$/);
      if(publications) {
        const [,key,platform,objectId]=publications;
        const legacy=DATE.test(key),record=legacy?await legacyScope(env,key,true):null;
        const id=legacy?(record?.batch_id || 'legacy-'+key):key;
        if(req.method==='GET' && !platform) {
          const result=await env.DB.prepare('SELECT rowid AS recorded_order,batch_id,date,platform,kind,object_id,account_id FROM publication_ids WHERE batch_id=? ORDER BY rowid').bind(id).all();
          return response({project:PROJECT,items:result.results});
        }
        if(req.method==='POST' && !platform) {
          const content=record || await stagedScope(env,id,req);if(!content) throw Error('No batch for publication identifiers');
          const p=await req.json();
          if(Object.keys(p).sort().join(',')!=='account_id,kind,object_id,platform' || !['instagram','facebook','tiktok'].includes(p.platform) || !['feed','story','photo'].includes(p.kind)) throw Error('Invalid publication identifier');
          const idPattern=p.platform==='tiktok'?/^[a-f0-9]{24}$/:/^\d+(?:_\d+)?$/;
          if(typeof p.object_id!=='string' || typeof p.account_id!=='string' || !idPattern.test(p.object_id) || !(p.platform==='tiktok'?/^[a-f0-9]{24}$/:/^\d+$/).test(p.account_id)) throw Error('Invalid provider identifier');
          if(p.platform==='instagram' && p.kind==='photo' || p.platform==='tiktok' && p.kind!=='feed') throw Error('Invalid provider media kind');
          await env.DB.prepare('INSERT INTO publication_ids(batch_id,date,platform,kind,object_id,account_id) VALUES(?,?,?,?,?,?) ON CONFLICT(platform,object_id) DO NOTHING').bind(id,content.date,p.platform,p.kind,p.object_id,p.account_id).run();
          const actual=await env.DB.prepare('SELECT batch_id,kind,account_id FROM publication_ids WHERE platform=? AND object_id=?').bind(p.platform,p.object_id).first();
          if(!actual || actual.batch_id!==id || actual.kind!==p.kind || actual.account_id!==p.account_id) throw Error('Identifier belongs to a different record');
          return response({stored:true});
        }
        if(req.method==='DELETE' && platform) {
          await env.DB.prepare('DELETE FROM publication_ids WHERE batch_id=? AND platform=? AND object_id=?').bind(id,platform,objectId).run();
          return response({removed:true});
        }
      }
      const content=path.match(/^\/v1\/history\/(?:batches\/)?(b-[a-f0-9]{32}|legacy-\d{4}-\d{2}-\d{2}|\d{4}-\d{2}-\d{2})$/);
      if(content) {
        const key=content[1],legacy=DATE.test(key);
        if(req.method==='DELETE') {
          if(legacy || !path.startsWith('/v1/history/batches/')) throw Error('Explicit batch path required for removal');
          const p=await req.json();
          if(Object.keys(p).join(',')!=='date' || !DATE.test(p.date)) throw Error('Expected content date required');
          const r=await row(env,key);
          if(!r) return response({removed:false});
          if(r.date!==p.date) throw Error('History removal date differs');
          await clearArtwork(env,key,r.date);
          const result=await env.DB.prepare('DELETE FROM history WHERE batch_id=? AND date=?').bind(key,p.date).run();
          // Unsupported/uncertain publication IDs remain available by date,
          // even after their content row is gone. Public URLs retain their TTL.
          return response({removed:result.meta.changes===1});
        }
        if(req.method==='GET') {const r=await scope(env,key);return r?response(JSON.parse(r.content_json)):response({error:'No reviewed content for this batch'},404);}
        if(req.method==='PUT') {
          const p=await req.json();let id=key;
          if(legacy) {if(p.date!==key) throw Error('Invalid content date');const r=await legacyScope(env,key,true);id=r?.batch_id || 'legacy-'+key;if(p.batch_id && p.batch_id!==id) throw Error('Wrong legacy batch');p.batch_id=id;}
          await saveHistory(env,p,id,req.headers.get('X-EasyBosnian-Preserve-Artwork')==='true');return response({batch_id:id,date:p.date,status:'reviewed content saved'});
        }
      }
      const background=path.match(/^\/v1\/backgrounds\/batches\/(b-[a-f0-9]{32}|legacy-\d{4}-\d{2}-\d{2})\/(quiz|lesson|word)$/);
      if(background && req.method==='GET') return await savedBackground(env,background[1],background[2]);
      const diagnostic=path.match(/^\/v1\/generation-errors\/batches\/(b-[a-f0-9]{32}|legacy-\d{4}-\d{2}-\d{2})\/(r-[a-f0-9]{32})\/(quiz|lesson|word)$/);
      if(diagnostic && req.method==='GET') {
        const body=await env.IMAGES.get(`private-error:${diagnostic[1]}:${diagnostic[2]}:${diagnostic[3]}`);
        return body===null || body===undefined?response({error:'No private provider diagnostic'},404):new Response(body,{headers:{'Content-Type':'text/plain; charset=utf-8','Cache-Control':'no-store'}});
      }
      if(path==='/v1/generate' && req.method==='POST') {
        const p=await req.json();if(!KINDS.includes(p.kind) || (p.batch_id?!BATCH.test(p.batch_id):!DATE.test(p.date))) throw Error('Invalid artwork identity');
        let r,reviewed;
        if(p.reviewed_content!==undefined) {
          safePackage(p.reviewed_content,p.date);
          if(!BATCH.test(p.batch_id) || p.reviewed_content.batch_id!==p.batch_id || !/^r-[a-f0-9]{32}$/.test(p.artwork_id)) throw Error('Invalid staged artwork identity');
          const old=await row(env,p.batch_id);if(old && old.date!==p.date) throw Error('Wrong existing batch date');
          reviewed=p.reviewed_content;r={batch_id:p.batch_id,date:p.date};
        } else {
          r=await scope(env,p.batch_id || p.date,true);if(!r) return response({error:'No reviewed content'},404);
          reviewed=JSON.parse(r.content_json);
          if(p.artwork_id!==undefined) throw Error('Artwork run ID requires inline reviewed content');
        }
        if(p.date && p.date!==r.date) throw Error('Wrong content date');
        if(reviewed.cards.find(c=>c.kind===p.kind).background_prompt!==p.prompt) throw Error('Prompt differs from reviewed content');
        const key=p.reviewed_content!==undefined?`private-ai:${r.batch_id}:${p.artwork_id}:${p.kind}`:`private-ai:${r.batch_id}:${p.kind}`;let cached,result,upstream;
        try {cached=await imageValue(env,key,r.batch_id,r.date);}
        catch {return generationFailure('cache_read_failed');}
        if(cached) return response({image:cached});
        if(typeof env.AI?.run!=='function') return generationFailure('ai_binding_missing');
        // A per-call Response retains the upstream status without consulting the
        // binding's mutable lastRequest fields. Exactly one inference is sent.
        try {upstream=await env.AI.run('@cf/black-forest-labs/flux-1-schnell',{prompt:p.prompt,steps:4},{returnRawResponse:true});}
        catch(error) {return generationFailure('ai_call_failed',error);}
        if(!(upstream instanceof Response)) return generationFailure('ai_response_invalid');
        let rawBody;
        try {rawBody=await upstream.text();result=JSON.parse(rawBody);}
        catch {return generationFailure(upstream.ok?'ai_response_invalid':'ai_call_failed',null,upstream.status,await captureGenerationError(env,p,rawBody || ''));}
        if(!upstream.ok || result?.success===false) return generationFailure('ai_call_failed',result,upstream.status,await captureGenerationError(env,p,rawBody));
        if(typeof result?.image!=='string' || !result.image) return generationFailure('ai_image_missing',null,upstream.status);
        try {await env.IMAGES.put(key,result.image,{expirationTtl:14*86400});}
        catch {return generationFailure('cache_write_failed');}
        return response({image:result.image});
      }
      const asset=path.match(/^\/v1\/(private|expose)\/(?:batches\/)?(b-[a-f0-9]{32}|legacy-\d{4}-\d{2}-\d{2}|\d{4}-\d{2}-\d{2})\/(.+)$/);
      if(asset && NAME.test(asset[3])) {
        const [,kind,id,name]=asset,r=await stagedScope(env,id,req);if(!r) return response({error:'No reviewed content'},404);const key=`private:${r.batch_id}:${name}`;
        if(kind==='private' && req.method==='GET') {
          try {const data=await imageValue(env,key,r.batch_id,r.date,{type:'arrayBuffer',cacheTtl:30});return data?new Response(data,{headers:{'Content-Type':'image/jpeg','Cache-Control':'no-store'}}):response({error:'Asset not found'},404);}
          catch {return storageFailure('asset_read_failed',503,name);}
        }
        if(kind==='private' && req.method==='PUT') {
          try {const data=await req.arrayBuffer();if(!validJpeg(data)) return storageFailure('asset_invalid',400,name);await env.IMAGES.put(key,data,{expirationTtl:14*86400});return response({stored:true});}
          catch {return storageFailure('asset_write_failed',503,name);}
        }
        if(kind==='expose' && req.method==='POST' && (name.endsWith('-card.jpg') || name.endsWith('-story.jpg'))) {
          try {
            // New callers supply the exact renderer output, avoiding KV's
            // eventual consistency between private PUT and exposure. Retain
            // empty-body compatibility for previously deployed callers.
            let data=await req.arrayBuffer();
            if(data.byteLength) {
              if(req.headers.get('Content-Type')!=='image/jpeg' || !validJpeg(data)) return storageFailure('asset_invalid',400,name);
            } else {
              data=await imageValue(env,key,r.batch_id,r.date,{type:'arrayBuffer',cacheTtl:30});
              if(!data) return storageFailure('asset_not_visible',409,name);
            }
            const publicId=Array.from(crypto.getRandomValues(new Uint8Array(32)),x=>x.toString(16).padStart(2,'0')).join('');
            await env.IMAGES.put('public:'+publicId,data,{expirationTtl:14*86400});
            return response({url:url.origin+'/images/'+publicId+'.jpg'});
          } catch {return storageFailure('asset_exposure_failed',503,name);}
        }
      }
      return response({error:'Not found'},404);
    } catch {return response({error:'Operation failed; inspect content validity, provider status and free limits'},409);}
  },
  async scheduled(controller,env,ctx) {
    ctx.waitUntil(dailyPreparationDispatch(env,new Date(controller.scheduledTime)).catch(()=>{
      console.error(JSON.stringify({event:'preparation_cron_failed'}));
      throw Error('Scheduled preparation failed; inspect private gate and dispatch status logs; no automatic retry');
    }));
  }
};

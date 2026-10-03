import {privacy} from './privacy.mjs';
export const REPO='TifahEfendijaM/easybosnian-daily-uploads';
export const PROJECT='tifahefendijam-easybosnian-daily-uploads-v1';
const DATE=/^\d{4}-\d{2}-\d{2}$/,KINDS=['quiz','lesson','word'],NAME=/^(quiz|lesson|word)-(background|card|story)\.jpg$/;
const response=(data,status=200)=>Response.json(data,{status,headers:{'Cache-Control':'no-store'}});
async function row(env,date) {return env.DB.prepare('SELECT content_json FROM history WHERE date=?').bind(date).first();}
function safePackage(p,date) {
  if(p.project!==PROJECT || p.schema_version!==1 || !DATE.test(date) || p.date!==date || p.cards?.length!==3 || p.words?.length!==3) throw Error('Invalid content identity');
  if(p.cards.map(c=>c.kind).join(',')!=='quiz,lesson,word') throw Error('Invalid cards');
  for(const flag of ['standard_bosnian_checked','sources_checked','semantic_history_checked','no_answer_leak_checked']) if(p.private_review?.[flag]!==true) throw Error('Editorial checks incomplete');
  if(!p.theme.equivalence_keys?.length || !p.words.every(w=>w.equivalence_keys?.length)) throw Error('Equivalence metadata missing');
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
  try {result=await fetch(base+'/actions/workflows/preparation.yml/dispatches',{method:'POST',headers,redirect:'manual',signal:AbortSignal.timeout(15000),body:JSON.stringify({ref:'main',inputs:{mode}})});}
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
      const data=await env.IMAGES.get('public:'+publicAsset[1],{type:'arrayBuffer'});
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
        const r=await env.DB.prepare('SELECT date,theme_json,words_json,content_json FROM history ORDER BY date').all();
        return response({project:PROJECT,days:r.results.map(x=>({date:x.date,theme:JSON.parse(x.theme_json),words:JSON.parse(x.words_json),content:JSON.parse(x.content_json)}))});
      }
      const content=path.match(/^\/v1\/history\/(\d{4}-\d{2}-\d{2})$/);
      if(content) {
        const date=content[1];
        if(req.method==='GET') {const r=await row(env,date);return r?response(JSON.parse(r.content_json)):response({error:'No reviewed content for this date'},404);}
        if(req.method==='PUT') {
          const p=await req.json();safePackage(p,date);
          await env.DB.prepare('INSERT INTO history(date,theme_json,words_json,content_json) VALUES(?,?,?,?) ON CONFLICT(date) DO UPDATE SET theme_json=excluded.theme_json,words_json=excluded.words_json,content_json=excluded.content_json').bind(date,JSON.stringify(p.theme),JSON.stringify(p.words),JSON.stringify(p)).run();
          // Reviewed replacements invalidate date-only image caches.
          for(const kind of KINDS) {await env.IMAGES.delete(`private-ai:${date}:${kind}`);for(const suffix of ['background','card','story']) await env.IMAGES.delete(`private:${date}:${kind}-${suffix}.jpg`);}
          return response({date,status:'reviewed content saved'});
        }
      }
      if(path==='/v1/generate' && req.method==='POST') {
        const p=await req.json();if(!DATE.test(p.date) || !KINDS.includes(p.kind)) throw Error('Invalid artwork identity');
        const r=await row(env,p.date);if(!r) return response({error:'No reviewed content'},404);
        if(JSON.parse(r.content_json).cards.find(c=>c.kind===p.kind).background_prompt!==p.prompt) throw Error('Prompt differs from reviewed content');
        const key=`private-ai:${p.date}:${p.kind}`,cached=await env.IMAGES.get(key);if(cached) return response({image:cached});
        const result=await env.AI.run('@cf/black-forest-labs/flux-1-schnell',{prompt:p.prompt,steps:4});if(!result.image) throw Error('FLUX returned no image');
        await env.IMAGES.put(key,result.image,{expirationTtl:14*86400});return response({image:result.image});
      }
      const asset=path.match(/^\/v1\/(private|expose)\/(\d{4}-\d{2}-\d{2})\/(.+)$/);
      if(asset && NAME.test(asset[3])) {
        const [,kind,date,name]=asset;if(!await row(env,date)) return response({error:'No reviewed content'},404);const key=`private:${date}:${name}`;
        if(kind==='private' && req.method==='GET') {const data=await env.IMAGES.get(key,{type:'arrayBuffer'});return data?new Response(data,{headers:{'Content-Type':'image/jpeg','Cache-Control':'no-store'}}):response({error:'Asset not found'},404);}
        if(kind==='private' && req.method==='PUT') {const data=await req.arrayBuffer();if(data.byteLength>3_000_000 || data.byteLength<100 || new Uint8Array(data)[0]!==255 || new Uint8Array(data)[1]!==216) throw Error('Asset must be a JPEG below 3MB');await env.IMAGES.put(key,data,{expirationTtl:14*86400});return response({stored:true});}
        if(kind==='expose' && req.method==='POST' && (name.endsWith('-card.jpg') || name.endsWith('-story.jpg'))) {
          const data=await env.IMAGES.get(key,{type:'arrayBuffer'});if(!data) return response({error:'Rendered asset not visible in KV yet'},409);
          const id=Array.from(crypto.getRandomValues(new Uint8Array(32)),x=>x.toString(16).padStart(2,'0')).join('');await env.IMAGES.put('public:'+id,data,{expirationTtl:14*86400});return response({url:url.origin+'/images/'+id+'.jpg'});
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

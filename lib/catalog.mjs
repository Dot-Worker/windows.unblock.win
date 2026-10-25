export const defaults = {family:'',productId:'',language:'',architecture:'',q:'',sort:'default',view:'cards',page:1};
export const dimensions=['family','productId','language','architecture'];
export function parseState(search){const p=new URLSearchParams(search),s={...defaults}; for(const k of [...dimensions,'q'])s[k]=(p.get(k)||'').slice(0,400);s.sort=['default','name','date'].includes(p.get('sort'))?p.get('sort'):'default';s.view=p.get('view')==='table'?'table':'cards';s.page=Math.max(1,Math.min(100000,parseInt(p.get('page'),10)||1));return s;}
export function serializeState(s){const p=new URLSearchParams();for(const k of Object.keys(defaults))if(s[k]!==defaults[k]&&s[k]!==''&&s[k]!=null)p.set(k,s[k]);return p.toString();}
export function changeState(s,key,value){const next={...s,[key]:value,page:1};const i=dimensions.indexOf(key);if(i>=0)for(const k of dimensions.slice(i+1))next[k]='';return next;}
export function filterResources(rows,s){const terms=s.q.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean);return rows.filter(r=>dimensions.every(k=>!s[k]||r[k]===s[k])&&terms.every(t=>[r.title,r.filename,r.product,r.version,r.sha1,r.language,r.architecture].join(' ').toLocaleLowerCase().includes(t)));}
export function facetOptions(rows,s,key){const i=dimensions.indexOf(key),scope={...defaults};for(const k of dimensions.slice(0,i))scope[k]=s[k];const counts=new Map();for(const r of filterResources(rows,scope)){const value=r[key]||'Unknown';counts.set(value,(counts.get(value)||0)+1);}return [...counts].map(([value,count])=>({value,count}));}
export function normalizeState(rows,state){let s={...state};for(const key of dimensions)if(s[key]&&!facetOptions(rows,s,key).some(o=>o.value===s[key]))s=changeState(s,key,'');return s;}
export function sortResources(rows,sort){return [...rows].sort(sort==='name'?(a,b)=>(a.filename||a.title).localeCompare(b.filename||b.title):sort==='date'?(a,b)=>(b.publishedAt||'').localeCompare(a.publishedAt||''):()=>0);}
export function downloadAction(raw){if(typeof raw!=='string'||/[\u0000-\u001f\u007f]/.test(raw))return 'blocked';if(/^ed2k:\/\/\|file\|[^|]+\|\d+\|[a-f0-9]+\|/i.test(raw)||/^magnet:\?[^\s]+/i.test(raw))return 'copy';try{const u=new URL(raw);if((u.protocol==='https:'||u.protocol==='http:')&&u.hostname&&!u.username&&!u.password)return 'open';}catch{}return 'blocked';}

// Status is untrusted metadata, separate from both release dates and link validation.
export function statusTimestamp(value, now=Date.now()) {
  if(typeof value!=='string'||!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,3})?Z$/.test(value))return null;
  const time=Date.parse(value);
  if(!Number.isFinite(time)||time>now+300000)return null;
  if(new Date(time).toISOString().slice(0,19)!==value.slice(0,19))return null;
  return new Date(time).toISOString().replace('T',' ').slice(0,16)+' UTC';
}
export function workflowRunLink(value) {
  if(typeof value!=='string')return null;
  try{const u=new URL(value);return u.protocol==='https:'&&u.hostname==='github.com'&&!u.port&&!u.username&&!u.password&&!u.search&&!u.hash&&/^\/[\w-]+\/[\w.-]+\/actions\/runs\/[1-9]\d*$/.test(u.pathname)?u.href:null;}catch{return null;}
}
export function updateStatusView(meta={}, status, now=Date.now()) {
  const live=meta.sourceMode==='live-html';
  const valid=status&&status.schemaVersion===1&&['updated','unchanged','failed','not-run'].includes(status.status);
  const attempted=valid?statusTimestamp(status.attemptedAt,now):null;
  const checked=valid&&status.status!=='not-run'?statusTimestamp(status.checkedAt,now):null;
  const updated=valid&&status.status!=='not-run'?statusTimestamp(status.updatedAt,now):null;
  const consistent=checked&&attempted&&(status.status==='failed'?Date.parse(status.checkedAt)<=Date.parse(status.attemptedAt):Date.parse(status.checkedAt)>=Date.parse(status.attemptedAt));
  const lastGood=consistent?checked:null;
  const changed=lastGood&&updated&&Date.parse(status.updatedAt)<=Date.parse(status.checkedAt)?updated:null;
  const stale=!!lastGood&&now-Date.parse(status.checkedAt)>48*60*60*1000;
  const failed=valid&&status.status==='failed';
  const snapshot=typeof meta.sourceSnapshotDate==='string'&&/^\d{4}-\d{2}-\d{2}$/.test(meta.sourceSnapshotDate)?meta.sourceSnapshotDate:'日期未标注';
  const summary=failed?'自动采集失败 · 保留上次可用目录':live&&lastGood?(stale?'目录采集记录已超过 48 小时':'目录已自动采集'):live?'实时来源目录 · 采集状态未确认':`源快照 ${snapshot} · 尚未完成自动更新`;
  const lines=[live?'目录来源：www.imsdn.cn 实时页面采集':'当前目录：GitHub 历史快照（不是最新实时内容）',`最近成功采集：${lastGood||'暂无可确认记录'}`,`目录内容最后变更：${changed||'暂无可确认记录'}`];
  if(attempted)lines.push(`最近尝试：${attempted}${failed?'（失败）':valid&&status.status==='unchanged'?'（目录无变化）':''}`);
  if(stale)lines.push('最近成功采集距今超过 48 小时，请查看运行记录。');
  if(failed)lines.push('本次未替换目录，继续显示上次可用数据。');
  if(!valid)lines.push('更新状态暂不可用；不影响浏览已加载目录。');
  if(failed&&typeof status.error==='string'&&status.error.trim())lines.push('错误：'+status.error.slice(0,400));
  lines.push('采集时间不等于产品发布日期；下载链接、校验值与安全性仍未经独立验证。');
  return {summary,lines,warning:failed||stale,runUrl:valid?workflowRunLink(status.workflowRunUrl):null};
}

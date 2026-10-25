import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {statusTimestamp,workflowRunLink,updateStatusView} from '../lib/catalog.mjs';
const now=Date.parse('2026-10-25T19:00:00Z');
const meta={sourceMode:'live-html'};
const good={schemaVersion:1,status:'updated',attemptedAt:'2026-10-25T18:00:00Z',checkedAt:'2026-10-25T18:00:00Z',updatedAt:'2026-10-24T18:00:00Z',workflowRunUrl:'https://github.com/example/catalog/actions/runs/123'};
test('timestamps reject malformed, impossible and future values',()=>{
  for(const date of [null,42,'yesterday','2026-02-30T12:00:00Z','2026-10-25','2026-10-26T12:00:00Z','2026-10-25T12:00:00+08:00'])assert.equal(statusTimestamp(date,now),null);
  assert.equal(statusTimestamp(good.checkedAt,now),'2026-10-25 18:00 UTC');
});
test('snapshot and missing status never invent a successful collection date',()=>{
  for(const status of [null,{},[],{schemaVersion:1,status:'not-run',checkedAt:good.checkedAt}, {...good,schemaVersion:2}]){
    const view=updateStatusView({sourceSnapshotDate:'2025-10-09',importedAt:good.checkedAt},status,now);
    assert.match(view.summary,/2025-10-09.*尚未完成自动更新/);
    assert.ok(view.lines.includes('最近成功采集：暂无可确认记录'));
  }
});
test('live success separates collection from content change and release validation',()=>{
 const view=updateStatusView(meta,good,now);
 assert.equal(view.summary,'目录已自动采集');assert.equal(view.warning,false);
 assert.ok(view.lines.includes('最近成功采集：2026-10-25 18:00 UTC'));
 assert.ok(view.lines.includes('目录内容最后变更：2026-10-24 18:00 UTC'));
 assert.match(view.lines.at(-1),/不等于产品发布日期.*未经独立验证/);
 assert.equal(view.runUrl,good.workflowRunUrl);
});
test('stale and failed runs preserve last success and warn truthfully',()=>{
 const stale=updateStatusView(meta,{...good,attemptedAt:'2026-10-20T18:00:00Z',checkedAt:'2026-10-20T18:00:00Z',updatedAt:null},now);
 assert.equal(stale.warning,true);assert.match(stale.summary,/超过 48 小时/);
 const failed=updateStatusView(meta,{...good,status:'failed',error:'<img src=x onerror=alert(1)>'},now);
 assert.equal(failed.warning,true);assert.match(failed.summary,/失败.*保留/);assert.ok(failed.lines.includes('最近成功采集：2026-10-25 18:00 UTC'));
 const unordered=updateStatusView(meta,{...good,attemptedAt:'2026-10-25T18:01:00Z'},now);
 assert.ok(unordered.lines.includes('最近成功采集：暂无可确认记录'));
});
test('workflow links only permit exact HTTPS GitHub action-run paths',()=>{
 for(const url of ['javascript:alert(1)','https://github.com.evil.test/x/y/actions/runs/1','http://github.com/x/y/actions/runs/1','https://u@github.com/x/y/actions/runs/1','https://github.com/x/y/actions/runs/1?x=1','https://github.com/x/y/actions','https://github.com/x/y/actions/runs/1#x','https://github.com/x/y/actions/runs/0'])assert.equal(workflowRunLink(url),null);
 assert.equal(workflowRunLink(good.workflowRunUrl),good.workflowRunUrl);
});
test('status fetch is independent and UI renders untrusted strings as text, never markup',()=>{
 const source=readFileSync(new URL('../app.js',import.meta.url),'utf8');
 assert.match(source,/load\(\);\s*loadUpdateStatus\(\);/);
 assert.match(source,/catch\{updateStatus=null;\}/);
 assert.match(source,/for\(const line of view.lines\)content.append\(el\('p','',line\)\)/);
 assert.doesNotMatch(source,/innerHTML|insertAdjacentHTML/);
 const html=readFileSync(new URL('../index.html',import.meta.url),'utf8');
 assert.match(html,/<details id="update-info"/);
});

test('completion timestamps follow attempt start, while failures retain earlier success',()=>{
 const completed={...good,attemptedAt:'2026-10-25T18:00:00Z',checkedAt:'2026-10-25T18:04:00Z',updatedAt:'2026-10-25T18:04:00Z'};
 for(const status of ['updated','unchanged']){
  const view=updateStatusView(meta,{...completed,status},now);
  assert.equal(view.summary,'目录已自动采集');
  assert.ok(view.lines.includes('最近成功采集：2026-10-25 18:04 UTC'));
 }
 const failed=updateStatusView(meta,{...completed,status:'failed',attemptedAt:'2026-10-25T18:30:00Z'},now);
 assert.ok(failed.lines.includes('最近成功采集：2026-10-25 18:04 UTC'));
 assert.equal(failed.warning,true);
 for(const status of [{...completed,checkedAt:'2026-10-25T17:59:00Z'},{...completed,status:'failed'},{...completed,checkedAt:'2026-10-26T18:04:00Z'}]){
  assert.ok(updateStatusView(meta,status,now).lines.includes('最近成功采集：暂无可确认记录'));
 }
 const badChange=updateStatusView(meta,{...completed,updatedAt:'2026-10-25T18:05:00Z'},now);
 assert.ok(badChange.lines.includes('目录内容最后变更：暂无可确认记录'));
});

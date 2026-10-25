import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const html=readFileSync(new URL('../index.html',import.meta.url),'utf8');
const js=readFileSync(new URL('../app.js',import.meta.url),'utf8');
test('clipboard live status persists inside native dialog outside replaced detail content',()=>{const dialog=html.match(/<dialog\b[\s\S]*?<\/dialog>/)[0];assert.match(dialog,/<div id="detail-status"[^>]*role="status"[^>]*aria-live="polite"[^>]*aria-atomic="true"><\/div><div id="detail-content">/);});
test('clipboard feedback targets modal status, gates stale requests, and resets for new detail',()=>{const copy=js.slice(js.indexOf('async function copy('),js.indexOf('\nfunction syncUrl'));assert.match(copy,/request===clipboardRequest/);assert.match(copy,/generation===detailGeneration/);assert.match(copy,/\$\('details'\)\.open/);assert.match(copy,/\$\('detail-status'\)\.textContent='已复制到剪贴板'/);assert.doesNotMatch(copy,/toast\(/);assert.match(js,/function showDetails\(r\)\{detailGeneration\+\+;\$\('detail-status'\)\.textContent=''/);});

const css=readFileSync(new URL('../styles.css',import.meta.url),'utf8');
test('narrow table scrolls within container and closed mobile sidebar is not focusable',()=>{assert.match(css,/\.table-wrap table\{min-width:700px\}/);assert.match(css,/@media\(max-width:800px\)\{\.sidebar\{visibility:hidden\}\.sidebar\.open\{visibility:visible\}\}/);assert.match(js,/if\(wasOpen\)\$\('menu-toggle'\)\.focus\(\)/);});

test('mobile drawer has an accessible touch close control wired to centralized focus restoration',()=>{assert.match(html,/<button id="close-sidebar"[^>]*aria-label="关闭分类导航"/);assert.match(js,/\$\('close-sidebar'\)\.onclick=closeSidebar/);assert.match(js,/function closeSidebar\(\)/);assert.match(css,/\.close-sidebar\{display:none\}/);});

test('HTML loads fingerprinted assets and generated app uses colocated immutable dependencies',()=>{const style=html.match(/href="(\.\/assets\/styles\.[a-f0-9]{16}\.css)"/);const app=html.match(/src="(\.\/assets\/app\.[a-f0-9]{16}\.js)"/);assert.ok(style);assert.ok(app);const generated=readFileSync(new URL('../'+app[1],import.meta.url),'utf8');assert.match(generated,/from '\.\/catalog-lib\.[a-f0-9]{16}\.mjs'/);assert.match(generated,/fetch\(new URL\('\.\/catalog-data\.[a-f0-9]{16}\.json', import\.meta\.url\)\)/);});

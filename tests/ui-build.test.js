import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync,existsSync,mkdtempSync,mkdirSync,copyFileSync,appendFileSync,rmSync,readdirSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join,dirname} from 'node:path';
import {fileURLToPath} from 'node:url';
import {spawnSync} from 'node:child_process';
const root=fileURLToPath(new URL('../',import.meta.url));
const run=(cwd,...args)=>spawnSync('python3',['scripts/build_assets.py',...args],{cwd,encoding:'utf8'});
test('published generated assets match current authored sources',()=>{const result=run(root,'--check');assert.equal(result.status,0,result.stderr);});
test('build is deterministic, detects stale sources, and retains previous immutable assets',()=>{const dir=mkdtempSync(join(tmpdir(),'catalog-build-'));try{for(const path of ['scripts/build_assets.py','index.html','app.js','styles.css','lib/catalog.mjs','data/catalog.json']){mkdirSync(dirname(join(dir,path)),{recursive:true});copyFileSync(join(root,path),join(dir,path));}assert.equal(run(dir).status,0);const before=readFileSync(join(dir,'index.html'),'utf8');const assets=readdirSync(join(dir,'assets'));assert.equal(run(dir).status,0);assert.equal(readFileSync(join(dir,'index.html'),'utf8'),before);assert.equal(run(dir,'--check').status,0);appendFileSync(join(dir,'styles.css'),'\n/* test change */\n');assert.equal(run(dir,'--check').status,1);assert.equal(run(dir).status,0);assert.notEqual(readFileSync(join(dir,'index.html'),'utf8'),before);for(const asset of assets)assert.ok(readdirSync(join(dir,'assets')).includes(asset));assert.equal(run(dir,'--check').status,0);}finally{rmSync(dir,{recursive:true,force:true});}});

test('generated catalog provenance pointer resolves while authored catalog stays canonical',()=>{const html=readFileSync(join(root,'index.html'),'utf8');const appPath=html.match(/src="\.\/(assets\/app\.[a-f0-9]+\.js)"/)[1];const app=readFileSync(join(root,appPath),'utf8');const dataPath=app.match(/new URL\('\.\/(catalog-data\.[a-f0-9]+\.json)'/)[1];const generated=JSON.parse(readFileSync(join(root,'assets',dataPath),'utf8'));assert.equal(generated.meta.provenanceFile,'../data/provenance.json');assert.ok(existsSync(join(root,'assets',generated.meta.provenanceFile)));const source=JSON.parse(readFileSync(join(root,'data/catalog.json'),'utf8'));assert.equal(source.meta.provenanceFile,'provenance.json');generated.meta.provenanceFile=source.meta.provenanceFile;assert.deepEqual(generated,source);});

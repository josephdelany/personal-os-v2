const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { queue } = require('../device/scriptable/PersonalOSQueue.js');
const meta = { captured_at: '2026-09-22T12:00:00Z', duration_s: 3.5, kind: 'food' };
const config = { endpoint: 'https://fixture.example.workers.dev/capture', token: 'fixture' };
function setup(t, mode = 'offline') {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'capture-device-'));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const fm = { joinPath: path.join, createDirectory: p => fs.mkdirSync(p,{recursive:true}),
    fileExists: fs.existsSync, listContents: fs.readdirSync, readString: p => fs.readFileSync(p,'utf8'),
    writeString: fs.writeFileSync, read: fs.readFileSync, remove: fs.unlinkSync, move: fs.renameSync,
    copy: (a,b) => fs.copyFileSync(a,b,fs.constants.COPYFILE_EXCL) };
  let seq=0;
  const requests=[];
  const platform = { fm, root, randomUUID: () => `00000000-0000-4000-8000-${String(++seq).padStart(12,'0')}`,
    timer: (ms, fn) => { assert.equal(ms,10000); const id=setTimeout(fn,5);return {invalidate:()=>clearTimeout(id)}; },
    request: url => { const req={ response: {statusCode: mode==='created'?202:200}, async loadJSON() {
      requests.push(this);
      assert.equal(this.timeoutInterval,10);assert.equal(this.onRedirect(),null);
      assert.equal(this.body.toString(),'fixture audio');
      if(mode==='offline') throw new Error('private error');
      if(mode==='late') { await new Promise(resolve=>setTimeout(resolve,20)); }
      return {capture_id: mode==='wrong'?'wrong':this.headers['X-Capture-ID'],
        status: mode==='upload'?'available':'duplicate'};
    }}; return req; } };
  const source=path.join(root,'source');fs.writeFileSync(source,'fixture audio');
  return {root,source,requests,q:queue(platform),platform};
}
test('REQ_CAP_018_019 saves recording and UUIDv7 before offline request', async t => {
  const {q,source,root,requests}=setup(t);
  const cid=q.save(source,meta);
  assert.match(cid,/^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-8[0-9a-f]{3}-[0-9a-f]{12}$/);
  assert.equal(parseInt(cid.slice(0,8)+cid.slice(9,13),16),Date.parse(meta.captured_at));
  assert.equal((await q.submit(cid,config)).status,'queued');
  assert.ok(fs.existsSync(path.join(root,'pending',cid+'.jsonl')));
  assert.ok(fs.existsSync(source));assert.equal(requests.length,1);
});
for(const mode of ['wrong','upload','late']) test(`REQ_CAP_019_020 ${mode} acknowledgement retains queue`,async t=>{
  const {q,source,root}=setup(t,mode);const cid=q.save(source,meta);
  assert.equal((await q.submit(cid,config)).status,'queued');
  await new Promise(resolve=>setTimeout(resolve,25));
  assert.ok(fs.existsSync(path.join(root,'pending',cid+'.jsonl')));
});
test('REQ_CAP_020 replay retains original identity and bytes, removes only acknowledged line',async t=>{
  const {q,source,root,platform}=setup(t);const cid=q.save(source,meta);
  await q.submit(cid,config);
  const seen=[];
  platform.request=()=>({response:{statusCode:200},async loadJSON(){seen.push(this.headers['X-Capture-ID']);
    assert.equal(this.body.toString(),'fixture audio');return {capture_id:cid,status:'duplicate'};}});
  const result=await queue(platform).replay(config);
  assert.deepEqual(result,{acknowledged:1,pending:0,recovery_errors:0});assert.deepEqual(seen,[cid]);
  assert.ok(fs.existsSync(path.join(root,'media',cid)));
  assert.ok(fs.existsSync(path.join(root,'manifests',cid+'.jsonl')));
});
test('REQ_CAP_019 recovery publishes manifest after interrupted queue publication',t=>{
  const {q,source,root,platform}=setup(t);const cid=q.save(source,meta);
  fs.unlinkSync(path.join(root,'pending',cid+'.jsonl'));
  queue(platform).recover();assert.ok(fs.existsSync(path.join(root,'pending',cid+'.jsonl')));
});
test('REQ_CAP_009 missing or unapproved endpoint never sends retained recording',async t=>{
  const {q,source,requests}=setup(t,'created');const cid=q.save(source,meta);
  assert.equal((await q.submit(cid,{...config,endpoint:'https://third-party.invalid/capture'})).status,'queued');
  assert.equal(requests.length,0);
});

test('REQ_CAP_019 actual Scriptable entrypoint returns queued silently after network failure',async t=>{
  const {source,platform,root}=setup(t);
  const vm=require('node:vm');
  let output,completed=false;
  const context=vm.createContext({
    importModule: name=>{assert.equal(name,'PersonalOSQueue');return require('../device/scriptable/PersonalOSQueue.js');},
    FileManager:{local:()=>({...platform.fm,documentsDirectory:()=>root})},
    UUID:{string:platform.randomUUID}, Request:function(url){return platform.request(url);},
    Timer:{schedule:(ms,repeats,fn)=>{assert.equal(repeats,false);return platform.timer(ms,fn);}},
    args:{shortcutParameter:meta,fileURLs:[source]},
    Keychain:{contains:()=>true,get:()=>JSON.stringify(config)},
    Script:{setShortcutOutput:value=>{output=value;},complete:()=>{completed=true;}},
  });
  const script=fs.readFileSync('device/scriptable/PersonalOSCapture.js','utf8');
  await vm.runInContext(`(async()=>{${script}\n})()`,context);
  assert.equal(completed,true);assert.equal(output.status,'queued');
  assert.ok(fs.existsSync(source));
});


test('REQ_CAP_019_020 repairs torn publications from validated saved metadata',t=>{
  const {q,source,root,platform}=setup(t);const cid=q.save(source,meta);
  for(const folder of ['manifests','pending']) fs.writeFileSync(path.join(root,folder,cid+'.jsonl'),'{broken');
  assert.equal(queue(platform).recover(),0);
  for(const folder of ['manifests','pending']) assert.equal(JSON.parse(fs.readFileSync(path.join(root,folder,cid+'.jsonl'),'utf8')).capture_id,cid);
});
test('REQ_CAP_019 unrecoverable metadata is counted and never sent',async t=>{
  const {q,source,root,platform,requests}=setup(t);const cid=q.save(source,meta);
  for(const folder of ['staging','manifests','pending']) fs.writeFileSync(path.join(root,folder,cid+'.jsonl'),'{broken');
  assert.equal((await queue(platform).replay(config)).recovery_errors,1);
  assert.equal(requests.length,0);assert.ok(fs.existsSync(source));
});

test('REQ_CAP_020 conflicting pending metadata is retained but never sent',async t=>{
  const {q,source,root,platform,requests}=setup(t,'created');const cid=q.save(source,meta);
  const pending=path.join(root,'pending',cid+'.jsonl');const record=JSON.parse(fs.readFileSync(pending,'utf8'));
  record.metadata.duration_s=999;fs.writeFileSync(pending,JSON.stringify(record)+'\n');
  assert.equal((await queue(platform).replay(config)).recovery_errors,1);
  assert.equal(requests.length,0);assert.ok(fs.existsSync(pending));
});
test('REQ_CAP_020 torn acknowledgement is repaired only after another matching raw receipt',async t=>{
  const {q,source,root}=setup(t,'created');const cid=q.save(source,meta);
  const ack=path.join(root,'acknowledged',cid+'.jsonl');fs.writeFileSync(ack,'{broken');
  assert.equal((await q.submit(cid,config)).status,'acknowledged');
  assert.equal(JSON.parse(fs.readFileSync(ack,'utf8')).capture_id,cid);
  assert.equal(fs.existsSync(path.join(root,'pending',cid+'.jsonl')),false);
});
test('REQ_CAP_019 missing file does not claim source retention',async t=>{
  const {platform,root}=setup(t);const vm=require('node:vm');let output;
  const context=vm.createContext({importModule:()=>require('../device/scriptable/PersonalOSQueue.js'),
    FileManager:{local:()=>({...platform.fm,documentsDirectory:()=>root})},
    args:{shortcutParameter:meta,fileURLs:[]},
    Script:{setShortcutOutput:value=>{output=value;},complete:()=>{}},
  });
  const script=fs.readFileSync('device/scriptable/PersonalOSCapture.js','utf8');
  await vm.runInContext(`(async()=>{${script}\n})()`,context);
  assert.equal(output.status,'unconfirmed');
});

test('REQ_CAP_019 interrupted metadata save reports orphan media without inventing a payload',async t=>{
  const {q,source,root,platform,requests}=setup(t);const cid=q.save(source,meta);
  for(const folder of ['staging','manifests','pending']) fs.unlinkSync(path.join(root,folder,cid+'.jsonl'));
  assert.deepEqual(await queue(platform).replay(config),{acknowledged:0,pending:0,recovery_errors:1});
  assert.equal(requests.length,0);assert.ok(fs.existsSync(path.join(root,'media',cid)));
});

test('REQ_CAP_006_011_018_020 device queue traverses actual combined Worker before removal',async t=>{
  const {source,root,platform}=setup(t);
  const {default:worker}=await import('../workers/capture-media/index.mjs');
  const jwt=role=>`fixture.${btoa(JSON.stringify({role}))}.fixture`;
  const env={CAPTURE_TOKEN:config.token,SUPABASE_URL:'https://fixture.supabase.co',
    SUPABASE_MEDIA_UPLOAD_JWT:jwt('capture_media_upload'),SUPABASE_ANON_KEY:jwt('anon'),
    SUPABASE_CAPTURE_JWT:jwt('capture_ingest')};
  let manifest,raw;
  const original=globalThis.fetch;
  t.after(()=>{globalThis.fetch=original;});
  globalThis.fetch=async(url,options)=>{
    const commit=body=>Response.json(body,{headers:{'preference-applied':'tx=commit'}});
    if(url.pathname.endsWith('begin_capture_media_upload')) {
      const args=JSON.parse(options.body);
      manifest={capture_id:args.p_capture_id,media_path:args.p_capture_id+'/audio',
        media_sha256:args.p_sha256,size_bytes:args.p_size,status:'awaiting_upload'};
      return commit(manifest);
    }
    if(url.pathname.includes('/storage/')) {
      assert.equal(new TextDecoder().decode(options.body),'fixture audio');
      return Response.json({Key:'captures/'+manifest.media_path});
    }
    if(url.pathname.endsWith('complete_capture_media_upload')) return commit({...manifest,status:'available'});
    assert.ok(url.pathname.endsWith('receive_capture'));
    raw=JSON.parse(JSON.parse(options.body).p_raw_body);
    return commit({capture_id:raw.capture_id,status:'created'});
  };
  platform.request=url=>({async loadJSON(){
    const response=await worker.fetch(new Request(url,{method:this.method,headers:this.headers,body:this.body}),env,{});
    this.response={statusCode:response.status};return response.json();
  }});
  platform.timer=(ms,fn)=>{const id=setTimeout(fn,ms);return{invalidate:()=>clearTimeout(id)};};
  const q=queue(platform),cid=q.save(source,meta);
  assert.equal((await q.submit(cid,config)).status,'acknowledged');
  assert.equal(raw.capture_id,cid);assert.equal(raw.captured_at,meta.captured_at);
  assert.equal(raw.payload.media_sha256,manifest.media_sha256);
  assert.equal(raw.payload.duration_s,meta.duration_s);
  assert.equal(fs.existsSync(path.join(root,'pending',cid+'.jsonl')),false);
  assert.ok(fs.existsSync(path.join(root,'media',cid)));
});

test('REQ_CAP_009 actual setup stores one coupled config without sending or printing token',async()=>{
  const vm=require('node:vm');
  const script=fs.readFileSync('device/scriptable/PersonalOSSetup.js','utf8');
  for(const choice of [-1,0]) {
    const writes=[];let output;
    class Alert {addTextField(){}addSecureTextField(){this.secure=true;}addAction(){}addCancelAction(){}
      async presentAlert(){assert.equal(this.secure,true);return choice;}
      textFieldValue(index){return index===0?config.endpoint:config.token;}}
    await vm.runInNewContext(`(async()=>{${script}\n})()`,{Alert,
      Keychain:{set:(key,value)=>writes.push([key,JSON.parse(value)])},
      Script:{setShortcutOutput:value=>{output=value;},complete:()=>{}}});
    assert.equal(writes.length,choice===0?1:0);
    if(choice===0) assert.deepEqual(writes,[['personal-os.capture.config',config]]);
    assert.ok(!JSON.stringify(output).includes(config.token));
  }
});

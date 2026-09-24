import test from 'node:test';
import assert from 'node:assert/strict';
import {createV0Client} from '../tools/v0_client.mjs';

test('RULE-02 retry preserves the complete request after uncertain delivery',async()=>{
  const calls=[]; let attempt=0;
  const client=createV0Client({rpc:async(name,args)=>{
    calls.push({name,args:structuredClone(args)});
    if (++attempt===1) throw new Error('private server error');
    return {data:{status:'saved',entry_id:args.p_request.entry_id}};
  }});
  const request={entry_id:'retained-id',supersedes:null,text:'original'};
  const operation=client.prepare('meal',request);request.text='changed';
  assert.deepEqual(await operation.send(),{status:'unconfirmed',retry:'same_request'});
  assert.equal((await operation.send()).status,'saved');
  assert.deepEqual(calls[0],calls[1]);assert.equal(calls[0].args.p_request.text,'original');
});
test('RULE-06 timeout is not success and late completion cannot replace the retry receipt',async()=>{
  let finish;let n=0;
  const client=createV0Client({timeoutMs:5,rpc:()=> ++n===1 ? new Promise(r=>finish=r) :
    Promise.resolve({data:{status:'saved',entry_id:'same',recorded_at:'retry'}})});
  const operation=client.prepare('checkin',{entry_id:'same'});
  assert.equal((await operation.send()).status,'unconfirmed');
  assert.equal((await operation.send()).receipt.recorded_at,'retry');
  finish({data:{status:'saved',entry_id:'same',recorded_at:'late'}});
  await new Promise(r=>setTimeout(r,0));assert.equal(operation.receipt().recorded_at,'retry');
});
test('RULE-02 concurrent sends share one request and mismatched receipt refuses',async()=>{
  let calls=0;
  const client=createV0Client({rpc:async()=>{calls++;return {data:{status:'saved',entry_id:'wrong'}};}});
  const operation=client.prepare('workout',{entry_id:'correct'});
  const a=operation.send(),b=operation.send();assert.equal(a,b);
  assert.equal((await a).status,'unconfirmed');assert.equal(calls,1);
});
test('RULE-10 correction passes predecessor; read failure does not erase saved receipt',async()=>{
  const client=createV0Client({rpc:async(name,args)=>{
    if(name==='get_v0_day') return {error:{message:'private'}};
    assert.equal(args.p_request.supersedes,'previous');
    return {data:{status:'saved',entry_id:'new'}};
  }});
  const op=client.prepare('checkin',{entry_id:'new',supersedes:'previous'});
  await op.send();assert.equal((await client.read('day')).status,'unavailable');
  assert.equal(op.receipt().entry_id,'new');
});
test('RULE-06 missing data stays missing and card decisions retain identity',async()=>{
  const client=createV0Client({rpc:async(name,args)=>name==='review_v0_card_row' ?
    {data:{status:'saved',decision_id:args.p_request.decision_id}} : {data:{entries:[],last_received:null}}});
  assert.deepEqual((await client.read('meals')).data,{entries:[],last_received:null});
  assert.equal((await client.prepare('card_review',{decision_id:'decision'}).send()).status,'saved');
});

test('RULE-06 nonfinite nullable fields refuse without sending',()=>{
  let calls=0;const client=createV0Client({rpc:()=>calls++});
  for(const rpe of [NaN,Infinity,undefined])
    assert.throws(()=>client.prepare('workout',{entry_id:'id',rpe}),/JSON/);
  assert.equal(calls,0);
});
test('RULE-10 explicit stale correction refusal requires reload, not same-request loop',async()=>{
  const client=createV0Client({rpc:async()=>({error:{code:'P0001',message:'private'}})});
  const op=client.prepare('meal',{entry_id:'id',supersedes:'old'});
  assert.deepEqual(await op.send(),{status:'rejected',recovery:'reload_and_review'});
  assert.equal(op.request().supersedes,'old');assert.equal(op.receipt(),null);
});

test('RULE-02 earlier uncertain commit survives a later permission refusal',async()=>{
  let attempt=0;
  const client=createV0Client({timeoutMs:5,rpc:()=> ++attempt===1 ? new Promise(()=>{}) :
    Promise.resolve({error:{code:'42501'}})});
  const op=client.prepare('meal',{entry_id:'retained'});
  assert.equal((await op.send()).status,'unconfirmed');
  assert.deepEqual(await op.send(),{status:'unconfirmed',retry:'same_request',recovery:'sign_in'});
  assert.equal(op.request().entry_id,'retained');
});

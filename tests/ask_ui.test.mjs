import test from 'node:test';
import assert from 'node:assert/strict';
import {mountAsk, renderAnswer} from '../app/ask.mjs';

function harness(rpc, timeoutMs) {
  let submit;
  const input = {value:'how is my sleep'}, date = {value:''}, button = {};
  const output = {innerHTML:'',textContent:''};
  const form = {addEventListener: (_name, handler) => { submit = handler; }};
  const controller = mountAsk({form,input,date,button,output,rpc,timeoutMs});
  return {input,date,button,output,...controller,submit: () => submit({preventDefault(){}})};
}

test('REQ-ASK-010 RULE-14 renders stored answers and escapes source text', () => {
  const html = renderAnswer({answer_text:'Stored 7 h <script>alert(1)</script>',tier:'DESCRIPTIVE',
    result:{unit:'h',low:6,high:8},coverage:null});
  assert.ok(html.includes('Stored 7 h &lt;script&gt;'));
  assert.ok(!html.includes('<script>'));
  assert.ok(html.includes('DESCRIPTIVE'));
  assert.ok(html.includes('&quot;coverage&quot;: null'));
  assert.throws(() => renderAnswer({result:{value:7}}), /Missing answer/);
});

test('REQ-ASK-003 sends owner RPC parameters and renders insufficiency', async () => {
  const h = harness(async (name, args) => {
    assert.equal(name,'ask');
    assert.deepEqual(args,{p_question:'how is my sleep',p_as_of:null});
    return {data:{refusal:'Not enough observations',tier:'INSUFFICIENT',would_raise_it:'Record more nights.'}};
  });
  await h.submit();
  assert.ok(h.output.innerHTML.includes('Not enough observations'));
  assert.ok(h.output.innerHTML.includes('Record more nights.'));
  assert.equal(h.button.disabled,false);
});

test('REQ-ASK-003 failures are not displayed as missing records or raw server errors', async () => {
  const h = harness(async () => ({error:{message:'private internal error'}}));
  await h.submit();
  assert.ok(h.output.textContent.includes('does not mean your records are empty'));
  assert.ok(!h.output.textContent.includes('private internal'));
  assert.equal(h.button.disabled,false);
});

test('REQ-ASK-003 duplicate submits suppressed and sign-out discards pending answer', async () => {
  let finish, calls=0;
  const h = harness(() => { calls++; return new Promise(resolve => {finish=resolve;}); });
  const pending=h.submit();
  await h.submit();
  assert.equal(calls,1);
  h.reset();
  finish({data:{answer_text:'private answer'}});
  await pending;
  assert.equal(h.output.innerHTML,'');
  assert.equal(h.input.value,'');
});

test('REQ-ASK-003 stalled request releases controls without replaying or accepting late answer', async () => {
  let finish, calls=0;
  const h=harness(() => { calls++; return new Promise(resolve => {finish=resolve;}); },5);
  await h.submit();
  assert.equal(h.button.disabled,false);
  assert.ok(h.output.textContent.includes('may still have been saved'));
  finish({data:{answer_text:'late answer'}});
  await new Promise(resolve => setTimeout(resolve,0));
  assert.equal(h.output.innerHTML,'');
  assert.equal(calls,1);
});

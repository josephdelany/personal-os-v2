// V0 owner API adapter. No network, storage, credentials or UI owned here.
// Supply rpc: (name, args) => signedInSupabase.rpc(name, args).
const writers = Object.freeze({checkin:'save_v0_checkin',meal:'save_v0_meal',
  workout:'save_v0_workout',card_review:'review_v0_card_row'});
const readers = Object.freeze({day:'get_v0_day',checkins:'get_v0_checkins',
  meals:'get_v0_meals',workouts:'get_v0_workouts',visits:'get_v0_visits',
  card_activity:'get_v0_card_activity'});
function validateJSON(value) {
  if (value===null || typeof value==='string' || typeof value==='boolean') return;
  if (typeof value==='number' && Number.isFinite(value)) return;
  if (typeof value!=='object' || (!Array.isArray(value) && Object.getPrototypeOf(value)!==Object.prototype))
    throw new TypeError('Plain JSON values required');
  for (const item of Array.isArray(value) ? Array.from(value) : Object.values(value)) validateJSON(item);
}
const clone = value => {validateJSON(value);return JSON.parse(JSON.stringify(value));};
export function createV0Client({rpc, timeoutMs=10000}) {
  if (typeof rpc !== 'function' || !Number.isFinite(timeoutMs) || timeoutMs<=0)
    throw new TypeError('RPC and positive timeout required');
  async function invoke(name,args) {
    let timer;
    try {
      const result = await Promise.race([
        Promise.resolve().then(() => rpc(name,clone(args))),
        new Promise((_,reject) => {timer=setTimeout(() => reject(new Error()),timeoutMs);})
      ]);
      if (result?.error) {
        // Known PostgreSQL validation/permission refusals did not commit the RPC.
        const code=result.error.code;
        const rejected=typeof code==='string' && /^(P0001|42501|22[A-Z0-9]{3}|23[A-Z0-9]{3})$/.test(code);
        return {ok:false,rejected,recovery:code==='42501'?'sign_in':'reload_and_review'};
      }
      const data = typeof result?.data === 'string' ? JSON.parse(result.data) : result?.data;
      if (!data || typeof data!=='object' || Array.isArray(data)) return {ok:false};
      return {ok:true,data:clone(data)};
    } catch {return {ok:false};}
    finally {clearTimeout(timer);}
  }
  function prepare(kind,request) {
    if (!Object.hasOwn(writers,kind)) throw new TypeError('Unknown V0 write');
    // Snapshot before any asynchronous work; never generate another identity on retry.
    const frozen=clone(request);
    const idKey=kind==='card_review'?'decision_id':'entry_id';
    if (!frozen || typeof frozen[idKey]!=='string' || !frozen[idKey])
      throw new TypeError('Retained request identity required');
    let pending=null, receipt=null, uncertain=false;
    return Object.freeze({
      request: () => clone(frozen),
      receipt: () => receipt===null ? null : clone(receipt),
      send() {
        if (receipt) return Promise.resolve({status:'saved',receipt:clone(receipt)});
        if (pending) return pending;
        pending=(async () => {
          const result=await invoke(writers[kind],{p_request:frozen});
          if (result.rejected) return uncertain
            ? {status:'unconfirmed',retry:'same_request',recovery:result.recovery}
            : {status:'rejected',recovery:result.recovery};
          if (!result.ok || result.data.status!=='saved' || result.data[idKey]!==frozen[idKey])
            {uncertain=true;return {status:'unconfirmed',retry:'same_request'};}
          receipt=clone(result.data);
          return {status:'saved',receipt:clone(receipt)};
        })().finally(() => {pending=null;});
        return pending;
      }
    });
  }
  async function read(kind,args={p_day:null}) {
    if (!Object.hasOwn(readers,kind)) throw new TypeError('Unknown V0 read');
    const result=await invoke(readers[kind],args);
    return result.ok ? {status:'available',data:result.data} : {status:'unavailable',retry:'read'};
  }
  return Object.freeze({prepare,read});
}

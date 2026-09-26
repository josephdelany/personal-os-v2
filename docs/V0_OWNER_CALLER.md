# Executable V0 owner API caller

`app/v0_client.mjs` has no dependencies or UI. Inject the existing signed-in
Supabase client's RPC method. It does not acquire credentials or bypass owner checks.

```javascript
import {createV0Client} from './app/v0_client.mjs';
const v0 = createV0Client({rpc: (name,args) => supabase.rpc(name,args)});
const operation = v0.prepare('meal', ownerSuppliedRequest);
// Persist operation.request() privately BEFORE sending; includes the original UUIDv7.
const outcome = await operation.send();
// 'saved' has a matching receipt. 'unconfirmed' retains the same request for retry.
const history = await v0.read('day', {p_day: selectedDay});
```

The example variables must come from real owner input and the authenticated session.
Prepare supports checkin, meal, workout and card_review. Read supports day, checkins,
meals, workouts, visits and card_activity (the last takes p_account/p_start/p_end).
Use the exact request fields documented in CAPTURE_RUNTIME and V0_CARD_IMPORT.
Corrections use a fresh identity and the current predecessor in supersedes.

The caller snapshots requests, coalesces concurrent sends of one operation and
confirms only a matching saved receipt. A ten-second timeout does not cancel a
server commit; retry the identical request. Receipts survive independent read
failures. Errors never become empty successful days. No raw server errors are
returned or logged. An unavailable read can be retried independently.

Persistence belongs to the consuming application: this module alone does not
survive a reload. Recreate the operation using the privately retained complete
request after restart. Never regenerate its ID on retry. The frontend must present
recoverable errors and retain drafts before sending. Known database validation/constraint refusals return rejected with reload_and_review;
permission refusal returns sign_in. After an uncertain send, a later refusal
retains unconfirmed/same_request and adds the recovery action: it cannot prove
the earlier send did not commit. Unknown errors remain unconfirmed. Reread
current entries before making a corrected new request. This is not an
automatic retry loop. Photo capture/upload remains the approved Shortcut path.

Local injected-transport tests cover response loss, late completion, duplicate
clicks, mismatched receipts, correction identity, missing data and save/read failure
separation. They do not prove HTTP authentication or production persistence; the
real-account cases in V0_BACKEND_ACTIVATION remain required.

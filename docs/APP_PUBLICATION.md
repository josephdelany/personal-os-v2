# App-only publication packet — approval pending

Prepared from release/usable-ask at a74355c, based on remote main b606c64.
Worktree: `.local/usable-app-release`. No commands below have been executed.

## Why the original main push is withdrawn

The main-branch tests workflow triggers on every main push and uses the production
SUPABASE_DB_URL. Its old test fixtures apply migrations without the modern disposable
server guard. An app update must not trigger those legacy database tests. Do not push
the release to main, disable its tests or push the unfinished root backend branch.

Read-only GitHub inspection also found that the github-pages environment allows only
main. A release-branch deployment therefore needs explicit approval to add precisely
release/usable-ask to that environment's allowed branches. Retain the existing main
policy; do not allow all branches or disable environment protection.

## Exact proposed authorized action

1. Recheck the local release SHA and verify no remote branch of this name has appeared.
2. Push `git push origin release/usable-ask:release/usable-ask` (no force).
3. Add one Pages environment branch policy:
   `gh api --method POST repos/josephdelany/personal-os-v2/environments/github-pages/deployment-branch-policies -f name=release/usable-ask -f type=branch`
4. Run only the app workflow:
   `gh workflow run pages.yml --repo josephdelany/personal-os-v2 --ref release/usable-ask`
5. Observe the workflow for this exact commit and fetch the served index/ask module;
   compare content with the release. Report failed jobs without claiming publication.
6. Verify owner sign-in and useful real-data reads/answers through the normal app.
   Do not extract browser tokens or send login emails without Joe's instruction.

The branch push runs the existing layout/guard checks. It does not match main's
database test trigger, and the scheduled analysis/extract jobs are not dispatched.
Pages runs the five Ask interaction tests before artifact upload. Publication changes
browser code, not database schema. Ask's deployed RPC compatibility is still unknown;
it cannot be established from the public API documentation endpoint because that
endpoint refused the anon key with a service-role-only message. Authentication
settings did return200 and report email enabled. No owner sign-in has been observed.

## Evidence

- Five Node interaction tests pass on the isolated release.
- Real Chrome offline mobile test passes guided sign-in, Ask, evidence, failure
  recovery and sign-out; no email or database requests are made by those fixtures.
- Isolated release layout:41pass/1warning (pre-existing absent local settings file);
  destructive-command guard:26pass. Root layout43pass is a different revision.
- Live page bytes match the original remote main app, so the app-only diff does
  not discard an unaccounted deployed interface.
- Independent app review found no blocker; stalled requests now release controls
  without automatic replay. Real-data usability remains unverified.

Production authorization is required by CLAUDE.md. Approval of this packet covers
the named branch publication, one environment policy addition and Pages dispatch;
it does not authorize database migrations, main updates or backend rollout.

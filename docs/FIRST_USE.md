# Open Personal OS

Open [Personal OS](https://josephdelany.github.io/personal-os-v2/) in your browser.
Enter your owner email, choose **Send magic link**, and open the email link in the
same browser. Keep passwords, login links and tokens out of chat.

The existing live app has daily records and a timeline. Choose a date with recorded
history and select **Day** or **Timeline**. Empty results for a recent date do not
prove old records are missing; some sources have stopped updating. **Trust** exposes
available coverage and job information. A successful page load is not proof that
these backend reads work; owner sign-in and real-data acceptance are still pending.

## Ask update — locally tested, not published

The pending update adds **Ask about your records** after sign-in. Type a question
such as “how is my sleep” or “how many steps last week”. Leave **As of** empty for
the backend's default date, or select a historical date. Answers show the stored
evidence level and expand to their data/source envelope. Insufficient evidence is
an answer; a connection failure is shown separately. No camera or voice setup is
required to ask about existing records.

Ask uses the existing owner-only backend and saves the question and computation.
It requires the deployed public.ask(text,date) RPC and its dependencies. Its live
availability has not been established. The unchanged production DB authentication
hold must be resolved through normal secret configuration before database-based
deployment verification; never paste that credential in chat.

## Verification and publication checkpoint

- Public page fetched successfully on 2026-09-23; it does not yet contain Ask.
- Latest reported successful Pages run: [33582668335](https://github.com/josephdelany/personal-os-v2/actions/runs/33582668335), revision c697efb8581dc854a8af2f2bf3127fbfceff40b9 on main.
- Current default branch reported by GitHub: v2-day1. Pending workflow change adds
  that branch while preserving main and runs Ask interaction tests before upload.
- Five Node interaction tests passed, including a stalled-request deadline. Offline real Chrome test at phone width
  passed sign-in visibility, question submission, evidence display, failure recovery
  and sign-out. Fixtures never reach a database. Live authentication remains unproven.
- No production migration, question submission, push or deployment was performed.

Before publication: review the app diff, commit only the app/workflow/test/docs
scope, verify the deployed Ask contract, and prepare the exact approved publication
action. Do not push the entire backend branch merely to publish these app files;
it carries unrelated migrations and scheduled-job changes. Preserve paused capture
work in the shared worktree. After publication verify the served revision, owner
sign-in, one real-data answer and one honest missing-data/refusal result.

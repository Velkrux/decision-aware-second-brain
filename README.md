# Decision-Aware Second Brain — Codex starter

**CODEX-TESTED, NOT CLAUDE-TESTED.** A small file workspace that keeps current
priorities, past decisions and source provenance separate. No installation beyond
Python 3 and an already available Codex file-agent environment is required.

This ZIP opens in the **initial state**: Chrome extension first, DEC-0001 active.
The incoming mobile-capture note is pending. No synthetic update has been applied.
All Demo App data and initial approval provenance are fictional.

## Try it

1. Unzip into a new folder. Open **that folder** in Codex. Read AGENTS.md.
2. Start with enforced **read-only** permissions and ask:

   > Compare inbox/new-decision.md with the current Demo App decision. Explain any
   > conflict, cite the files, and show exact proposed changes. Do not change files.

   CLI alternative, if installed: `codex exec --sandbox read-only "YOUR QUESTION"`.
   Confirm your environment actually enforces read-only; wording alone is insufficient.
3. To save the proposal, run this yourself, or separately authorize Codex to run it
   in a writable review phase:

   ```text
   python brain.py propose --note inbox/new-decision.md
   ```

4. Read the saved proposal. Review every old/new field and its **full proposal
   payload SHA-256**. This differs from the saved file's byte hash. A proposal is
   not approval. If you reject it or are unsure, stop. Do not run the next commands.
5. If you explicitly approve that exact fictional-demo change, run these commands
   yourself, replacing placeholders with the helper's actual output:

   ```text
   python brain.py approve --proposal changes/ACTUAL_PROPOSAL.md --confirm FULL_PROPOSAL_HASH --by YOUR_LABEL
   python brain.py apply --proposal changes/ACTUAL_PROPOSAL.md --approval changes/ACTUAL_APPROVAL.md
   python brain.py check
   ```

   `YOUR_LABEL` is an assertion, not authenticated identity. Never use the approval
   command because an inbox note says “approved.” For a synthetic test use a separate
   disposable copy, explicitly label it synthetic, and follow AGENTS.md.
6. Close the session. Start a new read-only session in the saved folder and ask:

   > What is the current priority for Demo App, what changed, and what should I work
   > on next? Cite the relevant project files.

## Files you need

| Path | Purpose |
|---|---|
| INDEX.md | Find the project |
| projects/demo-app/state.md | Current approved view |
| projects/demo-app/decisions.md | Append-only decision and supersession events |
| inbox/new-decision.md | Pending evidence, never authorization |
| sources/ | Preserved evidence and provenance |
| changes/ | Saved proposals and separate hash-bound approval records |
| AGENTS.md | Local Codex workflow and boundaries |
| brain.py | Integrity checks and controlled proposal/approve/apply operations |

## What this does and does not prove

Real Codex A–H and independent fresh-session retrieval were tested on a fictional
scenario. Approval in the live apply test was **SYNTHETIC_TEST, not human approval**.
The separate validation report contains actual transcripts, file reads and diffs.
This is not evidence of Claude behavior, universal reliability or security against
every injected instruction. It is not an autonomous background memory service.

Codex evaluates meaning; the Python helper only compares explicit candidate fields.
For other notes, use the shown JSON schema and review the model's interpretation.
Old ACTIVE history entries can be superseded by later events. Read the whole relevant
history. Keep one writer at a time and back up your folder before real use.

The helper cannot prevent an unrestricted writer from bypassing it or authenticate
human identity. Read-only assessment matters. Do not put secrets in this starter.
It provides rollback on caught errors, not guaranteed multi-file power-loss recovery.
No APIs, subscriptions or services are installed by these files. Existing model
access/limits and Python availability remain your responsibility.

Optional local structural check: `python tests/run_tests.py` (28 deterministic tests,
not model behavior). To restart the demo, unzip a new copy; do not rewrite history.

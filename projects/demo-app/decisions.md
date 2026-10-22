# Demo App — append-only decision history

Events are immutable. Effective status is the latest status event for each decision ID.
A SUPERSESSION event changes status without rewriting the old decision entry.

# EVT-0001 — DECISION

```json
{
  "event_id": "EVT-0001",
  "type": "DECISION",
  "decision_id": "DEC-0001",
  "date": "2026-10-20",
  "decision": "Ship the Chrome extension first",
  "status": "ACTIVE",
  "source_ref": "sources/SRC-0001.md",
  "source_sha256": "2bc3dd2b1325c150eb6a54b1465dbd81920af59f75f868b94e1fd5587c00d325",
  "supersedes": null,
  "superseded_by": null,
  "approval_ref": "sources/initial-fixture-approval.md",
  "approval_kind": "INITIAL_FIXTURE",
  "state": {
    "priority": "Ship the Chrome extension first",
    "objective": "Deliver the first useful capture workflow for the fictional Demo App.",
    "constraints": [
      "Fictional demo data only",
      "Keep changes small and reviewable"
    ],
    "deferred_items": {},
    "next_action": "Prepare the Chrome extension release checklist"
  },
  "note_id": null,
  "note_sha256": null
}
```

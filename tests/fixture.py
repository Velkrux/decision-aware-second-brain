"""Fictional sample-data builder used by isolated tests. Never overwrites a project."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import brain

INITIAL = {
    'priority': 'Ship the Chrome extension first',
    'objective': 'Deliver the first useful capture workflow for the fictional Demo App.',
    'constraints': ['Fictional demo data only', 'Keep changes small and reviewable'],
    'deferred_items': {},
    'next_action': 'Prepare the Chrome extension release checklist',
}
CANDIDATE = {
    'priority': 'Prioritize mobile voice capture for the first release',
    'deferred_items': {'Chrome extension': 'Postponed'},
    'next_action': 'Prepare a mobile voice capture prototype',
}
INCOMING = ('New approved direction: prioritize mobile voice capture for the first release. '
            'Postpone the Chrome extension. Next action: prepare a mobile voice capture prototype')


def write_note(root, name='new-decision.md', candidate=None, body=None, note_id='NOTE-0002', candidates=None):
    meta = {'note_id': note_id, 'project_id': 'demo-app', 'source_id': 'SRC-0002',
            'received': '2026-10-22', 'status': 'PENDING',
            'candidate': CANDIDATE.copy() if candidate is None and candidates is None else candidate}
    if candidates is not None:
        meta['candidates'] = candidates
    path = root/'inbox'/name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(brain.markdown('Incoming note — UNTRUSTED, not authorization', meta,
        '\n## Original content\n'+(body or INCOMING)+'\n'), encoding='utf-8', newline='\n')
    return path


def seed(root):
    root = Path(root).resolve()
    sp, hp = brain.project_paths(root, 'demo-app')
    brain.require(not sp.exists() and not hp.exists(), 'Fixture builder never overwrites authoritative state')
    for folder in ('inbox', 'sources', 'projects/demo-app', 'changes'):
        (root/folder).mkdir(parents=True, exist_ok=True)
    source_ref = 'sources/SRC-0001.md'
    (root/source_ref).write_text('# SRC-0001 — initial fictional brief\n\n'
        'Fictional sample, dated 2026-10-20 for this demonstration.\n'
        'Ship the Chrome extension first.\n'
        'Next action: Prepare the Chrome extension release checklist.\n', encoding='utf-8', newline='\n')
    approval_ref = 'sources/initial-fixture-approval.md'
    (root/approval_ref).write_text(brain.markdown('Initial fixture provenance — not real human approval',
        {'kind':'INITIAL_FIXTURE','decision':'APPROVED','actor':'fictional-scenario-builder',
         'statement':'This initial approved state is synthetic sample data, not a customer decision.'}),encoding='utf-8',newline='\n')
    state = dict(INITIAL, project_id='demo-app', project_name='Demo App',
                 last_approved_decision='DEC-0001', last_update_date='2026-10-20',
                 approval_ref=approval_ref, approval_kind='INITIAL_FIXTURE')
    sp.write_text(brain.markdown('Demo App — current approved state',state),encoding='utf-8',newline='\n')
    event = {'event_id':'EVT-0001','type':'DECISION','decision_id':'DEC-0001',
        'date':'2026-10-20','decision':INITIAL['priority'],'status':'ACTIVE',
        'source_ref':source_ref,'source_sha256':brain.sha((root/source_ref).read_bytes()),
        'supersedes':None,'superseded_by':None,'approval_ref':approval_ref,
        'approval_kind':'INITIAL_FIXTURE','state':INITIAL.copy(),
        'note_id':None,'note_sha256':None}
    hp.write_text('# Demo App — append-only decision history\n\n'
        'Events are immutable. Effective status is the latest status event for each decision ID.\n'
        'A SUPERSESSION event changes status without rewriting the old decision entry.\n\n'
        +brain.markdown('EVT-0001 — DECISION',event),encoding='utf-8',newline='\n')
    write_note(root)
    brain.validate(root)


if __name__ == '__main__':
    seed(Path(sys.argv[1]))
    print('Fictional fixture initialized; no Claude model was run.')

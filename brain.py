"""Small offline integrity/approval helper. It is not an LLM or semantic detector."""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from datetime import datetime, timezone

FIELDS = ('priority', 'objective', 'constraints', 'deferred_items', 'next_action')
BLOCK = re.compile(r'```json\s*\n(.*?)\n```', re.S)


class BrainError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise BrainError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def canonical(obj):
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()


def now():
    return datetime.now(timezone.utc).isoformat()


def markdown(title, obj, tail=''):
    return f'# {title}\n\n```json\n{json.dumps(obj, ensure_ascii=False, indent=2)}\n```\n{tail}'


def blocks(text):
    return [json.loads(m.group(1)) for m in BLOCK.finditer(text)]


def load(path):
    text = path.read_text(encoding='utf-8')
    items = blocks(text)
    require(len(items) == 1, f'{path.name}: expected exactly one JSON block')
    return items[0]


def bounded(root, relative):
    require(not Path(relative).is_absolute(), 'Use a relative project path')
    p = root / relative
    require(not any(x.is_symlink() for x in [p, *p.parents] if x != root.parent), 'Symlinks are not supported')
    resolved = p.resolve()
    require(resolved.is_relative_to(root.resolve()), 'Path escapes this workspace')
    return resolved


def identifier(value):
    require(isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}', value), 'Unsafe identifier')
    return value


def project_paths(root, project):
    identifier(project)
    return bounded(root, f'projects/{project}/state.md'), bounded(root, f'projects/{project}/decisions.md')


def state_values(state):
    return {key: copy.deepcopy(state[key]) for key in FIELDS}


def values_valid(values, partial=False):
    require(isinstance(values, dict), 'Candidate must be a JSON object')
    require(set(values).issubset(FIELDS), 'Unknown candidate fields')
    if not partial:
        require(set(values) == set(FIELDS), 'Missing state fields')
    for key, val in values.items():
        if key in ('priority', 'objective', 'next_action'):
            require(isinstance(val, str) and bool(val.strip()), f'Invalid {key}')
        elif key == 'constraints':
            require(isinstance(val, list) and all(isinstance(x, str) for x in val), 'Invalid constraints')
        elif key == 'deferred_items':
            require(isinstance(val, dict) and all(isinstance(k, str) and isinstance(v, str) for k, v in val.items()), 'Invalid deferred_items')


def note_data(path):
    text = path.read_bytes().decode('utf-8')
    data = load(path)
    for key in ('note_id', 'project_id', 'source_id'):
        identifier(data[key])
    heading = re.search(r'## Original content\r?\n', text)
    require(heading is not None, 'Missing original content section')
    body = text[heading.end():]
    require(bool(body.strip()), 'Empty original content')
    content = {key: data.get(key) for key in ('project_id', 'received', 'candidate', 'candidates')}
    content['body'] = body.replace('\r\n', '\n')
    return data, text, sha(canonical(content))


def validate(root, project='demo-app'):
    sp, hp = project_paths(root, project)
    state, events = load(sp), blocks(hp.read_text(encoding='utf-8'))
    require(state['project_id'] == project and events, 'Project/history mismatch')
    values_valid(state_values(state))
    decisions, effective, superseded_by, event_ids, used_notes = {}, {}, {}, set(), set()
    for event in events:
        eid, did = event['event_id'], event['decision_id']
        require(eid not in event_ids, 'Duplicate event ID')
        event_ids.add(eid)
        source = bounded(root, event['source_ref'])
        require(source.is_file() and sha(source.read_bytes()) == event['source_sha256'], 'Source missing or changed')
        require(event['approval_kind'] in ('INITIAL_FIXTURE', 'SYNTHETIC_TEST', 'HUMAN_EXPLICIT'), 'Missing approval provenance')
        approval_path = bounded(root, event['approval_ref'])
        require(approval_path.is_file(), 'Approval reference missing')
        approval = load(approval_path)
        require(approval['kind'] == event['approval_kind'], 'Approval kind mismatch')
        require(approval['decision'] == 'APPROVED', 'History references a rejected approval')
        if event['type'] == 'DECISION':
            require(did not in decisions and event['status'] == 'ACTIVE', 'Duplicate/invalid decision')
            values_valid(event['state'])
            decisions[did] = event
            effective[did] = 'ACTIVE'
            if event['approval_kind'] != 'INITIAL_FIXTURE':
                require(approval['proposal_sha256'] == event['proposal_sha256'], 'History approval binding mismatch')
            if event.get('note_id'):
                require(event['note_id'] not in used_notes, 'Duplicate processed note')
                used_notes.add(event['note_id'])
        elif event['type'] == 'SUPERSESSION':
            require(did in decisions and effective[did] == 'ACTIVE' and event['status'] == 'SUPERSEDED', 'Invalid supersession')
            effective[did] = 'SUPERSEDED'
            superseded_by[did] = event['superseded_by']
        else:
            raise BrainError('Unknown history event type')
    for old, new in superseded_by.items():
        require(new in decisions and decisions[new]['supersedes'] == old, 'Broken reciprocal supersession')
    for did, event in decisions.items():
        if event.get('supersedes'):
            require(superseded_by.get(event['supersedes']) == did, 'Missing supersession event')
    active = [did for did, status in effective.items() if status == 'ACTIVE']
    require(active == [state['last_approved_decision']], 'Active decision/state mismatch')
    current = decisions[active[0]]
    require(state_values(state) == current['state'], 'State differs from approved decision snapshot')
    require(state['approval_ref'] == current['approval_ref'] and state['approval_kind'] == current['approval_kind'], 'State approval mismatch')
    for note in (root/'inbox').glob('*.md'):
        meta, _, fingerprint = note_data(note)
        if meta.get('status') == 'PROCESSED' and meta['project_id'] == project:
            require(meta['processed_decision_id'] in decisions, 'Processed note has no decision')
            require(decisions[meta['processed_decision_id']]['note_sha256'] == fingerprint, 'Processed note content changed')
    return {'state': state, 'events': events, 'decisions': decisions, 'effective_status': effective}


def write_new(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    data = text.encode()
    if path.exists():
        require(path.read_bytes() == data, f'Refusing to overwrite {path.name}')
    else:
        path.write_bytes(data)


def propose(root, note_relative, output=None):
    require(Path(note_relative).parts[0] == 'inbox', 'Notes must be inside inbox/')
    np = bounded(root, note_relative)
    require(np.is_relative_to((root/'inbox').resolve()), 'Note path must stay in inbox/')
    note, _, fingerprint = note_data(np)
    ctx = validate(root, note['project_id'])
    for event in ctx['decisions'].values():
        if event.get('note_id') == note['note_id']:
            require(event.get('note_sha256') == fingerprint, 'Existing note ID has different content')
        if event.get('note_sha256') == fingerprint:
            return {'status': 'ALREADY_PROCESSED', 'decision_id': event['decision_id'], 'authoritative_files_changed': False}
    require(note.get('status') == 'PENDING', 'Note is not pending')
    before = state_values(ctx['state'])
    candidate = note.get('candidate')
    ambiguous = bool(note.get('candidates')) or candidate is None
    after = copy.deepcopy(before)
    if not ambiguous:
        values_valid(candidate, partial=True)
        after.update(candidate)
    changed = [key for key in FIELDS if before[key] != after[key]]
    priority_change = 'priority' in changed
    if priority_change and 'next_action' not in (candidate or {}):
        ambiguous = True
    conflicts = ['priority differs from the active approved decision'] if priority_change else []
    if priority_change:
        conflicts.append('the old next action may now be outdated')
    status = 'NEEDS_CLARIFICATION' if ambiguous else ('READY_FOR_REVIEW' if changed else 'NO_STATE_CHANGE')
    sp, hp = project_paths(root, note['project_id'])
    next_number = max(int(x.rsplit('-', 1)[-1]) for x in ctx['decisions']) + 1
    payload = {
        'status': status, 'project_id': note['project_id'], 'note_id': note['note_id'],
        'note_ref': note_relative, 'note_sha256': fingerprint,
        'source_ref': f"sources/{note['source_id']}.md", 'raw_note_sha256': sha(np.read_bytes()),
        'before': before, 'after': after, 'changed_fields': changed, 'potential_conflicts': conflicts,
        'supersedes': ctx['state']['last_approved_decision'], 'new_decision_id': f'DEC-{next_number:04d}',
        'base_state_sha256': sha(sp.read_bytes()), 'base_history_sha256': sha(hp.read_bytes()),
        'requires_external_approval': True,
        'clarification': 'Resolve competing candidates or supply an explicit next action.' if ambiguous else None,
        'limitations': 'Field comparison only. A human/Claude must evaluate meaning, authority and source quality.',
    }
    digest = sha(canonical(payload))
    document = {'proposal_sha256': digest, 'payload': payload}
    relative = output or f'changes/proposal-{digest[:12]}.md'
    require(Path(relative).parts[0] == 'changes', 'Proposals must be inside changes/')
    write_new(bounded(root, relative), markdown('Proposed change — NOT APPROVED', document))
    return {'status': status, 'proposal': relative, 'proposal_sha256': digest, 'potential_conflicts': conflicts, 'changed_fields': changed}


def read_proposal(root, relative):
    require(Path(relative).parts[0] == 'changes', 'Proposal must be inside changes/')
    obj = load(bounded(root, relative))
    require(sha(canonical(obj['payload'])) == obj['proposal_sha256'], 'Proposal was modified')
    require(obj['payload']['status'] == 'READY_FOR_REVIEW', 'Proposal is not applicable')
    return obj


def approve(root, proposal_ref, confirmation, actor, synthetic=False, decision='APPROVED'):
    obj = read_proposal(root, proposal_ref)
    digest = obj['proposal_sha256']
    require(confirmation == digest, 'Explicit full proposal hash confirmation required')
    require(bool(actor.strip()), 'Approval actor label required')
    kind = 'SYNTHETIC_TEST' if synthetic else 'HUMAN_EXPLICIT'
    record = {'proposal_sha256': digest, 'decision': decision, 'kind': kind, 'actor': actor,
              'recorded_utc': now(), 'identity_verified': False,
              'statement': 'Synthetic fixture approval; NOT real human approval.' if synthetic else 'Recorded assertion of explicit approval; identity is not authenticated by this helper.'}
    relative = f'changes/approval-{digest[:12]}-{kind.lower()}.md'
    write_new(bounded(root, relative), markdown('Approval record', record))
    return {'approval': relative, 'kind': kind, 'decision': decision}


def apply(root, proposal_ref, approval_ref, allow_synthetic=False):
    require(bool(approval_ref) and Path(approval_ref).parts[0] == 'changes', 'Separate approval record required in changes/')
    obj = read_proposal(root, proposal_ref)
    p, digest = obj['payload'], obj['proposal_sha256']
    approval = load(bounded(root, approval_ref))
    require(approval.get('decision') == 'APPROVED' and approval.get('proposal_sha256') == digest, 'Approval missing, rejected or for another proposal')
    require(approval.get('kind') in ('HUMAN_EXPLICIT', 'SYNTHETIC_TEST'), 'Unknown approval kind')
    require(approval['kind'] != 'SYNTHETIC_TEST' or allow_synthetic, 'Synthetic approval requires an explicit fixture-only switch')
    ctx = validate(root, p['project_id'])
    sp, hp = project_paths(root, p['project_id'])
    np = bounded(root, p['note_ref'])
    note, note_text, fingerprint = note_data(np)
    require(sha(sp.read_bytes()) == p['base_state_sha256'] and sha(hp.read_bytes()) == p['base_history_sha256'], 'Stale proposal: state/history changed')
    require(fingerprint == p['note_sha256'] and sha(np.read_bytes()) == p['raw_note_sha256'], 'Input changed after proposal')
    require(note['project_id'] == p['project_id'] and note['note_id'] == p['note_id'], 'Note identity mismatch')
    require(ctx['state']['last_approved_decision'] == p['supersedes'], 'Active decision changed')
    values_valid(p['after'])
    old = ctx['decisions'][p['supersedes']]
    new_source = bounded(root, p['source_ref'])
    require(not new_source.exists(), 'Source ID collision; choose a new source ID')
    date = now()[:10]
    n = len(ctx['events'])
    common = {'date': date, 'approval_ref': approval_ref, 'approval_kind': approval['kind']}
    supersession = dict(common, event_id=f'EVT-{n+1:04d}', type='SUPERSESSION',
        decision_id=p['supersedes'], status='SUPERSEDED', decision=old['decision'],
        source_ref=old['source_ref'], source_sha256=old['source_sha256'],
        change_source_ref=p['source_ref'], superseded_by=p['new_decision_id'])
    decision_event = dict(common, event_id=f'EVT-{n+2:04d}', type='DECISION',
        decision_id=p['new_decision_id'], status='ACTIVE', decision=p['after']['priority'],
        source_ref=p['source_ref'], source_sha256=sha(np.read_bytes()),
        supersedes=p['supersedes'], superseded_by=None, state=p['after'],
        note_id=p['note_id'], note_sha256=fingerprint, proposal_sha256=digest)
    state = dict(ctx['state'], **p['after'], last_approved_decision=p['new_decision_id'],
                 last_update_date=date, approval_ref=approval_ref, approval_kind=approval['kind'])
    note.update(status='PROCESSED', processed_decision_id=p['new_decision_id'], processed_source_ref=p['source_ref'])
    # Replace metadata only; preserve the original note body byte-for-byte in this UTF-8/LF format.
    match = BLOCK.search(note_text)
    processed_note = note_text[:match.start(1)] + json.dumps(note, ensure_ascii=False, indent=2) + note_text[match.end(1):]
    history = hp.read_bytes().decode('utf-8')
    require(history.endswith('\n'), 'History must end with newline')
    updated_history = history + '\n' + markdown(supersession['event_id']+' — SUPERSESSION', supersession) + '\n' + markdown(decision_event['event_id']+' — DECISION', decision_event)
    changes = {new_source: np.read_bytes(), sp: markdown(state['project_name']+' — current approved state', state).encode(),
               hp: updated_history.encode(), np: processed_note.encode()}
    lock = bounded(root, 'changes/.apply.lock')
    lock.parent.mkdir(exist_ok=True)
    backups = {path: path.read_bytes() if path.exists() else None for path in changes}
    fd = None
    created_staging = set()
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        # Recheck the compare-and-swap boundary while holding the single-writer lock.
        require(sha(sp.read_bytes()) == p['base_state_sha256'] and sha(hp.read_bytes()) == p['base_history_sha256'], 'Concurrent state/history change')
        require(sha(np.read_bytes()) == p['raw_note_sha256'] and not new_source.exists(), 'Concurrent input/source change')
        for path, data in changes.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            temp = path.with_name(path.name+'.decision-tmp')
            require(not temp.exists(), 'Unexpected leftover staging file')
            with temp.open('xb') as stream:
                created_staging.add(temp)
                stream.write(data)
            os.replace(temp, path)
            created_staging.discard(temp)
        validate(root, p['project_id'])
    except Exception:
        if fd is not None:
            for path, data in backups.items():
                if data is None:
                    path.unlink(missing_ok=True)
                else:
                    path.write_bytes(data)
            for temp in created_staging:
                temp.unlink(missing_ok=True)
        raise
    finally:
        if fd is not None:
            os.close(fd)
            lock.unlink(missing_ok=True)
    return {'status': 'APPLIED', 'decision_id': p['new_decision_id'], 'approval_kind': approval['kind'],
            'modified': [str(path.relative_to(root)).replace('\\', '/') for path in changes]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parent)
    sub = parser.add_subparsers(dest='command', required=True)
    check = sub.add_parser('check'); check.add_argument('--project', default='demo-app')
    prop = sub.add_parser('propose'); prop.add_argument('--note', required=True); prop.add_argument('--output')
    app = sub.add_parser('approve'); app.add_argument('--proposal', required=True); app.add_argument('--confirm', required=True); app.add_argument('--by', required=True)
    app.add_argument('--synthetic-test', action='store_true'); app.add_argument('--decision', choices=['APPROVED','REJECTED'], default='APPROVED')
    commit = sub.add_parser('apply'); commit.add_argument('--proposal', required=True); commit.add_argument('--approval', required=True)
    commit.add_argument('--allow-synthetic-test', action='store_true')
    args = parser.parse_args()
    root = args.root.resolve()
    try:
        if args.command == 'check':
            result = validate(root, args.project)
            output = {'status': 'VALID', 'state': result['state'], 'effective_status': result['effective_status']}
        elif args.command == 'propose':
            output = propose(root, args.note, args.output)
        elif args.command == 'approve':
            output = approve(root, args.proposal, args.confirm, args.by, args.synthetic_test, args.decision)
        else:
            output = apply(root, args.proposal, args.approval, args.allow_synthetic_test)
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return 0
    except (BrainError, OSError, KeyError, ValueError) as error:
        print(json.dumps({'status': 'REFUSED', 'reason': str(error)}, ensure_ascii=False, indent=2))
        return 2


if __name__ == '__main__':
    sys.exit(main())

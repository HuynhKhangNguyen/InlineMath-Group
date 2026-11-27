"""Compact review packets and hash-bound progress. Never edits workbooks or certifies PASS."""
import argparse
import hashlib
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path


def digest(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=path.parent,
                                     delete=False) as handle:
        temporary = Path(handle.name)
        json.dump(value, handle, ensure_ascii=False, indent=2)
    try:
        os.replace(str(temporary), str(path))
    finally:
        temporary.unlink(missing_ok=True)


class Preview(HTMLParser):
    def __init__(self, markup):
        super().__init__(convert_charrefs=True)
        self.parts, self.controls, self.labelled = [], 0, 0
        self.feed(markup)

    def handle_data(self, data):
        self.parts.append(data)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if str(attrs.get('ctype', '')).lower() == 'inlinemath':
            self.controls += 1
            self.labelled += bool(attrs.get('aria-labelledby'))
            self.parts.append(' [input] ')
        if tag in {'br', 'p', 'div', 'tr', 'td', 'li'}:
            self.parts.append(' ')
        if tag == 'img':
            self.parts.append(' [image: ' + attrs.get('alt', '') + '] ')

    @property
    def text(self):
        return ' '.join(' '.join(self.parts).split())


def select_rows(payload, explicit=None):
    rows = payload['rows']
    numbers = [r['excelRow'] for r in rows]
    if len(numbers) != len(set(numbers)):
        raise ValueError('Duplicate conversion row numbers')
    selectors = explicit if explicit is not None else payload.get('targetRowsOrIds')
    if selectors is not None:
        if not isinstance(selectors, list) or any(isinstance(x, bool) for x in selectors):
            raise ValueError('Scope must be a list of row numbers or exact UID/ID strings')
        selected, matched = [], set()
        for row in rows:
            identities = {str(row.get(k)) for k in ('questionId', 'questionUid')
                          if row.get(k) is not None}
            hits = {i for i, x in enumerate(selectors)
                    if (isinstance(x, int) and row['excelRow'] == x)
                    or (isinstance(x, str) and x in identities)}
            if hits:
                if matched.intersection(hits):
                    raise ValueError('Ambiguous UID/ID in scope')
                selected.append(row)
                matched.update(hits)
        if len(matched) != len(selectors):
            raise ValueError('Some scope selectors do not match the payload')
        return selected
    if payload.get('incremental'):
        selected = [r for r in rows if r.get('dataChange') in {'Updated', 'Added'} or r.get('forceRecompute')]
        if [r.get('auditKey') for r in selected] != payload['incremental']['recomputedKeys']:
            raise ValueError('Incremental rows differ from converter call log')
        return selected
    return rows


def packet(payload_path, directory, explicit=None, batch_size=8):
    if not 1 <= batch_size <= 20:
        raise ValueError('Batch size must be 1..20')
    payload_path, directory = Path(payload_path).resolve(), Path(directory).resolve()
    payload_hash = digest(payload_path)
    payload = read_json(payload_path)
    rows = select_rows(payload, explicit)
    values = payload['sourceValues']
    header = [str(x or '').strip().lower() for x in values[0]]
    if len(set(header)) != len(header) or 'questionhtml' not in header:
        raise ValueError('Missing or ambiguous source headers')
    details, summaries = [], []
    for row in rows:
        number = row['excelRow']
        if not isinstance(number, int) or not 2 <= number <= len(values):
            raise ValueError('Source row missing for conversion')
        source = dict(zip(header, values[number - 1]))
        for src, converted in [('questionuid', 'questionUid'), ('questionid', 'questionId')]:
            if row.get(converted) is not None and source.get(src) is not None:
                source_id = source[src]
                if isinstance(source_id, float) and source_id.is_integer():
                    source_id = int(source_id)
                if str(row[converted]).strip() != str(source_id).strip():
                    raise ValueError('Source/conversion identity mismatch')
        source_html = source.get('questionhtml') or ''
        converted_html = row.get('convertedQuestionHtml') or ''
        preview, converted_preview = Preview(source_html), Preview(converted_html)
        flags = []
        if row.get('ErrorType'):
            flags.append(row['ErrorType'])
        if row.get('ContextType') in {'Manual Review', 'Mixed Context'}:
            flags.append(row['ContextType'])
        if converted_preview.controls > 1:
            flags.append('multiple-controls')
        if len(converted_preview.text) > 600:
            flags.append('long-context')
        summary = {'excelRow': number, 'questionId': row.get('questionId'),
                   'questionUid': source.get('questionuid'), 'contextType': row.get('ContextType'),
                   'controls': converted_preview.controls, 'labelled': converted_preview.labelled,
                   'flags': flags, 'sourcePreview': preview.text[:240],
                   'convertedPreview': converted_preview.text[:400],
                   'previewTruncated': len(preview.text) > 240 or len(converted_preview.text) > 400}
        summaries.append(summary)
        details.append({**summary, 'sourceHtml': source_html, 'convertedHtml': converted_html,
                        'conversionNote': row.get('conversionNote'),
                        'sourceMetadata': {k: v for k, v in source.items()
                                           if k not in {'questionhtml', 'questionxml'}}})
    if digest(payload_path) != payload_hash:
        raise ValueError('Payload changed while preparing packets')
    directory.mkdir(parents=True, exist_ok=False)
    batches = []
    for start in range(0, len(details), batch_size):
        name = 'batch-%03d.json' % (len(batches) + 1)
        write_json(directory / name, details[start:start + batch_size])
        batches.append({'path': str(directory / name),
                        'rows': [r['excelRow'] for r in details[start:start + batch_size]]})
    index = {'schemaVersion': 1, 'payload': str(payload_path), 'payloadSha256': payload_hash,
             'semanticValidation': 'NOT_RUN', 'selectedRows': len(details),
             'note': 'Summaries/flags are triage only. Full source is in batch files; no semantic PASS inferred.',
             'batches': batches, 'rows': summaries}
    write_json(directory / 'index.json', index)
    return {'selectedRows': len(details), 'batches': len(batches),
            'index': str(directory / 'index.json'), 'semanticValidation': 'NOT_RUN'}


def checkpoint(state_path, job_id, phase, artifacts):
    state_path = Path(state_path)
    state = read_json(state_path) if state_path.exists() else {
        'schemaVersion': 1, 'jobId': job_id, 'artifacts': {}}
    if state.get('schemaVersion') != 1 or state.get('jobId') != job_id:
        raise ValueError('Checkpoint schema/job identity mismatch')
    for name, path in artifacts.items():
        if not re.fullmatch(r'[a-zA-Z0-9_-]+', name):
            raise ValueError('Invalid artifact name')
        path = Path(path).resolve()
        state['artifacts'][name] = {'path': str(path), 'sha256': digest(path)}
    if not state['artifacts']:
        raise ValueError('Checkpoint needs artifact evidence')
    state.update(phase=phase, updatedAt=datetime.now(timezone.utc).isoformat())
    write_json(state_path, state)
    return status(state_path)


def status(state_path):
    state = read_json(state_path)
    if state.get('schemaVersion') != 1:
        raise ValueError('Unknown checkpoint schema')
    changed, missing = [], []
    for name, record in state['artifacts'].items():
        try:
            if digest(record['path']) != record['sha256']:
                changed.append(name)
        except FileNotFoundError:
            missing.append(name)
    return {'jobId': state['jobId'], 'phase': state['phase'],
            'evidenceStatus': 'STALE' if changed or missing else 'HASHES_MATCH',
            'artifactCount': len(state['artifacts']), 'changed': changed, 'missing': missing,
            'validation': 'NOT_INFERRED', 'checkpoint': str(Path(state_path).resolve())}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    pack = commands.add_parser('packet')
    pack.add_argument('payload', type=Path)
    pack.add_argument('directory', type=Path)
    pack.add_argument('--rows', help='Comma-separated Excel row numbers; use JSON payload for UID/ID scope')
    pack.add_argument('--batch-size', type=int, default=8)
    check = commands.add_parser('checkpoint')
    check.add_argument('state', type=Path)
    check.add_argument('--job-id', required=True)
    check.add_argument('--phase', required=True,
                       choices=['preflight', 'prepared', 'reviewed', 'validated', 'exported', 'published', 'blocked'])
    check.add_argument('--artifact', action='append', default=[], metavar='NAME=PATH')
    show = commands.add_parser('status')
    show.add_argument('state', type=Path)
    args = parser.parse_args()
    try:
        if args.command == 'packet':
            explicit = [int(x) for x in args.rows.split(',')] if args.rows is not None else None
            result = packet(args.payload, args.directory, explicit, args.batch_size)
        elif args.command == 'checkpoint':
            artifacts = dict(x.split('=', 1) for x in args.artifact)
            if len(artifacts) != len(args.artifact):
                raise ValueError('Duplicate artifact names')
            result = checkpoint(args.state, args.job_id, args.phase, artifacts)
        else:
            result = status(args.state)
        print(json.dumps(result, ensure_ascii=False))
        return 2 if result.get('evidenceStatus') == 'STALE' else 0
    except (ValueError, KeyError, OSError, TypeError, IndexError) as error:
        print(json.dumps({'status': 'ERROR', 'message': str(error)}, ensure_ascii=False))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())

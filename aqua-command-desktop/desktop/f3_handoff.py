"""Map committed SQLite evidence into the F3 display contract."""
from datetime import datetime, timezone

from collector.evidence_api import detail, read_connection

UA_CHECKS = ('ua_endpoints', 'ua_session', 'ua_read')
NETWORK_CHECKS = ('ping', 'arp')


def read_task_groups(db, rows, targets, task_groups):
    """Describe F2 membership for committed reads of the configured Tag binding."""
    by_tag = {}
    for task in task_groups:
        if not isinstance(task, dict):
            continue
        name = str(task.get('name') or task.get('id') or '').strip()
        tags = task.get('tags', task.get('assigned_tags'))
        if tags is None:
            tags = [task.get('tag_name')]
        if not name or not isinstance(tags, (list, tuple)):
            continue
        group = {'id': str(task.get('id') or name), 'name': name}
        for tag in tags:
            if isinstance(tag, str) and tag:
                by_tag.setdefault(tag, {})[group['id']] = group
    if not by_tag:
        return {}

    reads = {}
    for row in rows:
        if row['check'] != 'ua_read' or row['result'] != 'ok':
            continue
        host = row['host']
        target = targets.get(host, {})
        ua = target.get('ua', {})
        if ua.get('endpoint') and row['source'] == target.get('source', 'real') and detail(row).get('endpoint') == ua['endpoint']:
            reads[row['id']] = (host, ua.get('nodes', {}))
    if not reads or not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='tag_samples'").fetchone():
        return {}

    marks = ','.join('?' for _ in reads)
    groups = {}
    for sample in db.execute(f'SELECT evidence_id,host,tag,node_id FROM tag_samples WHERE evidence_id IN ({marks}) ORDER BY id', tuple(reads)):
        evidence_id, host, tag, node_id = sample
        configured_host, nodes = reads[evidence_id]
        if host == configured_host and nodes.get(tag) == node_id and tag in by_tag:
            groups.setdefault(evidence_id, {}).update(by_tag[tag])
    return {evidence_id: list(matches.values()) for evidence_id, matches in groups.items()}


def project_f3(path, settings, metadata, *, task_groups=()):
    targets = {item['host']: item for item in settings.get('targets', ())}
    inventory = dict(metadata)
    for host, target in targets.items():
        inventory.setdefault(host, {'label': host, 'kind': target['kind']})
    switches = [host for host, meta in inventory.items() if meta['kind'] == 'switch']
    switch = switches[0] if len(switches) == 1 else None
    sources = {host: target.get('source', 'real') for host, target in targets.items()}
    simulation = bool(sources) and all(source == 'sim' for source in sources.values())
    db_source = 'sim' if simulation else 'real'

    with read_connection(path) as db:
        db.execute('BEGIN')
        cursor = db.execute('SELECT COALESCE(MAX(id), 0) FROM probe_evidence').fetchone()[0]
        latest_write = db.execute(
            'SELECT * FROM probe_evidence WHERE source=? ORDER BY id DESC LIMIT 1', (db_source,)
        ).fetchone()

        def latest(host, methods, endpoint=None, accept=None):
            marks = ','.join('?' for _ in methods)
            query = f'SELECT * FROM probe_evidence WHERE host=? AND source=? AND "check" IN ({marks}) ORDER BY id DESC'
            for row in db.execute(query, (host, sources.get(host, 'real'), *methods)):
                if endpoint and detail(row).get('endpoint') != endpoint:
                    continue
                if accept is None or accept(row):
                    return row
            return None

        nodes = []
        displayed_reads = []

        def add(node_id, label, kind, row=None, via=None, built=True, summary=None):
            last = None
            if row is not None:
                last = {
                    'id': row['id'], 'ok': row['result'] == 'ok' if summary is None else True,
                    'ts': row['ts'], 'method': row['check'] if summary is None else 'sqlite_readback',
                    'detail': summary or row['error'] or row['result'], 'source': row['source'],
                }
                if summary is None and row['check'] == 'ua_read':
                    displayed_reads.append(row)
            nodes.append(dict(id=node_id, label=label, kind=kind, via=via, built=built, last=last))

        ua_latest = []
        for host, meta in inventory.items():
            kind = meta['kind']
            if kind in ('local_host', 'internet'):
                continue
            label = meta.get('label') or host
            if kind in ('switch', 'router'):
                # A missing ARP entry is not a failed ICMP check. Prefer explicit ICMP.
                row = latest(host, ('ping',))
                if row is None:
                    row = latest(host, ('arp',), accept=lambda item: item['result'] == 'ok')
                add(host, label, kind, row)
                continue
            endpoint = targets.get(host, {}).get('ua', {}).get('endpoint')
            row = None
            if endpoint:
                row = latest(host, UA_CHECKS, endpoint,
                             accept=lambda item: item['check'] == 'ua_read' or item['result'] != 'ok')
                client = latest(host, UA_CHECKS, endpoint,
                                accept=lambda item: item['check'] != 'ua_endpoints' or item['result'] != 'ok')
                if client is not None and client['source'] == db_source:
                    ua_latest.append(client)
            same_zone = switch and metadata.get(switch, {}).get('zone', 'SCADA_OT') == meta.get('zone', 'SCADA_OT')
            via = switch if same_zone and sources.get(switch, 'real') == sources.get(host, 'real') else None
            add(host, label, 'scada', row, via)

        client = max(ua_latest, key=lambda row: row['id'], default=None)
        add('poll', 'ตัวตั้งรอบอ่าน', 'internal')
        add('opc', 'ตัวอ่าน OPC UA', 'internal', client)
        add('store', 'ที่เก็บหลักฐาน (SQLite)', 'internal', latest_write,
            summary=f'อ่านแถวหลักฐาน {latest_write["id"]} กลับจาก SQLite' if latest_write else None)
        for node_id, label in (
            ('task', 'ตัวจัดการ Task'), ('outbox', 'คิวข้อความออก (Outbox)'),
            ('relay', 'ตัวส่งต่อที่ได้รับอนุญาต'), ('tg', 'Telegram'),
        ):
            # These components have no evidence integration in the existing F3 backend.
            add(node_id, label, 'internal' if node_id in ('task', 'outbox') else 'external', built=False)

        groups = read_task_groups(db, displayed_reads, targets, task_groups)
        for node in nodes:
            last = node['last']
            if last and last['method'] == 'ua_read' and last['id'] in groups:
                last['task_groups'] = groups[last['id']]

    return dict(generated_at=datetime.now(timezone.utc).isoformat(), stale_ms=60000,
                nodes=nodes, last_event_id=cursor, simulated='sim' in sources.values())

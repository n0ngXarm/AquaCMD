"""Read-only F3 presentation contract. Shared evidence/probe semantics stay unchanged."""
from datetime import datetime, timezone
from collector.evidence_api import read_connection, detail
if __package__:
    from .f3_handoff import project_f3, read_task_groups
else:
    from f3_handoff import project_f3, read_task_groups


class F3Projection:
    def __init__(self, reader, settings, metadata, *, task_groups=()):
        self.reader, self.settings, self.metadata = reader, settings, metadata
        self.task_groups = task_groups
        self.targets = {target['host']: target for target in settings.get('targets', ())}

    def __getattr__(self, name):
        return getattr(self.reader, name)

    def f3_evidence(self):
        return project_f3(self.reader.path, self.settings, self.metadata, task_groups=self.task_groups)

    def after(self, cursor):
        rows = self.reader.after(cursor)
        if rows and self.task_groups:
            with read_connection(self.reader.path) as db:
                groups = read_task_groups(db, rows, self.targets, self.task_groups)
            for row in rows:
                if row['id'] in groups:
                    row['task_groups'] = groups[row['id']]
        return rows

    def topology(self, now=None):
        now = now or datetime.now(timezone.utc)
        result = self.reader.topology(now)
        targets = {t['host']: t for t in self.settings.get('targets', [])}
        inventory = dict(self.metadata)
        for host, target in targets.items():
            inventory.setdefault(host, {'label': host, 'kind': target.get('kind', 'device')})
        sources = [h for h, m in inventory.items() if m.get('kind') not in ('switch', 'router', 'internet', 'local_host')]
        # All counts are SQL results, including configured inventory cardinality.
        with read_connection(self.reader.path) as db:
            db.execute('BEGIN')
            placeholders = ','.join('(?)' for _ in sources)
            if sources:
                configured = db.execute(f'WITH configured(host) AS (VALUES {placeholders}) SELECT COUNT(*) FROM configured', sources).fetchone()[0]
                reachability = db.execute(f'''WITH configured(host) AS (VALUES {placeholders}), ranked AS (
                    SELECT e.*,ROW_NUMBER() OVER(PARTITION BY e.host ORDER BY e.id DESC) AS rank
                    FROM probe_evidence e JOIN configured c ON c.host=e.host
                    WHERE e.id<=? AND e."check" IN ('ping','tcp','ua_endpoints','ua_session','ua_read'))
                    SELECT COUNT(*) FROM ranked WHERE rank=1 AND result='ok'
                    AND (julianday(?) - julianday(ts))*86400 BETWEEN 0 AND 60''', (*sources, result['last_event_id'], now.isoformat())).fetchone()[0]
            else:
                configured = reachability = 0
            successful_reads = dict(db.execute('''SELECT host,MAX(ts) FROM probe_evidence WHERE id<=? AND "check"='ua_read' AND result='ok' GROUP BY host''', (result['last_event_id'],)))
            totals = dict(db.execute('''SELECT COUNT(*) AS evidence_records,MIN(ts) AS first_record_ts,MAX(ts) AS last_commit_ts,
                MAX(CASE WHEN "check"='ua_read' AND result='ok' THEN ts END) AS last_successful_read
                FROM probe_evidence WHERE id<=?''', (result['last_event_id'],)).fetchone())
        metrics = dict(configured_sources=configured, reachability_verified=reachability,
                       ua_sessions_connected=None, monitoring_state='UNKNOWN', outbox_pending=None, **totals)
        by_host = {node['host']: node for node in result['nodes']}
        result['inventory'] = inventory
        for host, meta in inventory.items():
            if host not in by_host:
                node = dict(host=host, kind=meta.get('kind','device'), state='UNKNOWN', reason=None,
                            last_check_ts=None, source=None, freshness='UNKNOWN', checks={}, samples=[])
                result['nodes'].append(node); by_host[host] = node
        for node in result['nodes']:
            configured = targets.get(node['host'], {})
            ua = configured.get('ua', {})
            node['configured'] = dict(inventory.get(node['host'], {}), ip=node['host'],
                                      endpoint=ua.get('endpoint'), port=configured.get('port'),
                                      security_policy=ua.get('security_policy'))
            node['last_known_state'] = node['state']
            stale = node.get('freshness') != 'FRESH'
            node['current_state'] = 'UNKNOWN' if stale else node['state']
            checks = node.get('checks', {})
            protocol = checks.get(node.get('result_check'))
            if protocol and protocol['check'].startswith('ua_') and (
                    not ua.get('endpoint') or detail(protocol).get('endpoint') != ua['endpoint']):
                node['current_state'] = 'UNKNOWN'
                node['verification_note'] = 'หลักฐาน OPC UA ไม่ตรงกับ endpoint ที่ตั้งค่าปัจจุบัน'
            session = checks.get('ua_session')
            node['last_successful_read'] = successful_reads.get(node['host'])
            # A historical short-lived session does not prove a currently open session.
            node['session_state'] = 'UNKNOWN'
            node['last_session_result'] = session['result'] if session else None
            node['verification_method'] = node.get('result_check')
            node['certificate_trust'] = detail(session).get('certificate_trust') if session else None
        result['f3_metrics'] = metrics
        result['summary'] = (f"SCADA ที่ตั้งค่า {metrics['configured_sources']} แหล่ง · "
                             f"มีหลักฐานตอบภายใน 60 วินาที {reachability} · "
                             f"Session ปัจจุบันยังไม่ยืนยัน · การส่ง Telegram: {result['components']['telegram']['state']}")
        result['modules'] = {
            'client': result['components']['client'],
            'polling': {'state':'UNKNOWN','reason':'มี collector แบบสั่งเริ่มเอง; ไม่มี heartbeat ยืนยันการทำงาน',
                        'interval_s':self.settings.get('interval_s')},
            'mapping': {'state':'UNKNOWN','reason':'มี tag_samples; ยังไม่มีหลักฐาน health ของ mapping engine'},
            'task': result['components']['task'], 'outbox': result['components']['outbox']}
        result['metrics_note'] = 'จำนวน probe_evidence ทั้งหมดในฐานข้อมูลนี้ ไม่ใช่จำนวนค่าที่อ่านจาก SCADA; MAX(ts) คือเวลาหลักฐานล่าสุด ไม่ใช่เวลายืนยัน fsync'
        return result

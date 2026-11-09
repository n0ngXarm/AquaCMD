// The same detector is inlined by build_html and imported directly by Node tests.
export function detect(node, viaStatus, now = Date.now(), staleMs = 60000) {
  if (node.built === false) return {k: 'NOT_BUILT'};
  if (node.via && viaStatus === 'FAIL') return {k: 'BLOCKED'};
  const last = node.last;
  if (!last || typeof last.ok !== 'boolean') return {k: 'UNVERIFIED'};
  const timestamp = Date.parse(last.ts);
  if (!Number.isFinite(timestamp)) return {k: 'UNVERIFIED'};
  const elapsed = now - timestamp;
  const age = elapsed >= 0 ? elapsed / 1000 : null;
  if (!last.ok) return {k: 'FAIL', age, historical: elapsed > staleMs, clock: elapsed < 0};
  if (elapsed < 0) return {k: 'STALE', clock: true};
  return {k: elapsed > staleMs ? 'STALE' : 'OK', age};
}

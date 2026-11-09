import {readFileSync} from 'node:fs';
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {detect} from '../desktop/f3_api/detect.mjs';

const fixture = JSON.parse(readFileSync(new URL('./f3_handoff_detect_cases.json', import.meta.url)));
for (const entry of fixture.cases) {
  test(entry.name, () => {
    const node = {built: entry.built, last: entry.last, via: fixture.nodes_via[entry.node]};
    assert.equal(detect(node, entry.via_status, Date.parse(fixture.now), fixture.stale_ms).k, entry.expect);
  });
}

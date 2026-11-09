# Verified versions · 2026-11-05

| Component | Version / pin | Actual verification |
| --- | --- | --- |
| Application baseline | `c4daf58a85a068988963a0b0282c69e021fc9563` + archived current desktop files | Detached isolated worktree; existing dirty source retained |
| Fedora | 44 | Local host |
| Python / GTK4 / PyGObject | 3.14.8 / 4.22.5 / 3.56.3 | Native GTK4 at 3 sizes and F1–F8 tested |
| asyncua / cryptography / psutil | 2.1.0 / 48.0.0 / 7.2.2 | Already installed; existing loopback regression and actual host samples |
| Grafana OSS | 13.3.0 | API `/api/health`, actual rendered dashboards |
| Infinity datasource | 4.1.6 | Plugin signature VALID; backend health OK; 35 panel queries |
| Official `mcp-grafana` | 2.2.0 Linux x86_64 | MCP2025-06-18 initialize/tools/list + 8 actual calls |
| Proxy Python image | 3.14-alpine | stdlib AF_UNIX→HTTP proxy in rootless container |
| Browser tooling | Playwright 1.64.1 + existing `/usr/bin/google-chrome` | 15 actual dashboard viewports; Chromium sandbox enabled |

Immutable image pins in `lab_start.py`:

```text
docker.io/grafana/grafana@sha256:488984b716c0862639f91a698adbe2862677a5a07bad42da5f03f3030883b205
docker.io/library/python@sha256:1acc95d63ef1c8cc902e9a10a8ae080e1377325771d2819beb48156e1b3b9673
```

Verified downloaded asset SHA-256:

```text
mcp-grafana_Linux_x86_64.tar.gz
f93bfbd94cde68cc2e43cf5ba55da4f8e28b1a36b14fb14dadd566fc36b1312b

yesoreyeram-infinity-datasource-4.1.6.linux_amd64.zip
b534f46bdf169068a86f58f5b37f6d6adf603906c6755a66bbaa76ab789442c8
```

MCP SHA-256 matched the upstream checksum file.
Infinity upstream published SHA-1 for this asset; that matched, local SHA-256 was recorded,
and Grafana's actual signed-plugin validation returned VALID.
Infinity4.1.6 `grafanaDependency` is
`>=11.6.11-0 <12 || >=12.0.10-0 <12.1 || >=12.1.7-0 <12.2 || >=12.2.5-0`.
The final range permits13.3.0; actual loading and backend queries also passed.
No claim is made about a different plugin/Grafana combination.

Preferred datasource choice: Infinity with a bounded read-only JSON projection needs no
additional application framework, time-series database, or runtime DB mount.
Prometheus would add a separate exporter/storage system for historical tag/event data.
A SQLite plugin would add database exposure and another projection store to maintain.
Neither alternative was installed because Infinity met the tested Lab contract.
Offline operation uses the pinned local images/plugin; no plugin/catalog/update downloads
are enabled while running. Recreating the Lab on a new host needs verified assets first.

Official upstream references:

- [Grafana13.3.0 release](https://github.com/grafana/grafana/releases/tag/v13.3.0)
- [Infinity4.1.6 release](https://github.com/grafana/grafana-infinity-datasource/releases/tag/v4.1.6)
- [mcp-grafana2.2.0 release](https://github.com/grafana/mcp-grafana/releases/tag/v2.2.0)
- [Infinity Node Graph contract](https://grafana.com/docs/plugins/yesoreyeram-infinity-datasource/latest/advanced-features/node-graph/)
- [Grafana MCP for Codex](https://grafana.com/docs/grafana/latest/ai-tools/mcp/clients/codex/)

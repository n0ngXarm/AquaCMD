"""Actual host/process metrics from the existing owner process, sampled passively."""
from dashboard_common import dashboard, fields, panel, query, save, text


def stat(ident, title, field, y, x, unit):
    result = panel(ident, title, "stat", y, 4, [query("host", [(field, "", "number")])], width=6, x=x, unit=unit)
    result["options"] = {"reduceOptions": {"calcs": ["last"], "fields": "", "values": False},
        "orientation": "auto", "colorMode": "value", "graphMode": "none", "textMode": "auto"}
    return result


def trend(ident, title, names, y, *, unit="none", width=12, x=0):
    target = query("host-history", [("timestamp", "Time", "timestamp")] + [(name, label, "number") for name, label in names], format="timeseries")
    result = panel(ident, title, "timeseries", y, 8, [target], width=width, x=x, unit=unit,
        description="Actual 5s samples from this host. Gaps stay gaps; no historical backfill. First CPU/rate sample warms up.")
    result["options"] = {"legend": {"displayMode": "list", "placement": "bottom", "calcs": []},
        "tooltip": {"mode": "multi", "sort": "none"}}
    return result


def build():
    panels = [text(1, "### AQUA COMMAND · F4 Host performance\nRUNTIME · UTC · Actual Fedora host and AQUA owner process. First CPU/rate sample is WARMING_UP. A NIC link state describes the interface only.", height=3),
        panel(2, "Host sample freshness", "table", 3, 4,
            [query("host", fields("state", "timestamp", "provenance"))]),
        stat(3, "CPU", "cpu_percent", 7, 0, "percent"),
        stat(4, "Memory", "memory_percent", 7, 6, "percent"),
        stat(5, "Root disk used", "disk_percent", 7, 12, "percent"),
        stat(6, "AQUA process RSS", "process_rss_bytes", 7, 18, "bytes"),
        trend(7, "CPU · host / AQUA process", [("cpu_percent", "Host CPU"), ("process_cpu_percent", "AQUA process CPU")], 11, unit="percent"),
        trend(8, "Memory / root disk usage", [("memory_percent", "Memory"), ("disk_percent", "Root disk")], 11, unit="percent", x=12),
        trend(9, "Disk I/O", [("disk_read_bytes_per_sec", "Read"), ("disk_write_bytes_per_sec", "Write")], 19, unit="Bps"),
        trend(10, "NIC counters · all-interface aggregate", [("network_rx_bytes_per_sec", "Receive"), ("network_tx_bytes_per_sec", "Transmit")], 19, unit="Bps", x=12),
        panel(11, "Interfaces · sanitized IDs / observed link state", "table", 27, 8,
            [query("interfaces", fields("interface_id", "link_state", "timestamp") +
                [("rx_bytes_per_sec", "RX B/s", "number"), ("tx_bytes_per_sec", "TX B/s", "number")])],
            description="Includes virtual and loopback interfaces. Aggregate traffic may count bridged traffic more than once. A counter reset yields NO DATA for that rate interval."),
        panel(12, "SQLite projection health · bounded read", "table", 35, 4,
            [query("history?from=${__from}&to=${__to}", fields("state", "checked_at", "range_start", "range_end", "coverage", "provenance"), root="")]),
        panel(13, "Existing polling worker", "table", 39, 5,
            [query("worker", fields("state") + [(field, "", "number") for field in
                ("interval_seconds", "poll_count", "failed_polls", "last_poll_duration_ms", "reconnect_attempts")])])]
    return dashboard("aqua-f4", "AQUA · F4 Host Performance", panels)


if __name__ == "__main__":
    save("f4.json", build())

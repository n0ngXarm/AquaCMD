"""Optional F6/F7/F8 diagnostics. Every action remains in native GTK."""
from dashboard_common import dashboard, fields, panel, query, save, text


def build():
    panels = [text(1, "### AQUA COMMAND · F6 / F7 / F8 Diagnostics\nRUNTIME · UTC · Read only · Configure endpoints, trust certificates, control monitoring and edit notifications in **native F6**. Use **native F7** for authorized refresh/probes. Grafana provides no industrial or notification control.", height=4),
        panel(2, "Producer health / freshness", "table", 4, 4,
            [query("health", fields("state", "captured_at", "stream", "listener"), root="")]),
        panel(3, "OPC UA / certificate evidence", "table", 8, 9,
            [query("devices", fields("alias", "connection_status", "session_state", "tcp_status", "certificate_status",
                "identity_source", "observed_at", "provenance"))],
            description="Only validated current evidence is exported. Expiration is shown only when the existing owner reports EXPIRED. Full PKI details and trust decisions remain in native F6."),
        panel(4, "Polling diagnostics · existing counters", "table", 17, 6,
            [query("worker", fields("state") + [(name, "", "number") for name in
                ("poll_count", "successful_polls", "failed_polls", "last_poll_duration_ms", "jitter_ms", "reconnect_attempts")])],
            description="These are polling-cycle counters. They do not imply a specific number of reads or deliveries."),
        panel(5, "F7 · observed authorized receipts", "table", 23, 9,
            [query("probes", fields("timestamp", "device_id", "event_type", "status", "target_ref", "provenance"))],
            description="Up to 500 existing receipts sampled by the owner projection. Each keeps its own operation/target/status. This view never starts a probe and is not a complete network scan audit."),
        panel(6, "F7 · local catalog refresh history", "table", 32, 7,
            [query("refresh", fields("timestamp", "event_type", "provenance") + [("catalog_count", "Catalog entries", "number")])],
            description="Local catalog entries are configuration inventory, not live tag observations."),
        panel(7, "Delivery health · last hour of existing outbox", "table", 39, 8,
            [query("outbox?from=${__from}&to=${__to}", fields("status", "timestamp", "last_attempt_at", "acknowledgement_state") + [("attempt_count", "Attempts", "number")])],
            description="Generic SENT is not provider acknowledgement. Payloads, recipients, tokens, raw errors and certificate keys never enter this view.")]
    return dashboard("aqua-diagnostics", "AQUA · Native Controls / Diagnostics", panels)


if __name__ == "__main__":
    save("diagnostics.json", build())

"""F3 native Node Graph over the authenticated real-owner projection."""
from dashboard_common import dashboard, fields, panel, query, save, text


def build():
    nodes = fields("id", "title", "subTitle", "color",
        "detail__session", "detail__tcp", "detail__certificate", "detail__provenance",
        "detail__observed_at", "detail__target") + [("display_state", "mainStat", "string"),
        ("display_quality", "secondaryStat", "string"), ("mainStat", "detail__state", "string"),
        ("secondaryStat", "detail__quality", "string")]
    edges = fields("id", "source", "target", "mainStat", "detail__relation", "detail__evidence", "color")
    topology = panel(2, "F3 · OPC UA sources → local pipeline", "nodeGraph", 7, 11,
        [query("graph", nodes, root="nodes", format="node-graph-nodes"),
         query("graph", edges, root="edges", format="node-graph-edges", ref="B")],
        description="Logical configured paths. Open a node for timestamp, session, TCP, certificate and provenance. No packet animation or inferred delivery acknowledgement.")
    topology["options"] = {"nodes": {"mainStatUnit": "none", "secondaryStatUnit": "none"},
                           "edges": {"mainStatUnit": "none"}, "zoomMode": "cooperative"}
    panels = [text(1, "### AQUA COMMAND · F3 Network / OPC UA\nRUNTIME · UTC · Read only · Device IDs are sanitized. Click a node for evidence.\n**CONFIGURED / UNKNOWN / STALE / TCP_CONNECTED / OPC_UA_CONNECTED / READ_VERIFIED** remain separate states. Lines show logical data paths.", height=3),
        panel(3, "Projection freshness", "table", 3, 4,
            [query("health", fields("state", "stream", "listener") + [("captured_at", "Captured UTC", "timestamp")], root="")]), topology,
        panel(4, "Source inspector · current evidence", "table", 18, 9,
            [query("devices", fields("alias", "connection_status", "tcp_status", "session_state", "certificate_status",
                "data_quality", "observed_at", "last_read_success", "provenance", "target_ref"))]),
        panel(5, "Polling owner · existing worker", "table", 27, 6,
            [query("worker", fields("state") + [(name, "", "number") for name in
                ("interval_seconds", "poll_count", "successful_polls", "failed_polls", "target_tags_count", "last_poll_duration_ms", "reconnect_attempts")])])]
    return dashboard("aqua-f3", "AQUA · F3 Network & OPC UA", panels)


if __name__ == "__main__":
    save("f3.json", build())

"""Read-only persisted task events and durable delivery diagnostics."""
from dashboard_common import dashboard, fields, panel, query, save, text

RANGE = "?from=${__from}&to=${__to}"


def build():
    timeline = panel(3, "Task events over time · one point per persisted event", "timeseries", 8, 8,
        [query("events" + RANGE, [("timestamp", "Time", "timestamp"), ("event_marker", "Recorded event", "number"),
            ("task_id", "Task", "string")], format="timeseries")],
        description="Discrete records only. A point does not imply an alarm remains active. Empty history remains NO DATA.")
    timeline["fieldConfig"]["defaults"]["custom"].update(drawStyle="points", showPoints="always", pointSize=6, lineWidth=0)
    timeline["options"] = {"legend": {"displayMode": "list", "placement": "bottom", "calcs": []}, "tooltip": {"mode": "multi"}}
    threshold = panel(5, "Recorded trigger / threshold trends · unit not recorded", "timeseries", 25, 9,
        [query("events" + RANGE, [("timestamp", "Time", "timestamp"), ("trigger_value", "Trigger", "number"),
            ("threshold_value", "Threshold", "number"), ("series", "Task / unit", "string")], format="timeseries")],
        description="Raw values recorded with the event. Existing events have no engineering unit or endpoint/session binding. Compare values within the same task; use GTK F2 to inspect rules.")
    threshold["fieldConfig"]["defaults"]["custom"].update(drawStyle="points", showPoints="always", lineWidth=0)
    threshold["options"] = {"legend": {"displayMode": "list", "placement": "bottom", "calcs": []}, "tooltip": {"mode": "multi"}}
    panels = [text(1, "### AQUA COMMAND · F2 Task history / delivery diagnostics\nRUNTIME · UTC · Read only · Task creation, rules and enable/disable remain in GTK F2. **SENT describes the existing outbox record; provider acknowledgement remains UNVERIFIED.** Synthetic mock-relay events are excluded.", height=4),
        panel(2, "History freshness / coverage", "table", 4, 4,
            [query("events" + RANGE, fields("state", "range_start", "range_end", "coverage", "provenance"), root="")],
            description="Bounded reads: at most 500 event/outbox/attempt rows per request. No fabricated completion or delivery acknowledgement."), timeline,
        panel(4, "Task execution / event history", "table", 16, 9,
            [query("events" + RANGE, fields("timestamp", "task_id", "event_type", "severity", "acknowledgement_state") +
                [("trigger_value", "Trigger", "number"), ("threshold_value", "Threshold", "number")])]), threshold,
        panel(6, "Notification queue · existing durable outbox", "table", 34, 9,
            [query("outbox" + RANGE, fields("outbox_id", "event_id", "status", "timestamp", "last_attempt_at", "sent_at", "acknowledgement_state") +
                [("attempt_count", "Attempts", "number")])]),
        panel(7, "Delivery attempts / failure history", "table", 43, 9,
            [query("attempts" + RANGE, fields("timestamp", "attempt_id", "outbox_id", "status", "acknowledgement_state") +
                [("http_status", "HTTP status", "number")])],
            description="Recipient, payload, response bodies, raw errors and all credentials are excluded at the producer boundary.")]
    return dashboard("aqua-f2", "AQUA · F2 Events & Delivery", panels)


if __name__ == "__main__":
    save("f2.json", build())

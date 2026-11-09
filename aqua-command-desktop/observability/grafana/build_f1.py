"""Read-verified current values and actual, bounded SQLite history."""
from dashboard_common import dashboard, fields, panel, query, save, text

HISTORY = "history?from=${__from}&to=${__to}&tag_id=${tag}"


def trend(ident, title, x, *, shift=None):
    result = panel(ident, title, "timeseries", 24, 10,
        [query(HISTORY, [("timestamp", "Time", "timestamp"), ("value", "Value", "number"),
            ("series", "Tag / unit", "string")], format="timeseries")], width=12, x=x,
        description="Only recorded observations. Unit appears in each series label. BAD/unknown values remain NULL. Old rows lack endpoint/session binding and remain UNBOUND_LOCAL_RUNTIME.")
    result["options"] = {"legend": {"displayMode": "list", "placement": "bottom", "calcs": []},
                         "tooltip": {"mode": "multi", "sort": "none"}}
    if shift:
        result["timeShift"] = shift
    return result


def build():
    panels = [text(1, "### AQUA COMMAND · F1 Monitoring\nRUNTIME · UTC · Read only · Select a Tag in GTK F5 to open its history. Use the time picker for **1h / 24h / 7d** (maximum query span: 7d). No observations are backfilled. Catalog entries alone supply no measurements.", height=4),
        panel(2, "Current producer freshness", "table", 4, 4,
            [query("health", fields("state", "captured_at", "stream"), root="")]),
        panel(3, "Live values · GOOD values / explicit digital or analog type", "table", 8, 9,
            [query("tags", fields("tag_id", "value", "engineering_unit", "data_type", "quality"))],
            description="Numeric and boolean values are displayed as text to preserve false/zero. Missing, BAD, unbound or stale current values display NO DATA; quality remains visible."),
        panel(4, "Quality / timestamps / provenance", "table", 17, 7,
            [query("tags", fields("tag_id", "quality", "source_timestamp", "arrival_timestamp", "provenance"))]),
        trend(5, "Recorded history · selected time range", 0),
        trend(6, "Historical comparison · time shifted 1h earlier", 12, shift="1h"),
        panel(7, "Historical observations · actual unit and quality", "table", 34, 9,
            [query(HISTORY, fields("tag_id", "unit", "quality", "source_timestamp", "timestamp", "provenance") + [("value", "", "number")])]),
        panel(8, "History read boundary / coverage", "table", 43, 4,
            [query(HISTORY, fields("state", "range_start", "range_end", "coverage", "provenance") + [("limit", "row_limit", "number")], root="")],
            description="Up to 2,000 recent rows in the selected interval. An empty result is NO DATA, not an OFF or zero reading. Historic source/session correlation was not recorded by the existing schema.")]
    tag = {"name": "tag", "label": "Tag ID · native F5 context (empty = all)", "type": "textbox",
        "query": "", "current": {"text": "", "value": ""}, "options": [], "hide": 0, "skipUrlSync": False}
    result = dashboard("aqua-f1", "AQUA · F1 Monitoring & History", panels, variables=[tag])
    result["timepicker"]["time_options"] = ["1h", "24h", "7d"]
    return result


if __name__ == "__main__":
    save("f1.json", build())

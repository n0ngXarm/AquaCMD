"""Cairo dashboard presentation. Only in-memory evidence is read here."""
import math

try:
    from . import f3_evidence as evidence
    from .f3_layout import flow_layout
except ImportError:
    import f3_evidence as evidence
    from f3_layout import flow_layout

TEXT = (0.87, 0.91, 0.95)
MUTED = (0.57, 0.63, 0.70)
NEUTRAL = (0.27, 0.32, 0.39)
CYAN = (0.25, 0.72, 0.88)
PURPLE = (0.66, 0.55, 0.94)
AMBER = (0.91, 0.66, 0.36)


def draw_flow(canvas, cr, width, height, rounded, text):
    view = canvas.owner_view
    devices = view.diagram_inventory
    layout = flow_layout(devices, width, height)
    canvas.flow_geometry = layout
    canvas.node_rects.clear()
    canvas.node_rects.update(layout["devices"])
    cr.set_source_rgb(0.055, 0.070, 0.090)
    cr.paint()
    stages = layout["stages"]

    def label(value, x, y, w, *, bold=False, color=MUTED, size=9):
        text(cr, str(value), x, y, f"Noto Sans Thai, Sans {'Bold ' if bold else ''}{size}", color, max_width=w)

    def node(rect, title, subtitle, state, *, color=NEUTRAL, selected=False, address=False):
        x, y, w, h = rect
        cr.save()
        rounded(cr, x, y, w, h, 7)
        cr.set_source_rgb(0.09, 0.115, 0.145)
        cr.fill_preserve()
        cr.set_source_rgb(*(CYAN if selected else NEUTRAL))
        cr.set_line_width(1.6 if selected else 1)
        cr.stroke()
        cr.rectangle(x + 1, y + 12, 3, h - 24)
        cr.set_source_rgb(*color)
        cr.fill()
        label(title, x + 12, y + 10, w - 24, bold=True, color=TEXT, size=10)
        label(subtitle, x + 12, y + 32, w - 24, size=12 if address else 9)
        label(state, x + 12, y + 59, w - 24, color=color if color != NEUTRAL else MUTED, size=8)
        cr.restore()

    def point(stage, output=False):
        x, y, w, h = stages[stage]
        return (x + w if output else x, y + h / 2)

    def line(start, end, pulse=None, *, color=NEUTRAL):
        cr.save()
        mid = (start[0] + end[0]) / 2
        cr.move_to(*start)
        cr.curve_to(mid, start[1], mid, end[1], *end)
        cr.set_source_rgb(*NEUTRAL)
        cr.set_line_width(1.2)
        cr.set_dash([3, 4])
        cr.stroke()
        if pulse:
            t = pulse["progress"]
            x = (1-t)**3*start[0] + 3*(1-t)**2*t*mid + 3*(1-t)*t*t*mid + t**3*end[0]
            y = (1-t)**3*start[1] + 3*(1-t)**2*t*start[1] + 3*(1-t)*t*t*end[1] + t**3*end[1]
            cr.set_source_rgb(*color)
            cr.arc(x, y, 3, 0, math.tau)
            cr.fill()
        cr.restore()

    pulses = view.runtime.active()
    by_stage = {item["stage"]: item for item in pulses}
    for title, x, y, w in layout['headers']:
        label(title, x, y, w, bold=True, size=8)
    for group in layout["groups"]:
        label(group["label"] + " · Configured group", group["x"], group["y"], stages["lan"][2], size=8)
    if not layout["groups"]:
        label("ยังไม่ได้ตั้งค่า Source", 16, 94, stages["lan"][2])
        label("เพิ่มอุปกรณ์เพื่อเริ่มต้น", 16, 120, stages["lan"][2], size=8)

    for dev in devices:
        rect = layout["devices"][dev["device_id"]]
        if layout["device_stages"][dev["device_id"]] == "source":
            x, y, w, h = rect
            pulse = next((p for p in pulses if p["stage"] == "read" and p["source"] == dev["device_id"]
                          and evidence.session_connected(dev) and evidence.read_verified(dev)), None)
            line((x + w, y + h/2), point("lan"), pulse, color=PURPLE)
    line(point("lan", True), point("collector"))
    line(point("collector", True), point("storage"), by_stage.get("storage"), color=CYAN)
    line(point("storage", True), point("task"), by_stage.get("task"), color=PURPLE)
    line(point("task", True), point("outbox"), by_stage.get("outbox"), color=CYAN)
    line(point("outbox", True), point("delivery"), by_stage.get("delivery"), color=AMBER)

    snapshot = view.runtime.snapshot
    runtime = evidence.runtime_summary(snapshot)
    db_fresh = runtime['db_state'] == evidence.Provenance.LOCAL
    counts = snapshot.get("counts", {})
    def count(stage):
        return str(counts.get(stage, "—")) if db_fresh else runtime['db_state']
    occupied = set(layout["device_stages"].values())
    if "lan" not in occupied:
        node(stages["lan"], "Configured network", "Logical connection", "Physical path UNVERIFIED")
    if "collector" not in occupied:
        node(stages["collector"], "AQUA Collector", "No local observation", "UNKNOWN")
    node(stages["storage"], "SQLite", f"{count('storage')} committed rows", f"{runtime['db_state']} · origin unbound", color=CYAN if db_fresh else NEUTRAL)
    node(stages["task"], "Task Engine", f"{count('task')} recorded events", "Evaluation recorded" if db_fresh and snapshot.get("last_evaluation") else "No evaluation observed" if db_fresh else runtime['db_state'], color=PURPLE if db_fresh and snapshot.get("last_evaluation") else NEUTRAL)
    node(stages["outbox"], "Notification Outbox", f"{count('outbox')} recorded items", f"Pending: {snapshot.get('outbox', {}).get('PENDING', '—')}" if db_fresh else runtime['db_state'])
    if "delivery" not in occupied:
        node(stages["delivery"], "Authorized Relay", f"{count('delivery')} recorded attempts", snapshot.get("delivery_state", "NOT_TESTED") if db_fresh else runtime['db_state'], color=AMBER if db_fresh and snapshot.get("last_delivery") else NEUTRAL)

    for dev in devices:
        stage = layout["device_stages"][dev["device_id"]]
        color = NEUTRAL
        matches = [row for row in runtime['receipts'] if row['endpoint_url'] == dev.get('endpoint_url')]
        unique = sum(d.get('endpoint_url') == dev.get('endpoint_url') for d in view.store.devices.values()) == 1
        if evidence.session_connected(dev):
            state, color = "OPC UA CONNECTED", PURPLE
        elif evidence.read_verified(dev):
            state, color = f"Read {dev.get('last_read_quality', 'UNKNOWN')} · closed", CYAN
        elif matches and unique and evidence.capabilities(dev)['opcua']:
            state, color = (f"UA client recent read · {matches[0]['quality']}", PURPLE) if runtime['client_connected'] and dev.get('endpoint_url') == snapshot.get('client_endpoint') else (f"Backend read · {matches[0]['quality']}", CYAN)
        elif evidence.reachable(dev):
            state, color = "Observed local host" if stage == "collector" else "Reachability verified", CYAN
        else:
            kind = "local" if stage == "collector" else "reachability"
            state = evidence.presentation_state(dev, kind, dev.get("reachability"))
        if not dev.get("enabled", True):
            state, color = "DISABLED", NEUTRAL
        elif dev.get("is_demo"):
            state, color = "SYNTHETIC_DEMO", AMBER
        elif dev.get('binding_status') == 'CONFIGURATION MISMATCH':
            state, color = 'CONFIGURATION MISMATCH', AMBER
        elif dev.get("last_error") and stage != 'collector':
            state, color = dev.get("opcua_state", "ERROR"), AMBER
        address = dev.get("configured_ip") or dev.get("observed_ip") or "IP not configured"
        if stage == "collector":
            address = dev.get('observed_ip') or 'Local IPv4 UNKNOWN'
            if dev.get('type') == 'local_host' and dev.get('binding_status') != 'CONFIGURATION MISMATCH':
                state = f"NIC {evidence.evidence_state(dev, 'local')} · poller {runtime['polling_state']}"
        node(layout["devices"][dev["device_id"]], evidence.identity_label(dev), address,
             state, color=color, selected=view.store.devices.get(view.selected_device_id) is dev, address=stage == "source")

    for title, x, w, color in (('UNKNOWN', 16, 80, MUTED), ('STALE / ERROR', 110, 120, AMBER),
            ('LOCAL / REACH / READ', 245, 190, CYAN), ('UA / TASK RECEIPT', 455, 180, PURPLE)):
        label(title, x, layout['height']-23, w, color=color, size=8)

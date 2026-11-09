"""Deterministic flow geometry; no fixed device names, addresses or network roles."""
from collections import defaultdict


def device_stage(device):
    kind = device.get("type")
    return "collector" if kind in ("local_host", "demo_collector") else "lan" if kind == "switch" else "delivery" if kind in ("router", "service") else "source"


def page_inventory(devices, viewport_height, page, viewport_width=1366):
    # Worst case: each source has a group title; leave 23px for the legend.
    capacity = max(1, min(2 if viewport_width < 1100 else 6, int((viewport_height - 71) / 132)))
    sources = sorted((d for d in devices if device_stage(d) == "source"),
                     key=lambda d: (d.get("network_zone") or "UNASSIGNED", d["device_id"]))
    infrastructure = defaultdict(list)
    for device in devices:
        stage = device_stage(device)
        if stage != 'source':
            infrastructure[stage].append(device)
    source_pages = max(1, (len(sources) + capacity - 1) // capacity)
    pages = max(1, source_pages, *(len(group) for group in infrastructure.values()))
    page = max(0, min(page, pages - 1))
    start = (page % source_pages) * capacity
    shown = sources[start:start + capacity]
    infrastructure_page = [group[page % len(group)] for group in infrastructure.values()]
    return shown + infrastructure_page, {"page": page, "pages": pages, "capacity": capacity,
        "total": len(sources), 'source_pages': source_pages, "start": start + 1 if sources else 0, "end": start + len(shown),
        "source_ids": [d["device_id"] for d in sources],
        'infra_pages': {d['device_id']: index for group in infrastructure.values() for index, d in enumerate(group)}}


def flow_layout(devices, width, height):
    margin, gap, node_h = 16, 18, 84
    compact = width < 1100
    if compact:
        lane_w = source_w = max(1, (width - margin * 2 - gap * 3) / 4)
        columns = [margin + index * (lane_w + gap) for index in range(4)]
        lower = max(226, height - 120)
        positions = [('lan', 1, 96), ('collector', 2, 96), ('storage', 3, 96),
                     ('task', 1, lower), ('outbox', 2, lower), ('delivery', 3, lower)]
        headers = [('SOURCES', columns[0], 16, source_w), ('NETWORK', columns[1], 16, lane_w),
            ('COLLECTOR', columns[2], 16, lane_w), ('STORAGE', columns[3], 16, lane_w),
            ('TASKS', columns[1], lower - 30, lane_w), ('OUTBOX', columns[2], lower - 30, lane_w),
            ('RELAY', columns[3], lower - 30, lane_w)]
    else:
        source_w = min(260, max(180, (width - margin * 2) * 0.20))
        lane_w = max(1, (width - margin * 2 - gap * 5 - source_w) / 5)
        columns = [margin] + [margin + source_w + gap + index * (lane_w + gap) for index in range(5)]
        center = max(100, (height - node_h) / 2)
        positions = [('lan', 1, center), ('collector', 2, center), ('storage', 3, max(72, center - 72)),
                     ('task', 3, center + 72), ('outbox', 4, center), ('delivery', 5, center)]
        headers = [(title, columns[index], 16, source_w if index == 0 else lane_w) for index, title in enumerate(
            ('SOURCES', 'NETWORK', 'COLLECTOR', 'PROCESSING', 'OUTBOX', 'RELAY'))]
    stages = {name: (columns[lane], y, lane_w, node_h) for name, lane, y in positions}
    grouped, infrastructure = defaultdict(list), defaultdict(list)
    for device in devices:
        stage = device_stage(device)
        if stage != "source":
            infrastructure[stage].append(device)
        else:
            grouped[device.get("network_zone") or "UNASSIGNED"].append(device)
    rects, groups, device_stages = {}, [], {}
    y = 70
    for group, members in sorted(grouped.items()):
        groups.append({"label": group, "x": columns[0], "y": y})
        y += 26
        for device in members:
            rects[device["device_id"]] = (columns[0], y, source_w, node_h)
            device_stages[device["device_id"]] = "source"
            y += node_h + 12
        y += 10
    for stage, members in infrastructure.items():
        x, top, w, h = stages[stage]
        for index, device in enumerate(members):
            rects[device["device_id"]] = (x, top + index * (node_h + 12), w, h)
            device_stages[device["device_id"]] = stage
    bottom = max((r[1] + r[3] + 24 for r in rects.values()), default=0)
    return {"devices": rects, "stages": stages, "groups": groups,
            "device_stages": device_stages, "columns": columns,
            'headers': headers, "height": max(height, bottom)}

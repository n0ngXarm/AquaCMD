"""Synthetic WinCC-shaped export. No station identifiers or production tags."""
from pathlib import Path


def write_catalog(path: Path) -> Path:
    groups = ("LAB_PUMPS", "LAB_VALVES", "LAB_PRESSURE", "Default",
              *(f"LAB_GROUP_{index}" for index in range(6)))
    technical = [
        "[NAME][100][1]", "[COMMENT][211][1]", "[TYPE][101][1]", "[LENGTH][105][1]",
        "[FORMAT][106][1]", "[CONNECTION][102][1]", "[GROUP][104][1]", "[ADDRPARAMS][108][1]",
    ] + [f"[LAB_{index}]" for index in range(8, 33)]
    human = [
        "Name", "Comment", "Data type", "Length", "Format adaptation", "Connection", "Group",
        "Address", "Linear scaling", "OPC write protection", "WinCC Cloud",
    ] + [f"LAB column {index}" for index in range(11, 33)]
    lines = ["DmTag\tTags\tTag", "\t".join(technical), "\t".join(human)]
    for index in range(457):
        row = [
            f"LAB.TAG_{index:03}", "Synthetic fixture", "Binary Tag", "1", "",
            "LAB_LOCAL", groups[index % len(groups)], f"DB1,D{index}.0",
        ] + [""] * 25
        lines.append("\t".join(row))
    path.write_text("\r\n".join(lines) + "\r\n", encoding="utf-16")
    return path

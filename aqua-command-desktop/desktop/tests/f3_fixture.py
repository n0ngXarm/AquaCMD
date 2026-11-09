"""Explicit historical configuration for legacy tests; never a runtime default.

These addresses are inert configuration assertions. The guarded runner refuses
all non-loopback connections, so this fixture cannot authorize an actual probe.
"""
from pathlib import Path


def configure_legacy_inventory(directory):
    fixture = Path(__file__).parent / "fixtures/f3_legacy_inventory.json"
    (Path(directory) / "network_topology.json").write_bytes(fixture.read_bytes())

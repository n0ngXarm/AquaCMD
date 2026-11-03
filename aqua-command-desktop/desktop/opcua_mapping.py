#!/usr/bin/env python3
"""
AquaCMD Gate B2 — OPC UA NodeId Mapping Module
Provides declarative, verified mapping between WinCC Tag Names and OPC UA NodeIds.
Resolves Namespace URIs dynamically to prevent namespace index shifting errors.
Strictly prohibits heuristic guessing.
"""

import json
import logging
from pathlib import Path
from typing import Dict, Optional, Tuple, List

logger = logging.getLogger("aquacmd.opcua.mapping")


class TagMapping:
    """Represents a verified OPC UA mapping record for a SCADA tag."""
    def __init__(self, tag_name: str, node_id_identifier: str, namespace_uri: str,
                 data_type: str = "Float", unit: str = "",
                 provenance: str = "Manual_Configuration", verified: bool = True):
        self.tag_name = tag_name
        self.node_id_identifier = node_id_identifier.strip()
        self.namespace_uri = namespace_uri.strip()
        self.data_type = data_type.strip()
        self.unit = unit.strip()
        self.provenance = provenance.strip()
        self.verified = bool(verified)

    def to_dict(self) -> dict:
        return {
            "tag_name": self.tag_name,
            "node_id_identifier": self.node_id_identifier,
            "namespace_uri": self.namespace_uri,
            "data_type": self.data_type,
            "unit": self.unit,
            "provenance": self.provenance,
            "verified": self.verified
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TagMapping":
        return cls(
            tag_name=data.get("tag_name", ""),
            node_id_identifier=data.get("node_id_identifier", ""),
            namespace_uri=data.get("namespace_uri", ""),
            data_type=data.get("data_type", "Float"),
            unit=data.get("unit", ""),
            provenance=data.get("provenance", "Unknown"),
            verified=data.get("verified", False)
        )


class NodeIdMapper:
    """Manages tag mapping dictionary, allowlist checks, and dynamic namespace resolution."""

    def __init__(self, mapping_file: Optional[Path] = None):
        self.mapping_file = mapping_file
        self.mappings: Dict[str, TagMapping] = {}
        if mapping_file and mapping_file.exists():
            self.load_from_file(mapping_file)

    def load_from_file(self, filepath: Path) -> bool:
        """Loads mapping definitions from JSON file."""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            raw_mappings = data.get("mappings", {})
            self.mappings.clear()
            for tag_name, entry in raw_mappings.items():
                entry["tag_name"] = tag_name
                self.mappings[tag_name] = TagMapping.from_dict(entry)
            logger.info("Loaded %d verified OPC UA tag mappings from %s", len(self.mappings), filepath)
            return True
        except Exception as e:
            logger.error("Failed to load tag mappings from %s: %s", filepath, e)
            return False

    def add_mapping(self, mapping: TagMapping):
        """Adds or updates a mapping in memory."""
        self.mappings[mapping.tag_name] = mapping

    def is_allowed(self, tag_name: str) -> bool:
        """Enforces explicit allowlist: tag must exist in mapping and be verified."""
        m = self.mappings.get(tag_name)
        return m is not None and m.verified

    def get_mapping(self, tag_name: str) -> Optional[TagMapping]:
        return self.mappings.get(tag_name)

    async def resolve_node_id_string(self, tag_name: str, client) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Dynamically resolves exact NodeId string by looking up namespace URI in the server.
        Prevents namespace index shifting errors across server restarts.
        Returns: (success, node_id_string, error_message)
        """
        if not self.is_allowed(tag_name):
            return False, None, f"Tag '{tag_name}' is not in the verified allowlist (Refused)"

        mapping = self.mappings[tag_name]
        try:
            # Dynamic Namespace Index Resolution via asyncua Client
            ns_idx = await client.get_namespace_index(mapping.namespace_uri)
        except Exception as ex:
            return False, None, f"Namespace URI '{mapping.namespace_uri}' not found on server: {ex}"

        # Construct deterministic NodeId string with dynamic ns_idx
        # Supports string identifiers: ns=X;s=... or numeric: ns=X;i=...
        identifier = mapping.node_id_identifier
        if identifier.startswith("s=") or identifier.startswith("i="):
            node_id_str = f"ns={ns_idx};{identifier}"
        else:
            # Default to string identifier if not prefixed
            node_id_str = f"ns={ns_idx};s={identifier}"

        return True, node_id_str, None

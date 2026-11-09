#!/usr/bin/env python3
"""
AquaCMD Gate B2 — Observable State Store Module
Maintains in-memory observations of OPC UA variables with quality fidelity,
distinct temporal domains (Source, Server, Arrival), and Industrial Graphite formatting.
"""

import threading
from copy import copy
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional


class Quality:
    """Standardized industrial data qualities."""
    GOOD = "GOOD"
    UNCERTAIN = "UNCERTAIN"
    BAD = "BAD"
    STALE = "STALE"
    NOT_OBSERVED = "NOT_OBSERVED"
    DISCONNECTED = "DISCONNECTED"


class TagObservation:
    """Represents a validated, point-in-time observation of a SCADA tag."""

    def __init__(self, tag_name: str, node_id: Optional[str] = None,
                 value: Any = None, quality: str = Quality.NOT_OBSERVED,
                 source_time: Optional[datetime] = None,
                 server_time: Optional[datetime] = None,
                 arrival_time: Optional[datetime] = None,
                 raw_status_name: str = "Good",
                 unit: str = "", endpoint_url: Optional[str] = None,
                 session_state: str = "UNKNOWN"):
        self.tag_name = tag_name
        self.node_id = node_id
        self.value = value
        self.quality = quality
        self.source_time = source_time
        self.server_time = server_time
        self.arrival_time = arrival_time
        self.raw_status_name = raw_status_name
        self.unit = unit
        # Private receipt binding; sanitized by the optional dashboard projection.
        self.endpoint_url = endpoint_url
        self.session_state = session_state

    def is_stale(self, max_age_seconds: float = 600.0) -> bool:
        """Determines if the observation is stale based on arrival or source time."""
        if self.quality in (Quality.NOT_OBSERVED, Quality.DISCONNECTED):
            return False
        ref_time = self.source_time or self.arrival_time
        if not ref_time:
            return True
        now = datetime.now(timezone.utc)
        if ref_time.tzinfo is None:
            ref_time = ref_time.replace(tzinfo=timezone.utc)
        return (now - ref_time).total_seconds() > max_age_seconds

    def to_presentation(self, stale_threshold_sec: float = 600.0) -> dict:
        """
        Formats observation into presentation tokens adhering strictly to Industrial Graphite rules.
        Never coerces Bad or Unknown values to 0 or False.
        """
        # 1. Not Observed
        if self.quality == Quality.NOT_OBSERVED:
            return {
                "display_val": "Not Observed",
                "badge_class": "badge-standby",
                "quality_text": "Not Observed",
                "timestamp_str": "-",
                "unit_str": self.unit
            }

        # 2. Disconnected
        if self.quality == Quality.DISCONNECTED:
            return {
                "display_val": f"❌ Disconnected ({self.raw_status_name[:20]})",
                "badge_class": "badge-nope",
                "quality_text": f"DISCONNECTED: {self.raw_status_name}",
                "timestamp_str": self.arrival_time.strftime("%H:%M:%S") if self.arrival_time else "-",
                "unit_str": self.unit
            }

        # 3. Stale Check (Applies to Good or Uncertain data)
        effective_quality = self.quality
        if effective_quality in (Quality.GOOD, Quality.UNCERTAIN) and self.is_stale(stale_threshold_sec):
            effective_quality = Quality.STALE

        # 4. Bad Quality
        if effective_quality == Quality.BAD:
            return {
                "display_val": f"⚠️ Fault ({self.raw_status_name})",
                "badge_class": "badge-nope",
                "quality_text": f"BAD: {self.raw_status_name}",
                "timestamp_str": self.source_time.strftime("%H:%M:%S") if self.source_time else "-",
                "unit_str": self.unit
            }

        # 5. Stale Quality
        if effective_quality == Quality.STALE:
            val_str = f"{self.value}" if self.value is not None else "-"
            return {
                "display_val": f"⚠️ Stale: {val_str}",
                "badge_class": "badge-sensor",
                "quality_text": "STALE (>10m)",
                "timestamp_str": self.source_time.strftime("%H:%M:%S") if self.source_time else "-",
                "unit_str": self.unit
            }

        # 6. Uncertain Quality
        if effective_quality == Quality.UNCERTAIN:
            val_str = f"{self.value}" if self.value is not None else "-"
            return {
                "display_val": f"⚠️ Uncertain ({self.raw_status_name}): {val_str}",
                "badge_class": "badge-sensor",
                "quality_text": f"UNCERTAIN: {self.raw_status_name}",
                "timestamp_str": self.source_time.strftime("%H:%M:%S") if self.source_time else "-",
                "unit_str": self.unit
            }

        # 7. Good Quality
        if isinstance(self.value, bool):
            display = "🟢 ON (ทำงาน)" if self.value else "⚪ OFF (หยุดทำงาน)"
            badge = "badge-active" if self.value else "badge-standby"
        elif isinstance(self.value, (int, float)):
            unit_suffix = f" {self.unit}" if self.unit else ""
            display = f"{self.value:.2f}{unit_suffix}"
            badge = "badge-active"
        else:
            unit_suffix = f" {self.unit}" if self.unit else ""
            display = f"{self.value}{unit_suffix}"
            badge = "badge-active"

        return {
            "display_val": display,
            "badge_class": badge,
            "quality_text": "GOOD",
            "timestamp_str": self.source_time.strftime("%H:%M:%S") if self.source_time else "-",
            "unit_str": self.unit
        }


class ObservableStateStore:
    """Thread-safe state repository for active SCADA observations."""

    def __init__(self):
        self._lock = threading.Lock()
        self._observations: Dict[str, TagObservation] = {}

    def get_observation(self, tag_name: str) -> TagObservation:
        with self._lock:
            if tag_name not in self._observations:
                return TagObservation(tag_name=tag_name, quality=Quality.NOT_OBSERVED)
            return self._observations[tag_name]

    def update_observation(self, obs: TagObservation):
        with self._lock:
            self._observations[obs.tag_name] = obs

    def snapshot_observations(self):
        """Copy receipt fields without exposing mutable store entries or holding its lock during I/O."""
        with self._lock:
            return tuple(copy(obs) for obs in self._observations.values())

    def update_from_datavalue(self, tag_name: str, node_id: str,
                              data_value: Any, unit: str = "",
                              arrival_time: Optional[datetime] = None,
                              *, endpoint_url: Optional[str] = None,
                              session_state: str = "UNKNOWN") -> TagObservation:
        """
        Parses an authentic asyncua.ua.DataValue object, extracts genuine value and status,
        and records the observation in the store without data coercion.
        """
        if arrival_time is None:
            arrival_time = datetime.now(timezone.utc)

        # Handle None response
        if data_value is None:
            obs = TagObservation(
                tag_name=tag_name,
                node_id=node_id,
                value=None,
                quality=Quality.BAD,
                arrival_time=arrival_time,
                raw_status_name="BadNoData",
                unit=unit, endpoint_url=endpoint_url, session_state=session_state
            )
            self.update_observation(obs)
            return obs

        # Extract StatusCode & Quality
        status_code = getattr(data_value, 'StatusCode', None)
        is_good = status_code.is_good() if status_code else False
        is_bad = status_code.is_bad() if status_code else True
        status_name = status_code.name if hasattr(status_code, 'name') else str(status_code)

        # Extract Raw Value without coercive conversion
        val_wrapper = getattr(data_value, 'Value', None)
        raw_val = val_wrapper.Value if hasattr(val_wrapper, 'Value') else val_wrapper

        if is_good:
            qual = Quality.GOOD
        elif is_bad:
            qual = Quality.BAD
        else:
            qual = Quality.UNCERTAIN

        obs = TagObservation(
            tag_name=tag_name,
            node_id=node_id,
            value=raw_val,
            quality=qual,
            source_time=getattr(data_value, 'SourceTimestamp', None),
            server_time=getattr(data_value, 'ServerTimestamp', None),
            arrival_time=arrival_time,
            raw_status_name=status_name,
            unit=unit, endpoint_url=endpoint_url, session_state=session_state
        )
        self.update_observation(obs)
        return obs

    def mark_disconnected(self, tag_name: str, node_id: Optional[str], reason: str):
        with self._lock:
            self._observations[tag_name] = TagObservation(
                tag_name=tag_name,
                node_id=node_id,
                value=None,
                quality=Quality.DISCONNECTED,
                arrival_time=datetime.now(timezone.utc),
                raw_status_name=reason
            )

    def clear(self):
        with self._lock:
            self._observations.clear()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
task_engine.py — Task Evaluation & Alert Rule Engine for AQUA COMMAND
Evaluates real-time OPC UA Tag Observations against configured Task rules
with Strict Quality Isolation, Debounce/Consecutive Sampling, Cooldown,
and Event Deduplication.

Strict Invariants:
- Bad quality is NEVER treated as False/0 (prevents false OFF transitions).
- Event deduplication prevents continuous 5-second notification spam.
- Multiple tasks monitoring the same tag share a single observation fan-out.
"""

import sys
import uuid
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional, Set, Tuple
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field

from opcua_storage import DurableStorage, TaskEvent, TaskRuntimeState, StoredObservation

logger = logging.getLogger("aqua.task_engine")


@dataclass
class TaskDefinition:
    id: str
    name: str
    enabled: bool = True
    tags: List[str] = field(default_factory=list)
    condition_type: str = "threshold_above"  # threshold_above, threshold_below, transition_on, transition_off, quality_bad
    threshold: Optional[float] = None
    debounce_samples: int = 1  # Required consecutive cycles
    cooldown_seconds: float = 60.0  # Minimum delay between alerts
    severity: str = "WARNING"  # INFO, WARNING, CRITICAL
    notification_channels: List[Dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "TaskDefinition":
        # Support both 'enabled' and 'active' keys
        enabled_val = d.get("enabled")
        if enabled_val is None:
            enabled_val = d.get("active", True)

        # Support 'tags', 'assigned_tags', or single 'tag_name'
        tags_val = d.get("tags")
        if tags_val is None:
            tags_val = d.get("assigned_tags")
        if tags_val is None:
            tags_val = [d["tag_name"]] if d.get("tag_name") else []
        elif isinstance(tags_val, (set, tuple)):
            tags_val = list(tags_val)

        # Support 'condition_type' or 'rule_type'
        cond_type = d.get("condition_type", d.get("rule_type", "threshold_above"))

        # Support 'debounce_samples' or 'debounce_count' or 'debounce'
        deb_samples = d.get("debounce_samples")
        if deb_samples is None:
            deb_samples = d.get("debounce_count", d.get("debounce", 1))

        # Support 'cooldown_seconds' or 'cooldown'
        cd_sec = d.get("cooldown_seconds")
        if cd_sec is None:
            cd_sec = d.get("cooldown", 60.0)

        # Support 'notification_channels' or 'alert_channel'
        channels = d.get("notification_channels")
        if not channels:
            ch_type = d.get("alert_channel", "telegram")
            recip = d.get("recipient", "")
            channels = [{"channel": ch_type, "recipient": recip}]

        return cls(
            id=str(d.get("id") or str(uuid.uuid4().hex[:8])),
            name=d.get("name", "Untitled Task"),
            enabled=bool(enabled_val),
            tags=list(tags_val),
            condition_type=str(cond_type),
            threshold=float(d["threshold"]) if d.get("threshold") is not None else None,
            debounce_samples=int(deb_samples),
            cooldown_seconds=float(cd_sec),
            severity=d.get("severity", "WARNING"),
            notification_channels=list(channels)
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "enabled": self.enabled,
            "tags": self.tags,
            "condition_type": self.condition_type,
            "threshold": self.threshold,
            "debounce_samples": self.debounce_samples,
            "cooldown_seconds": self.cooldown_seconds,
            "severity": self.severity,
            "notification_channels": self.notification_channels
        }


class TaskEngine:
    """Evaluates Tag Observations against Task Definitions and dispatches alerts to DurableStorage."""

    def __init__(self, storage: DurableStorage):
        self.storage = storage
        self.tasks: Dict[str, TaskDefinition] = {}

    def load_tasks(self, task_list: List[Dict[str, Any]]):
        self.tasks.clear()
        for t_dict in task_list:
            t = TaskDefinition.from_dict(t_dict)
            self.tasks[t.id] = t
        logger.info("TaskEngine loaded %d tasks (%d enabled)", len(self.tasks), sum(1 for t in self.tasks.values() if t.enabled))

    def get_task(self, task_id: str) -> Optional[TaskDefinition]:
        return self.tasks.get(task_id)

    def get_required_tags(self) -> Set[str]:
        """Returns the distinct set of tags needed by all enabled tasks."""
        required: Set[str] = set()
        for t in self.tasks.values():
            if t.enabled:
                for tag in t.tags:
                    required.add(tag)
        return required

    def evaluate_observations(
        self,
        observations: Dict[str, StoredObservation],
        current_time: Optional[datetime] = None
    ) -> List[TaskEvent]:
        """
        Evaluates a dictionary of observations {tag_name: StoredObservation}.
        Fanes out each observation to matching enabled tasks.
        Returns a list of newly generated TaskEvents.
        """
        if not current_time:
            current_time = datetime.now(timezone.utc)
        now_iso = current_time.isoformat()

        generated_events: List[TaskEvent] = []

        for task in self.tasks.values():
            if not task.enabled:
                continue

            # A task can monitor one primary tag or multiple; for each assigned tag that has a new observation:
            for tag_name in task.tags:
                if tag_name not in observations:
                    continue
                obs = observations[tag_name]
                event = self._evaluate_single_task_tag(task, obs, current_time, now_iso)
                if event:
                    generated_events.append(event)

        return generated_events

    def _evaluate_single_task_tag(
        self,
        task: TaskDefinition,
        obs: StoredObservation,
        now: datetime,
        now_iso: str
    ) -> Optional[TaskEvent]:
        state = self.storage.get_runtime_state(task.id)
        if not state:
            state = TaskRuntimeState(task_id=task.id)

        # Rule B: Strict Quality Isolation
        # If quality is BAD/UNCERTAIN and task is NOT checking for 'quality_bad', do not evaluate as false/0
        is_bad_quality = (obs.quality.upper() != "GOOD")

        if task.condition_type != "quality_bad" and is_bad_quality:
            # Bad quality must NEVER be treated as 0 or OFF!
            # Reset consecutive count or preserve state without false transition
            state.consecutive_samples = 0
            state.last_evaluated_quality = obs.quality
            state.last_evaluated_at = now_iso
            self.storage.save_runtime_state(state)
            return None

        condition_met = False
        desc = ""
        trigger_val = obs.value

        # Numeric conversion if applicable
        num_val: Optional[float] = None
        if isinstance(obs.value, (int, float)) and not isinstance(obs.value, bool):
            num_val = float(obs.value)
        elif isinstance(obs.value, str):
            try:
                num_val = float(obs.value)
            except ValueError:
                num_val = None

        bool_val: Optional[bool] = None
        if isinstance(obs.value, bool):
            bool_val = obs.value
        elif num_val is not None:
            bool_val = bool(num_val != 0.0)

        # Condition logic
        if task.condition_type == "threshold_above":
            if num_val is not None and task.threshold is not None:
                condition_met = (num_val > task.threshold)
                desc = f"{task.name}: {obs.tag_name} = {num_val:.2f} {obs.unit} เกินเกณฑ์ที่กำหนด (> {task.threshold:.2f})"
        elif task.condition_type == "threshold_below":
            if num_val is not None and task.threshold is not None:
                condition_met = (num_val < task.threshold)
                desc = f"{task.name}: {obs.tag_name} = {num_val:.2f} {obs.unit} ต่ำกว่าเกณฑ์ที่กำหนด (< {task.threshold:.2f})"
        elif task.condition_type == "transition_on":
            # ON transition: previous was False/0, now True/1
            prev_bool = bool(state.last_evaluated_value) if state.last_evaluated_value is not None else False
            if bool_val is True and (prev_bool is False or state.active_state == 0):
                condition_met = True
                desc = f"{task.name}: {obs.tag_name} เปลี่ยนสถานะเป็นเปิด (ON / Running)"
        elif task.condition_type == "transition_off":
            # OFF transition: previous was True/1, now False/0
            prev_bool = bool(state.last_evaluated_value) if state.last_evaluated_value is not None else True
            if bool_val is False and (prev_bool is True or state.active_state == 0):
                condition_met = True
                desc = f"{task.name}: {obs.tag_name} เปลี่ยนสถานะเป็นปิด (OFF / Stopped)"
        elif task.condition_type == "quality_bad":
            condition_met = is_bad_quality
            desc = f"{task.name}: คุณภาพสัญญาณ {obs.tag_name} ขัดข้อง (Quality: {obs.quality})"

        # Debounce / Consecutive Samples evaluation
        if condition_met:
            state.consecutive_samples += 1
        else:
            state.consecutive_samples = 0
            # Reset active_state when condition is no longer met
            if state.active_state == 1:
                state.active_state = 0
                logger.info("Task %s condition cleared. active_state reset to 0.", task.name)

        # Check debounce threshold
        debounced = (state.consecutive_samples >= max(1, task.debounce_samples))

        # Event Deduplication & Cooldown Check
        should_trigger = False
        if condition_met and debounced:
            if state.active_state == 0:
                # First time triggering into active state
                should_trigger = True
            else:
                # Already active: check cooldown
                if state.last_triggered_at and task.cooldown_seconds > 0:
                    try:
                        last_trig_dt = datetime.fromisoformat(state.last_triggered_at)
                        elapsed = (now - last_trig_dt).total_seconds()
                        if elapsed >= task.cooldown_seconds:
                            should_trigger = True
                    except Exception:
                        should_trigger = True

        event: Optional[TaskEvent] = None
        if should_trigger:
            state.active_state = 1
            state.last_triggered_at = now_iso
            evt_id = f"evt_{uuid.uuid4().hex[:12]}"
            event = TaskEvent(
                event_id=evt_id,
                task_id=task.id,
                task_name=task.name,
                tag_name=obs.tag_name,
                trigger_type=task.condition_type,
                trigger_value=obs.value,
                threshold_value=task.threshold,
                description=desc,
                severity=task.severity,
                created_at=now_iso
            )

            # Prepare notification outbox items
            outbox_entries = []
            for ch in task.notification_channels:
                c_type = ch.get("channel", "telegram")
                recip = ch.get("recipient", "")
                payload = {
                    "event_id": evt_id,
                    "task_name": task.name,
                    "tag_name": obs.tag_name,
                    "trigger_type": task.condition_type,
                    "value": obs.value,
                    "unit": obs.unit,
                    "severity": task.severity,
                    "description": desc,
                    "timestamp": now.strftime("%Y-%m-%d %H:%M:%S")
                }
                outbox_entries.append((c_type, recip, payload))

        # Update runtime state
        state.last_evaluated_value = num_val if num_val is not None else (1.0 if bool_val else 0.0)
        state.last_evaluated_quality = obs.quality
        state.last_evaluated_at = now_iso
        if event is None:
            self.storage.save_runtime_state(state)
            return None
        if not self.storage.record_event_and_enqueue_outbox(event, outbox_entries, runtime_state=state):
            logger.error("Task %s trigger was not committed", task.id)
            return None
        logger.warning("Task triggered: %s -> Event %s enqueued", desc, event.event_id)
        return event

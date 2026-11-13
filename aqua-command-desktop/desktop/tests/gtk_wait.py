"""Shared deterministic GLib/GTK wait helpers for test suites."""
import time
from gi.repository import GLib


def pump_events(max_events=100):
    """Drain pending GLib events without blocking."""
    context = GLib.MainContext.default()
    count = 0
    while context.pending() and count < max_events:
        context.iteration(False)
        count += 1
    return count


def wait_for(predicate, timeout=5.0, interval=0.01, message=None):
    """Iterate the GLib main context until predicate returns truthy or timeout expires."""
    deadline = time.monotonic() + timeout
    last_val = None
    while time.monotonic() < deadline:
        pump_events()
        try:
            val = predicate()
            if val:
                return val
            last_val = val
        except Exception as exc:
            last_val = exc
        time.sleep(interval)
    err_msg = message() if callable(message) else message
    if err_msg is None:
        err_msg = f"Timed out after {timeout:.2f}s waiting for condition (last value: {last_val!r})"
    raise AssertionError(err_msg)


def wait_for_layout_stable(widget, *, condition=None, timeout=5.0, interval=0.01, stable_cycles=2):
    """Wait until widget allocation satisfies condition and remains stable for consecutive iterations."""
    history = []

    def check():
        if hasattr(widget, 'get_mapped') and not widget.get_mapped():
            return False
        w = widget.get_width() if hasattr(widget, 'get_width') else 0
        h = widget.get_height() if hasattr(widget, 'get_height') else 0
        if condition is not None and not condition(widget):
            return False
        history.append((w, h))
        if len(history) >= stable_cycles and len(set(history[-stable_cycles:])) == 1:
            return history[-1]
        return False

    def on_timeout():
        w = widget.get_width() if hasattr(widget, 'get_width') else 'N/A'
        h = widget.get_height() if hasattr(widget, 'get_height') else 'N/A'
        mapped = widget.get_mapped() if hasattr(widget, 'get_mapped') else 'N/A'
        return (f"Layout for {widget} did not stabilize within {timeout:.2f}s "
                f"(mapped={mapped}, width={w}, height={h}, recent_history={history[-4:]})")

    return wait_for(check, timeout=timeout, interval=interval, message=on_timeout)

"""Passive metrics from this host/process. No address enumeration or probes."""
import time

try:
    import psutil
except ImportError:
    psutil = None

from .contract import iso


def rate(current, previous, elapsed):
    if current is None or previous is None or elapsed <= 0 or current < previous:
        return None
    return (current - previous) / elapsed


class HostMetrics:
    def __init__(self, contract):
        self.contract = contract
        self.previous = None
        self.process = psutil.Process() if psutil else None

    def sample(self):
        wall, mono = time.time(), time.monotonic()
        result = {"timestamp": iso(wall), "provenance": "OBSERVED_LOCAL", "state": "ERROR",
                  "cpu_percent": None, "process_cpu_percent": None, "interfaces": []}
        if psutil is None:
            return result
        try:
            cpu = psutil.cpu_percent(interval=None)
            process_cpu = self.process.cpu_percent(interval=None)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage("/")
            io = psutil.disk_io_counters(nowrap=False)
            network = psutil.net_io_counters(pernic=True, nowrap=False)
            stats = psutil.net_if_stats()
            previous = self.previous
            elapsed = mono - previous[0] if previous else 0
            old_io = previous[1] if previous else None
            old_net = previous[2] if previous else {}
            self.previous = (mono, io, network)
            result.update(state="AVAILABLE" if previous else "WARMING_UP",
                cpu_percent=cpu if previous else None,
                process_cpu_percent=process_cpu if previous else None,
                memory_percent=memory.percent, memory_used_bytes=memory.used,
                memory_total_bytes=memory.total, disk_percent=disk.percent,
                disk_free_bytes=disk.free, process_rss_bytes=self.process.memory_info().rss,
                process_threads=self.process.num_threads(),
                disk_read_bytes_per_sec=rate(io.read_bytes if io else None, old_io.read_bytes if old_io else None, elapsed),
                disk_write_bytes_per_sec=rate(io.write_bytes if io else None, old_io.write_bytes if old_io else None, elapsed))
            for name, counter in network.items():
                old = old_net.get(name)
                interface = stats.get(name)
                result["interfaces"].append({"interface_id": self.contract.identity("nic", name),
                    "link_state": "UP" if interface and interface.isup else "DOWN" if interface else "UNKNOWN",
                    "rx_bytes_per_sec": rate(counter.bytes_recv, old.bytes_recv if old else None, elapsed),
                    "tx_bytes_per_sec": rate(counter.bytes_sent, old.bytes_sent if old else None, elapsed),
                    "timestamp": iso(wall), "provenance": "OBSERVED_LOCAL"})
            for direction in ("rx", "tx"):
                rates = [r[direction + "_bytes_per_sec"] for r in result["interfaces"]]
                result["network_" + direction + "_bytes_per_sec"] = sum(rates) if rates and all(v is not None for v in rates) else None
        except (OSError, psutil.Error):
            self.previous = None
        return result

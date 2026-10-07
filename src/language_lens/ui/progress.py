"""Shared transfer feedback; callers provide monotonic times for easy testing."""
from collections import deque


def size_label(size: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1000 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1000
    return ""


def duration_label(seconds: float) -> str:
    seconds = max(0, int(seconds))
    return f"{seconds} s" if seconds < 60 else f"{seconds // 60} min {seconds % 60:02} s"


class TransferMetrics:
    def __init__(self, now: float) -> None:
        self.reset(now)

    def reset(self, now: float) -> None:
        self.started = self.last_byte = now
        self.received: int | None = None
        self.total: int | None = None
        self.samples: deque[tuple[float, int]] = deque()

    def update(self, received: int, total: int | None, now: float) -> None:
        # Restarted transfers and new files must not inherit an old speed/ETA.
        if self.received is None or received < self.received:
            self.reset(now)
            self.samples.append((now, received))
        if self.received is None or received > self.received:
            self.last_byte = now
        self.received, self.total = received, total

    def text(self, now: float) -> str:
        if self.received is None:
            return f"{duration_label(now - self.started)} elapsed"
        self.samples.append((now, self.received))
        while len(self.samples) > 2 and self.samples[1][0] <= now - 3:
            self.samples.popleft()
        elapsed = now - self.samples[0][0]
        rate = max(0, self.received - self.samples[0][1]) / elapsed if elapsed > .1 else 0
        amount = (f"{min(100, self.received * 100 / self.total):.1f}% · "
                  f"{size_label(self.received)} / {size_label(self.total)}" if self.total else
                  f"{size_label(self.received)} downloaded · total size unavailable")
        details = f"{amount} · {size_label(rate)}/s · {duration_label(now - self.started)} elapsed"
        idle = now - self.last_byte
        if idle >= 3:
            details += f" · Waiting for data ({duration_label(idle)})"
        elif self.total and rate > 0 and self.received < self.total:
            details += f" · ~{duration_label((self.total - self.received) / rate)} remaining"
        return details

"""工具共用的数据模型与纯计算。"""

from __future__ import annotations

import hashlib
import statistics
import time
from dataclasses import asdict, dataclass
from enum import StrEnum

import numpy as np


class FrameProblem(StrEnum):
    """画面有效性问题。"""

    BLACK = '黑帧'
    DUPLICATE = '重复帧'
    STALE = '固定旧帧'
    SIZE_CHANGED = '尺寸变化'


@dataclass(frozen=True)
class CaptureResult:
    """一次截图的统一返回值。"""

    image: np.ndarray | None
    timestamp: float
    elapsed_ms: float
    error: str | None = None


@dataclass(frozen=True)
class WindowIdentity:
    """用于共同识别游戏窗口的信息。"""

    hwnd: int
    pid: int
    executable: str
    class_name: str
    title: str
    client_width: int
    client_height: int
    dpi: int
    minimized: bool
    foreground: bool
    occluded: bool | None
    handle_rebuilt: bool = False


@dataclass(frozen=True)
class Metrics:
    """一次状态测试的统计结果。"""

    average_ms: float
    p50_ms: float
    p95_ms: float
    effective_fps: float
    cpu_percent: float
    memory_delta_mb: float
    valid_ratio: float
    failures: int

    def to_dict(self) -> dict[str, float | int]:
        """转换为可导出的字典。"""
        return asdict(self)


class FrameValidator:
    """检测黑帧、重复帧、固定旧帧和尺寸变化。"""

    def __init__(self, stale_seconds: float = 2.0) -> None:
        """初始化检测器。

        Args:
            stale_seconds: 相同画面持续多久后算固定旧帧。
        """
        self.stale_seconds: float = stale_seconds
        self._digest: bytes | None = None
        self._shape: tuple[int, ...] | None = None
        self._same_since: float | None = None

    def inspect(self, image: np.ndarray, now: float | None = None) -> set[FrameProblem]:
        """检查一帧并返回发现的问题。"""
        current_time = time.monotonic() if now is None else now
        problems: set[FrameProblem] = set()
        if image.size == 0 or float(image.mean()) < 2.0:
            problems.add(FrameProblem.BLACK)
        if self._shape is not None and image.shape != self._shape:
            problems.add(FrameProblem.SIZE_CHANGED)
        digest = hashlib.blake2b(image.tobytes(), digest_size=16).digest()
        if digest == self._digest:
            problems.add(FrameProblem.DUPLICATE)
            if (
                self._same_since is not None
                and current_time - self._same_since >= self.stale_seconds
            ):
                problems.add(FrameProblem.STALE)
        else:
            self._same_since = current_time
        self._digest = digest
        self._shape = image.shape
        return problems


def percentile(values: list[float], fraction: float) -> float:
    """使用线性插值计算百分位。"""
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def calculate_metrics(
    latencies: list[float],
    valid_frames: int,
    duration_seconds: float,
    cpu_percent: float,
    memory_delta_bytes: int,
    failures: int,
) -> Metrics:
    """计算后端状态测试的指标。"""
    total = valid_frames + failures
    return Metrics(
        average_ms=statistics.fmean(latencies) if latencies else 0.0,
        p50_ms=percentile(latencies, 0.50),
        p95_ms=percentile(latencies, 0.95),
        effective_fps=valid_frames / duration_seconds if duration_seconds > 0 else 0.0,
        cpu_percent=cpu_percent,
        memory_delta_mb=memory_delta_bytes / 1024 / 1024,
        valid_ratio=valid_frames / total if total else 0.0,
        failures=failures,
    )

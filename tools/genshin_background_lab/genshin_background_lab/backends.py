"""统一截图后端及显式回退控制。"""

from __future__ import annotations

import ctypes
import sys
import time
from abc import ABC, abstractmethod
from collections.abc import Callable

import mss
import numpy as np

from genshin_background_lab.models import CaptureResult


class CaptureBackend(ABC):
    """所有截图实现必须遵守的接口。"""

    name: str

    @abstractmethod
    def capture(self, hwnd: int) -> CaptureResult:
        """截取目标客户区，失败时返回明确错误。"""


def _failed(start: float, message: str) -> CaptureResult:
    """构造带耗时的失败结果。"""
    return CaptureResult(
        None, time.time(), (time.perf_counter() - start) * 1000, message
    )


def _client_box(hwnd: int) -> tuple[int, int, int, int]:
    """读取客户区在桌面中的坐标。"""
    import win32gui

    left, top = win32gui.ClientToScreen(hwnd, (0, 0))
    _, _, width, height = win32gui.GetClientRect(hwnd)
    return left, top, width, height


class MssDesktopBackend(CaptureBackend):
    """通过 MSS 从桌面截取客户区，可被遮挡。"""

    name = 'MSS/桌面截取'

    def capture(self, hwnd: int) -> CaptureResult:
        """截取桌面中目标客户区的位置。"""
        start = time.perf_counter()
        if sys.platform != 'win32':
            return _failed(start, 'MSS 客户区定位仅支持 Windows')
        try:
            left, top, width, height = _client_box(hwnd)
            with mss.mss() as recorder:
                frame = np.asarray(
                    recorder.grab(
                        {'left': left, 'top': top, 'width': width, 'height': height}
                    )
                )
            return CaptureResult(
                frame[:, :, :3].copy(),
                time.time(),
                (time.perf_counter() - start) * 1000,
            )
        except (OSError, ValueError) as error:
            return _failed(start, f'MSS 截图失败：{error}')


class BitBltBackend(CaptureBackend):
    """通过 BitBlt 复制客户区设备上下文。"""

    name = 'BitBlt'

    def capture(self, hwnd: int) -> CaptureResult:
        """使用 BitBlt 截取客户区。"""
        start = time.perf_counter()
        if sys.platform != 'win32':
            return _failed(start, 'BitBlt 仅支持 Windows')
        import win32con
        import win32gui
        import win32ui

        width, height = _client_box(hwnd)[2:]
        window_dc = win32gui.GetDC(hwnd)
        source = win32ui.CreateDCFromHandle(window_dc)
        target = source.CreateCompatibleDC()
        bitmap = win32ui.CreateBitmap()
        try:
            bitmap.CreateCompatibleBitmap(source, width, height)
            target.SelectObject(bitmap)
            target.BitBlt((0, 0), (width, height), source, (0, 0), win32con.SRCCOPY)
            data = bitmap.GetBitmapBits(True)
            frame = np.frombuffer(data, dtype=np.uint8).reshape(height, width, 4)
            return CaptureResult(
                frame[:, :, :3].copy(),
                time.time(),
                (time.perf_counter() - start) * 1000,
            )
        except (OSError, ValueError) as error:
            return _failed(start, f'BitBlt 截图失败：{error}')
        finally:
            win32gui.DeleteObject(bitmap.GetHandle())
            target.DeleteDC()
            source.DeleteDC()
            win32gui.ReleaseDC(hwnd, window_dc)


class PrintWindowBackend(CaptureBackend):
    """通过 PrintWindow 请求窗口绘制客户区。"""

    name = 'PrintWindow'

    def capture(self, hwnd: int) -> CaptureResult:
        """使用 PW_CLIENTONLY 截取客户区。"""
        start = time.perf_counter()
        if sys.platform != 'win32':
            return _failed(start, 'PrintWindow 仅支持 Windows')
        import win32gui
        import win32ui

        width, height = _client_box(hwnd)[2:]
        window_dc = win32gui.GetWindowDC(hwnd)
        source = win32ui.CreateDCFromHandle(window_dc)
        target = source.CreateCompatibleDC()
        bitmap = win32ui.CreateBitmap()
        try:
            bitmap.CreateCompatibleBitmap(source, width, height)
            target.SelectObject(bitmap)
            ok = ctypes.windll.user32.PrintWindow(hwnd, target.GetSafeHdc(), 1)
            if not ok:
                return _failed(start, 'PrintWindow 返回失败')
            frame = np.frombuffer(bitmap.GetBitmapBits(True), dtype=np.uint8).reshape(
                height, width, 4
            )
            return CaptureResult(
                frame[:, :, :3].copy(),
                time.time(),
                (time.perf_counter() - start) * 1000,
            )
        except (OSError, ValueError) as error:
            return _failed(start, f'PrintWindow 截图失败：{error}')
        finally:
            win32gui.DeleteObject(bitmap.GetHandle())
            target.DeleteDC()
            source.DeleteDC()
            win32gui.ReleaseDC(hwnd, window_dc)


class WindowsGraphicsCaptureBackend(CaptureBackend):
    """Windows Graphics Capture 后端。

    windows-capture 的回调式会话需要单独线程持续运行；本实验版会明确报告
    尚未建立会话，不会拿桌面截图冒充 WGC 结果。
    """

    name = 'Windows Graphics Capture'

    def capture(self, hwnd: int) -> CaptureResult:
        """报告 WGC 会话状态。"""
        start = time.perf_counter()
        if sys.platform != 'win32':
            return _failed(start, 'Windows Graphics Capture 仅支持 Windows')
        try:
            __import__('windows_capture')
        except ImportError:
            return _failed(start, '缺少 windows-capture 可选依赖')
        return _failed(start, f'尚未为窗口 {hwnd} 建立 WGC 连续捕获会话')


class BackendSelector:
    """管理实际后端，禁止无提示地切换。"""

    def __init__(
        self,
        backends: list[CaptureBackend],
        auto_fallback: bool = False,
        on_switch: Callable[[str], None] | None = None,
    ) -> None:
        """初始化后端选择器。"""
        if not backends:
            raise ValueError('至少需要一个截图后端')
        self.backends: list[CaptureBackend] = backends
        self.index: int = 0
        self.auto_fallback: bool = auto_fallback
        self.on_switch: Callable[[str], None] | None = on_switch

    @property
    def active(self) -> CaptureBackend:
        """返回实际正在使用的后端。"""
        return self.backends[self.index]

    def capture(self, hwnd: int) -> CaptureResult:
        """截图；仅在用户允许时记录原因并回退。"""
        result = self.active.capture(hwnd)
        if (
            result.error is None
            or not self.auto_fallback
            or self.index + 1 >= len(self.backends)
        ):
            return result
        previous = self.active.name
        self.index += 1
        reason = f'{previous} 失效：{result.error}；切换到 {self.active.name}'
        if self.on_switch is not None:
            self.on_switch(reason)
        return self.active.capture(hwnd)

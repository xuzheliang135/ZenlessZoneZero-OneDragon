"""Windows 窗口枚举与识别。"""

from __future__ import annotations

import sys
from pathlib import Path

import psutil

from genshin_background_lab.models import WindowIdentity

GENSHIN_EXECUTABLES = {'GenshinImpact.exe', 'YuanShen.exe'}
GENSHIN_CLASSES = {'UnityWndClass'}


def is_genshin_candidate(
    executable: str,
    class_name: str,
    title: str,
    expected_pid: int | None = None,
    pid: int | None = None,
) -> bool:
    """用进程、文件名、窗口类名和标题共同筛选原神窗口。"""
    if expected_pid is not None and pid != expected_pid:
        return False
    executable_match = Path(executable).name.casefold() in {
        item.casefold() for item in GENSHIN_EXECUTABLES
    }
    class_match = class_name in GENSHIN_CLASSES
    title_match = '原神' in title or 'genshin impact' in title.casefold()
    return executable_match and class_match and title_match and pid is not None


def enumerate_genshin_windows(
    previous: dict[int, int] | None = None,
) -> list[WindowIdentity]:
    """枚举原神顶层窗口并记录运行状态。"""
    if sys.platform != 'win32':
        return []
    import win32gui
    import win32process

    results: list[WindowIdentity] = []
    foreground = win32gui.GetForegroundWindow()

    def visit(hwnd: int, _: object) -> None:
        """检查一个顶层窗口。"""
        if not win32gui.IsWindowVisible(hwnd):
            return
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        try:
            executable = psutil.Process(pid).exe()
        except (psutil.Error, OSError):
            return
        class_name = win32gui.GetClassName(hwnd)
        title = win32gui.GetWindowText(hwnd)
        if not is_genshin_candidate(executable, class_name, title, pid=pid):
            return
        left, top, right, bottom = win32gui.GetClientRect(hwnd)
        dpi = (
            int(win32gui.GetDpiForWindow(hwnd))
            if hasattr(win32gui, 'GetDpiForWindow')
            else 96
        )
        old_handle = None if previous is None else previous.get(pid)
        results.append(
            WindowIdentity(
                hwnd=hwnd,
                pid=pid,
                executable=executable,
                class_name=class_name,
                title=title,
                client_width=right - left,
                client_height=bottom - top,
                dpi=dpi,
                minimized=bool(win32gui.IsIconic(hwnd)),
                foreground=hwnd == foreground,
                occluded=None,
                handle_rebuilt=old_handle is not None and old_handle != hwnd,
            )
        )

    win32gui.EnumWindows(visit, None)
    return results

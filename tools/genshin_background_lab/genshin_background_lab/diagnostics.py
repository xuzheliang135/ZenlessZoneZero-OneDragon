"""启动诊断。"""

from __future__ import annotations

import ctypes
import importlib.util
import platform
import sys
from dataclasses import dataclass


@dataclass(frozen=True)
class DiagnosticItem:
    """一项启动诊断结果。"""

    name: str
    passed: bool
    detail: str


def run_diagnostics() -> list[DiagnosticItem]:
    """检查 Windows、权限、依赖和虚拟手柄驱动。"""
    windows = sys.platform == 'win32'
    items = [
        DiagnosticItem(
            'Python 3.11', sys.version_info[:2] == (3, 11), platform.python_version()
        ),
        DiagnosticItem('Windows 版本', windows, platform.platform()),
        DiagnosticItem(
            'MSS', importlib.util.find_spec('mss') is not None, '桌面截图依赖'
        ),
        DiagnosticItem(
            'windows-capture',
            importlib.util.find_spec('windows_capture') is not None,
            'WGC 可选依赖',
        ),
    ]
    elevated = bool(ctypes.windll.shell32.IsUserAnAdmin()) if windows else False
    items.append(DiagnosticItem('权限等级', True, '管理员' if elevated else '标准用户'))
    try:
        import vgamepad

        device = vgamepad.VX360Gamepad()
        device.reset()
        device.update()
        del device
        items.append(
            DiagnosticItem(
                'ViGEmBus 创建设备', True, '已实际创建并释放 Xbox 360 测试设备'
            )
        )
    except (ImportError, OSError, RuntimeError) as error:
        items.append(DiagnosticItem('ViGEmBus 创建设备', False, f'创建失败：{error}'))
    return items

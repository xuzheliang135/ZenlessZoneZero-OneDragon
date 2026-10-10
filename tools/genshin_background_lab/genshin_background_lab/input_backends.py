"""安全输入后端与统一释放。"""

from __future__ import annotations

import ctypes
import sys
from abc import ABC, abstractmethod


def encode_client_coordinates(x: int, y: int) -> int:
    """按 Windows 消息格式编码完整客户区坐标。"""
    return ((y & 0xFFFF) << 16) | (x & 0xFFFF)


class InputBackend(ABC):
    """输入后端统一接口。"""

    name: str
    system_wide: bool

    @abstractmethod
    def tap_cancel(self, hwnd: int) -> str:
        """发送一次安全的取消动作并返回验证说明。"""

    @abstractmethod
    def release_all(self) -> None:
        """释放按键、按钮、扳机和摇杆。"""


class WindowMessageBackend(InputBackend):
    """标准窗口键盘和鼠标消息后端。"""

    name = '窗口消息'
    system_wide = False

    def tap_cancel(self, hwnd: int) -> str:
        """发送一次 Escape；返回成功不等于游戏收到。"""
        if sys.platform != 'win32':
            return '仅支持 Windows'
        import win32con
        import win32gui

        down = win32gui.PostMessage(hwnd, win32con.WM_KEYDOWN, win32con.VK_ESCAPE, 0)
        up = win32gui.PostMessage(hwnd, win32con.WM_KEYUP, win32con.VK_ESCAPE, 0)
        return f'消息已投递({down and up})；必须看画面或人工确认游戏是否收到'

    def move_drag(self, hwnd: int, points: list[tuple[int, int]]) -> None:
        """用连续 WM_MOUSEMOVE 发送客户区拖拽。"""
        import win32con
        import win32gui

        for x, y in points:
            win32gui.PostMessage(
                hwnd,
                win32con.WM_MOUSEMOVE,
                win32con.MK_LBUTTON,
                encode_client_coordinates(x, y),
            )

    def release_all(self) -> None:
        """窗口消息没有持久设备状态。"""


class SendInputBackend(InputBackend):
    """系统级 SendInput 后端，不绑定目标窗口。"""

    name = 'SendInput（系统级）'
    system_wide = True

    def tap_cancel(self, hwnd: int) -> str:
        """向当前系统前台发送一次 Escape。"""
        if sys.platform != 'win32':
            return '仅支持 Windows'
        ctypes.windll.user32.keybd_event(0x1B, 0, 0, 0)
        ctypes.windll.user32.keybd_event(0x1B, 0, 2, 0)
        return '已向系统前台发送；不保证目标游戏收到'

    def release_all(self) -> None:
        """释放本后端可能按住的测试键。"""
        if sys.platform == 'win32':
            ctypes.windll.user32.keybd_event(0x1B, 0, 2, 0)


class VirtualGamepadBackend(InputBackend):
    """vgamepad 虚拟手柄后端，可创建 Xbox 360 或 DS4。"""

    system_wide = True

    def __init__(self, kind: str) -> None:
        """创建指定类型的虚拟手柄。"""
        import vgamepad

        self.kind: str = kind
        self.name: str = f'vgamepad {kind}（系统级）'
        self._module: object = vgamepad
        self._device: object = (
            vgamepad.VX360Gamepad() if kind == 'Xbox 360' else vgamepad.VDS4Gamepad()
        )

    def tap_cancel(self, hwnd: int) -> str:
        """短按一次取消按钮并立即释放。"""
        module = self._module
        if self.kind == 'Xbox 360':
            self._device.press_button(button=module.XUSB_BUTTON.XUSB_GAMEPAD_B)
            self._device.update()
            self._device.release_button(button=module.XUSB_BUTTON.XUSB_GAMEPAD_B)
        else:
            self._device.press_button(button=module.DS4_BUTTONS.DS4_BUTTON_CIRCLE)
            self._device.update()
            self._device.release_button(button=module.DS4_BUTTONS.DS4_BUTTON_CIRCLE)
        self._device.update()
        return '系统虚拟手柄已短按；需同时确认游戏收到且前台程序未受影响'

    def release_all(self) -> None:
        """重置全部按钮、扳机和摇杆。"""
        self._device.reset()
        self._device.update()

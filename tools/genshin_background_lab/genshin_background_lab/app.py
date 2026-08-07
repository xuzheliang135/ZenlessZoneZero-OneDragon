"""Fluent 风格验证界面。"""

from __future__ import annotations

import atexit
import csv
import json
import sys
import time
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from genshin_background_lab.backends import (
    BackendSelector,
    BitBltBackend,
    MssDesktopBackend,
    PrintWindowBackend,
    WindowsGraphicsCaptureBackend,
)
from genshin_background_lab.diagnostics import run_diagnostics
from genshin_background_lab.input_backends import SendInputBackend, WindowMessageBackend
from genshin_background_lab.models import FrameValidator
from genshin_background_lab.windows import enumerate_genshin_windows


class LabWindow(QMainWindow):
    """截图与输入实验主窗口。"""

    def __init__(self) -> None:
        """创建界面和定时器。"""
        super().__init__()
        self.setWindowTitle('原神后台截图与输入验证实验室')
        self.resize(1180, 820)
        self.windows: list[object] = []
        self.frames: int = 0
        self.failures: int = 0
        self.elapsed_total: float = 0.0
        self.validator: FrameValidator = FrameValidator()
        self.input_backend: WindowMessageBackend | SendInputBackend = (
            WindowMessageBackend()
        )
        self.selector: BackendSelector = BackendSelector(
            [
                MssDesktopBackend(),
                PrintWindowBackend(),
                BitBltBackend(),
                WindowsGraphicsCaptureBackend(),
            ],
            on_switch=self.log,
        )
        self._build_ui()
        self.refresh_windows()
        self.preview_timer: QTimer = QTimer(self)
        self.preview_timer.timeout.connect(self.update_preview)
        self.preview_timer.start(200)
        atexit.register(self.release_inputs)
        for item in run_diagnostics():
            self.log(
                f'诊断 {"通过" if item.passed else "失败"}：{item.name}；{item.detail}'
            )

    def _build_ui(self) -> None:
        """构建 Fluent 风格的紧凑界面。"""
        root = QWidget(self)
        layout = QVBoxLayout(root)
        warning = QLabel('仅验证非侵入式系统接口。请先确认游戏服务条款及反作弊风险。')
        warning.setStyleSheet(
            'padding: 10px; background: #fff4ce; color: #6b4f00; border-radius: 6px;'
        )
        layout.addWidget(warning)
        controls = QGridLayout()
        self.window_combo = QComboBox()
        refresh = QPushButton('刷新窗口')
        refresh.clicked.connect(self.refresh_windows)
        controls.addWidget(QLabel('窗口选择'), 0, 0)
        controls.addWidget(self.window_combo, 0, 1)
        controls.addWidget(refresh, 0, 2)
        self.process_info = QLabel('未选择')
        self.foreground_info = QLabel('当前前台：未知')
        controls.addWidget(QLabel('进程信息'), 1, 0)
        controls.addWidget(self.process_info, 1, 1)
        controls.addWidget(self.foreground_info, 1, 2)
        self.capture_combo = QComboBox()
        self.capture_combo.addItems(
            [backend.name for backend in self.selector.backends]
        )
        self.capture_combo.currentIndexChanged.connect(self.change_capture)
        self.input_combo = QComboBox()
        self.input_combo.addItems(
            [
                '窗口消息',
                'SendInput（系统级）',
                'vgamepad Xbox 360（系统级）',
                'vgamepad DS4（系统级）',
                '虚拟 HID（条件方案）',
            ]
        )
        self.input_combo.currentIndexChanged.connect(self.change_input)
        controls.addWidget(QLabel('截图后端'), 2, 0)
        controls.addWidget(self.capture_combo, 2, 1)
        controls.addWidget(QLabel('输入后端'), 3, 0)
        controls.addWidget(self.input_combo, 3, 1)
        self.fallback = QCheckBox('允许自动回退（会显示实际后端和原因）')
        self.fallback.toggled.connect(self.change_fallback)
        controls.addWidget(self.fallback, 2, 2)
        layout.addLayout(controls)
        self.preview = QLabel('等待有效截图')
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setMinimumHeight(390)
        self.preview.setStyleSheet(
            'background: #202020; color: white; border-radius: 8px;'
        )
        layout.addWidget(self.preview)
        self.metrics = QLabel(
            '实际后端：MSS/桌面截取 | 帧率 0 | 单帧 0 ms | 失败数 0 | 平均/P50/P95：等待采样'
        )
        layout.addWidget(self.metrics)
        buttons = QHBoxLayout()
        test_input = QPushButton('输入测试（3 秒倒计时）')
        test_input.clicked.connect(self.start_input_test)
        stop = QPushButton('立即停止并释放全部输入')
        stop.clicked.connect(self.release_inputs)
        export = QPushButton('导出 JSON/CSV 报告')
        export.clicked.connect(self.export_report)
        buttons.addWidget(test_input)
        buttons.addWidget(stop)
        buttons.addWidget(export)
        layout.addLayout(buttons)
        self.log_area = QPlainTextEdit()
        self.log_area.setReadOnly(True)
        self.log_area.setPlaceholderText('日志区域')
        layout.addWidget(self.log_area)
        self.setCentralWidget(root)

    def log(self, message: str) -> None:
        """写入带时间的日志。"""
        self.log_area.appendPlainText(f'[{time.strftime("%H:%M:%S")}] {message}')

    def refresh_windows(self) -> None:
        """重新枚举共同匹配的原神窗口。"""
        previous = {window.pid: window.hwnd for window in self.windows}
        self.windows = enumerate_genshin_windows(previous)
        self.window_combo.clear()
        for window in self.windows:
            self.window_combo.addItem(
                f'{window.title} | PID {window.pid} | HWND {window.hwnd}'
            )
        self.log(f'找到 {len(self.windows)} 个共同匹配的原神窗口')

    def change_capture(self, index: int) -> None:
        """切换用户指定的截图后端。"""
        self.selector.index = index
        self.validator = FrameValidator()
        self.log(f'用户切换截图后端：{self.selector.active.name}')

    def change_fallback(self, enabled: bool) -> None:
        """更改自动回退选项。"""
        self.selector.auto_fallback = enabled
        self.log(f'自动回退：{"开启" if enabled else "关闭"}')

    def change_input(self, index: int) -> None:
        """创建选定的输入后端；失败时明确提示。"""
        self.release_inputs()
        if index == 0:
            self.input_backend = WindowMessageBackend()
        elif index == 1:
            self.input_backend = SendInputBackend()
        elif index in (2, 3):
            try:
                from genshin_background_lab.input_backends import VirtualGamepadBackend

                self.input_backend = VirtualGamepadBackend(
                    'Xbox 360' if index == 2 else 'DS4'
                )
            except (ImportError, OSError, RuntimeError) as error:
                self.log(f'虚拟手柄创建失败：{error}')
                self.input_combo.setCurrentIndex(0)
        else:
            self.log('虚拟 HID 需要用户自行准备签名驱动，本工具不会安装内核驱动')
            self.input_combo.setCurrentIndex(0)

    def update_preview(self) -> None:
        """使用已选且通过检测的后端刷新预览。"""
        if not self.windows or self.window_combo.currentIndex() < 0:
            return
        window = self.windows[self.window_combo.currentIndex()]
        self.process_info.setText(
            f'PID {window.pid} | {window.executable} | {window.client_width}×{window.client_height} | DPI {window.dpi}'
        )
        self.foreground_info.setText(
            f'当前前台：{"是" if window.foreground else "否"} | 最小化：{"是" if window.minimized else "否"} | 遮挡：需人工确认 | 句柄重建：{"是" if window.handle_rebuilt else "否"}'
        )
        result = self.selector.capture(window.hwnd)
        if result.error or result.image is None:
            self.failures += 1
            self.preview.setText(f'后端失效：{result.error}\n未静默切换')
            self.log(f'{self.selector.active.name}：{result.error}')
            return
        problems = self.validator.inspect(result.image)
        if problems:
            self.failures += 1
            self.preview.setText(
                f'帧未通过检测：{"、".join(problem.value for problem in problems)}'
            )
            return
        self.frames += 1
        self.elapsed_total += result.elapsed_ms
        rgb = result.image[:, :, ::-1].copy()
        height, width, channels = rgb.shape
        image = QImage(
            rgb.data, width, height, width * channels, QImage.Format.Format_RGB888
        )
        self.preview.setPixmap(
            QPixmap.fromImage(image).scaled(
                self.preview.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        average = self.elapsed_total / self.frames
        self.metrics.setText(
            f'实际后端：{self.selector.active.name} | 有效帧 {self.frames} | 单帧 {result.elapsed_ms:.1f} ms | 平均 {average:.1f} ms | 失败数 {self.failures}'
        )

    def start_input_test(self) -> None:
        """倒计时后发送一次可观察的取消动作。"""
        if not self.windows:
            QMessageBox.warning(self, '没有目标', '请先选择共同匹配的原神窗口。')
            return
        self.log('输入测试将在 3 秒后执行；可随时点击立即停止')
        QTimer.singleShot(3000, self.perform_input_test)

    def perform_input_test(self) -> None:
        """执行单次测试并提醒人工验证边界。"""
        window = self.windows[self.window_combo.currentIndex()]
        result = self.input_backend.tap_cancel(window.hwnd)
        self.log(f'输入结果：{result}')
        self.log('请分别记录：目标游戏收到输入、前台程序未受影响，或无法自动确认')

    def release_inputs(self) -> None:
        """立即释放所有由当前后端控制的输入。"""
        self.input_backend.release_all()
        if hasattr(self, 'log_area'):
            self.log('已释放全部按键、按钮、扳机和摇杆')

    def export_report(self) -> None:
        """同时导出 JSON 和 CSV 报告骨架。"""
        path, _ = QFileDialog.getSaveFileName(
            self, '导出报告', 'reports/genshin-lab.json', 'JSON (*.json)'
        )
        if not path:
            return
        report = {
            '时间': time.strftime('%Y-%m-%d %H:%M:%S'),
            '实际截图后端': self.selector.active.name,
            '有效帧': self.frames,
            '失败数': self.failures,
            '人工测试': {
                '前台': '待验证',
                '遮挡': '待验证',
                '后台可见': '待验证',
                '最小化': '待验证',
            },
            '环境': {
                'Windows版本': '请填写',
                '显示模式': '请填写',
                '分辨率': '请填写',
                '帧率限制': '请填写',
            },
            '输入结论': '无法自动确认，需要人工观察',
        }
        json_path = Path(path)
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8'
        )
        with json_path.with_suffix('.csv').open(
            'w', encoding='utf-8-sig', newline=''
        ) as file:
            writer = csv.writer(file)
            writer.writerow(['项目', '结果'])
            writer.writerows(
                (
                    key,
                    json.dumps(value, ensure_ascii=False)
                    if isinstance(value, dict)
                    else value,
                )
                for key, value in report.items()
            )
        self.log(f'报告已导出：{json_path} 和 {json_path.with_suffix(".csv")}')

    def closeEvent(self, event: object) -> None:
        """退出前释放输入设备。"""
        self.release_inputs()
        event.accept()


def main() -> int:
    """启动桌面应用。"""
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    window = LabWindow()
    window.show()
    return app.exec()


if __name__ == '__main__':
    raise SystemExit(main())

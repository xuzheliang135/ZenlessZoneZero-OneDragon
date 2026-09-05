"""工具配置读写。"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class LabConfig:
    """可持久化的界面配置。"""

    capture_backend: str = 'MSS/桌面截取'
    input_backend: str = '窗口消息'
    auto_fallback: bool = False
    output_directory: str = 'reports'

    @classmethod
    def load(cls, path: Path) -> LabConfig:
        """从 JSON 读取配置，不存在时使用默认值。"""
        if not path.exists():
            return cls()
        data = json.loads(path.read_text(encoding='utf-8'))
        return cls(**data)

    def save(self, path: Path) -> None:
        """原子写入 JSON 配置。"""
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix('.tmp')
        temporary.write_text(
            json.dumps(asdict(self), ensure_ascii=False, indent=2), encoding='utf-8'
        )
        temporary.replace(path)

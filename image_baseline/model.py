"""数据模型：清单条目、基线与差异报告。"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Dict, List, Optional


class EntryType(enum.Enum):
    FILE = "file"
    DIR = "dir"
    SYMLINK = "symlink"


@dataclass(frozen=True)
class ManifestEntry:
    """清单中的一个最终可见路径。

    - FILE: 记录 length 与 sha256。
    - SYMLINK: 记录 target（符号链接目标原文）。
    - DIR: 不记录额外属性。
    """

    path: str
    type: EntryType
    length: Optional[int] = None
    sha256: Optional[str] = None
    target: Optional[str] = None


@dataclass
class Baseline:
    """BuildBaseline 的输出：路径 -> 清单条目。"""

    entries: Dict[str, ManifestEntry] = field(default_factory=dict)


@dataclass
class DiffReport:
    """Check 的输出：四类差异，元素为 POSIX 相对路径。"""

    added: List[str] = field(default_factory=list)
    missing: List[str] = field(default_factory=list)
    type_changed: List[str] = field(default_factory=list)
    content_changed: List[str] = field(default_factory=list)

    def is_clean(self) -> bool:
        return not (
            self.added or self.missing or self.type_changed or self.content_changed
        )

"""清单数据类型：镜像基线的最终可见文件系统视图。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional

# 条目类型
TYPE_FILE = "file"
TYPE_DIR = "dir"
TYPE_SYMLINK = "symlink"


@dataclass
class Entry:
    """清单中的单个路径条目。

    - 普通文件：记录 length 与 sha256（硬链接在清单中也表示为普通文件）。
    - 符号链接：记录 target 原文，不跟随。
    - 目录：无附加信息。
    """

    type: str
    length: Optional[int] = None
    sha256: Optional[str] = None
    target: Optional[str] = None


@dataclass
class Baseline:
    """最终可见文件系统的清单。键为相对 POSIX 路径（不含根目录本身）。"""

    entries: Dict[str, Entry] = field(default_factory=dict)

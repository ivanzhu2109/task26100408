"""Check：将实际 rootfs 目录与基线清单比对，报告差异。"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field
from typing import Dict, List

from manifest import Baseline, Entry, TYPE_DIR, TYPE_FILE, TYPE_SYMLINK

_TYPE_OTHER = "other"


@dataclass
class DiffReport:
    """实测树与清单不一致的路径集合（均为相对 POSIX 路径）。"""

    added: List[str] = field(default_factory=list)          # 实测存在、清单没有
    missing: List[str] = field(default_factory=list)        # 清单有、实测不存在
    type_changed: List[str] = field(default_factory=list)   # 两边都有但类型不同
    content_changed: List[str] = field(default_factory=list)  # 同为文件/链接但内容不同

    def is_clean(self) -> bool:
        return not (self.added or self.missing or self.type_changed or self.content_changed)


def _scan(root_dir: str) -> Dict[str, Entry]:
    """扫描实测目录，不跟随符号链接。键为相对 POSIX 路径，不含根本身。"""
    found: Dict[str, Entry] = {}

    def walk(dir_abs: str, dir_rel: str) -> None:
        with os.scandir(dir_abs) as it:
            for de in sorted(it, key=lambda e: e.name):
                rel = f"{dir_rel}/{de.name}" if dir_rel else de.name
                if de.is_symlink():
                    found[rel] = Entry(type=TYPE_SYMLINK, target=os.readlink(de.path))
                elif de.is_dir(follow_symlinks=False):
                    found[rel] = Entry(type=TYPE_DIR)
                    walk(de.path, rel)
                elif de.is_file(follow_symlinks=False):
                    with open(de.path, "rb") as fh:
                        data = fh.read()
                    found[rel] = Entry(
                        type=TYPE_FILE,
                        length=len(data),
                        sha256=hashlib.sha256(data).hexdigest(),
                    )
                else:
                    found[rel] = Entry(type=_TYPE_OTHER)

    walk(root_dir, "")
    return found


def check(baseline: Baseline, root_dir: str) -> DiffReport:
    """检查实际目录，返回差异报告。根目录本身不参与比较。"""
    actual = _scan(root_dir)
    report = DiffReport()
    for path in sorted(actual):
        if path not in baseline.entries:
            report.added.append(path)
    for path in sorted(baseline.entries):
        if path not in actual:
            report.missing.append(path)
    for path in sorted(actual.keys() & baseline.entries.keys()):
        want = baseline.entries[path]
        got = actual[path]
        if want.type != got.type:
            report.type_changed.append(path)
        elif want.type == TYPE_FILE and (
            want.length != got.length or want.sha256 != got.sha256
        ):
            report.content_changed.append(path)
        elif want.type == TYPE_SYMLINK and want.target != got.target:
            report.content_changed.append(path)
    return report

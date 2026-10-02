"""Check：将实际 rootfs 目录与基线清单对比，报告差异。"""

from __future__ import annotations

import hashlib
import os
from typing import Dict, Optional

from .model import Baseline, DiffReport, EntryType, ManifestEntry


def _scan(root_dir: str) -> Dict[str, ManifestEntry]:
    """遍历 rootfs（不跟随符号链接），返回相对路径 -> 实测条目。"""
    found: Dict[str, ManifestEntry] = {}

    def walk(abs_dir: str, rel_dir: str) -> None:
        with os.scandir(abs_dir) as it:
            for entry in it:
                rel = entry.name if not rel_dir else rel_dir + "/" + entry.name
                if entry.is_symlink():
                    found[rel] = ManifestEntry(
                        path=rel,
                        type=EntryType.SYMLINK,
                        target=os.readlink(entry.path),
                    )
                elif entry.is_dir(follow_symlinks=False):
                    found[rel] = ManifestEntry(path=rel, type=EntryType.DIR)
                    walk(entry.path, rel)
                elif entry.is_file(follow_symlinks=False):
                    digest = hashlib.sha256()
                    length = 0
                    with open(entry.path, "rb") as fh:
                        for chunk in iter(lambda: fh.read(1 << 20), b""):
                            digest.update(chunk)
                            length += len(chunk)
                    found[rel] = ManifestEntry(
                        path=rel,
                        type=EntryType.FILE,
                        length=length,
                        sha256=digest.hexdigest(),
                    )
                else:
                    # 非常规类型（设备、套接字等）：记为未知类型，
                    # 与清单中任何类型都不匹配，计入类型变化或新增。
                    found[rel] = ManifestEntry(path=rel, type=None)  # type: ignore[arg-type]

    walk(root_dir, "")
    return found


def Check(baseline: Baseline, root_dir: str) -> DiffReport:
    """检查 root_dir 与 baseline 的一致性。

    报告新增、缺失、类型变化和内容变化；根目录本身不参与比较。
    """
    actual = _scan(root_dir)
    report = DiffReport()

    for path in sorted(actual):
        want = baseline.entries.get(path)
        got = actual[path]
        if want is None:
            report.added.append(path)
        elif want.type is not got.type:
            report.type_changed.append(path)
        elif want.type is EntryType.FILE and (
            want.length != got.length or want.sha256 != got.sha256
        ):
            report.content_changed.append(path)
        elif want.type is EntryType.SYMLINK and want.target != got.target:
            report.content_changed.append(path)

    for path in sorted(set(baseline.entries) - set(actual)):
        report.missing.append(path)

    return report

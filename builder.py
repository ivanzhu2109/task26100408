"""BuildBaseline：解释有序 tar 层列表，生成最终可见文件系统清单。"""

from __future__ import annotations

import hashlib
import tarfile
from typing import Dict, Iterable, Union

from manifest import Baseline, Entry, TYPE_DIR, TYPE_FILE, TYPE_SYMLINK

_WH_PREFIX = ".wh."
_WH_OPAQUE = ".wh..wh..opq"


class ImageRejected(ValueError):
    """镜像违反层语义（如非法祖先、悬空硬链接）时抛出。"""


def _is_whiteout(member: tarfile.TarInfo) -> bool:
    base = member.name.rsplit("/", 1)[-1]
    return member.isfile() and member.size == 0 and base.startswith(_WH_PREFIX)


def _remove_subtree(entries: Dict[str, Entry], path: str) -> None:
    """删除 path 自身及其全部后代。"""
    prefix = path + "/"
    for key in [k for k in entries if k == path or k.startswith(prefix)]:
        del entries[key]


def _remove_descendants(entries: Dict[str, Entry], dir_path: str) -> None:
    """删除 dir_path 的全部后代，但保留 dir_path 自身。空串表示根。"""
    prefix = dir_path + "/" if dir_path else ""
    for key in [k for k in entries if k.startswith(prefix) and k != dir_path]:
        del entries[key]


def _ensure_ancestors(entries: Dict[str, Entry], path: str) -> None:
    """自动补建缺失的祖先目录；祖先为非目录时拒绝镜像。"""
    parts = path.split("/")[:-1]
    for i in range(1, len(parts) + 1):
        ancestor = "/".join(parts[:i])
        existing = entries.get(ancestor)
        if existing is None:
            entries[ancestor] = Entry(type=TYPE_DIR)
        elif existing.type != TYPE_DIR:
            raise ImageRejected(
                f"ancestor {ancestor!r} of {path!r} is a {existing.type}, not a directory"
            )


def _apply_member(
    entries: Dict[str, Entry], tf: tarfile.TarFile, member: tarfile.TarInfo
) -> None:
    path = member.name.rstrip("/")
    if not path:
        return
    _ensure_ancestors(entries, path)

    if member.isdir():
        new_entry = Entry(type=TYPE_DIR)
    elif member.issym():
        new_entry = Entry(type=TYPE_SYMLINK, target=member.linkname)
    elif member.islnk():
        target = entries.get(member.linkname)
        if target is None or target.type != TYPE_FILE:
            raise ImageRejected(
                f"hardlink {path!r} target {member.linkname!r} is not an existing regular file"
            )
        new_entry = Entry(type=TYPE_FILE, length=target.length, sha256=target.sha256)
    elif member.isreg():
        data = tf.extractfile(member).read()
        new_entry = Entry(
            type=TYPE_FILE, length=len(data), sha256=hashlib.sha256(data).hexdigest()
        )
    else:
        raise ImageRejected(f"unsupported member type for {path!r}")

    old = entries.get(path)
    if old is not None and old.type == TYPE_DIR and new_entry.type != TYPE_DIR:
        _remove_descendants(entries, path)
    if new_entry.type == TYPE_DIR and old is not None and old.type == TYPE_DIR:
        return  # 目录覆盖目录：保留已有后代
    entries[path] = new_entry


def _apply_layer(entries: Dict[str, Entry], layer_path: str) -> None:
    with tarfile.open(layer_path, "r:") as tf:
        members = tf.getmembers()
        # 第一阶段：处理全部白化标记，与归档位置无关
        for member in members:
            if not _is_whiteout(member):
                continue
            dir_path, _, base = member.name.rpartition("/")
            if base == _WH_OPAQUE:
                _remove_descendants(entries, dir_path)
            else:
                victim = f"{dir_path}/{base[len(_WH_PREFIX):]}" if dir_path else base[len(_WH_PREFIX):]
                _remove_subtree(entries, victim)
        # 第二阶段：按归档顺序应用普通成员
        for member in members:
            if _is_whiteout(member):
                continue
            _apply_member(entries, tf, member)


def build_baseline(layers: Iterable[str]) -> Baseline:
    """解释从底到顶排列的本地未压缩 tar 层，返回最终清单。"""
    entries: Dict[str, Entry] = {}
    for layer in layers:
        _apply_layer(entries, layer)
    return Baseline(entries)

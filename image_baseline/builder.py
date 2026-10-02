"""BuildBaseline：解释有序 tar 层，产出最终可见文件系统清单。"""

from __future__ import annotations

import hashlib
import io
import tarfile
from dataclasses import dataclass
from typing import BinaryIO, Dict, List, Optional, Union

from .errors import ImageRejectedError
from .model import Baseline, EntryType, ManifestEntry

# 层可以是 tar 文件路径、二进制文件对象，或 tar 字节串。
LayerInput = Union[str, BinaryIO, bytes]

_WHITEOUT_PREFIX = ".wh."
_OPAQUE_NAME = ".wh..wh..opq"


@dataclass
class _Node:
    type: EntryType
    length: Optional[int] = None
    sha256: Optional[str] = None
    target: Optional[str] = None


def _normalize(name: str) -> str:
    """去掉 tar 成员名中可能出现的 './' 前缀与结尾 '/'。"""
    while name.startswith("./"):
        name = name[2:]
    return name.rstrip("/")


def _open_layer(layer: LayerInput) -> tarfile.TarFile:
    if isinstance(layer, (bytes, bytearray)):
        return tarfile.open(fileobj=io.BytesIO(bytes(layer)), mode="r:*")
    if isinstance(layer, str):
        return tarfile.open(layer, mode="r:*")
    return tarfile.open(fileobj=layer, mode="r:*")


class _ImageState:
    """构建过程中的虚拟文件系统状态。"""

    def __init__(self) -> None:
        self.nodes: Dict[str, _Node] = {}

    def remove_subtree(self, path: str) -> None:
        """删除 path 及其全部后代；不存在则无效果。"""
        prefix = path + "/"
        for key in [k for k in self.nodes if k == path or k.startswith(prefix)]:
            del self.nodes[key]

    def remove_children(self, path: str) -> None:
        """删除 path 的全部后代，但保留 path 自身。"""
        prefix = path + "/"
        for key in [k for k in self.nodes if k.startswith(prefix)]:
            del self.nodes[key]

    def ensure_ancestors(self, path: str) -> None:
        """补建缺失的祖先目录；祖先为非目录时拒绝镜像。"""
        parts = path.split("/")[:-1]
        current = ""
        for part in parts:
            current = part if not current else current + "/" + part
            node = self.nodes.get(current)
            if node is None:
                self.nodes[current] = _Node(EntryType.DIR)
            elif node.type is not EntryType.DIR:
                raise ImageRejectedError(
                    f"祖先路径 {current!r} 不是目录，无法应用成员 {path!r}"
                )

    def apply_member(
        self,
        path: str,
        mtype: EntryType,
        length: Optional[int] = None,
        sha256: Optional[str] = None,
        target: Optional[str] = None,
    ) -> None:
        self.ensure_ancestors(path)
        old = self.nodes.get(path)
        if mtype is EntryType.DIR:
            if old is not None and old.type is EntryType.DIR:
                return  # 目录覆盖目录：保留已有后代
            self.remove_subtree(path)
            self.nodes[path] = _Node(EntryType.DIR)
            return
        # 文件或符号链接覆盖：若为目录需移除其全部后代
        if old is not None and old.type is EntryType.DIR:
            self.remove_children(path)
        self.nodes[path] = _Node(mtype, length=length, sha256=sha256, target=target)


def _apply_whiteouts(state: _ImageState, members: List[tarfile.TarInfo]) -> None:
    for member in members:
        name = _normalize(member.name)
        if not name:
            continue
        base = name.rsplit("/", 1)[-1]
        parent = name[: -(len(base) + 1)] if "/" in name else ""
        if base == _OPAQUE_NAME:
            if parent:
                state.remove_children(parent)
        elif base.startswith(_WHITEOUT_PREFIX):
            victim = (parent + "/" if parent else "") + base[len(_WHITEOUT_PREFIX):]
            state.remove_subtree(victim)


def _apply_regular_members(
    state: _ImageState, tf: tarfile.TarFile, members: List[tarfile.TarInfo]
) -> None:
    for member in members:
        name = _normalize(member.name)
        if not name:
            continue
        base = name.rsplit("/", 1)[-1]
        if base.startswith(_WHITEOUT_PREFIX):
            continue  # 白化标记已在第一阶段处理，自身不进入清单
        if member.isdir():
            state.apply_member(name, EntryType.DIR)
        elif member.isreg():
            data = tf.extractfile(member).read() if member.size else b""
            state.apply_member(
                name,
                EntryType.FILE,
                length=member.size,
                sha256=hashlib.sha256(data).hexdigest(),
            )
        elif member.issym():
            state.apply_member(name, EntryType.SYMLINK, target=member.linkname)
        elif member.islnk():
            target_name = _normalize(member.linkname)
            target_node = state.nodes.get(target_name)
            if target_node is None or target_node.type is not EntryType.FILE:
                raise ImageRejectedError(
                    f"硬链接 {name!r} 的目标 {target_name!r} 不存在或不是普通文件"
                )
            state.apply_member(
                name,
                EntryType.FILE,
                length=target_node.length,
                sha256=target_node.sha256,
            )
        else:
            raise ImageRejectedError(
                f"不支持的成员类型: {name!r} (type={member.type!r})"
            )


def BuildBaseline(layers: List[LayerInput]) -> Baseline:
    """按从底到顶的顺序解释各层，返回最终可见文件系统清单。

    违反层语义时抛出 ImageRejectedError。
    """
    state = _ImageState()
    for layer in layers:
        with _open_layer(layer) as tf:
            members = tf.getmembers()
            _apply_whiteouts(state, members)
            _apply_regular_members(state, tf, members)
    baseline = Baseline()
    for path, node in state.nodes.items():
        baseline.entries[path] = ManifestEntry(
            path=path,
            type=node.type,
            length=node.length,
            sha256=node.sha256,
            target=node.target,
        )
    return baseline

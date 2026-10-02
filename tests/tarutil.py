"""测试辅助：在内存中按指定顺序构造 tar 层。"""

from __future__ import annotations

import io
import tarfile
from typing import List, Tuple

# 成员描述：("file", path, data) / ("dir", path) /
# ("symlink", path, target) / ("hardlink", path, target)
Member = Tuple


def make_layer(members: List[Member]) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tf:
        for spec in members:
            kind = spec[0]
            if kind == "file":
                _, path, data = spec
                info = tarfile.TarInfo(path)
                info.size = len(data)
                tf.addfile(info, io.BytesIO(data))
            elif kind == "dir":
                info = tarfile.TarInfo(spec[1])
                info.type = tarfile.DIRTYPE
                tf.addfile(info)
            elif kind == "symlink":
                _, path, target = spec
                info = tarfile.TarInfo(path)
                info.type = tarfile.SYMTYPE
                info.linkname = target
                tf.addfile(info)
            elif kind == "hardlink":
                _, path, target = spec
                info = tarfile.TarInfo(path)
                info.type = tarfile.LNKTYPE
                info.linkname = target
                tf.addfile(info)
            else:
                raise ValueError(f"未知成员类型: {kind}")
    return buf.getvalue()

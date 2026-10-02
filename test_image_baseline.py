"""BuildBaseline / Check 的自动化测试。运行：python3 -m pytest -v"""

from __future__ import annotations

import hashlib
import io
import os
import tarfile

import pytest

from builder import ImageRejected, build_baseline
from checker import check
from manifest import TYPE_DIR, TYPE_FILE, TYPE_SYMLINK


def make_tar(path, members):
    """按给定顺序写未压缩 tar。成员为元组：
    ("file", name, bytes) / ("dir", name) / ("symlink", name, target) /
    ("hardlink", name, target)。
    """
    with tarfile.open(path, "w") as tf:
        for m in members:
            kind = m[0]
            if kind == "file":
                data = m[2]
                ti = tarfile.TarInfo(m[1])
                ti.size = len(data)
                tf.addfile(ti, io.BytesIO(data))
            elif kind == "dir":
                ti = tarfile.TarInfo(m[1])
                ti.type = tarfile.DIRTYPE
                tf.addfile(ti)
            elif kind == "symlink":
                ti = tarfile.TarInfo(m[1])
                ti.type = tarfile.SYMTYPE
                ti.linkname = m[2]
                tf.addfile(ti)
            elif kind == "hardlink":
                ti = tarfile.TarInfo(m[1])
                ti.type = tarfile.LNKTYPE
                ti.linkname = m[2]
                tf.addfile(ti)
            else:
                raise AssertionError(f"unknown kind {kind}")
    return str(path)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------- 层语义

def test_whiteouts_processed_before_normal_members(tmp_path):
    """下层含多级目录；上层先新增子文件，白化/不透明标记在归档末尾出现。
    旧后代消失，同层新增文件保留，标记不进清单。"""
    lower = make_tar(tmp_path / "lower.tar", [
        ("dir", "a"),
        ("dir", "a/b"),
        ("dir", "a/b/c"),
        ("file", "a/top.txt", b"top"),
        ("file", "a/b/c/deep.txt", b"deep"),
    ])
    upper = make_tar(tmp_path / "upper.tar", [
        ("file", "a/b/c/new.txt", b"new"),      # 先新增子文件
        ("file", "a/.wh.top.txt", b""),          # 普通白化标记最后才出现
        ("file", "a/b/.wh..wh..opq", b""),       # 不透明目录标记最后才出现
    ])
    bl = build_baseline([lower, upper])

    assert set(bl.entries) == {"a", "a/b", "a/b/c", "a/b/c/new.txt"}
    assert not any(".wh." in p for p in bl.entries)
    # 旧后代被删除
    assert "a/top.txt" not in bl.entries
    assert "a/b/c/deep.txt" not in bl.entries
    # 同层新增文件仍存在（不被同层标记删除）
    entry = bl.entries["a/b/c/new.txt"]
    assert entry.type == TYPE_FILE and entry.length == 3 and entry.sha256 == sha(b"new")
    # 被不透明标记清空后由新增文件自动补建的目录是空目录的后代链
    assert bl.entries["a/b/c"].type == TYPE_DIR


def test_whiteout_of_nonexistent_path_is_noop(tmp_path):
    layer = make_tar(tmp_path / "l.tar", [
        ("file", ".wh.ghost", b""),
        ("file", "d/.wh..wh..opq", b""),  # d 不存在，不建立父目录
        ("file", "ok.txt", b"x"),
    ])
    bl = build_baseline([layer])
    assert set(bl.entries) == {"ok.txt"}


def test_ancestor_file_rejected(tmp_path):
    layer = make_tar(tmp_path / "l.tar", [
        ("file", "f", b"x"),
        ("file", "f/child", b"y"),
    ])
    with pytest.raises(ImageRejected):
        build_baseline([layer])


def test_ancestor_symlink_rejected(tmp_path):
    layer = make_tar(tmp_path / "l.tar", [
        ("symlink", "s", "/some/where"),
        ("file", "s/child", b"y"),
    ])
    with pytest.raises(ImageRejected):
        build_baseline([layer])


def test_ancestor_hardlink_rejected(tmp_path):
    layer = make_tar(tmp_path / "l.tar", [
        ("file", "src", b"x"),
        ("hardlink", "hl", "src"),
        ("file", "hl/child", b"y"),
    ])
    with pytest.raises(ImageRejected):
        build_baseline([layer])


def test_file_over_dir_removes_descendants(tmp_path):
    lower = make_tar(tmp_path / "l1.tar", [
        ("dir", "d"),
        ("file", "d/inner.txt", b"i"),
    ])
    upper = make_tar(tmp_path / "l2.tar", [
        ("file", "d", b"now-a-file"),
    ])
    bl = build_baseline([lower, upper])
    assert set(bl.entries) == {"d"}
    assert bl.entries["d"].type == TYPE_FILE
    assert bl.entries["d"].sha256 == sha(b"now-a-file")


def test_dir_over_file_gives_empty_dir_and_dir_over_dir_keeps(tmp_path):
    lower = make_tar(tmp_path / "l1.tar", [
        ("file", "x", b"f"),
        ("dir", "y"),
        ("file", "y/keep.txt", b"k"),
    ])
    upper = make_tar(tmp_path / "l2.tar", [
        ("dir", "x"),
        ("dir", "y"),
    ])
    bl = build_baseline([lower, upper])
    assert bl.entries["x"].type == TYPE_DIR
    assert "y/keep.txt" in bl.entries  # 目录覆盖目录保留后代


def test_symlink_target_kept_raw_and_overwrites_dir(tmp_path):
    lower = make_tar(tmp_path / "l1.tar", [
        ("dir", "lnk"),
        ("file", "lnk/inner", b"i"),
    ])
    upper = make_tar(tmp_path / "l2.tar", [
        ("symlink", "lnk", "../weird/./target"),
    ])
    bl = build_baseline([lower, upper])
    assert set(bl.entries) == {"lnk"}
    assert bl.entries["lnk"].type == TYPE_SYMLINK
    assert bl.entries["lnk"].target == "../weird/./target"  # 原文保存


def test_hardlink_copies_content_and_survives_target_removal(tmp_path):
    lower = make_tar(tmp_path / "l1.tar", [
        ("file", "src", b"payload"),
        ("hardlink", "hl1", "src"),
        ("hardlink", "hl2", "hl1"),  # 目标也可以是此前建立的硬链接
    ])
    upper = make_tar(tmp_path / "l2.tar", [
        ("file", ".wh.src", b""),                 # 删除目标名
        ("file", "hl1", b"overwritten"),          # 覆盖 hl1
    ])
    bl = build_baseline([lower, upper])
    assert "src" not in bl.entries
    assert bl.entries["hl1"].sha256 == sha(b"overwritten")
    # hl2 固定为建立时 src 的内容，不受后续覆盖/删除影响
    assert bl.entries["hl2"].type == TYPE_FILE
    assert bl.entries["hl2"].length == 7
    assert bl.entries["hl2"].sha256 == sha(b"payload")


def test_dangling_hardlink_rejected(tmp_path):
    layer = make_tar(tmp_path / "l.tar", [
        ("hardlink", "hl", "missing"),
    ])
    with pytest.raises(ImageRejected):
        build_baseline([layer])


def test_hardlink_to_directory_rejected(tmp_path):
    layer = make_tar(tmp_path / "l.tar", [
        ("dir", "d"),
        ("hardlink", "hl", "d"),
    ])
    with pytest.raises(ImageRejected):
        build_baseline([layer])


def test_duplicate_paths_same_layer_last_wins(tmp_path):
    layer = make_tar(tmp_path / "l.tar", [
        ("file", "p", b"first"),
        ("file", "p", b"second"),
    ])
    bl = build_baseline([layer])
    assert bl.entries["p"].sha256 == sha(b"second")


# ---------------------------------------------------------------- Check

def _build_simple_baseline(tmp_path):
    layer = make_tar(tmp_path / "l.tar", [
        ("dir", "etc"),
        ("file", "etc/app.conf", b"config"),
        ("symlink", "etc/link", "app.conf"),
        ("file", "top.txt", b"top"),
    ])
    return build_baseline([layer])


def _make_rootfs(root):
    (root / "etc").mkdir()
    (root / "etc" / "app.conf").write_bytes(b"config")
    os.symlink("app.conf", root / "etc" / "link")
    (root / "top.txt").write_bytes(b"top")


def test_check_clean(tmp_path):
    bl = _build_simple_baseline(tmp_path)
    root = tmp_path / "root"
    root.mkdir()
    _make_rootfs(root)
    report = check(bl, str(root))
    assert report.is_clean(), report


def test_check_reports_all_diff_kinds(tmp_path):
    bl = _build_simple_baseline(tmp_path)
    root = tmp_path / "root"
    root.mkdir()
    _make_rootfs(root)
    (root / "top.txt").unlink()                       # 缺失
    (root / "extra.txt").write_bytes(b"e")            # 新增
    (root / "etc" / "app.conf").write_bytes(b"changed")  # 内容变化
    os.unlink(root / "etc" / "link")
    (root / "etc" / "link").mkdir()                   # 类型变化（链接 -> 目录）

    report = check(bl, str(root))
    assert report.added == ["extra.txt"]
    assert report.missing == ["top.txt"]
    assert report.type_changed == ["etc/link"]
    assert report.content_changed == ["etc/app.conf"]
    assert not report.is_clean()


def test_check_type_change_not_masked_by_same_content(tmp_path):
    """文件与同名符号链接即使'内容'相关，也必须报类型变化。"""
    layer = make_tar(tmp_path / "l.tar", [("file", "p", b"data")])
    bl = build_baseline([layer])
    root = tmp_path / "root"
    root.mkdir()
    os.symlink("data", root / "p")  # 目标文本恰为原文件内容
    report = check(bl, str(root))
    assert report.type_changed == ["p"]
    assert report.content_changed == []


def test_check_symlink_compares_target_text_only(tmp_path):
    """符号链接只比较目标文本；即使指向目录也不扫描其目标。"""
    layer = make_tar(tmp_path / "l.tar", [
        ("symlink", "dlink", "realdir"),
    ])
    bl = build_baseline([layer])
    root = tmp_path / "root"
    root.mkdir()
    (root / "realdir").mkdir()
    (root / "realdir" / "anything").write_bytes(b"x")  # 链接目标里的内容不参与
    os.symlink("realdir", root / "dlink")
    report = check(bl, str(root))
    # realdir 自身是新增路径，但 dlink 不会因指向目录而被展开扫描
    assert report.added == ["realdir", "realdir/anything"]
    assert report.type_changed == []
    assert report.content_changed == []

    os.unlink(root / "dlink")
    os.symlink("other", root / "dlink")  # 仅目标文本变化
    report = check(bl, str(root))
    assert report.content_changed == ["dlink"]


def test_check_missing_directory_reports_subtree(tmp_path):
    bl = _build_simple_baseline(tmp_path)
    root = tmp_path / "root"
    root.mkdir()
    (root / "top.txt").write_bytes(b"top")
    report = check(bl, str(root))
    assert report.missing == ["etc", "etc/app.conf", "etc/link"]

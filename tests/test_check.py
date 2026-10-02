"""Check：实际 rootfs 与基线对比的差异报告测试。"""

import os

from image_baseline import BuildBaseline, Check, EntryType

from tarutil import make_layer


def _write_file(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def _make_rootfs(tmp_path):
    root = tmp_path / "rootfs"
    root.mkdir()
    _write_file(root / "etc" / "app.conf", b"key=value")
    _write_file(root / "usr" / "bin" / "tool", b"\x7fELF fake")
    (root / "var" / "log").mkdir(parents=True)
    os.symlink("/etc/hostname", root / "etc" / "hostname-link")
    return root


def _baseline_for_rootfs():
    layer = make_layer([
        ("file", "etc/app.conf", b"key=value"),
        ("file", "usr/bin/tool", b"\x7fELF fake"),
        ("dir", "var/log"),
        ("symlink", "etc/hostname-link", "/etc/hostname"),
    ])
    return BuildBaseline([layer])


def test_clean_tree_reports_no_diffs(tmp_path):
    root = _make_rootfs(tmp_path)
    report = Check(_baseline_for_rootfs(), str(root))
    assert report.is_clean(), report


def test_added_missing_type_and_content_changes(tmp_path):
    root = _make_rootfs(tmp_path)
    # 新增
    _write_file(root / "extra.txt", b"extra")
    # 缺失
    os.remove(root / "usr" / "bin" / "tool")
    # 类型变化：目录被同名文件替换（内容无法相同，仍须报告类型变化）
    os.rmdir(root / "var" / "log")
    _write_file(root / "var" / "log", b"not a dir")
    # 内容变化
    _write_file(root / "etc" / "app.conf", b"key=tampered")
    # 符号链接目标文本变化
    os.remove(root / "etc" / "hostname-link")
    os.symlink("/etc/hosts", root / "etc" / "hostname-link")

    report = Check(_baseline_for_rootfs(), str(root))
    assert report.added == ["extra.txt"]
    assert report.missing == ["usr/bin/tool"]
    assert report.type_changed == ["var/log"]
    assert sorted(report.content_changed) == [
        "etc/app.conf", "etc/hostname-link"]


def test_type_change_not_masked_by_same_content(tmp_path):
    # 文件与符号链接内容"相同"（目标文本等于文件字节）时仍须报类型变化
    baseline = BuildBaseline([make_layer([("file", "p", b"target")])])
    root = tmp_path / "rootfs"
    root.mkdir()
    os.symlink("target", root / "p")
    report = Check(baseline, str(root))
    assert report.type_changed == ["p"]
    assert report.content_changed == []


def test_symlink_to_directory_is_not_followed(tmp_path):
    # 符号链接指向目录：只比较目标文本，不扫描其目标
    baseline = BuildBaseline([make_layer([
        ("symlink", "dirlink", "realdir"),
    ])])
    root = tmp_path / "rootfs"
    root.mkdir()
    (root / "realdir").mkdir()
    _write_file(root / "realdir" / "untracked.txt", b"x")
    os.symlink("realdir", root / "dirlink")
    report = Check(baseline, str(root))
    # realdir 及其内容属于实测树的新增路径，但 dirlink 本身不计内容变化
    assert sorted(report.added) == ["realdir", "realdir/untracked.txt"]
    assert report.content_changed == []
    assert report.type_changed == []


def test_root_dir_itself_not_compared(tmp_path):
    # 清单为空时，空目录（根自身）不产生任何差异
    baseline = BuildBaseline([])
    root = tmp_path / "rootfs"
    root.mkdir()
    assert Check(baseline, str(root)).is_clean()


def test_dir_entries_participate_in_comparison(tmp_path):
    baseline = BuildBaseline([make_layer([
        ("dir", "d1"),
        ("dir", "d2/sub"),
    ])])
    root = tmp_path / "rootfs"
    (root / "d2").mkdir(parents=True)
    (root / "d3").mkdir()
    # d2 由祖先补建进入清单；d1、d2/sub 缺失；d3 为新增目录
    report = Check(baseline, str(root))
    assert report.added == ["d3"]
    assert sorted(report.missing) == ["d1", "d2/sub"]


def test_baseline_entry_types_match_manifest():
    baseline = _baseline_for_rootfs()
    assert baseline.entries["var/log"].type is EntryType.DIR
    assert baseline.entries["etc/hostname-link"].type is EntryType.SYMLINK
    assert baseline.entries["usr/bin/tool"].type is EntryType.FILE

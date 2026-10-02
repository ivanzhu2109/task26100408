"""普通成员覆盖、硬链接与清单内容的构建语义测试。"""

import hashlib

from image_baseline import BuildBaseline, EntryType

from tarutil import make_layer


def test_file_records_length_and_sha256():
    data = b"hello baseline"
    baseline = BuildBaseline([make_layer([("file", "f.txt", data)])])
    entry = baseline.entries["f.txt"]
    assert entry.type is EntryType.FILE
    assert entry.length == len(data)
    assert entry.sha256 == hashlib.sha256(data).hexdigest()


def test_symlink_records_target_text_verbatim():
    baseline = BuildBaseline([make_layer([
        ("symlink", "rel", "../weird/./target"),
        ("symlink", "abs", "/etc/hostname"),
    ])])
    assert baseline.entries["rel"].target == "../weird/./target"
    assert baseline.entries["abs"].target == "/etc/hostname"


def test_file_over_dir_removes_descendants():
    lower = make_layer([
        ("dir", "d"),
        ("file", "d/a.txt", b"a"),
        ("dir", "d/sub"),
        ("file", "d/sub/b.txt", b"b"),
    ])
    upper = make_layer([("file", "d", b"now a file")])
    entries = BuildBaseline([lower, upper]).entries
    assert entries["d"].type is EntryType.FILE
    assert "d/a.txt" not in entries
    assert "d/sub" not in entries
    assert "d/sub/b.txt" not in entries


def test_dir_over_file_gives_empty_dir_and_dir_over_dir_keeps_children():
    lower = make_layer([
        ("file", "x", b"x"),
        ("dir", "d"),
        ("file", "d/child.txt", b"c"),
    ])
    upper = make_layer([
        ("dir", "x"),
        ("dir", "d"),
    ])
    entries = BuildBaseline([lower, upper]).entries
    assert entries["x"].type is EntryType.DIR
    assert entries["d"].type is EntryType.DIR
    assert entries["d/child.txt"].type is EntryType.FILE  # 后代保留


def test_same_layer_duplicate_paths_apply_in_archive_order():
    layer = make_layer([
        ("file", "p", b"first"),
        ("file", "p", b"second"),
    ])
    entry = BuildBaseline([layer]).entries["p"]
    assert entry.sha256 == hashlib.sha256(b"second").hexdigest()


def test_missing_ancestors_auto_created():
    baseline = BuildBaseline([make_layer([("file", "a/b/c/deep.txt", b"d")])])
    for path in ("a", "a/b", "a/b/c"):
        assert baseline.entries[path].type is EntryType.DIR
    assert baseline.entries["a/b/c/deep.txt"].type is EntryType.FILE


def test_hardlink_content_frozen_at_link_time():
    lower = make_layer([
        ("file", "orig", b"v1"),
        ("hardlink", "hl", "orig"),
    ])
    # 上层覆盖目标名称：不影响已建立的硬链接
    upper = make_layer([("file", "orig", b"v2-longer")])
    entries = BuildBaseline([lower, upper]).entries
    assert entries["orig"].sha256 == hashlib.sha256(b"v2-longer").hexdigest()
    hl = entries["hl"]
    assert hl.type is EntryType.FILE
    assert hl.length == 2
    assert hl.sha256 == hashlib.sha256(b"v1").hexdigest()
    # 再删除目标名称：硬链接仍不受影响
    top = make_layer([("file", ".wh.orig", b"")])
    entries = BuildBaseline([lower, upper, top]).entries
    assert "orig" not in entries
    assert entries["hl"].sha256 == hashlib.sha256(b"v1").hexdigest()


def test_hardlink_to_hardlink_allowed():
    layer = make_layer([
        ("file", "a", b"payload"),
        ("hardlink", "b", "a"),
        ("hardlink", "c", "b"),
    ])
    entries = BuildBaseline([layer]).entries
    expected = hashlib.sha256(b"payload").hexdigest()
    assert entries["c"].sha256 == expected
    assert entries["c"].length == len(b"payload")

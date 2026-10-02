"""白化标记与不透明目录的层语义测试。"""

from image_baseline import BuildBaseline, EntryType

from tarutil import make_layer


def test_whiteout_and_opaque_applied_before_regular_members():
    # 下层：多级目录结构
    lower = make_layer([
        ("dir", "a"),
        ("dir", "a/b"),
        ("dir", "a/b/c"),
        ("file", "a/b/c/deep.txt", b"deep"),
        ("file", "a/b/old.txt", b"old"),
        ("dir", "a/b/gone"),
        ("file", "a/b/gone/gone.txt", b"gone"),
        ("dir", "keep"),
        ("file", "keep/keep.txt", b"keep"),
    ])
    # 上层：先新增子文件，普通白化与不透明标记出现在归档末尾
    upper = make_layer([
        ("file", "a/b/new.txt", b"new"),
        ("file", "a/b/.wh.gone", b""),
        ("file", "a/.wh..wh..opq", b""),
    ])
    baseline = BuildBaseline([lower, upper])
    entries = baseline.entries

    # 旧后代全部消失（不透明标记删除 a 的全部继承后代）
    for gone in ("a/b/c", "a/b/c/deep.txt", "a/b/old.txt", "a/b/gone",
                 "a/b/gone/gone.txt"):
        assert gone not in entries, gone
    # 同层新增文件仍存在，其祖先目录自动补建
    assert entries["a/b/new.txt"].type is EntryType.FILE
    assert entries["a/b/new.txt"].sha256 is not None
    assert entries["a"].type is EntryType.DIR  # 目录本身不被不透明标记删除
    assert entries["a/b"].type is EntryType.DIR
    # 未受影响的子树保留
    assert entries["keep/keep.txt"].type is EntryType.FILE
    # 标记自身不进入清单
    for path in entries:
        assert ".wh." not in path, path


def test_whiteout_removes_named_subtree_only():
    lower = make_layer([
        ("dir", "d"),
        ("file", "d/victim.txt", b"v"),
        ("dir", "d/victim"),
        ("file", "d/victim/inner.txt", b"i"),
        ("file", "d/stay.txt", b"s"),
    ])
    upper = make_layer([
        ("file", "d/.wh.victim", b""),
        ("file", "d/.wh.victim.txt", b""),
    ])
    baseline = BuildBaseline([lower, upper])
    entries = baseline.entries
    assert "d/victim" not in entries
    assert "d/victim/inner.txt" not in entries
    assert "d/victim.txt" not in entries
    assert entries["d/stay.txt"].type is EntryType.FILE
    assert entries["d"].type is EntryType.DIR


def test_whiteout_of_nonexistent_path_is_noop():
    lower = make_layer([("file", "x.txt", b"x")])
    upper = make_layer([
        ("file", "nope/.wh.ghost", b""),
        ("file", ".wh.x.txt", b""),
    ])
    baseline = BuildBaseline([lower, upper])
    # x.txt 被删除；不存在的路径删除无效果；标记不建立父目录
    assert "x.txt" not in baseline.entries
    assert "nope" not in baseline.entries

"""祖先为文件、符号链接或硬链接时，应用成员必须拒绝镜像。"""

import pytest

from image_baseline import BuildBaseline, ImageRejectedError

from tarutil import make_layer


def test_ancestor_is_file_rejected():
    layer = make_layer([
        ("file", "f", b"data"),
        ("file", "f/child.txt", b"c"),
    ])
    with pytest.raises(ImageRejectedError):
        BuildBaseline([layer])


def test_ancestor_is_symlink_rejected():
    # 不得穿过符号链接
    layer = make_layer([
        ("dir", "real"),
        ("symlink", "s", "real"),
        ("file", "s/child.txt", b"c"),
    ])
    with pytest.raises(ImageRejectedError):
        BuildBaseline([layer])


def test_ancestor_is_hardlink_rejected():
    # 硬链接在清单中是普通文件，同样不能作为祖先被穿过或替换
    layer = make_layer([
        ("file", "orig", b"data"),
        ("hardlink", "hl", "orig"),
        ("file", "hl/child.txt", b"c"),
    ])
    with pytest.raises(ImageRejectedError):
        BuildBaseline([layer])


def test_ancestor_rejection_across_layers():
    lower = make_layer([("symlink", "link", "/etc")])
    upper = make_layer([("dir", "link/sub")])
    with pytest.raises(ImageRejectedError):
        BuildBaseline([lower, upper])


def test_hardlink_target_must_exist_and_be_regular_file():
    # 目标不存在
    with pytest.raises(ImageRejectedError):
        BuildBaseline([make_layer([("hardlink", "h", "missing")])])
    # 目标是目录
    with pytest.raises(ImageRejectedError):
        BuildBaseline([make_layer([
            ("dir", "d"),
            ("hardlink", "h", "d"),
        ])])
    # 目标是符号链接
    with pytest.raises(ImageRejectedError):
        BuildBaseline([make_layer([
            ("symlink", "s", "/tmp"),
            ("hardlink", "h", "s"),
        ])])
    # 目标是同层稍后出现的目标：应用时不存在，拒绝
    with pytest.raises(ImageRejectedError):
        BuildBaseline([make_layer([
            ("hardlink", "h", "later"),
            ("file", "later", b"x"),
        ])])

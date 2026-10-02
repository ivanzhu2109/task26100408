# 容器运行时完整性检查：离线镜像基线组件

只解释镜像层并检查本地 rootfs 目录，不执行容器。纯标准库实现，无第三方依赖。

## 模块

- `manifest.py` — 清单数据类型（`Entry` / `Baseline`）
- `builder.py` — `build_baseline(layers)`：解释从底到顶排列的本地未压缩 tar 层，
  返回最终可见文件系统清单（路径、类型，普通文件的长度与 SHA-256，符号链接的目标文本）。
  违反层语义（非目录祖先、悬空/目录硬链接、不支持的成员类型）时抛出 `ImageRejected`。
- `checker.py` — `check(baseline, root_dir)`：比对实际目录，返回 `DiffReport`
  （`added` / `missing` / `type_changed` / `content_changed`）。目录参与比较，
  根目录本身除外；不比较权限、时间戳与 inode 关系；符号链接只比较目标文本且不跟随。

## 用法

```python
from builder import build_baseline
from checker import check

baseline = build_baseline(["layer1.tar", "layer2.tar"])  # 从底到顶
report = check(baseline, "/path/to/rootfs")
assert report.is_clean(), report
```

## 运行测试

```sh
python3 -m pytest -v
```

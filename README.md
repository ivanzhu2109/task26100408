# task26100408

容器运行时完整性检查：离线镜像基线组件（纯 Python，无第三方依赖）。

## 功能

- `BuildBaseline(layers)`：按从底到顶的顺序解释本地未压缩 tar 层
  （路径、文件对象或字节串），返回最终可见文件系统的清单
  （`Baseline.entries`：路径 -> `ManifestEntry`，含类型、普通文件的长度与
  SHA-256、符号链接的目标文本）。
- `Check(baseline, root_dir)`：检查实际 rootfs 目录，报告新增、缺失、
  类型变化和内容变化（`DiffReport`）。目录参与比较，根目录本身除外；
  不比较权限、时间戳或 inode 关系；不跟随符号链接。

镜像违反层语义（祖先为非目录、硬链接目标非法等）时抛出
`ImageRejectedError`。

## 运行测试

```sh
python3 -m pytest tests/ -q
```

## 代码结构

- `image_baseline/model.py` — 清单条目、基线与差异报告的数据模型
- `image_baseline/builder.py` — 层解释与白化/覆盖/硬链接语义
- `image_baseline/checker.py` — rootfs 扫描与差异对比
- `image_baseline/errors.py` — `ImageRejectedError`
- `tests/` — 自动化测试（白化标记、拒绝语义、覆盖语义、差异报告）

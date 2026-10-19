# 独立 Multiwfn 服务

这些源码对应服务器 `/root/workspace/equiformer_v2/descriptor_service/`，独立于平台 Docker 容器。`atom_selection.py` 的唯一源码位于 `backend/tools/multiwfn/atom_selection.py`，发布时复制到服务目录，确保两层校验一致。

Ti 编号默认 0（自动）：唯一 Ti 自动选择；多个 Ti 要求显式指定；显式编号必须指向 Ti。O 编号默认取最近两个 O，显式编号必须指向两个不同 O。没有适用 Ti–O 原子对时，Mayer 标记 skipped，不计入 partial 失败。

更新步骤：先确认 `/v1/descriptors/health` 的 pending 为 0，备份旧源码，复制 `descriptor_api.py`、`extract_descriptors.py`、`repair_mayer.py` 和共享原子选择模块，通过 `python -m py_compile` 检查后重启 `eqv2-descriptors.service`。不要在计算进行时重启服务。

旧任务可从已有 `mayer.log` 恢复，默认只预览，必须加 `--apply` 才写入：

```bash
cd /root/workspace/equiformer_v2/descriptor_service
/root/miniconda3/envs/equiformer_v2/bin/python repair_mayer.py <远程任务UUID>
/root/miniconda3/envs/equiformer_v2/bin/python repair_mayer.py <远程任务UUID> --apply
```

修复会先备份旧 JSON/CSV 和平台缓存，然后更新指定 Ti–O 键级、Ti/O 电荷摘要、任务状态及下载文件。不会运行 Multiwfn，不修改上传原文件，也不重算其他电荷分析。

# YAOF 项目维护规则

## 开始改动前

- 涉及 R5C、内核/驱动、构建、软件源、默认网络、在线升级或发布时，先阅读 `docs/r5c.md`，按其中已批准阶段的范围工作；后续阶段路线不是自动实施授权。
- 核对上游能力、优化或平台差异时，先阅读 `docs/upstream-alignment.md`；区分源码继承、成功产物和实机生效，不从版本号或分支提示推断功能。
- 修改构建配置前读取 `profiles/r5c.json` 和 `.github/workflows/R5C-OpenWrt.yml`；核对最新固件时读取 `.state/r5c.json` 及其对应 Release，不把固定版本号或 GitHub latest 接口当作成功构建状态。
- 推送前执行 `git remote -v`，确认 origin 为 https://github.com/lsls01/YAOF；main 是自有发布分支，upstream 仅用于拉取 QiuSimons/YAOF。不要向上游推送本地定制，也不要强制覆盖自有 main 来同步上游。

## 验证

- 修改代码或构建配置后执行：

```sh
python3 -m unittest discover -s tests -v
bash -n scripts/build.sh
sh -n files/usr/bin/yaof-update
sh -n files/etc/board.d/99-lsls-network
git diff --check
```

- 影响固件内容或发布流程后，在自有仓库运行 R5C firmware 工作流，核对镜像、包清单、构建信息和公开下载文件的校验值；具体触发与验收方法见 `docs/r5c.md`。
- 报告验证结果时区分 CI 静态/产物检查与 R5C 实机验收；启动、双网口、eBPF verifier、吞吐和保留配置升级不能用 CI 成功代替。

## 文档维护

- 流程、兼容性边界或验证范围改变时更新 `docs/r5c.md`；能力、优化或平台对齐变化时更新 `docs/upstream-alignment.md`。`README.md` 保留用户入口，不复制完整流程。
- 最新版本、指纹、镜像校验值和包清单以成功发布记录为准，不在本文件维护版本快照或会话历史。

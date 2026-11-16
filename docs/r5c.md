# R5C 固件维护

维护或改动本项目时先阅读根目录 [AGENTS.md](../AGENTS.md)。本文提供固件流程、验证边界和后续路线；实际配置查 `profiles/r5c.json` 与 `.github/workflows/R5C-OpenWrt.yml`，最新成功产物查 [成功构建状态](../.state/r5c.json) 及对应 Release。

## 第一阶段约定

- 公开仓库：`lsls01/YAOF`，发布分支为 `main`，上游为 `QiuSimons/YAOF` 的 `25.12` 分支。
- 设备为 FriendlyElec NanoPi R5C，Profile 为 `friendlyarm_nanopi-r5c`，Target 为 `rockchip/armv8`。
- 使用所选稳定系列的最新正式 OpenWrt ImageBuilder；不选 RC、snapshot，也不自动跨大版本。
- 每 6 小时检查一次（UTC 00:17、06:17、12:17、18:17），支持手动检查及强制构建。
- 默认 LAN 为 `192.168.100.1/24`。不改官方 LAN/WAN 端口定义，不覆盖保留配置升级时的现有地址。
- 自动生成 ext4、squashfs 两种镜像，发布为 prerelease；不后台自动刷机。
- 配置入口为 `profiles/r5c.json`；成功构建状态为本仓库 `.state/r5c.json`。

## 内核、eBPF 与优化边界

当前 YAOF 使用官方 ImageBuilder，**不自行重编内核，也不应用历史 YAOF fullcone 内核补丁**。那些补丁不在当前源码的构建链中，不应重新混入第一阶段。Linux 更新必须经过 OpenWrt 的配置、设备支持、补丁和模块 ABI 集成；不能直接替换成 kernel.org 最新内核。

实际每次构建的内核版本、配置和软件包记录在成功状态与 Release 的 `kernel.config`、`packages.manifest`、`build-info.json`，以它们为准，不在本文冻结“最新版本”。评估升级时重新查询 kernel.org 当前 LTS/稳定发布与 OpenWrt 的 Rockchip 支持、补丁和模块 ABI。较新的版本是候选，不证明它在 R5C 上更快、更稳。

已检查官方 ImageBuilder 内的实际内核 `.config`，而非仅看 OpenWrt 默认配置片段：

- BPF、BPF syscall、JIT、cgroup BPF 和 TC classifier/action BPF 支持存在。
- 官方内核未提供原生 BTF；保留上游 `vmlinux-btf` 外挂 BTF 包。
- AF_XDP 的 `CONFIG_XDP_SOCKETS` 未启用。不能宣传完整 AF_XDP 支持；外挂 BTF 也不能开启缺失的内核功能。
- FlowCone 声明需要 Linux 6.6+、BPF、TC 和原生或外挂 BTF。现有基线满足其静态基础条件，不能据此替代 verifier、挂载与流量的实机检查。
- `vmlinux-btf` 使用 SDK 的内核头和配置生成 detached BTF，不是官方内核直接导出的完整运行时 BTF。CI 校验文件格式、内核版本关联和包存在性，不保证所有内部类型布局在运行时都正确。
- 保留 `system-addon` 的网络参数、Ring Buffer、网卡卸载和 zram 设置；CI 检查关键优化脚本存在。
- Rockchip 配置排除了 `kmod-tcp-bbr3`，第一阶段不重新添加。内核中 BBR 模块可用，不等于固件已安装或默认启用 BBR；不作这种保证。

ImageBuilder 不能改变编译后的内核配置。未安装、未加载的模块通常不会消耗运行时内存；裁剪驱动不能直接推导出更高性能。尤其不能为减小体积删掉 BPF、TC、cgroup、防火墙、网络存储、热管理或需要的无线功能。

参考：

- https://downloads.openwrt.org/releases/25.12.6/targets/rockchip/armv8/
- https://www.kernel.org/releases.json
- https://github.com/QiuSimons/YAOF
- https://github.com/QiuSimons/OpenWrt-Add/tree/master/apps/system-addon
- https://github.com/QiuSimons/vmlinux-btf
- https://github.com/QiuSimons/FlowCone

## 自动更新链路

`R5C firmware` 工作流按以下顺序执行：

1. 在只读构建任务中检查本仓库的控制脚本和测试。
2. 解析配置稳定系列的最新正式发布，确认 R5C Profile 和官方 ImageBuilder SHA256。
3. 拉取并在临时工作区合并上游。涉及工作流、信任配置、控制脚本、测试或本地地址配置的上游变更必须人工 review；冲突也停止，不强推。
4. 只接受最近一次已经成功完成的 OpenWrt-Add feed 构建。签名公钥 SHA256 固定，轮换必须审核。
5. 对官方各软件源索引、第三方签名索引、固定 commit 的清理脚本、内核配置和构建配方计算指纹。
6. 与**本仓库**的 `.state/r5c.json` 比较；相同且未强制重建时跳过。状态提交本身不改变配方指纹，不会形成循环构建。
7. 构建时不允许缺包后静默跳过。完成后再次核对软件源索引，若构建期间变化，拒绝发布并等待下一次重新检查。
8. 校验固件设备元数据、gzip 完整性、两种文件系统输出、全部必需包、外挂 BTF、默认地址和固件更新入口。
9. 独立的写权限发布任务重新校验资产、上游来源及源码树；若 `main` 在构建期间前进，停止，不覆盖用户提交。
10. 使用唯一 tag 发布；只有发布成功后才提交新的 `.state/r5c.json`。失败不会把未发布输入标记为成功。

构建不会执行带写权限的上游代码。发布任务不运行下载的固件或附件。GitHub 自动 token 的 push 不是后续构建触发器；当前工作流直接完成检查、构建和发布，普通自己的配方 push 也有独立入口。

GitHub 定时任务可能延迟；公开仓库长期无活动时定时任务可能在 60 天后被停用。第一阶段不制造 keep-alive 空提交。若需要长期无人值守保证，可在第三阶段加入独立健康检查或外部调度兜底。

## 已验证与待验证

第一阶段已完成自有仓库的实际构建和公开下载核验。证据入口为 [R5C 工作流记录](https://github.com/lsls01/YAOF/actions/workflows/R5C-OpenWrt.yml)、[成功构建状态](../.state/r5c.json) 和它指向的 Release；产物列表与校验值以记录为准。

| 项目 | 当前验证范围 |
| --- | --- |
| 单元测试与静态检查 | 更新指纹、无变化跳过、强制重建、上游保护、密钥变化、缓存损坏、资产完整性、默认地址及 Shell/Actions 检查通过 |
| push 构建与发布 | 自有 main 的实际 R5C 构建、独立发布及成功状态提交通过 |
| 手动检查 | 输入不变时，实际 GitHub workflow_dispatch 跳过编译和发布 |
| 手动强制重建 | 输入不变时，实际生成新的唯一 tag 并成功发布；构建输入指纹保持相同 |
| 镜像和 rootfs | ext4/squashfs 元数据、压缩完整性、必需包、外挂 BTF、网络默认值、更新 descriptor/脚本及上游优化脚本通过 CI 检查 |
| 公开下载 | 两个镜像及全部校验清单条目已从公开 Release 下载并验证；发布附带被校验的 release-notes.md |
| 实机验收 | R5C 启动、SD/eMMC、双网口、无线、eBPF verifier/TCX 协同、吞吐、温度及保留配置升级尚未验证 |
| 固件内更新命令 | 入口和 descriptor 已验证打进 rootfs；在真实 R5C 上执行查询、下载和 sysupgrade -T 仍属于实机验收 |
| 定时检查 | 六小时 cron 已配置并启用；手动与 push 路径已验证，不把它们说成已经观察到自然定时触发 |
| 其他设备 | 保留原有手动入口，本阶段未重新实测所有设备 |

CI 的 BTF 检查不是运行时类型布局证明，文件中的默认 IP 也不是已观察到设备启动后的地址。只有用户确认完成实机验收后，才将某个构建认定为已验证稳定版本。

## 手动触发

网页入口：

https://github.com/lsls01/YAOF/actions/workflows/R5C-OpenWrt.yml

选择 **Run workflow**：

- 不勾选 `force_build`：立即检查，输入未变时不编译。
- 勾选 `force_build`：即使输入相同，也生成一个新的唯一构建。

也可使用 GitHub CLI：

```sh
gh workflow run R5C-OpenWrt.yml --repo lsls01/YAOF --ref main
gh workflow run R5C-OpenWrt.yml --repo lsls01/YAOF --ref main -f force_build=true
```

`force_build` 只改变是否重建的判断，不绕过签名密钥、内核能力、软件包完整性或源码保护检查。强制重建输入相同的固件会产生新 tag，但固件内更新查询仍按输入指纹判断是否有实质更新。

自有分支仅修改 README、AGENTS.md 或维护文档时，不改变本地配方指纹，也不匹配 push 构建入口；成功状态提交本身不是新的配方。上游 commit 则属于输入记录，即使只改变上游文档，也会按新输入处理。

其他型号保留原有手动工作流，不自动推进 R5C 的成功状态。自动清理改为手动，避免删除仍需要的回滚固件及诊断。

## 故障与恢复

- 网络暂时失败、缺包或构建期间索引变化：保留现有成功状态和可下载产物。排查工作流日志及失败诊断，恢复后重新 Run workflow；不要手工伪造成功状态。
- 上游保护文件变化或合并冲突：先 review 对自有配置、权限和兼容性的影响，再在当前 main 上做最小整合。强制重建不会绕过这些保护；不要以强推上游分支覆盖自有 main 来“修复”。
- 公钥变化：确认上游正式轮换和新公钥来源，再审核配置更新。不要为构建通过取消校验或允许不可信包。
- 发布失败或留下草稿：确认完整资产后再重试，不修改已有镜像或校验值。只有成功公开发布才能推进 `.state/r5c.json`；新构建使用新 tag。
- 发布时 main 前进：同步最新自有分支后重新触发，不覆盖期间新增的用户提交。
- 设备升级失败或不兼容：不使用强制忽略检查的选项。先通过 microSD 验证与恢复，保留设置备份及可启动旧镜像；eMMC/bootloader 处理必须结合实际存储布局。

## 固件内查询与升级

受控 R5C 构建包含 `/etc/yaof-release.json` 和 `yaof-update`。它读取 descriptor 中的自有仓库，查询该仓库 `main/.state/r5c.json`，比较构建输入指纹，而不是仅比较 OpenWrt 版本号。

```sh
yaof-update check
yaof-update download squashfs
# 或选择自己使用的 ext4 镜像：
yaof-update download ext4
```

下载流程校验发布记录的 SHA256，并执行 `sysupgrade -T` 设备兼容检查。它只下载和检查，**不执行刷机**。准备升级时：

1. 先备份设置，并确认供电、存储和恢复方式。
2. 阅读对应 Release 的验证范围；首阶段自动产物尚无实机验收保证。
3. 保持现有文件系统，不随意跨 ext4/squashfs 切换。
4. 使用命令输出给出的镜像路径，显式执行 `sysupgrade /tmp/<image>.img.gz`。不要使用强制忽略兼容检查的选项。

首次迁移建议先通过 microSD 验证，确认后再考虑 eMMC；FriendlyWrt 等系统的存储布局和 bootloader 不应假定与 OpenWrt 相同。

## 管理地址

地址配置通过 `files/etc/board.d/99-lsls-network` 在 OpenWrt 生成默认网络配置前设置，只改变 LAN 的默认 IP 和掩码：

- 首次安装、恢复出厂、不保留配置升级：`192.168.100.1/24`。
- 保留配置升级：保持现有 `/etc/config/network`，不会强制改地址。
- 默认 DHCP 起始值 100、数量 150，对应新子网 `.100`～`.249`。

若上级网络也是 `192.168.100.0/24`，LAN/WAN 会发生网段冲突，需要调整网络规划。

## 产物、源码与许可证

固件不提交到 Git，只放 GitHub Releases。每次发布包含两个镜像、`sha256sums`、`packages.manifest`、`kernel.config`、`build-info.json` 和 `release-notes.md`。校验清单中的每个文件都应作为公开资产提供，不能只在 Actions 附件中存在。固件与记录保持唯一构建标识；不覆盖同版本同日的旧文件。

保留 YAOF 的 LICENSE、版权及原有声明。Release 明确提供对应 YAOF、OpenWrt 和 OpenWrt-Add 源码引用，第三方包许可证以各组件为准。发布者须持续确保相应的 Corresponding Source 可取得；单纯给一个会变化的上游主页不等于完成所有源码义务。

版本号、commit 和校验值提供可追溯性，**不保证未来完整重建或逐位复现**。若要长期复现，需额外保留实际 APK、工具链输入及相应源码，不可把短期 Actions cache 当作长期源归档。

## 第二阶段：先验证，再优化内核

第二、三阶段是候选路线，不属于第一阶段的实施授权；开始前需要用户批准具体范围。

先在 R5C 建立性能和稳定性基线：双网口、PPPoE、NAT、代理、FlowCone、SQM、WireGuard、无线、USB、温度、功耗及长期运行；验证 BPF verifier、TCX 挂载和外挂 BTF 的真实兼容性。

随后按低风险到高风险推进：

1. 测量并审核现有网卡 Ring Buffer、GRO/TSO、IRQ/RPS/XPS、队列和 cpufreq 设置；不盲目叠加“优化”。
2. 评估同一 LTS 的更新补丁版本，保留 OpenWrt 补丁和准确的模块 ABI。
3. 自行构建原生 BTF 内核，验证能否替代 shadow BTF，并评估 dae/AF_XDP 等真实需要的配置。
4. 在确认使用需求后审查编译配置及驱动裁剪；保留硬件恢复、热管理、安全和网络功能。
5. 再比较较新 LTS，只有回归测试和基准支持时才迁移；不默认追 Linux 主线或 RC。

验收应同时保留调整前后的内核配置、准确模块 ABI、包清单、基准方法和恢复镜像；验证启动、网络功能、安全性及长时间运行，不能只依据短时吞吐或构建成功。没有回归与实机证据时，不替换已验证的基线。

这些工作需要完整源码构建与实机证据，不应在 ImageBuilder 上伪装成内核配置已经变化。

## 第三阶段：按需要扩展

可选项包括独立的精确版本第三方 feed、源码/输入长期归档、硬件自动冒烟和性能回归、外部定时任务健康兜底，以及 LuCI 内的受控升级入口。只有确实需要更快吸收内核修复时，才将完整源码 rolling 构建作为另一渠道；它不能替代已验证的稳定固件。

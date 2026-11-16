# R5C 固件维护

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

首阶段基线的 OpenWrt 25.12.6 发布内核为 6.12.112。调研时 kernel.org 提供 6.12.117、较新的 LTS 6.18.63 和稳定版 7.3.4。这个版本差距真实存在，但不证明新系列在 R5C 上更快、更稳。实际每次构建的内核版本、配置和软件包记录在 Release 的 `kernel.config`、`packages.manifest` 和 `build-info.json`，以它们为准。

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

其他型号保留原有手动工作流，不自动推进 R5C 的成功状态。自动清理改为手动，避免删除仍需要的回滚固件及诊断。

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

固件不提交到 Git，只放 GitHub Releases。每次发布包含两个镜像、`sha256sums`、实际包清单、实际内核配置与输入记录。固件与记录保持唯一构建标识；不覆盖同版本同日的旧文件。

保留 YAOF 的 LICENSE、版权及原有声明。Release 明确提供对应 YAOF、OpenWrt 和 OpenWrt-Add 源码引用，第三方包许可证以各组件为准。发布者须持续确保相应的 Corresponding Source 可取得；单纯给一个会变化的上游主页不等于完成所有源码义务。

版本号、commit 和校验值提供可追溯性，**不保证未来完整重建或逐位复现**。若要长期复现，需额外保留实际 APK、工具链输入及相应源码，不可把短期 Actions cache 当作长期源归档。

## 第二阶段：先验证，再优化内核

先在 R5C 建立性能和稳定性基线：双网口、PPPoE、NAT、代理、FlowCone、SQM、WireGuard、无线、USB、温度、功耗及长期运行；验证 BPF verifier、TCX 挂载和外挂 BTF 的真实兼容性。

随后按低风险到高风险推进：

1. 测量并审核现有网卡 Ring Buffer、GRO/TSO、IRQ/RPS/XPS、队列和 cpufreq 设置；不盲目叠加“优化”。
2. 评估同一 LTS 的更新补丁版本，保留 OpenWrt 补丁和准确的模块 ABI。
3. 自行构建原生 BTF 内核，验证能否替代 shadow BTF，并评估 dae/AF_XDP 等真实需要的配置。
4. 在确认使用需求后审查编译配置及驱动裁剪；保留硬件恢复、热管理、安全和网络功能。
5. 再比较较新 LTS，只有回归测试和基准支持时才迁移；不默认追 Linux 主线或 RC。

这些工作需要完整源码构建与实机证据，不应在 ImageBuilder 上伪装成内核配置已经变化。

## 第三阶段：按需要扩展

可选项包括独立的精确版本第三方 feed、源码/输入长期归档、硬件自动冒烟和性能回归、外部定时任务健康兜底，以及 LuCI 内的受控升级入口。只有确实需要更快吸收内核修复时，才将完整源码 rolling 构建作为另一渠道；它不能替代已验证的稳定固件。

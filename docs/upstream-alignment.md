# YAOF 上游能力与优化对齐

## 新 session 从这里开始

先读根目录 [AGENTS.md](../AGENTS.md)，再读本文和 [R5C 维护说明](r5c.md)。本文回答“继承了什么、哪里不同、还有哪些证据缺口”；构建、发布、升级与阶段授权流程只在 R5C 维护说明中维护。

当前事实按以下顺序核对，不依赖旧会话或固定版本快照：

| 来源 | 用途 |
| --- | --- |
| `profiles/r5c.json` | 实际上游、稳定系列、设备 Profile、包配置、源与信任设置 |
| 上游跟踪分支和当前工作区 | 判断是否还有未合入的源码提交；检查语义差异，而不是要求 main 与上游 SHA 相同 |
| `profiles/packages.common`、`profiles/packages.rockchip`、`profiles/packages.x86_64` | 实际平台包选择；负号条目是排除默认包，不是“缺包” |
| `.github/workflows/R5C-OpenWrt.yml`、`scripts/build.sh`、`scripts/firmware.py` | 实际 R5C 自动化、组装和校验行为 |
| [成功构建状态](../.state/r5c.json) | 最近一次成功产物的上游 commit、addon commit、输入指纹和验证范围 |
| 对应 Release 的 `kernel.config`、`packages.manifest`、`build-info.json` | 最终内核配置和包，而不是仅凭 README 宣传或 SDK 编译选择判断 |

OpenWrt-Add 源码应优先读取成功状态中 `inputs.addon_sha` 对应的版本。软件源仓库最新源码与已经发布的 APK 不一定是同一时刻；默认分支链接只用于导航，不是实际产物版本证明。

## 分支对齐的含义

- `main` 是自有开发和发布分支，可以比上游多出定制提交。它应包含已接受的上游提交，但不应被重置成纯上游。
- 与 `profiles/r5c.json` 的 `upstream_branch` 同名的自有分支，是纯上游镜像；当前为 `25.12`，不要在该分支开发本地定制。
- R5C 成功发布后，工作流尝试将镜像**非强制快进**到本次验证的上游输入。它追踪已验证输入，不承诺任意时刻都与刚发生的新上游提交相同。
- 上游替换/重写提交，或镜像混入自己的提交时，非强制推送会拒绝。镜像步骤告警，不回滚已经发布的固件，也不自动强推任何分支。
- 人工处理纯镜像分歧前，确认其没有自有定制并保存旧引用；必要时只能对该镜像使用精确 lease。不要强制覆盖 main。`archive/upstream-*` 仅保存历史，不作为“最新上游”比较对象。

核对当前配置分支的例子：

```sh
upstream_branch=$(python3 -c 'import json; print(json.load(open("profiles/r5c.json"))["upstream_branch"])')
git fetch upstream "$upstream_branch"
git fetch origin "$upstream_branch"
git rev-list --left-right --count "HEAD...upstream/$upstream_branch"
git rev-list --left-right --count "origin/$upstream_branch...upstream/$upstream_branch"
git diff "upstream/$upstream_branch" -- profiles/packages.common profiles/packages.rockchip profiles/packages.x86_64
```

第一组计数右侧为 main 尚未包含的上游提交数；第二组计数用于镜像比较。单看“落后一条”不够，还要区分新提交与同一父提交上的替换提交。分支名若变更，应先审查自有镜像命名，不能让镜像推送指向 main。

## 上游能力及 R5C 继承状态

“已继承”表示对应配置/包进入构建链，不代表已启用、已配置或已通过实机验收。多个代理入口是选择，不等于应该同时启用。

| 能力 | 上游实现入口 | R5C 对齐状态与限制 |
| --- | --- | --- |
| 固件基础 | 官方 OpenWrt ImageBuilder、官方内核和 kmods，叠加 OpenWrt-Add APK | 同一构建架构；使用 R5C 官方 Profile，不移植历史 fullcone 内核补丁 |
| 管理界面与中文 | `luci`、Vantage 主题/应用、对应中文包、`system-addon` | 沿用通用清单。上游强调现代 JS LuCI，但本项目未证明所有第三方组件完全不含 Lua |
| HomeProxy / Nikki | `luci-app-homeproxy`、`luci-app-nikki` 及其依赖 | 包和语言包继承；账号、订阅、分流和真实代理流量需要用户配置及验收 |
| Honk / dae | 对应 LuCI、daemon、TC/BPF 模块、BTF 来源 | 继承；程序加载、BTF 布局、LAN/WAN 路径及与其他代理的组合未做实机验证 |
| FullCone NAT | FlowCone、TCX eBPF、nftables、外挂 BTF | 继承现行实现；不是依靠历史内核 fullcone 补丁。挂载、NAT、IPv6/PPPoE 和重启回退需要验收 |
| SQM / NATMap-T | `luci-app-sqm`、`luci-app-natmapt` | 继承；队列策略、上行带宽、实际时延及与 offload 的关系需要测量 |
| 网络管理 | Bandix、ARP 绑定、AP-Modem | 继承；统计准确性、绑定效果与实际调制解调器均未验收 |
| VPN 与服务 | WireGuard、ZeroTier、DDNS/Cloudflare、UPnP、3cat、AirConnect | 通用包清单继承；服务是否运行和实际可用取决于配置与外部环境 |
| 存储与系统工具 | f2fs、zram、文件管理、分区扩展、ethtool | 继承；不代表可以盲目扩分区或改变文件系统，需要确认存储布局 |
| 手机 USB 共享 | RNDIS、CDC-Ether、ipheth、usbmuxd | 继承；具体手机、USB 线、电源和连接流程需要实测 |
| R5C 网卡与无线 | 官方设备 Profile 的 r8169、rtw88-8822ce、firmware、wpad 选择 | 官方驱动随匹配内核提供；保留官方端口映射。实际无线模块必须匹配，不保证任意 M.2 模块都支持 |
| Rockchip 风扇 | `kmod-hwmon-pwmfan` | 沿用平台清单，不代表 R5C 的具体风扇硬件或控制已经验收 |
| x86 扩展 | Intel/Realtek/Mellanox NIC、虚拟网卡、i915、BBR3 | 保留上游手动配置，不把 x86 包或 Intel 专属优化当成 R5C 能力 |

`dnsmasq-full` 替换默认 dnsmasq；上游清单排除了 Attended Sysupgrade 相关入口。R5C 自有更新入口查询本仓库成功状态，不能改回按上游固件 Release 或 GitHub latest 接口盲目判断。

## 优化实现对齐表

以下是源码中的具体行为，不是性能提升结论。`system-addon` 的路径均相对 OpenWrt-Add，实际版本从成功状态读取。

| 项目 | 源码入口及行为 | R5C 状态／验证要求 |
| --- | --- | --- |
| TCP 拥塞控制 | 通用清单选择官方 `kmod-tcp-bbr`（BBR1）；x86 清单换成 BBR3。官方 BBR 包安装选择 `bbr` 的 sysctl 配置 | R5C 继承 BBR1，不加入 BBR3。内核编译默认 CUBIC 不证明运行时仍用 CUBIC；在设备上查生效算法。它不自动改变所有转发 TCP 连接 |
| Socket 缓冲区与排队 | `apps/system-addon/files/sys-tuning` 按实际 `MemTotal` 选择缓冲上限，设置 somaxconn、SYN backlog、netdev backlog 和 TCP rmem/wmem | 脚本继承。当前阈值对应 32/64/128 MiB 上限；标称 4 GB 不保证实际 MemTotal 越过 4 GiB 阈值。需测内存与高负载表现 |
| Ring Buffer 与中断合并 | `01-maximize_nic_rx_tx_buffers` 查询 ethtool 最大 RX/TX ring，尝试设为最大；支持时启用 adaptive RX/TX | 脚本继承。驱动可能不支持或拒绝设置；最大 ring 不保证最低时延，需要看实际 ethtool 值和 SQM 表现 |
| 网卡卸载 | `sys-tuning` 对物理 Ethernet 类型设备设置 GRO，并尝试 RX/TX checksum、SG、TSO 等 | 继承。失败可能被跳过；需核查真实网卡与 eBPF/PPPoE/队列组合，不能按脚本存在就认定全部生效 |
| 分流与软件 offload | `zzz-default-settings` 设置 packet_steering、steering_flows，启用软件 flow offload | 继承。不是手工逐 IRQ/RPS/XPS 绑核已经调优。FlowCone 文档声明软件 flowtable 兼容，但硬件 offload 会绕过 CPU TC；与 SQM/代理组合需验收 |
| zram | 默认压缩算法与 `sys-tuning`、`01-zram-tuning` 的 swappiness/page-cluster 动态设置 | 继承。实际 zram 存在、swap 启用和内存压力效果尚未实测 |
| Intel P-state | `sys-tuning` 仅在 Intel pstate 接口存在时调整 active、powersave、EPP | R5C 不具有该 Intel 接口，不能声称已做 R5C governor 优化。PC 型号 fallback 也不是 ARM 性能优化 |
| 首次初始化 | 中文、时区、NTP、软件镜像、IPv6/DHCP 和界面默认值 | 继承。自有 LAN 默认值单独在 board.d 设置；不应把“保留旧 LAN 地址”扩展成“上游初始化绝不覆盖其他用户偏好” |
| 内核 BPF 基础 | 官方内核实际 BPF/syscall/JIT、cgroup BPF、TC classifier/action 配置 | 构建门禁检查并保留，未为了裁剪而删除。实际程序加载仍需设备证据 |
| CO-RE 类型信息 | 上游 `vmlinux-btf` 从 SDK 头和配置生成 detached BTF | 继承。当前基础不是原生完整内核 BTF；版本/文件校验不证明所有运行时结构布局准确 |

当前没有新增 R5C 专属 IRQ/RPS/XPS、CPU governor、设备树裁剪、驱动删减或自定义内核性能补丁。不要在新 session 把候选二阶段优化写成已经实现。

## 必须单独评审的上游默认行为

这些行为被继承，但不能无条件称为“优化”或更安全。本次不擅自修改它们：

- 默认初始化关闭 DNS rebind protection、uhttpd RFC1918 filter 和 HTTP 到 HTTPS 的重定向，并修改 keepalive/timeouts。
- 初始化修改 firewall 全局 input/SYN flood 设置，并启用 UPnP。全局 input 值不等于所有 WAN zone 都开放；应检查实际 zone、服务监听与映射。
- 这些设置可能适应上游个人使用环境，却不必然适合本人的家庭/公网网络。安全性验收必须与吞吐测试分开。
- `fuck` 是上游 overlay 清理/恢复工具，不是固件版本更新器；执行前应先审查对应固定源码并备份，不为排查问题盲目执行。
- 配置了多个代理、NAT、队列或 offload 功能不表示任意组合都兼容；不要把多个透明代理都开启后将冲突归咎于内核版本。

## 自有差异：保留，不用上游覆盖

| 差异 | 本地入口 | 含义 |
| --- | --- | --- |
| R5C 专属构建 | `profiles/r5c.json`、R5C 工作流 | 原上游矩阵没有 R5C 行，本项目用专属流程调用已有通用组装脚本 |
| 默认管理地址 | `files/etc/board.d/99-lsls-network` | 初始 LAN 为 192.168.100.1/24；保留配置升级不强制改旧 LAN，官方端口定义不变 |
| 自有版本查询 | `files/usr/bin/yaof-update`、生成的 `/etc/yaof-release.json` | 查询 lsls01/YAOF 成功状态；下载、SHA 校验及兼容检查，不自动刷机 |
| 辅助包 | R5C `extra_packages` | 增加 curl、jsonfilter 支持自有更新命令，不改变其他平台清单 |
| 可追踪更新 | `scripts/firmware.py`、`.state/r5c.json` | 对源码、配方、内核配置和已发布软件源计算输入指纹；状态提交不触发循环构建 |
| 构建输入与包完整性 | `scripts/build.sh`、R5C 校验脚本 | 校验 ImageBuilder 与公钥、使用固定 addon 清理脚本；R5C 不允许静默跳过所选包 |
| 发布与镜像 | R5C 工作流 | 只读构建、独立写权限发布、唯一 tag、完整公共校验资产及纯上游镜像快进 |
| 诊断与其他设备 | Cleaning / 旧设备工作流 | 自动清理改为手动；其他设备仍使用原手动入口，不声称已纳入 R5C 同等完整验收 |

通用与平台包清单按当前上游对齐。不要重新加回旧合并留下的冗余排除项，也不要在自动同步时丢掉上述自有差异。

## 新 session 的证据缺口与下一步

1. 先核对 Git 上游包含关系和成功状态，区分“当前源码已同步”“最近固件已发布”“设备已经升级”三件事。
2. 用实际 R5C 建立基线：启动/恢复、SD/eMMC、双网口、无线、USB、LuCI、BBR、VPN、代理、FlowCone、SQM、温度和长期运行。
3. eBPF 验收必须包含 daemon 日志、verifier、TC/TCX 挂载和真实流量；当前 dae 包声明 XDP sockets，但官方内核没有开启 AF_XDP，外挂 BTF 也不能补缺失功能。
4. 在这些证据之前，不宣称“YAOF 全部特性已正常”或“新内核必然更快更稳”。内核原生 BTF、更新 LTS、配置裁剪和 BBR3 评估仍按 R5C 维护说明的后续阶段审批。
5. 变更后重新检查包清单、内核配置、公共校验文件及自有更新路径，并将能力/优化的变化更新到本文；操作流程与验证边界更新 R5C 维护说明。

## 上游导航

- [YAOF](https://github.com/QiuSimons/YAOF)：以配置的跟踪分支和实际接受的 commit 为准。
- [OpenWrt-Add](https://github.com/QiuSimons/OpenWrt-Add)：以成功状态的 addon commit 对照包、system-addon 脚本和生成的 BTF。
- [OpenWrt Rockchip 设备配置](https://github.com/openwrt/openwrt/tree/main/target/linux/rockchip)：对照实际 OpenWrt 发布版本，不按 main 推断当前固件配置。
- [FlowCone](https://github.com/QiuSimons/FlowCone) 与 [vmlinux-btf](https://github.com/QiuSimons/vmlinux-btf)：对照实际打包版本，检查最低要求与运行边界。

<p align="center">
<img width="768" src="https://raw.githubusercontent.com/QiuSimons/Others/master/YAOF.png" >
</p>
<p align="center">
<img src="https://github.com/Tired-Fox/cargors/raw/aabd34c/assets/badges/built_with_love.svg">
<p>
<p align="center">
<img alt="GitHub All Releases" src="https://img.shields.io/github/downloads/lsls01/YAOF/total?style=for-the-badge">
<img alt="GitHub" src="https://img.shields.io/github/license/lsls01/YAOF?style=for-the-badge">
<p>
<p align="center">
<img src="https://github.com/lsls01/YAOF/actions/workflows/R5C-OpenWrt.yml/badge.svg">
<img src="https://github.com/lsls01/YAOF/workflows/R2C-OpenWrt/badge.svg">
<img src="https://github.com/lsls01/YAOF/workflows/R2S-OpenWrt/badge.svg">
<img src="https://github.com/lsls01/YAOF/workflows/R3S-OpenWrt/badge.svg">
<img src="https://github.com/lsls01/YAOF/workflows/R4S-OpenWrt/badge.svg">
<img src="https://github.com/lsls01/YAOF/workflows/X86-OpenWrt/badge.svg">
<p>

<h1 align="center">请勿用于商业用途!!!</h1>

### 特性

- 基于 OpenWrt 官方 ImageBuilder 与 [OpenWrt-Add](https://github.com/QiuSimons/OpenWrt-Add) 预编译 APK 签名源组装，默认管理地址 192.168.100.1；保留配置升级时不覆盖原地址
- 纯 JS 现代 LuCI 界面，彻底淘汰老旧 Lua CBI 与 luci-compat
- 首次开机动态初始化中文环境、国内 NTP、国内软件源镜像及 Vantage 现代主题与实时网络仪表盘
- 插件包含：HomeProxy、Nikki、Honk / dae (基于 eBPF 的透明代理)、FlowCone (基于 eBPF 的 FullCone NAT)、WireGuard、ZeroTier、SQM (CAKE / FQ_Codel)、NATMap-T、Bandix (实时流量监控)、AP-Modem、ARP 绑定、AirConnect、DDNS、UPnP、3cat
- 保留上游 system-addon 的网络参数、网卡 Ring Buffer 和卸载设置；R5C 沿用官方内核及官方 BBR 模块选择，BBR3 仅随上游保留在 x86 专属包配置中，不加入 R5C
- 支持 iOS / Android 手机 USB 共享网络 (RNDIS / CDC-Ether / usbmuxd 随身 WiFi)
- X86: 覆盖 Intel、Realtek 2.5G、Mellanox 10G/25G、VirtIO/VMXNet3 虚拟化网卡及 Intel 核显 (i915 DRM)
- NanoPi 系列：支持 R2S / R2C / R3S / R4S / R5C；R5C 使用官方双 2.5G 网卡和无线设备 Profile
- 如有任何问题，请先尝试 ssh 进入后台，输入 fuck 后回车，等待机器重启后确认问题是否已经解决

### 硬件支持与 Profile

| 设备型号 | 架构 Target/Subtarget | 官方 Profile 名 | 固件输出标识 |
| :--- | :--- | :--- | :--- |
| **X86** | `x86/64` | `generic` | `YAOF-x86-64-...` |
| **NanoPi R2S** | `rockchip/armv8` | `friendlyarm_nanopi-r2s` | `YAOF-nanopi-r2s-...` |
| **NanoPi R2C** | `rockchip/armv8` | `friendlyarm_nanopi-r2c` | `YAOF-nanopi-r2c-...` |
| **NanoPi R3S** | `rockchip/armv8` | `friendlyarm_nanopi-r3s` | `YAOF-nanopi-r3s-...` |
| **NanoPi R4S** | `rockchip/armv8` | `friendlyarm_nanopi-r4s` | `YAOF-nanopi-r4s-...` |
| **NanoPi R5C** | `rockchip/armv8` | `friendlyarm_nanopi-r5c` | `r5c-<version>-<fingerprint>-<run>-<attempt>-...` |

### 固件下载与自动更新

- 本仓库 fork 自 [QiuSimons/YAOF](https://github.com/QiuSimons/YAOF)，上游许可证与声明保留。
- 下载自己设备对应的固件：[Releases](https://github.com/lsls01/YAOF/releases)。R5C 自动构建为 prerelease，不代表已通过实机验收。
- [R5C firmware](https://github.com/lsls01/YAOF/actions/workflows/R5C-OpenWrt.yml) 每 6 小时检查一次；也可 Run workflow，勾选 `force_build` 强制重建。
- 更新判断使用本仓库 `.state/r5c.json` 的成功构建指纹；软件源变化也会触发，不只比较 OpenWrt 版本号。
- 固件内 `yaof-update check` 查询本仓库；`yaof-update download squashfs` 或 `yaof-update download ext4` 下载并校验，绝不后台自动刷机。
- 内核边界、稳定性约束、升级方法及后续阶段见 [R5C 维护说明](docs/r5c.md)。维护或修改项目前先阅读 [AGENTS.md](AGENTS.md)；其他设备保留原有手动工作流。

### 鸣谢

|               [ImmortalWrt](https://github.com/immortalwrt)               |              [coolsnowwolf](https://github.com/coolsnowwolf)              |                    [Lienol](https://github.com/Lienol)                    |
| :-----------------------------------------------------------------------: | :-----------------------------------------------------------------------: | :-----------------------------------------------------------------------: |
| <img width="60" src="https://avatars.githubusercontent.com/u/53193414"/>  | <img width="60" src="https://avatars.githubusercontent.com/u/31687149" /> | <img width="60" src="https://avatars.githubusercontent.com/u/23146169" /> |
|            [NoTengoBattery](https://github.com/NoTengoBattery)            |                    [tty228](https://github.com/tty228)                    |                  [destan19](https://github.com/destan19)                  |
| <img width="60" src="https://avatars.githubusercontent.com/u/11285513" /> | <img width="60" src="https://avatars.githubusercontent.com/u/33397881" /> | <img width="60" src="https://avatars.githubusercontent.com/u/3950091" />  |
|                 [jerrykuku](https://github.com/jerrykuku)                 |                    [lisaac](https://github.com/lisaac)                    |             [rufengsuixing](https://github.com/rufengsuixing)             |
| <img width="60" src="https://avatars.githubusercontent.com/u/9485680" />  | <img width="60" src="https://avatars.githubusercontent.com/u/3320969" />  | <img width="60" src="https://avatars.githubusercontent.com/u/22387141" /> |
|                     [ElonH](https://github.com/ElonH)                     |                   [NateLol](https://github.com/NateLol)                   |                   [kiddin9](https://github.com/kiddin9)                   |
| <img width="60" src="https://avatars.githubusercontent.com/u/32666230" /> | <img width="60" src="https://avatars.githubusercontent.com/u/5166306" />  | <img width="60" src="https://avatars.githubusercontent.com/u/48883331" /> |
|              [AmadeusGhost](https://github.com/AmadeusGhost)              |                [1715173329](https://github.com/1715173329)                |                 [vernesong](https://github.com/vernesong)                 |
| <img width="60" src="https://avatars.githubusercontent.com/u/42570690" /> | <img width="60" src="https://avatars.githubusercontent.com/u/22235437" /> | <img width="60" src="https://avatars.githubusercontent.com/u/42875168" /> |

# Marco Movie HarmonyOS NEXT 0.1.3

发布日期：2026-11-28。应用版本 `0.1.3`（构建号 `1000004`）；最低 HarmonyOS NEXT API 12（通用未签名 `.hap`）。

## 核心更新

- **HarmonyOS NEXT 局域网扫码直绑 WebDAV**：同时覆盖触屏端扫码推/拉绑定与智慧屏大屏端展示 `marco-bind-box-v1` 加密二维码，实现鸿蒙设备与 Android / Windows / macOS / Apple TV 间快速安全绑定 WebDAV 与双向合并。
- **Emby / Jellyfin HTTP 8096 与 4K DirectPlay 修复**：连接弹窗默认采用 `HTTP + 8096` 并支持 HTTPS 切换与裸域名直填，自动兼容 `/emby` 与根路径 `/` 回退、标准 `X-Emby-Authorization` 头、TLS 握手失败 HTTP 端口明确引导及 DirectPlay 放行。

## 安装与校验说明

- **精确构建提交**：`4475ca1b22acefa3a282bbe0ce25186601f0d995`
- **安装方式**：未签名通用 `.hap`，安装前需使用 DevEco Studio 自动签名或 `hap-sign-tool` 签名后安装；因缺少物理鸿蒙真机，实机冷启动与播放表现仍待反馈。

## 包文件校验

- `MarcoMovie-0.1.3-harmonyos-universal.hap`（`54626398` B），SHA-256：`95efa6160b691557a4812f21ffbf27a5a49382525b698e0367709687f69d9477`
- `MarcoMovie-0.1.3-harmonyos.hap`（`54626398` B），SHA-256：`95efa6160b691557a4812f21ffbf27a5a49382525b698e0367709687f69d9477`
- 对应源码包：`MarcoMovie-harmonyos-v0.1.3-source.zip`（`23489437` B），SHA-256：`afc3ab1bfc8bd27c61959fbf37e52f2e1581356bf1ef59cb689298f43470de3e`

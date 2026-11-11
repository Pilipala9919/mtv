# Marco Movie iOS / iPadOS 0.5.19

应用版本：0.5.19（69）。本次重点修复百度网盘扫码登录失败、网盘原画/高码率资源播放失败等核心问题，并同步全端架构与稳定性优化。

## 核心修复与优化

- **修复百度网盘扫码登录失败**：兼容百度 Passport 扫码轮询接口返回数字型 `error_code: 0` 及跨端跳转完成态，解决切去百度 App 确认授权再切回 Marco Movie 时因后台挂起断开轮询或误判状态导致的无法登录问题；优先展示百度官方二维码图片。
- **修复百度网盘 / 夸克网盘资源播放失败**：为 iOS / 桌面端播放器补齐与 Android 端一致的本地云盘鉴权流代理（`CloudMediaProxy`），由本地回环代理自动携带网盘 `Cookie`、`User-Agent`、`Referer` 并跟随 302 多级 CDN 跳转及 `Range` 分片拖动请求，解决 `libmpv` 重定向丢鉴权头导致的播放报错。
- **内置站点脚本与首页聚合加固**：同步最新验证通过的内置脚本清单，玩偶/网盘站及聚合首页在部分源超时时自动跳过慢源并优先呈现可用结果。
- **多端代码线与更新通道统一**：保留 0.5.18 的分层胶囊设置、首页放大 Logo、更新校验及巨魔（TrollStore）/ 系统分享自签安装流程。

## 验证与包信息

- 本机与云端完整 Flutter 回归（**649 项测试**）及 iOS 内置运行时回归全部通过。
- IPA 已核验为 **0.5.19（69）**，`MarcoMovie-0.5.19-ios-unsigned.ipa` 与 `MarcoMovie-0.5.19-ios-iphone-ipad-unsigned.ipa` 字节一致；未签名包支持巨魔（TrollStore）直接覆盖更新或证书自签安装。
- 构建提交：`39e2cf2d00c4ef3b71ff395a7d5742a1afc1c33e`。[构建与检查记录（42937702864）](https://github.com/Pilipala9919/MarcoMovie/actions/runs/42937702864)。
- IPA SHA-256：`1ecc1b405b1867dbde4448e0b5661e58315369e1b18479f90bf27d071ad82f36`。

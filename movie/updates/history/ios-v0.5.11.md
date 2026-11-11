# iOS / iPadOS 0.5.11

- 发布平台：iOS / iPadOS（`ios`，iOS / iPadOS 14.0+，支持巨魔 TrollStore 直接安装与自签安装）
- 版本：`0.5.11`（`build 61`）
- 发布日期：2026-11-09
- 安装包：`MarcoMovie-0.5.11-ios-iphone-ipad-unsigned.ipa`（兼容名：`MarcoMovie-0.5.11-ios-unsigned.ipa`）

## 本次新增与改进

1. **新增 iOS 软件内拉取更新、应用内下载 IPA 与巨魔 (TrollStore) 一键覆盖安装**：
   - 在 `AppUpdate` 与「设置 → 软件更新与版本」弹窗中完整打通 iOS 端版本检测与安装包校验（自动请求国内镜像源 `updates/ios.json` 与 GitHub Releases 备用源）。
   - **巨魔 (TrollStore) 一键安装更新**：新增「巨魔 (TrollStore) 一键安装」主按钮（通过 `apple-magnifier://install?url=...` 协议直连国内镜像加速直链），点击直接拉起 TrollStore 自动下载并覆盖安装新版，无需跳转浏览器手动下载。
   - **应用内拉取 IPA 更新包（含进度条与 SHA-256 校验）**：支持在软件内直接下载新版 `.ipa` 并校验 SHA-256 完整性，自动存入系统「文件 (Files) → 我的 iPhone / iPad → Marco Movie」目录，方便轻松签、全能签、SideStore、AltStore 或巨魔直接导入安装。
   - **浏览器直链下载**：同步提供一键拉起 Safari 直链下载新版 `.ipa`。

2. **包含 0.5.10 全部修复**：
   - 修复夸克、百度、UC、阿里云盘扫码提示“已过期”的问题，支持 iPhone 本机一键跳转网盘 App 授权与返回前台自动登录。
   - 修复 iPhone 播放网盘资源仅显示 `01:40`（1 分 40 秒试看流）及夸克播放失败的问题。
   - 恢复 `玩偶哥哥` 等源的 4K 网盘线路（`优汐智1`、`夸父智1`、`嘟嘟无限2`、`阿狸原画`）与详情页横向播放线路选择栏，移除首页顶部网盘大卡片。


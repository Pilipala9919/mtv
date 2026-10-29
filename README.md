# MarcoTV 镜像站

Marco TV（Pilipala 开发的免费开源 Android 电视桌面）的镜像站源码，部署在 Cloudflare Pages，绑定域名 `marcotv.wlj9919.top`。

- 原项目：https://github.com/Pilipala9919/MarcoTV
- 本站首页：`index.html`，安装包和截图都在仓库根目录
- 协议：原项目为 GPL-3.0-only，本站内容整理自原项目 README 与文档

## 自动同步是怎么做的

1. 每天 10:00（北京时间），`.github/workflows/sync-release.yml` 自动跑一次，也可以在 Actions 里手动点 Run workflow 立即跑。
2. `scripts/sync_release.py` 去原项目查最新稳定版（`releases/latest`，不含预览版），有新版时下载新安装包和 4 张展示截图，更新首页里的版本号、发布日期、安装包文件名、大小和 SHA256 校验值，然后提交回本仓库。
3. Cloudflare Pages 接了本仓库，收到提交就自动重新部署，不用手动重传。

首页稳定版继续跟随最新稳定发布。电视更新另同步原项目 stable/preview 索引与对应 APK，逐一验证版本渠道、公开发布、大小、SHA-256 和官方校验文件；全部通过后再提交。保留旧版本 APK，避免打断已有下载。体验版区域的下载链接和版本文字随 preview 索引更新。

版权 © 2026 Pilipala。电视默认稳定渠道，用户主动选择体验渠道才会收到预览版。APK 安装仍需用户确认。`_headers` 设置索引短缓存；`404.html` 防止不存在的更新路径回退首页。

## Lite 实验版镜像

- 独立说明和下载入口：`/lite/`，首页也提供 Lite 下载卡片。
- 当前镜像 Lite 0.1.2，文件为 `MarcoTV-Lite-0.1.2.apk` 与同名 `.sha256`，逐字节校验与官方 Release 一致。
- `lite/validation.json` 和 `lite/docs/assets/` 来自相同版本。展示图是 Android 4.0.2 模拟器界面绘制，不是真机兼容或性能证明。
- Lite 不写入 `updates/stable.json` / `updates/preview.json`；现有稳定版同步任务不自动更新 Lite。后续 Lite 发布应单独核验官方 `lite-v*` Release、APK SHA-256、说明和验证记录，再更新此入口。
- 源码下载链接指向 GitHub 上对应的 Lite 标签及完整源码包。现有无 U 盘安装助手内含完整版，不用于自动安装 Lite。

## Cloudflare Pages 设置

- 连接仓库：本仓库，生产分支 `main`
- 构建命令：空（纯静态站）
- 输出目录：根目录
- 自定义域名：`marcotv.wlj9919.top`

# MarcoTV 镜像站

Marco TV（Pilipala 开发的免费开源 Android 电视桌面）的镜像站源码，部署在 Cloudflare Pages，绑定域名 `marcotv.wlj9919.top`。

- 原项目：https://github.com/Pilipala9919/MarcoTV
- 本站首页：`index.html`，安装包和截图都在仓库根目录
- 协议：原项目为 GPL-3.0-only，本站内容整理自原项目 README 与文档

## 自动同步是怎么做的

1. 每天 10:00（北京时间），`.github/workflows/sync-release.yml` 自动跑一次，也可以在 Actions 里手动点 Run workflow 立即跑。
2. `scripts/sync_release.py` 去原项目查最新稳定版（`releases/latest`，不含预览版），有新版时下载新安装包和 4 张展示截图，更新首页里的版本号、发布日期、安装包文件名、大小和 SHA256 校验值，然后提交回本仓库。
3. Cloudflare Pages 接了本仓库，收到提交就自动重新部署，不用手动重传。

注意：同步只跟稳定版，`0.12.0-rc.1` 这类预览版不会自动上镜像站；首页文案、功能介绍这些内容仍需手动改，同步脚本只改版本、日期、安装包、大小、校验值和截图。

## Cloudflare Pages 设置

- 连接仓库：本仓库，生产分支 `main`
- 构建命令：空（纯静态站）
- 输出目录：根目录
- 自定义域名：`marcotv.wlj9919.top`

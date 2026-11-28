# Marco Movie Android Lite 0.5.11

发布日期：2026-11-28。应用版本 `0.5.11`（版本代码 `61`）；最低 Android 4.0 / API 14 单 DEX 超轻量版（包名 `com.pilipala.marcomovie.lite`）。

## 核心更新

- **Emby / Jellyfin 连接兼容性全面修复**：连接界面新增 `HTTP / HTTPS` 协议开关（默认 `HTTP`、端口默认 `8096`）与选填端口/路径输入，支持直接填写裸域名或粘贴 `/web/` 地址；登录自动兼容 `/emby` 与根路径 `/` 回退及 HTTP → HTTPS 安全重定向，TLS 握手失败时在无凭据前提下主动探测给出清晰 HTTP 端口切换指引，并放行 DirectPlay。

## 包信息与构建记录

- **正式安装包**：`MarcoMovie-0.5.11-android-lite.apk`（`1328288` B；兼容别名 `MarcoMovie-0.5.11-lite.apk`）
- **APK SHA-256**：`3a4c3a3e1910ac3d498ca807cb42ca890d91a852c4bda255a5b205112bceee5f`
- **官方签名证书 SHA-256**：`2549f01e89c41201ea171847048228c6df79a7c57fff2ec9a439195c757a80de`
- **精确构建提交**：`a9d5c8cb2bc5c083dc82639c3cbf7026c01882db`
- **自动化验证**：已通过 API 14 单 DEX 构建与官方正式签名验证、`280` 项 JVM 回归、`8` 项 TLS 检查与 `20/20` 三端源一致性测试。实体 Android 4.x 电视盒实机播放仍待实测。

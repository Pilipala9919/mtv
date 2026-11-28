# Marco Movie macOS 0.6.2

发布日期：2026-11-28。应用版本 `0.6.2`（构建号 `74`）；Apple Silicon & Intel 通用包（`.app` ZIP）。

## 核心更新

- **macOS 专项流畅度、4K 臻彩与桌面体验升级**：
  - 合入 `CVDisplayLink` 屏幕刷新率自适应视频同步机制，改善高刷 Mac 播控平滑度；
  - 完善 4K / 臻彩分类识别与高画质网盘选集体验，新增起播阶段与网速遥测及有界下一集预缓冲；
  - 完善 Finder 本地 `.json`/`.zip` 配置导入、后台无感订阅刷新与多显示器窗口尺寸记忆。
- **桌面端 WebDAV 局域网扫码直绑**：macOS「云同步」新增局域网加密二维码生成，手机扫码即可快速推送或同步 WebDAV 配置与凭据。
- **Emby / Jellyfin 连接表单与 HTTP 8096 兼容修复**：连接弹窗默认 `HTTP + 8096` 并支持 HTTPS 切换、选填端口/路径/名称、裸域名直填与 `/emby` → `/` 根路径自动回退，补齐 `X-Emby-Authorization` 头与 TLS 握手无凭据引导，默认启用 4K DirectPlay。

## 构建与说明

- **精确构建提交**：`4475ca1b22acefa3a282bbe0ce25186601f0d995`
- **公证说明**：发布包采用 ad-hoc 签名未做 Apple 公证，首次运行如遇系统拦截请右键点击应用「打开」或核对官方 `.sha256` 校验和。

## 包文件校验

- `MarcoMovie-0.6.2-macos-desktop.zip`（`137098074` B），SHA-256：`bee810d5b7a02fdca92c84a75022e0a2235fcc11e30974c6ec99fe74f28c19ff`
- `MarcoMovie-0.6.2-macos.zip`（`137098074` B），SHA-256：`bee810d5b7a02fdca92c84a75022e0a2235fcc11e30974c6ec99fe74f28c19ff`
- 对应源码包：`MarcoMovie-macos-v0.6.2-source.zip`（`23463045` B），SHA-256：`fe035c386a0618c30026239fd9ee5f8c41842c043a46ee739cb3313071b51c5a`

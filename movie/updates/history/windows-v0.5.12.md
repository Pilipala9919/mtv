# Marco Movie Windows 0.5.12

应用版本：0.5.12（62）。本次同步百度网盘扫码登录与网盘流播放修复，并完善 Windows 桌面端快捷键、窗口管理与更新安装安全性。

## 更新内容

- **百度网盘扫码与云盘流播放修复**：修复百度扫码登录数字状态码解析与授权重定向，新增本地 `CloudMediaProxy` 云盘鉴权流代理，解决百度网盘、夸克网盘直链 302 跳转丢失请求头导致的播放失败。
- **桌面端交互体验优化**：修复搜索输入框聚焦时按 `Space`、`F`、`M`、方向键误触播放器快捷键的问题；修复退出全屏后窗口意外置顶的问题。
- **覆盖更新安装器加固**：安全转义安装包路径参数，安装向导升级前自动清理旧版 `flutter_assets` 与运行库残留，保留用户订阅、收藏、观看记录与网盘登录态。
- **分层设置与聚合加载优化**：同步六大胶囊分层设置抽屉与更稳健的并发源加载策略。

## 包信息

- 安装版：`MarcoMovie-0.5.12-windows-x64-setup.exe`（兼容别名 `MarcoMovie-0.5.12-windows-setup.exe`），SHA-256：`fd61d5cf327f428eb7d7a547bbbfc41470951021786f65c2c63642720b65f4af`。
- 绿色便携版：`MarcoMovie-0.5.12-windows-x64-portable.zip`（兼容别名 `MarcoMovie-0.5.12-windows-x64.zip`），SHA-256：`eb786d653033f8db2eb8da2e11f3280199e66cac68b012f56088d385ecb4f8c6`。
- 构建提交：`39e2cf2d00c4ef3b71ff395a7d5742a1afc1c33e`。[构建与检查记录（42937702864）](https://github.com/Pilipala9919/MarcoMovie/actions/runs/42937702864)。


# Marco Movie Android 手机 / 平板 0.5.17

应用版本：0.5.17（versionCode 72）。本次整合单站 CMS JSON 接口直连导入、双架构原生库体积精简与网络稳定性优化。

## 更新内容

1. **单站 CMS JSON 接口直连导入**
- 支持在订阅管理中直接粘贴苹果 CMS JSON 接口地址，自动探测站名并生成可用片源，无需手工编写订阅仓库 JSON。
2. **播放兼容与页面并发优化**
- 同步可选隧道播放开关（默认关闭以保障高兼容性）；详情页、搜索页与换源流程在页面退出或切换时即时中断旧请求，操作更跟手。
- 原生 QuickJS 引擎同时提供 `arm64-v8a`（16KB 页对齐，兼容 Android 15+ 新设备）与 `armeabi-v7a` 双架构编译并剥离调试符号。
3. **局域网配对防护与存储优化**
- 局域网配置服务增加跨站请求拦截保护；历史缓存清理改为数据库单事务执行。

## 包信息

- 安装包：`MarcoMovie-0.5.17-android-mobile.apk`（兼容别名 `MarcoMovie-0.5.17-mobile.apk`），官方正式签名，可直接覆盖安装升级。
- SHA-256：`43a0ca1c3d2a28a958ff585ecc30652ddd6c5999095f432834d55ed27c28d1a0`。
- 构建提交：`39e2cf2d00c4ef3b71ff395a7d5742a1afc1c33e`。[构建与检查记录（42937702864）](https://github.com/Pilipala9919/MarcoMovie/actions/runs/42937702864)。


# Marco Movie Android Lite 0.5.3

应用版本：0.5.3（versionCode 53）。专为 Android 4.0+（API 14+）老旧电视、机顶盒与老手机打造的超轻量独立版本（包名 `com.pilipala.marcomovie.lite`，可与标准版共存）。

## 更新内容

1. **老设备明文 HTTP 片源与 Android 9+ 兼容修复**
- 调整目标 SDK 兼容策略并保持 API 14 最低支持，解决在较新 Android 系统上访问部分传统 HTTP 影视采集站被系统拦截的问题，同时保留 Android 14+ 正常安装能力。
2. **遥控器加载取消与防串台优化**
- 新增详情加载、搜索与分类翻页任务令牌机制，快速按返回键或切换条目时不再被慢响应覆盖当前画面，遥控器焦点恢复更准确。
3. **局域网扫码配对安全防护**
- 局域网配置推送页新增 `Origin` / `Referer` 跨站请求校验，防止局域网内其他网页越权推送配置。

## 包信息

- 安装包：`MarcoMovie-0.5.3-android-lite.apk`（兼容别名 `MarcoMovie-0.5.3-lite.apk`），官方正式签名。
- SHA-256：`fac34864bb34c82f45a55aeca67b3166ae781e3bb11d3d8514839c0adcb3b8ca`。
- 构建提交：`39e2cf2d00c4ef3b71ff395a7d5742a1afc1c33e`。[构建与检查记录（42937702864）](https://github.com/Pilipala9919/MarcoMovie/actions/runs/42937702864)。

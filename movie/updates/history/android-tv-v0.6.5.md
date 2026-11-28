# Marco Movie Android 电视 / 盒子 0.6.5

发布日期：2026-11-28。应用版本 `0.6.5`（版本代码 `102`）；最低 Android 6 / API 23（32 位 `armeabi-v7a`）。本次为电视端背景视觉专项修复版本，彻底消除 `0.6.4` 大屏动态柔光背景出现的菱形噪点纹，并完整保留 `0.6.4` 全部功能与稳定性改进。

## 本次修复

- **修复电视端首页背景出现菱形网格纹问题**：将 `HomeAmbient.acquireTvScratchBitmap()` 缓存位图色彩格式由 16 位 `Bitmap.Config.RGB_565` 恢复为 32 位 `Bitmap.Config.ARGB_8888`（保留双缓冲复用与绘图前底色擦除，消除有序抖动矩阵在 `192×108` 放大至 `1920×1080` 大屏时的菱形棋盘纹），恢复细腻平滑的影院柔光渐变背景。

## 包信息与实机验证

- **正式安装包**：`MarcoMovie-0.6.5-android-tv.apk`（`56936646` B；兼容别名 `MarcoMovie-0.6.5-preview.apk`），包名 `com.pilipala.marcomovie`
- **APK SHA-256**：`ca077300759218e262aa4fe46425ca83019d10c72b1b367c6f5834145fef011d`
- **对应源码包**：`MarcoMovie-android-tv-v0.6.5-source.zip`（`23509378` B），SHA-256：`e1d85c51df2bb8e4f07ebb951549f3b904329baa59756bf6c8d57d895161bc90`
- **官方签名证书 SHA-256**：`2549f01e89c41201ea171847048228c6df79a7c57fff2ec9a439195c757a80de`（覆盖安装无损保留本地配置、收藏与观看记录）
- **精确构建提交**：`79d63024ce6fedd872b6748b9de208ad08d81c2f`
- **实机验证**：已在小米电视 Android 9（`MiTV-ASTP0`，`armeabi-v7a`）完成保留配置从 `0.6.4` 无损覆盖升级至 `0.6.5`（`versionCode: 102`）、冷启动拉起（零崩溃）及实机首页截屏对比确认首页柔光渐变背景已彻底消除菱形纹。

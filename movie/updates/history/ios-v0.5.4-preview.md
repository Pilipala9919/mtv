### Marco Movie iPhone / iPad 0.5.4 验证版

发布日期：2026-11-09。仅适用于 iPhone / iPad，版本 0.5.4（54），最低目标 iOS / iPadOS 14.0。

本次发布修复 TVBox / 影视仓 `drpy2.min.js` 及 `assets://js/lib/cheerio.min.js` 等模块在 iOS 端的运行适配，自动过滤网盘配置引导条占位源，并将换源弹窗、详情页与播放器 UI 布局同步对齐安卓手机端 0.5.6–0.5.7。

### 下载与安装

- [下载 iPhone / iPad 未签名 IPA](https://github.com/Pilipala9919/MarcoMovie/releases/download/ios-v0.5.4-preview/MarcoMovie-0.5.4-ios-iphone-ipad-unsigned.ipa)
- [IPA SHA-256 校验文件](https://github.com/Pilipala9919/MarcoMovie/releases/download/ios-v0.5.4-preview/MarcoMovie-0.5.4-ios-iphone-ipad-unsigned.ipa.sha256)
- IPA 需要自行签名，或使用设备系统支持的安装方式；不承诺所有系统均可使用 TrollStore。
- 包大小：65,103,447 字节（62.1 MB）。SHA-256：`e8b8d1a59c7b74ed724a95aa7b1659a68c05fa116cf5830875c5b922c2f49962`。

### 本次新增与修复

- **修复 `assets://js/lib/cheerio.min.js` 缺失报错与 `drpy2` 规则源适配**：识别 `api` 指向 `drpy2.min.js` 且 `ext` 为规则脚本地址的 TVBox / 影视仓站点，直接交由内置 `DrpySource` 引擎加载执行，并自动为规则补全顶层 `muban` 模板字典；同时在 QuickJS ES Module 预加载器中内置支持 `assets://js/lib/cheerio.min.js`（映射至 `drpy-dependencies.js`）、`assets://js/lib/crypto-js.js`、`assets://js/lib/cat.js` 及同源 `assets://js/lib/*` 脚本解析。
- **过滤网盘配置引导条占位站点**：扩充 `CspBridge.isMyDriveSite` 识别规则，自动过滤 `🔄 请先点击👇【网盘配置 ● 享受4K画质】`（`panWebShare.js` / `网盘配置` / `配置中心`）等非点播引导占位项，防止启动时默认选中占位项导致首页报错。
- **同步安卓手机端换源弹窗双列网格与折叠未适配列表**：iPhone 竖屏换源弹窗升级为双列紧凑胶囊网格（横屏 / iPad 为三列），搜索框与“管理线路”整合为单行；底部“当前设备未适配”插件列表默认折叠收纳（点击或搜索时展开），不再遮挡可用片源。
- **同步安卓手机端详情页双评分徽章与播放器交互**：竖屏详情页海报前景新增 `豆瓣 ★` 与 `🍅` 双评分胶囊徽章，精简主播放按钮文案；播放器呼出控制栏时移除上下全屏暗色遮罩，并为横向滑动快进快退加入随滑动距离线性加速的灵敏度曲线。

### 已完成验证

- [iOS 构建 42510466862](https://github.com/Pilipala9919/MarcoMovie/actions/runs/42510466862) 成功，全部 Flutter 单元与组件测试通过。
- 核对 IPA 压缩包完整性、`Info.plist` 版本号（`0.5.4` / `54`，`MinimumOSVersion 14.0`）及 SHA-256 校验值。

### 已知限制

- 33 条待验收 Android Guard / JAR 插件线路尚未全部跨平台移植。
- 不保证任意第三方 TXT、JS、JSON、Python、PHP 或本地包订阅均可用；配置格式可解析不等于其中每条自定义爬虫插件均可在 iOS 独立运行。

### 构建来源

安装包构建提交：`b3fd0a7defd59f84b90389ac349f42897c3d71cc`。随发布附上该提交的源码 ZIP 及 SHA-256 文件。


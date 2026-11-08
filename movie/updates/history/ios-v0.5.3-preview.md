## Marco Movie iPhone / iPad 0.5.3 验证版

发布日期：2026-11-09。仅适用于 iPhone / iPad，版本 0.5.3（53），最低目标 iOS / iPadOS 14.0。

本次发布修复 TVBox / 影视仓主流订阅源（含 `#EXTINF` 广告过滤规则与 `//` 注释的 JSON 配置）在 iOS 端被误判为 M3U 导致加载出 0 个站点的问题，并优化 `豆豆┃片单` 跨源搜索匹配与镜像站主下载入口。

### 下载与安装

- [下载 iPhone / iPad 未签名 IPA](https://github.com/Pilipala9919/MarcoMovie/releases/download/ios-v0.5.3-preview/MarcoMovie-0.5.3-ios-iphone-ipad-unsigned.ipa)
- [IPA SHA-256 校验文件](https://github.com/Pilipala9919/MarcoMovie/releases/download/ios-v0.5.3-preview/MarcoMovie-0.5.3-ios-iphone-ipad-unsigned.ipa.sha256)
- IPA 需要自行签名，或使用设备系统支持的安装方式；不承诺所有系统均可使用 TrollStore。
- 包大小：65,097,331 字节（62.1 MB）。SHA-256：`78f888ca696ca441896319fd275cf4a0cc1e211326381d2bdf3c91a8a584aa6d`。

### 本次新增与修复

- **修复含 `#EXTINF` 广告过滤规则与 `//` 注释的 TVBox / 影视仓 JSON 配置解析失败（0.5.2 关键修复）**：调整 `CmsParser.parseConfig`、`unpackConfigText`、`detectSubscriptionFormat` 与 `LiveCatalogParser.parse` 的解析优先级，先剥离 JSON 注释并识别 `{` / `[` JSON 根节点结构，避免将含有 `#EXTINF` HLS 广告过滤正则（`"rules"`）的 TVBox / 影视仓 JSON 配置（如饭太硬、无邪优选仓等）误送入 M3U 解析器导致抛出 `FormatException` 或丢失全部点播站点（此前表现为首页提示“共 0 个安卓专用插件站点”）。
- **优化 `豆豆┃片单` 跨源匹配与 Guard 源冷启动超时**：将 `CmsClient.playableDetail` 跨源检索调整为双并发批次与 12 秒超时窗口，支持片名标点规范化回退匹配，并排除 `csp_S_zpsGuard` 等非 MacCMS 网页搜索源干扰，确保首次点击豆瓣推荐海报时有充足时间完成 Guard 源 JAR 下载、NodeMobile 启动与规则提取。
- **多仓子仓库列表持久化保护**：`StorageService._loadImportedConfig` 在解析单仓内容前优先合并保存多仓子仓库列表（`depots`），确保任意子仓库异常时仍可直接切换其他子仓库。
- **完整保留 0.5.2 全部适配能力与 Glasswork UI**：包含 GZIP / `**`+Base64 / `2423` Hex-AES 订阅与直播解包、`jar` 与 `parses` 字段支持、XML CMS `ac=videolist`、AppYsV2（`V1.vod`）接口适配、移除网盘入口，以及 Glasswork 光学毛玻璃 UI。

### 已完成验证

- [iOS 构建 42504265429](https://github.com/Pilipala9919/MarcoMovie/actions/runs/42504265429) 成功，全部 Flutter 单元与组件测试（含带 `//` 注释与 `#EXTINF` `rules` 的 TVBox JSON 回归测试）通过。
- 核对 IPA 压缩包完整性、`Info.plist` 版本号（`0.5.3` / `53`，`MinimumOSVersion 14.0`）及 SHA-256 校验值。

### 已知限制

- 33 条待验收 Android Guard / JAR 插件线路尚未全部跨平台移植。
- 不保证任意第三方 TXT、JS、JSON、Python、PHP 或本地包订阅均可用；配置格式可解析不等于其中每条自定义爬虫插件均可在 iOS 独立运行。

### 构建来源

安装包构建提交：`3fe90ca55d954a26858cf8b92f10e51c82c7dcf3`。随发布附上该提交的源码 ZIP 及 SHA-256 文件。

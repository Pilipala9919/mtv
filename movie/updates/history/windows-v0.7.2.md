# Marco Movie Windows 0.7.2

发布日期：2026-11-26。应用版本 `0.7.2`（构建号 `79`）。本次 Windows x64 专项稳定性与桌面体验升级重点根治正常关闭时的原生访问冲突崩溃（`0xc0000005`）、MPV 开启人声增强后无声、MDK 换集延迟释放纹理跨过窗口销毁边界等核心问题，并同步交付首次启动官方渠道声明、应用内双形态自动更新、窗口位置记忆、跨线路同集保进度与离线下载非阻塞冷启动等多项桌面端优化。

## 更新内容

- **根治 Windows 正常关闭时进程崩溃（`0xc0000005`）与统一退出生命周期**：统一直接退出与托盘退出的单次幂等入口，在 Win32 窗口销毁前阻断 Flutter 消息转发与销毁子窗口同步重入，确保 `flutter_controller_` 与窗口在 `CoUninitialize()` 前于 UI 线程按序释放，并限定 Windows 预退出钩子与销毁标记不污染 macOS / Linux 关闭路径；完整保留「直接退出」与「关闭到托盘 → 恢复 → 退出」语义。
- **修复 MPV 开启人声增强后无声及快速换集恢复/选轨竞态**：将轻度 / 标准 / 影院人声三档切换为随包 `libmpv-2.dll` 原生支持的 `lavfi=[equalizer=...]` 参数均衡链（旧 `cinemaVocal` 配置冷启动即有声，立体声与 5.1 声道、热切与换集均正常输出）；滤镜故障自动原声恢复按播放器实例、媒体会话与任务身份严格隔离，并绑定音轨事件到当前媒体会话以防旧集迟到选轨污染新一集（同时保留本集手选音轨）。
- **根治 MDK 换集延迟释放纹理跨过窗口销毁边界的竞态**：释放旧纹理 `ReleaseRT` 与创建新纹理 `CreateRT` 之间新增原生销毁边界与取消门禁（销毁后新增 `CreateRT = 0`，正常换集仍可创建新纹理），完善 MDK 异常事件流与自动回退 MPV 续播（保留断点与默认 MDK 偏好）。
- **桌面端更新、窗口记忆与浏览体验升级**：新增首次启动官方渠道提示与联系反馈入口、`WindowsUpdateSheet` 应用内更新（自动识别 Inno Setup 安装版 / 便携版并校验 SHA-256、禁止旧版降级）、多屏安全窗口位置/尺寸记忆、跨线路同集保进度、直播小窗展开继承频道与路线、多源聚合与播中换源，以及离线下载非阻塞异步冷启动与「我的」页虚拟滚动优化。

## 包信息与构建记录

- **Windows 64 位安装版（Inno Setup）**：`MarcoMovie-0.7.2-windows-x64-setup.exe`（`72209363` B，兼容别名 `MarcoMovie-0.7.2-windows-setup.exe`），SHA-256：`d5e0fdd42556e7594542cc1b00351e486c17a66e76fc495e687ace4e00a76e98`
- **Windows 64 位绿色便携版**：`MarcoMovie-0.7.2-windows-x64-portable.zip`（`103492098` B，兼容别名 `MarcoMovie-0.7.2-windows-x64.zip`），SHA-256：`0f8284f262cae12ee2e5d66ee22a809e33d61c65591d04b70c36e19e5a996d2e`
- **对应源码包**：`MarcoMovie-windows-v0.7.2-source.zip`（`21901506` B），SHA-256：`5634501ea9af0ba5a2d867850dad51937d3edabf50603e92676af01294e6d88b`
- **构建提交与 CI 记录**：主分支提交 `e196d53b08a4df0e59028a059a168943df976479` · [Windows x64 构建（Job 139966489463 · Run 45835704452）](https://github.com/Pilipala9919/MarcoMovie/actions/runs/45835704452/job/139966489463) / [公开守卫与离线校验（Job 139963875072）](https://github.com/Pilipala9919/MarcoMovie/actions/runs/45835704452/job/139963875072)

## 验证范围与已知限制

- GitHub Actions `windows-latest`（Flutter `3.38.9` + Inno Setup 6）全绿通过：`1662` 项 Flutter 单元测试（`18` 项非 Windows 专属跳过）、`13` 项打包 `libmpv-2.dll` 播放测试、`test_windows_installer.py` 与 `2764` 文件公开内容守卫均通过；本机实测云端正式 `0.7.2` EXE 14 轮退出（含原生调试器 `0xC0000005` 监测、10 轮 `WM_CLOSE`、`Alt+F4`、快速 10 连关与托盘退出）全部退出码 `0`、零残留进程、零新增崩溃事件，且正式 `libmpv-2.dll` / `fvp.dll` 通过人声恢复与 MDK 销毁边界复测。
- 安装包与便携程序未购买商业代码签名证书，Windows SmartScreen 首次运行可能提示未知发布者；动态网页嗅探与 WebView2 异步 JS 需系统已安装 Microsoft Edge WebView2 Runtime。

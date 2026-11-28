# Marco Movie Apple TV 0.1.3

发布日期：2026-11-28。应用版本 `0.1.3`（构建号 `4`）；最低系统要求 `tvOS 16.0`（未签名 `.ipa`）。

## 核心更新

- **客厅 WebDAV 局域网扫码直绑**：在 Apple TV 端引入 `WebdavBindCrypto`（AES/HMAC `marco-bind-box-v1`）与 `/bind` 端点；客厅大屏展示局域网二维码后，使用移动设备扫码即可直接将 WebDAV 地址、账号与加密密码安全同步至 Apple TV 并触发合并。
- **同步合入近期 tvOS 稳定性与体验改进**：包含大屏播放 HUD 操控优化、6 路流式网盘 Range 代理、焦点恢复与弹幕稳定性增强。

## 安装与校验说明

- **精确构建提交**：`4475ca1b22acefa3a282bbe0ce25186601f0d995`
- **安装方式**：未签名 `.ipa`（`MarcoMovie-0.1.3-tvos-appletv-unsigned.ipa` 及兼容别名 `MarcoMovie-0.1.3-appletv-unsigned.ipa`），可通过 Xcode 或自签工具部署，未真机验证全部商业片源。

## 包文件校验

- `MarcoMovie-0.1.3-tvos-appletv-unsigned.ipa`（`3451700` B），SHA-256：`07cd22222f2701e6a8a3e4d42c5cc7c8a8c90544cc2e0b18ece83816a969d110`
- `MarcoMovie-0.1.3-appletv-unsigned.ipa`（`3451700` B），SHA-256：`07cd22222f2701e6a8a3e4d42c5cc7c8a8c90544cc2e0b18ece83816a969d110`
- 对应源码包：`MarcoMovie-appletv-v0.1.3-source.zip`（`23476241` B），SHA-256：`91eb56bdabbc4e1119304c78b7e60756e684cb47c580fc73769269aafb49055c`

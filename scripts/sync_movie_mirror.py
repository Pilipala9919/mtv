"""Sync published Marco Movie preview releases into an isolated static mirror directory.

Copyright (C) 2026 Pilipala. SPDX-License-Identifier: GPL-3.0-only.
Only official release assets are accepted; all downloads are checked before writing the feed.

Packages are mirrored in the repo (files up to the 25 MiB Pages limit) so
the in-app update feeds and the edge download proxy keep working; larger
packages stay on GitHub. Every download card's button goes to the permanent
Quark Drive share link; the GitHub release URL only survives as the
checksum file link. Per-platform
feeds (movie/updates/<platform>.json) may override a card with that platform's
latest version.
"""
import argparse
import hashlib
import html
import io
import json
import os
from pathlib import Path
import re
import struct
import urllib.request
import zipfile

REPO = 'Pilipala9919/MarcoMovie'
BASE = 'https://marcotv.wlj9919.top/movie/'
LIMIT = 25 * 1024 * 1024
# Desktop and Apple packages may exceed the 25 MiB per-file limit of the Cloudflare Pages host.
# Those are listed on the mirror page but downloaded from the official GitHub release asset.
PLATFORM_LIMIT = 300 * 1024 * 1024

# Official QQ group (universal: covers Marco TV and Marco Movie, not one product).
QQ_GROUP_URL = 'https://qun.qq.com/universal-share/share?ac=1&authKey=%2FqKQ4IqdIqi2mRxgPr8PBGGEhIo0M5yMI6%2BBNKH7CoOFDczcaEXekgiu8Kbt%2BORc&busi_data=eyJncm91cENvZGUiOiI4MTUwODUxMDIiLCJ0b2tlbiI6Im9CUW4wejI1NlB6UW9uK1EzdGNEMlZXdkgvMExVcGpVdXhOMFVrVXZmcWt0N3ZoaHRLMzNzd2lLVVp6UzZXc2QiLCJ1aW4iOiI5MjYwMDQzIn0%3D&data=VXYI4NkXW1KuR0A5qzeADzpuJOBl7PrdDs8NBNT4RMeKMjrMmev1_pjDDKH3CfTw7VwFoH-5Hkd71EDQ9_qj1w&svctype=4&tempid=h5_group_info'
QQ_GROUP_CODE = '815085102'
# Second official QQ group, same universal scope (added 2026-11-08).
QQ_GROUP2_URL = 'https://qun.qq.com/universal-share/share?ac=1&authKey=4nZ%2F26D%2BhMLo6lpV1MQfM69dkpOz2TvHsfIf9bRWMtZA0gKGiIqgH2vzgqcaIvPT&busi_data=eyJncm91cENvZGUiOiIxMDM2NDA0MjM4IiwidG9rZW4iOiIvdWRhVUc5WjRpQkZkZkdvYTNZa1ViVlhGVmVGOGsxTUVYZUJHV0lVOWZ2aUxSM2pQUHNBRTVMMS9sb01ETHVNIiwidWluIjoiOTI2MDA0MyJ9&data=9yPnjsGlyhnKtpk8QK9noXL2QkiODxOBsmKZ3IaeJyiux1GGkQ133sh8-szNRlS_L3LkjShSMyXMaH3uiyyH3w&svctype=4&tempid=h5_group_info'
QQ_GROUP2_CODE = '1036404238'
# Third official QQ group, same universal scope (added 2026-11-09).
QQ_GROUP3_URL = 'https://qun.qq.com/universal-share/share?ac=1&authKey=ws6auJW%2BuftWj0%2BsnZbOLnvNbl0Ggt%2FcTmQN7%2BlonNBzUamrwpioeqnOC9WgAykn&busi_data=eyJncm91cENvZGUiOiIxMTA5Mzk3ODQyIiwidG9rZW4iOiJILzBhR05mdENBckpwMFBudmNzd1JDS3ZFTkZhcjNWMlJnVjFiLzhReHlMc1VuS2Q2emR6N211cDhJUVZFY3VRIiwidWluIjoiOTI2MDA0MyJ9&data=G8FC-Qq9g9Hc60XTobpCu8MVb-W4EwRZJoYYgQxTJzSkutIWe-8LWboOF451y2aMdH8N4I3p1H1XtAoqRLzgVQ&svctype=4&tempid=h5_group_info'
QQ_GROUP3_CODE = '1109397842'
# Fourth official QQ group, same universal scope (added 2026-11-10).
QQ_GROUP4_URL = 'https://qun.qq.com/universal-share/share?ac=1&authKey=4R4VS2AZHrwlVDj%2BgPmVxmcoPOjrnr9ENZVwvmjCcibaj9bbvA%2Bt7wHfUx2p6DhK&busi_data=eyJncm91cENvZGUiOiIxMTM1NTU2MzQyIiwidG9rZW4iOiI3UDI5WjZRNVdEUW9vU2dpaHZpejgxRm8xbzJKYk53TUhkVkF5VVZqeGJ2QU1WWHo1dFpIS2kwRWRiNjVPTTFJIiwidWluIjoiOTI2MDA0MyJ9&data=cCs0QRwbu37CVPXnKa8dCNjBmg64vKQNc-SvEyqqHCtTaH9dFIVK_ebEpz1R6epl-UFxvXmwgD3DcbEbDaDFDg&svctype=4&tempid=h5_group_info'
QQ_GROUP4_CODE = '1135556342'
# Fifth official QQ group, same universal scope (added 2026-11-13).
QQ_GROUP5_URL = 'https://qun.qq.com/universal-share/share?ac=1&authKey=65Mqw9daSUbAtgzCx4pJfUrtu%2FFSVG8EaMf7NabXrs3oZAWrQikcppAOmzBrWxCB&busi_data=eyJncm91cENvZGUiOiI3MTk2NTMyMDgiLCJ0b2tlbiI6Imt6dXMwTUhxcW9JM1VhV2RBMGZKUHZVdnBaa2p1MTgvS2RlN1ByMzZyRzcxZm9oSk5UMzZyam5va0Y5enBrYnAiLCJ1aW4iOiI5MjYwMDQzIn0%3D&data=-RJGncjsQc24ceUyIj5fqQAioLoqI9NM05EirWbDkurn_LN2dzT1oMUAY5opGwCmHLHKu_kMjBgshLNU66zD8A&svctype=4&tempid=h5_group_info'
QQ_GROUP5_CODE = '719653208'
# Sixth official QQ group, same universal scope (added 2026-11-15).
QQ_GROUP6_URL = 'https://qun.qq.com/universal-share/share?ac=1&authKey=AjxHG3yHvzzYhak51CIowxk0VdnymHxcHhpzP9KX130uzdzBrDJifxuwi%2FCHxZzD&busi_data=eyJncm91cENvZGUiOiIxMTM2MjUyNzg2IiwidG9rZW4iOiIvRnZmZFdTNjF3eWVIUlYvQ3VpU1lWWjBJZENHdUZuQWtyVUFpOHdNcE1YaTl4TmJOdTZDcW1zQldjdlhJOTMyIiwidWluIjoiOTI2MDA0MyJ9&data=L2iVl1AmbfbbwzxnZQyJXmo7khoYflsYSDjkRnJMqEouDDRsI46_NtzWI-9nr48crOziKWr4-pqKjGVvEvZKQw&svctype=4&tempid=h5_group_info'
QQ_GROUP6_CODE = '1136252786'

QQ_GROUP7_URL = 'https://qun.qq.com/universal-share/share?ac=1&authKey=BwtsqpgLEJSl27gFHWB%2BIcJ7eOMFxdugHZatXl63g7lfrVBVM%2BX0Ler5HLevajcA&busi_data=eyJncm91cENvZGUiOiIxMDkyODgxMTUwIiwidG9rZW4iOiJFSmlOdFNGQ2d2bUpwc0NBN1d6Z0taUUxyc1VkUUllTU8za2gxeGd5WS9JOFM4amdyUlROL1JMQ0R4akxhd05pIiwidWluIjoiOTI2MDA0MyJ9&data=IDgssTWvaVVBWlGPnyUPGWjLbIEvmGxNS8lsaOYyHlUSqdCicIYdLeRdnNUj5lkEPs01NzTQ0f73ATLwJ4ciFw&svctype=4&tempid=h5_group_info'
QQ_GROUP7_CODE = '1092881150'
# Eighth official QQ group, same universal scope (added 2026-11-23).
QQ_GROUP8_URL = 'https://qun.qq.com/universal-share/share?ac=1&authKey=83IjYjBMDYnVi4HyiDyG5Tg7jUZr6mO7%2BEe7siM46OkTDqz1UdxOlUii03ksIiQx&busi_data=eyJncm91cENvZGUiOiIxOTAzMzAyOTciLCJ0b2tlbiI6InlpdzdtWjlZZDM4N3Y2Q0hIWDI5Qnd0Q0dsL2w5OEhVcngwMVlnVnRMWkUxbnQ5NGFCQjZkcEZ4VXRXaVZWYUYiLCJ1aW4iOiI5MjYwMDQzIn0%3D&data=Hh8YquUZLsQsNs8cZNjvnvGI0x3gZwrAVA9xSLDzXasDDHAVlfd7ZEA9_hlMryQe9F8uqZVKXXxKeTOOf6Hupw&svctype=4&tempid=h5_group_info'
QQ_GROUP8_CODE = '190330297'
# Quark Drive share links, written by scripts/sync_quark.py (one permanent
# folder link per platform). Absent on first run: cards render without the
# Quark button until the first Quark sync writes the manifest.
QUARK_MANIFEST = Path(__file__).resolve().parent / 'quark.json'
# (file name pattern, button label, short note). Mirrored only when the release carries the
# package together with its official .sha256 file.
PLATFORMS = (
    ('MarcoMovie-{version}-mobile.apk', 'Android 手机 / 平板版 (64位)', 'Android 6.0+ · 原生 64 位 (arm64-v8a) 与 32 位双架构 · 竖屏触控 UI'),
    ('MarcoMovie-{version}-ios-unsigned.ipa', 'iPhone / iPad 版 (IPA)', 'iOS / iPadOS 14.0+ · 支持巨魔 (TrollStore) 直接安装或自签安装'),
    ('MarcoMovie-{version}-windows-setup.exe', 'Windows 安装版（推荐）', 'Windows 10 / 11 · 64 位安装向导 · 内置运行库与快捷方式，支持后续一键更新'),
    ('MarcoMovie-{version}-windows-x64.zip', 'Windows 绿色版（ZIP）', 'Windows 10 / 11 · 64 位便携压缩包 · 解压后运行 marco_movie.exe'),
    ('MarcoMovie-{version}-macos.zip', 'macOS 版', 'macOS · 解压后拖入“应用程序”；未公证，首次打开请右键选择“打开”'),
    ('MarcoMovie-{version}-lite.apk', 'Android 4.0+ 轻量版', 'Android 4.0+ (API 14+) · 适配老旧电视/盒子/老手机 · 独立包名可共存'),
)

# Page layout (2026-11-22, approved from the local preview): pure black
# background, electric-blue accent, same design language as the Hub and the
# TV page. Order: hero -> download -> donate -> features -> changelog ->
# group -> footer. The hero has no download button (only a "全部平台" text
# link to #download); every card button just says "下载" and goes to Quark.
# The wordmark is movie/assets/movie-wordmark-dark.png; the nav symbol, app
# icon and donation QR codes live in the repo-root /assets/. The changelog
# section below renders only the current release; the platform patcher
# (sync_platform_packages.py) replaces it with the full per-platform
# history on every workflow run.
# Stars shown on the page are fetched live from the repo API on every sync;
# if the API is unreachable, keep the number already on the page, else the
# last verified count below. Never fail the sync over a star count.
STARS_FALLBACK = 602  # verified 2026-11-09 (was a stale 165 snapshot from 2026-11-07)
PAGE_CSS = """
  :root{
    --bg:#000000;
    --text:#F5F5F7;
    --muted:#A1A1A6;
    --faint:#6E6E73;
    --line:rgba(255,255,255,.12);
    --accent:#0A84FF;
    --accent-hover:#409CFF;
    --warn:#FFB340;
    --max:1120px;
  }
  *{box-sizing:border-box}
  html{-webkit-text-size-adjust:100%;scroll-behavior:smooth}
  body{
    margin:0;background:var(--bg);color:var(--text);
    font-family:-apple-system,BlinkMacSystemFont,"SF Pro Display","SF Pro Text","PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif;
    line-height:1.7;-webkit-font-smoothing:antialiased;text-rendering:optimizeLegibility;
    overflow-x:hidden;
  }
  a{color:var(--text);text-decoration:underline;text-decoration-color:rgba(255,255,255,.35);text-underline-offset:3px}
  a:hover{text-decoration-color:var(--text)}
  a:focus-visible,button:focus-visible,summary:focus-visible,select:focus-visible{outline:2px solid var(--accent);outline-offset:3px;border-radius:4px}

  /* ---------- 顶栏（与 Hub / TV 一致） ---------- */
  nav{
    position:fixed;top:0;left:0;right:0;z-index:10;height:48px;
    background:rgba(22,22,23,.72);
    -webkit-backdrop-filter:saturate(180%) blur(20px);
    backdrop-filter:saturate(180%) blur(20px);
  }
  .nav-inner{
    max-width:1024px;height:100%;margin:0 auto;padding:0 24px;
    display:flex;align-items:center;justify-content:space-between;gap:16px;
  }
  .nav-brand{color:var(--text);font-size:17px;font-weight:700;letter-spacing:-.01em;text-decoration:none;display:inline-flex;align-items:center;gap:8px}
  .nav-brand img{display:block}
  .nav-links{display:flex;gap:28px;font-size:14px}
  .nav-links a{color:var(--muted);text-decoration:none;transition:color .3s ease}
  .nav-links a:hover{color:var(--text)}
  .nav-links .current{color:var(--text);font-weight:600}

  /* ---------- 首屏 ---------- */
  .hero{padding:120px 24px 0;text-align:center}
  .hero-wordmark{width:min(560px,82vw);height:auto;display:block;margin:0 auto}
  .hero .lead{margin:32px auto 0;font-size:21px;line-height:1.6;max-width:680px}
  .hero .actions{display:flex;flex-wrap:wrap;align-items:center;justify-content:center;gap:14px;margin-top:32px}
  .hero .meta{margin:28px auto 0;font-size:15px;color:var(--muted)}
  .hero .meta b{color:var(--text);font-weight:600}
  .hero .free{margin:12px auto 0;font-size:14px;color:var(--muted);max-width:640px}
  .hero-el{opacity:0;transform:translateY(20px);animation:heroIn .9s cubic-bezier(.22,1,.36,1) forwards;animation-delay:var(--d,0s)}
  @keyframes heroIn{to{opacity:1;transform:translateY(0)}}

  .btn{display:inline-block;text-decoration:none;font-weight:600;font-size:16px;line-height:1.4;
    padding:12px 26px;border-radius:999px;cursor:pointer;white-space:nowrap}
  .btn-primary{background:var(--accent);color:#fff}
  .btn-primary:hover{background:var(--accent-hover);text-decoration:none}
  .btn-ghost{border:1px solid rgba(255,255,255,.28);color:var(--text)}
  .btn-ghost:hover{border-color:rgba(255,255,255,.55);text-decoration:none}
  .textlink{font-size:16px;color:var(--accent);text-decoration:none}
  .textlink:hover{color:var(--accent-hover);text-decoration:underline}

  /* 工具声明：首屏下一句安静的说明 */
  .notice{max-width:680px;margin:64px auto 0;padding:20px 24px 0;border-top:1px solid var(--line);
    font-size:14px;color:var(--muted);text-align:center;line-height:1.8}

  /* ---------- 滚动揭示动效（与 Hub / TV 一致） ---------- */
  .reveal{opacity:0;transform:translateY(24px);transition:opacity .9s ease-out,transform .9s cubic-bezier(.22,1,.36,1);transition-delay:var(--d,0s)}
  .reveal.in{opacity:1;transform:translateY(0)}

  /* ---------- 实用区（左对齐窄栏，与 TV 一致） ---------- */
  .util{max-width:980px;margin:0 auto;padding:0 24px}
  section.util{margin-top:104px}
  section.util h2{margin:0 0 8px;font-size:30px;line-height:1.3;font-weight:700;letter-spacing:-.015em}
  section.util .intro{margin:0 0 8px;font-size:17px;color:var(--muted);max-width:720px}
  section.util .intro + .intro{margin-top:12px}
  section.util .intro.wide{max-width:none}

  /* ---------- 下载卡片 ----------
     约束（同步脚本 patch_card 依赖，改版式时不可破坏）：
     每张卡是一个带 dl 类的独立容器，内部不能再嵌套容器元素；
     卡内恰好一处 "N MB"、恰好一处 "SHA-256：<64位>"、恰好一个
     含包文件名的 .sha256 校验链接；版本放在 package-version
     标记里，由脚本更新。 */
  .dl-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:20px;margin-top:32px}
  .dl{border:1px solid var(--line);border-radius:18px;padding:24px;display:flex;flex-direction:column}
  .dl h3{margin:0;font-size:19px;font-weight:700;letter-spacing:-.01em;line-height:1.4}
  .package-version{
    display:inline-block;vertical-align:middle;margin-left:8px;
    font-size:13px;font-weight:600;color:var(--muted);
    border:1px solid var(--line);border-radius:999px;padding:1px 10px;
  }
  .card-meta .package-version{margin-left:0;margin-right:6px}
  .card-status{
    display:inline-block;vertical-align:middle;margin-left:8px;
    font-size:13px;font-weight:600;color:var(--warn);
    border:1px solid rgba(255,179,64,.45);border-radius:999px;padding:1px 10px;
  }
  .card-status:empty{display:none}
  .dl .card-note{margin:12px 0 0;font-size:14px;color:var(--muted);line-height:1.7;flex:1}
  .dl .card-meta{margin:10px 0 0;font-size:14px;color:var(--muted)}
  .dl .btn{
    display:block;text-align:center;margin-top:16px;
    background:var(--accent);color:#fff;
    padding:11px 20px;font-size:15px;
    position:relative;overflow:hidden;
    transition:background .2s ease,transform .2s ease;
  }
  .dl .btn::after{
    content:"";position:absolute;top:0;left:-80%;width:50%;height:100%;
    background:linear-gradient(105deg,transparent,rgba(255,255,255,.45),transparent);
    transform:skewX(-20deg);animation:btnShine 3.2s ease-in-out infinite;
  }
  @keyframes btnShine{0%,55%{left:-80%}100%{left:130%}}
  .dl:nth-child(3n+2) .btn::after{animation-delay:.55s}
  .dl:nth-child(3n+3) .btn::after{animation-delay:1.1s}
  .dl .btn:hover{background:var(--accent-hover);text-decoration:none;transform:translateY(-1px)}
  @media (prefers-reduced-motion:reduce){.dl .btn::after{animation:none}}
  .package-check{margin-top:16px;font-size:13px;color:var(--muted)}
  .package-check summary{cursor:pointer;list-style:none;color:var(--muted)}
  .package-check summary::-webkit-details-marker{display:none}
  .package-check summary::after{content:" ›";display:inline-block;transition:transform .2s ease}
  .package-check[open ] summary::after{transform:rotate(90deg)}
  .package-check code{
    display:block;margin-top:10px;
    font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
    font-size:12px;line-height:1.6;color:var(--text);word-break:break-all;
  }
  .package-check .check-link{display:inline-block;margin-top:8px;font-size:13px}

  /* ---------- 步骤（编号行，与 TV 一致） ---------- */
  .steps{margin-top:40px}
  .steps ol{margin:0;padding:0;list-style:none;counter-reset:step}
  .steps ol li{counter-increment:step;border-top:1px solid var(--line);padding:20px 0 20px 44px;position:relative;max-width:760px;font-size:16px}
  .steps ol li:last-child{border-bottom:1px solid var(--line)}
  .steps ol li::before{
    content:counter(step);position:absolute;left:0;top:20px;
    width:28px;height:28px;border-radius:50%;border:1px solid var(--line);
    font-size:14px;font-weight:600;color:var(--muted);
    display:flex;align-items:center;justify-content:center}
  .steps ol li strong{font-weight:600}
  .steps ol li span{color:var(--muted);font-size:15px}

  /* ---------- 功能清单（两栏，与 TV 一致） ---------- */
  .feat{display:grid;grid-template-columns:1fr 1fr;column-gap:56px;border-bottom:1px solid var(--line)}
  .feat p{margin:0;padding:20px 0;border-top:1px solid var(--line);font-size:16px}
  .feat p strong{font-weight:600}

  /* ---------- 版本更新（内容由同步脚本整段生成，CSS 必须覆盖生成类名） ---------- */
  .section-heading{display:flex;align-items:flex-end;justify-content:space-between;gap:24px;flex-wrap:wrap}
  .section-heading .eyebrow{margin:0 0 4px;font-size:13px;letter-spacing:.12em;color:var(--faint)}
  .section-heading h2{margin:0}
  .filter-control{display:flex;align-items:center;gap:10px;font-size:14px;color:var(--muted);padding-bottom:6px}
  .filter-control select{
    background:#111;color:var(--text);border:1px solid var(--line);border-radius:8px;
    font:inherit;font-size:14px;padding:6px 10px;
  }
  .release-entry{border-top:1px solid var(--line)}
  .release-entry:last-child{border-bottom:1px solid var(--line)}
  .release-entry summary{
    display:flex;align-items:baseline;justify-content:space-between;gap:16px;
    padding:18px 0;cursor:pointer;list-style:none;font-size:17px;font-weight:600;
  }
  .release-entry summary::-webkit-details-marker{display:none}
  .release-entry summary::after{content:"›";color:var(--muted);transition:transform .2s ease;flex:none}
  .release-entry[open ] summary::after{transform:rotate(90deg)}
  .release-entry .release-date{font-size:14px;font-weight:400;color:var(--muted);white-space:nowrap}
  .release-content{padding:0 0 24px;font-size:15px;color:var(--muted)}
  .release-content p{margin:0 0 12px;max-width:760px}
  .release-content .release-platforms{font-size:14px}
  .release-content .release-links{font-size:14px}
  .release-content h4{margin:18px 0 8px;font-size:16px;color:var(--text)}
  .release-content ul{margin:0 0 12px;padding-left:20px}
  .release-content li{margin-bottom:6px}
  .release-content code{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:13px;color:var(--text);word-break:break-all}
  .release-content strong{color:var(--text)}
  .release-archive{margin-top:28px;border-top:1px solid var(--line)}
  .release-archive > summary{padding:18px 0;cursor:pointer;list-style:none;font-size:17px;font-weight:600}
  .release-archive > summary::-webkit-details-marker{display:none}
  .release-archive > summary span{font-size:14px;font-weight:400;color:var(--muted)}
  #release-empty{margin-top:20px}
  /* 全量重渲染模板的旧版更新说明格式（ol.feats），保留样式以防回退 */
  ol.feats{list-style:none;counter-reset:f;display:grid;gap:12px;margin:20px 0 0;padding:0}
  ol.feats > li{counter-increment:f;border:1px solid var(--line);border-radius:12px;
    padding:16px 18px 16px 56px;position:relative;overflow-wrap:anywhere}
  ol.feats > li::before{content:counter(f);position:absolute;left:16px;top:16px;
    width:26px;height:26px;border-radius:50%;border:1px solid var(--line);
    font-weight:700;font-size:14px;color:var(--muted);text-align:center;line-height:26px}
  ol.feats li b{display:block;font-size:15px;margin-bottom:2px}
  ol.feats li span{color:var(--muted);font-size:14px}
  ol.feats li ul{margin-top:6px;padding-left:18px;color:var(--muted);font-size:14px}
  ol.feats li ul li{border:none;border-radius:0;padding:0;position:static}
  ol.feats li ul li::before{content:none}

  /* ---------- 交流群（与 TV 一致） ---------- */
  .group-row{display:flex;align-items:baseline;gap:16px;flex-wrap:wrap;
    border-top:1px solid var(--line);padding:18px 0}
  .group-row:last-child{border-bottom:1px solid var(--line)}
  .group-row .name{font-size:17px;font-weight:600;min-width:150px}
  .group-row .num{font-size:15px;color:var(--muted)}
  .group-row a{margin-left:auto;font-size:15px}

  /* ---------- 捐赠区（纯静态内容，同步脚本不改写） ----------
     两张收款码已裁成同尺寸正方形、只留二维码本体；展示固定宽、
     两张均为正方形、展示尺寸一致。 */
  .donate-grid{display:flex;gap:32px;justify-content:center;flex-wrap:wrap;margin-top:36px;align-items:flex-start}
  .donate-card{margin:0;text-align:center}
  .donate-card img{display:block;width:260px;height:auto;border-radius:16px;
    border:1px solid var(--line);background:#fff}
  .donate-card figcaption{margin-top:14px;font-size:16px;font-weight:600}

  /* ---------- 页脚（与 TV 一致） ---------- */
  footer{margin-top:104px;padding:32px 0 64px}
  footer .inner{max-width:980px;margin:0 auto;padding:40px 24px 0;border-top:1px solid var(--line)}
  footer p{margin:0;font-size:14px;color:var(--muted);max-width:760px}
  footer p + p{margin-top:10px}
  footer .proj{font-size:15px;color:var(--text)}

  /* ---------- 减动效 ---------- */
  @media (prefers-reduced-motion:reduce){
    html{scroll-behavior:auto}
    .hero-el{animation:none;opacity:1;transform:none}
    .reveal{opacity:1 !important;transform:none !important;transition:none}
  }

  /* ---------- 手机 ---------- */
  @media (max-width:640px){
    .nav-links{gap:18px;font-size:14px}
    .hero{padding-top:96px}
    .hero .lead{font-size:18px}
    .hero .actions{gap:12px}
    .notice{margin-top:48px}
    section.util{margin-top:72px}
    section.util h2{font-size:26px}
    .dl-grid{grid-template-columns:1fr;gap:16px}
    .feat{grid-template-columns:1fr}
    .section-heading{flex-direction:column;align-items:flex-start;gap:12px}
    .release-entry summary{font-size:16px}
    .group-row a{margin-left:0;width:100%}
    .donate-card img{width:220px}
    footer{margin-top:72px}
  }
  @media (min-width:641px) and (max-width:900px){
    .dl-grid{grid-template-columns:repeat(2,1fr)}
  }
"""


# Page script from the approved preview: scroll-reveal animations and the
# changelog platform filter. The filter markup itself is generated by the
# platform patcher (sync_platform_packages.py patch_notes); this script
# only unhides and wires it, and no-ops when the section is absent.
PAGE_JS = """
  // 滚动揭示：元素进入视口时加 .in，依次淡入上浮
  (function () {
    var els = document.querySelectorAll('.reveal');
    if (!('IntersectionObserver' in window)) {
      els.forEach(function (el) { el.classList.add('in'); });
      return;
    }
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          entry.target.classList.add('in');
          io.unobserve(entry.target);
        }
      });
    }, { threshold: 0.15 });
    els.forEach(function (el) { io.observe(el); });
  })();

  // 版本更新按平台筛选：同步脚本生成的筛选器默认是隐藏的，
  // 这里启用它，按每条记录的 data-platforms 过滤。
  (function () {
    var sel = document.getElementById('release-platform');
    if (!sel) return;
    var label = sel.closest('label');
    if (label) label.hidden = false;
    var empty = document.getElementById('release-empty');
    var archive = document.querySelector('.release-archive');
    sel.addEventListener('change', function () {
      var v = sel.value, any = false, anyArchive = false;
      document.querySelectorAll('.release-entry').forEach(function (el) {
        var show = v === 'all' || el.getAttribute('data-platforms').split(' ').indexOf(v) !== -1;
        el.style.display = show ? '' : 'none';
        if (show) {
          any = true;
          if (archive && archive.contains(el)) anyArchive = true;
        }
      });
      if (archive) archive.style.display = (v === 'all' || anyArchive) ? '' : 'none';
      if (empty) empty.hidden = any;
    });
  })();
"""


NOSCRIPT_BLOCK = """<noscript><style>
  .hero-el{animation:none;opacity:1;transform:none}
  .reveal{opacity:1 !important;transform:none !important;transition:none}
</style></noscript>"""



def load_quark_links(path=None):
    """Return {platform key: share URL} from scripts/quark.json, or {}."""
    manifest = Path(path) if path else QUARK_MANIFEST
    if not manifest.exists():
        return {}
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {}
    return {k: v.get("share_url") for k, v in data.items()
            if isinstance(v, dict) and v.get("share_url")}


def quark_key_for_asset(name):
    """Map a release asset filename to its Quark manifest key, or None."""
    for suffix, key in (
            ("-mobile.apk", "android-mobile"),
            ("-ios-unsigned.ipa", "ios"),
            ("-windows-x64-setup.exe", "windows-setup"),
            ("-windows-setup.exe", "windows-setup"),
            ("-windows-x64-portable.zip", "windows-zip"),
            ("-windows-x64.zip", "windows-zip"),
            ("-macos.zip", "macos"),
            ("-lite.apk", "android-lite")):
        if name.endswith(suffix):
            return key
    return None


def quark_button(key, links):
    """A Quark download button for one card, or '' when no link exists yet."""
    url = links.get(key) if links else None
    if not url:
        return ""
    return (f' <a class="btn" href="{html.escape(url, quote=True)}" '
            f'target="_blank" rel="noopener">下载</a>')


def platform_feed_override(output, key):
    """Return (href, size, sha256, version) from output/updates/<platform>.json if present."""
    mapping = {
        "android-tv": ("android-tv", ".apk"),
        "android-mobile": ("android-mobile", ".apk"),
        "ios": ("ios", ".ipa"),
        "windows-setup": ("windows", "-setup.exe"),
        "windows-zip": ("windows", ".zip"),
        "macos": ("macos", ".zip"),
        "android-lite": ("android-lite", ".apk"),
    }
    if key not in mapping:
        return None
    feed_name, suffix = mapping[key]
    updates = Path(output) / "updates"
    path = updates / f"{feed_name}.json"
    if not path.exists():
        path = updates / f"{feed_name}-preview.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        ver = data.get("versionName") or data.get("version")
        single = data.get("package") or {}
        if single.get("url") and single.get("size") and single.get("sha256"):
            return single["url"], single["size"], single["sha256"], ver
        packages = data.get("packages") or {}
        candidates = [n for n in packages if n.endswith(suffix)]
        if not candidates:
            return None
        candidates.sort(key=lambda n: ("x64" not in n, "portable" not in n, n))
        info = packages[candidates[0]]
        if info.get("url") and info.get("size") and info.get("sha256"):
            return info["url"], info["size"], info["sha256"], ver
    except (ValueError, OSError, KeyError, TypeError):
        return None
    return None


def fetch(url, limit=LIMIT):
    headers = {'User-Agent': 'MarcoMovie-Mirror', 'Accept-Encoding': 'identity'}
    if url.startswith('https://api.github.com/') and os.environ.get('GITHUB_TOKEN'):
        headers['Authorization'] = 'Bearer ' + os.environ['GITHUB_TOKEN']
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=60) as response:
        data = response.read(limit + 1)
    if len(data) > limit:
        raise ValueError('Download exceeds limit')
    return data


def fetch_stars():
    """Live star count from the repo API; None when it cannot be read."""
    try:
        repo = json.loads(fetch(f'https://api.github.com/repos/{REPO}'))
        count = int(repo['stargazers_count'])
    except (ValueError, OSError, KeyError, TypeError):
        return None
    return count if count > 0 else None


def _previous_stars(output):
    page = output / 'index.html'
    try:
        text = page.read_text(encoding='utf-8')
    except OSError:
        return None
    match = re.search(r'<b>(\d+) Stars</b>', text)
    return int(match.group(1)) if match else None


def apk_identity(apk, *, lite=False):
    """Read literal package/version/minSdk from the actual binary APK manifest."""
    with zipfile.ZipFile(io.BytesIO(apk)) as z:
        entry = z.getinfo('AndroidManifest.xml')
        if entry.file_size > 1024 * 1024:
            raise ValueError('Manifest too large')
        data = z.read(entry)
    if struct.unpack_from('<H', data)[0] != 3:
        raise ValueError('Expected binary Android manifest')
    strings, values, editions, elements = [], {}, [], []
    offset = 8
    while offset < len(data):
        kind, header, size = struct.unpack_from('<HHI', data, offset)
        if size < header or header < 8 or offset + size > len(data):
            raise ValueError('Invalid XML chunk')
        if kind == 1:
            count, _, flags, start = struct.unpack_from('<IIII', data, offset + 8)
            if count > 65536 or header + count * 4 > size:
                raise ValueError('Invalid string pool')
            for i in range(count):
                pos = offset + start + struct.unpack_from('<I', data, offset + header + 4 * i)[0]
                if flags & 256:
                    def length8(p):
                        n = data[p]
                        return (((n & 127) << 8) | data[p + 1], p + 2) if n & 128 else (n, p + 1)
                    _, pos = length8(pos)
                    length, pos = length8(pos)
                    strings.append(data[pos:pos + length].decode('utf-8'))
                else:
                    length = struct.unpack_from('<H', data, pos)[0]; pos += 2
                    if length & 32768:
                        length = ((length & 32767) << 16) | struct.unpack_from('<H', data, pos)[0]; pos += 2
                    strings.append(data[pos:pos + length * 2].decode('utf-16le'))
        elif kind == 0x102:
            name = strings[struct.unpack_from('<I', data, offset + 20)[0]]
            start, stride, count = struct.unpack_from('<HHH', data, offset + 24)
            if stride < 20 or 16 + start + stride * count > size:
                raise ValueError('Invalid attributes')
            if name in ('manifest', 'uses-sdk', 'meta-data'):
                attributes = {}
                for i in range(count):
                    pos = offset + 16 + start + i * stride
                    _, key, raw, _, _, value_type, value = struct.unpack_from('<IIIHBBI', data, pos)
                    attributes[strings[key]] = strings[raw] if raw != 0xffffffff else strings[value] if value_type == 3 else value
                    values[(name, strings[key])] = attributes[strings[key]]
                if name == 'meta-data' and elements == ['manifest', 'application'] and attributes.get('name') == 'com.pilipala.marcomovie.EDITION':
                    editions.append(attributes.get('value'))
            elements.append(name)
        elif kind == 0x103:
            name = strings[struct.unpack_from('<I', data, offset + 20)[0]]
            if not elements or elements.pop() != name:
                raise ValueError('Unbalanced Android manifest')
        offset += size
    result = {'package': values[('manifest', 'package')], 'versionName': values[('manifest', 'versionName')],
              'versionCode': int(values[('manifest', 'versionCode')]), 'minSdk': int(values[('uses-sdk', 'minSdkVersion')])}
    expected_package = 'com.pilipala.marcomovie.lite' if lite else 'com.pilipala.marcomovie'
    minimum_sdk = 14 if lite else 23
    if result['package'] != expected_package or result['minSdk'] < minimum_sdk or result['versionCode'] <= 0:
        raise ValueError('Wrong application identity')
    if lite:
        if editions:
            raise ValueError('Lite package must not claim a standard edition')
        result['edition'] = 'lite'
    if editions:
        if len(editions) != 1 or editions[0] not in ('tv', 'mobile'):
            raise ValueError('Invalid application edition')
        result['edition'] = editions[0]
    return result


def choose(releases):
    valid = [r for r in releases if not r.get('draft') and r.get('published_at')
             and re.fullmatch(r'v\d+\.\d+\.\d+-preview', r.get('tag_name', ''))]
    if not valid:
        raise ValueError('No published preview release')
    return max(valid, key=lambda r: tuple(map(int, r['tag_name'][1:-8].split('.'))))


def _plain_md(text):
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    text = re.sub(r'`([^`]+)`', r'\1', text)
    return text.strip()

def _linkify_md(text):
    """Escape text, turning [label](https://...) into a real link.

    Only links to the project's own GitHub repo and the mirror domain are
    linked; anything else stays plain text, so a release note can never
    inject an arbitrary link. Without this, a long bare URL is one
    unbreakable token that forces the page wider than a phone screen.
    Mirror package files are never linked either: the mirror hosts them
    for the in-app update feeds, and manual downloads go through GitHub
    or Quark, so a changelog link to a mirror APK/IPA/ZIP/EXE stays
    plain text.
    """
    parts = []
    last = 0
    for m in re.finditer(r'\[([^\]]+)\]\((https://[^)\s]+)\)', text):
        url = m.group(2)
        if not (url.startswith('https://github.com/Pilipala9919/') or
                url.startswith('https://marcotv.wlj9919.top/')):
            continue
        bare = url.split('?')[0].split('#')[0].lower()
        if url.startswith('https://marcotv.wlj9919.top/') and bare.endswith(('.apk', '.ipa', '.zip', '.exe')):
            continue
        parts.append(html.escape(text[last:m.start()]))
        parts.append('<a href="' + html.escape(url, quote=True) + '">' +
                     html.escape(m.group(1)) + '</a>')
        last = m.end()
    parts.append(html.escape(text[last:]))
    return ''.join(parts)


def render_changelog(notes):
    """Render a release body as a numbered list; fall back to escaped <pre> text.

    Release bodies are Markdown like "### Marco Movie 0.4.36 ..." followed by
    numbered items with a bold title and "- " sub-bullets. Anything that does
    not parse as numbered items is shown escaped, never as raw HTML.
    """
    items = []
    current = None
    for raw_line in (notes or '').splitlines():
        line = raw_line.strip().lstrip('\ufeff')
        if not line or line.startswith('#'):
            continue
        numbered = re.match(r'(\d+)\.\s+(.*)$', line)
        if numbered:
            current = {'title': _plain_md(numbered.group(2)).rstrip(':：'), 'points': []}
            items.append(current)
            continue
        if line.startswith('- ') and current is not None:
            current['points'].append(_plain_md(line[2:]))
            continue
        if current is not None and current['points']:
            current['points'][-1] += ' ' + _plain_md(line)
        elif current is not None:
            current['title'] += ' ' + _plain_md(line)
    if not items:
        return '<pre>' + html.escape(notes or '') + '</pre>'
    parts = ['<ol class="feats">']
    for item in items:
        parts.append('<li><b>' + _linkify_md(item['title']) + '</b>')
        if item['points']:
            parts.append('<ul>' + ''.join('<li>' + _linkify_md(point) + '</li>'
                                          for point in item['points']) + '</ul>')
        parts.append('</li>')
    parts.append('</ol>')
    return ''.join(parts)


def asset(release, name, output, limit=LIMIT):
    matches = [a for a in release['assets'] if a['name'] == name and a['state'] == 'uploaded']
    if len(matches) != 1:
        raise ValueError('Missing or duplicate asset: ' + name)
    info = matches[0]
    expected = f'https://github.com/{REPO}/releases/download/{release["tag_name"]}/{name}'
    if info['browser_download_url'] != expected or not 0 < info['size'] <= limit:
        raise ValueError('Unexpected asset URL or size')
    sha_url = expected + '.sha256'
    checksums = [a for a in release['assets'] if a['name'] == name + '.sha256' and a['state'] == 'uploaded' and a['browser_download_url'] == sha_url]
    if len(checksums) != 1:
        raise ValueError('Missing official checksum')
    local_sha = output / (name + '.sha256')
    if local_sha.exists():
        raw_sha = local_sha.read_bytes()
    else:
        try:
            raw_sha = fetch(sha_url, 4096)
        except urllib.error.HTTPError:
            if (info.get('digest') or '').startswith('sha256:'):
                raw_sha = f"{info['digest'][7:]}  {name}\n".encode('ascii')
            else:
                raise
    checksum = raw_sha.decode('ascii').strip().split()
    if len(checksum) != 2 or checksum[1].lstrip('*') != name or not re.fullmatch('[0-9a-f]{64}', checksum[0]):
        raise ValueError('Invalid checksum file')
    local = output / name
    body = local.read_bytes() if local.exists() else fetch(expected, limit)
    digest = hashlib.sha256(body).hexdigest()
    if len(body) != info['size'] or digest != checksum[0] or info.get('digest') not in (None, 'sha256:' + digest):
        raise ValueError('Release digest mismatch: ' + name)
    return body, digest


def platform_asset(release, name, output):
    """Return (href, size, sha256, body-or-None). Large packages stay on GitHub, never on Pages."""
    info = [a for a in release['assets'] if a['name'] == name and a['state'] == 'uploaded']
    if len(info) != 1:
        raise ValueError('Missing or duplicate asset: ' + name)
    size = info[0]['size']
    if size <= LIMIT:
        body, digest = asset(release, name, output)
        return name, size, digest, body
    expected = f'https://github.com/{REPO}/releases/download/{release["tag_name"]}/{name}'
    if info[0]['browser_download_url'] != expected or size > PLATFORM_LIMIT:
        raise ValueError('Unexpected asset URL or size')
    sha_url = expected + '.sha256'
    if len([a for a in release['assets'] if a['name'] == name + '.sha256' and a['state'] == 'uploaded'
            and a['browser_download_url'] == sha_url]) != 1:
        raise ValueError('Missing official checksum')
    local_sha = output / (name + '.sha256')
    if local_sha.exists():
        raw_sha = local_sha.read_bytes()
    else:
        try:
            raw_sha = fetch(sha_url, 4096)
        except urllib.error.HTTPError:
            if (info[0].get('digest') or '').startswith('sha256:'):
                raw_sha = f"{info[0]['digest'][7:]}  {name}\n".encode('ascii')
            else:
                raise
    checksum = raw_sha.decode('ascii').strip().split()
    if len(checksum) != 2 or checksum[1].lstrip('*') != name or not re.fullmatch('[0-9a-f]{64}', checksum[0]):
        raise ValueError('Invalid checksum file')
    if info[0].get('digest') not in (None, 'sha256:' + checksum[0]):
        raise ValueError('Release digest mismatch: ' + name)
    return expected, size, checksum[0], None


def sync(output):
    release = choose(json.loads(fetch(f'https://api.github.com/repos/{REPO}/releases?per_page=100', 4 * 1024 * 1024)))
    version = release['tag_name'][1:-8]
    release_tag = release['tag_name']
    published_date = (release.get('published_at') or '')[:10]
    stars = fetch_stars() or _previous_stars(output) or STARS_FALLBACK
    apk_name, source_name = f'MarcoMovie-{version}-preview.apk', f'MarcoMovie-{version}-source.zip'
    # Page buttons always point at GitHub (plus Quark); the mirror files are
    # still hosted in the repo for the in-app update feeds and the edge proxy.
    def _gh(name):
        return f'https://github.com/{REPO}/releases/download/{release_tag}/{name}'
    cached_prev = None
    if not (output / apk_name).exists() and (output / 'updates/preview.json').exists():
        try:
            cand = json.loads((output / 'updates/preview.json').read_text(encoding='utf-8'))
            if cand.get('versionName') == version and cand.get('size', 0) > LIMIT:
                cached_prev = cand
        except (ValueError, OSError):
            pass
    if cached_prev is not None:
        apk = None
        apk_size = cached_prev['size']
        sha = cached_prev['sha256']
        identity = {
            'versionCode': cached_prev['versionCode'],
            'versionName': cached_prev['versionName'],
            'minSdk': cached_prev['minSdk'],
        }
    else:
        apk, sha = asset(release, apk_name, output, limit=PLATFORM_LIMIT)
        apk_size = len(apk)
        identity = apk_identity(apk)
    apk_href = apk_name if apk_size <= LIMIT else f'https://github.com/{REPO}/releases/download/{release_tag}/{apk_name}'
    source, source_sha = asset(release, source_name, output)
    platforms = []
    for pattern, label, note in PLATFORMS:
        name = pattern.format(version=version)
        if any(a['name'] == name for a in release['assets']):
            href, size, digest, body = platform_asset(release, name, output)
            platforms.append((name, label, note, href, size, digest, body))
    if identity['versionName'] != version:
        raise ValueError('APK version does not match release')
    with zipfile.ZipFile(io.BytesIO(source)) as archive:
        if archive.testzip() is not None:
            raise ValueError('Source ZIP failed CRC')
        license_text = archive.read(f'MarcoMovie-{version}/LICENSE')
        notice = archive.read(f'MarcoMovie-{version}/NOTICE')
    feed = dict(schema=1, versionCode=identity['versionCode'], versionName=version, minSdk=identity['minSdk'],
                size=apk_size, sha256=sha, url=apk_href if apk_href.startswith('https://') else BASE + apk_name,
                prerelease=bool(release.get('prerelease',True)), notes=(release.get('body') or '')[:8000])
    for name, _, _, href, size, digest, _ in platforms:
        for suffix, key in (('-mobile.apk','mobile'),('-windows-setup.exe','windows')):
            if name == f'MarcoMovie-{version}{suffix}':
                feed[key] = dict(size=size, sha256=digest, url=href if href.startswith('https://') else BASE + name)
    feed_path = output / 'updates/preview.json'
    feed_paths = [feed_path] + ([] if feed['prerelease'] else [output/'updates/stable.json'])
    for channel in feed_paths:
        if channel.exists():
            previous = json.loads(channel.read_text(encoding='utf-8'))
            if previous['versionCode'] > feed['versionCode']:
                raise ValueError('Refusing to roll the mirror back')
            if previous['versionCode'] == feed['versionCode'] and previous['sha256'] != sha:
                raise ValueError('Refusing to replace a published version')
    escaped = html.escape
    quark_links = load_quark_links()
    tv_override = platform_feed_override(output, "android-tv")
    tv_card_href, tv_card_size, tv_card_sha, tv_card_ver = tv_override or (_gh(apk_name), apk_size, sha, None)
    # 2026-11-22 layout: the version always shows in the card's
    # package-version span (the override version, else this release);
    # the hero has no download buttons, so the old tv_button /
    # mobile_button shortcuts are gone.
    def _card(platform_key, label, note, href, size, sha256, ver):
        # Card markup is the patcher contract (sync_platform_packages.py
        # patch_card): one <div class="dl"> per card, no nested divs,
        # exactly one "N MB", one SHA-256, one .sha256 checksum link
        # carrying the package filename, and the version in the
        # package-version span.
        button = quark_button(platform_key, quark_links)
        button_line = f'        {button.strip()}\n' if button else ''
        return (
            f'      <div class="dl" data-platform="{platform_key}">\n'
            f'        <h3>{escaped(label)} <!-- 状态标签：新版发布后、同步完成前，手动填入「待同步」 --><span class="card-status"></span></h3>\n'
            f'        <p class="card-meta"><span class="package-version">{escaped(ver)}</span> · {size/1024/1024:.1f} MB</p>\n'
            f'        <p class="card-note">{escaped(note)}</p>\n'
            f'{button_line}'
            f'        <details class="package-check"><summary>校验</summary><code>SHA-256：{sha256}</code><a class="check-link" href="{escaped(href)}.sha256" target="_blank" rel="noopener">校验文件</a></details>\n'
            '      </div>\n')
    download_cards = [_card('android-tv', 'Android 电视版',
                            'Android 6.0+ 电视 / 盒子 / 投影仪大屏专享版 · ARM 32 位（内置 FFmpeg / AV1 / VP9 扩展）',
                            tv_card_href, tv_card_size, tv_card_sha, tv_card_ver or version)]
    for name, label, note, href, size, digest, body in platforms:
        qkey = quark_key_for_asset(name)
        p_override = platform_feed_override(output, qkey)
        c_href, c_size, c_digest, c_ver = p_override or (_gh(name), size, digest, None)
        download_cards.append(_card(qkey, label, note, c_href, c_size, c_digest, c_ver or version))
    if platforms:
        platforms_note = ('<p class="intro wide reveal" style="--d:0.2s"><strong style="color:var(--text)">全平台独立更新</strong> · '
                          '覆盖 Android、Apple TV（tvOS）、HarmonyOS NEXT、iOS / iPadOS、Windows 与 macOS；'
                          '云端自动构建校验，最低系统声明不代替每台设备实机验证。</p>')
        fallback_link = ''
    else:
        platforms_note = ''
        fallback_link = (f'<div class="reveal" style="margin-top:28px"><a class="btn btn-ghost" '
                         f'href="https://github.com/{REPO}/releases/tag/{release_tag}">'
                         'Windows / macOS / iOS 多平台下载</a></div>')
    changelog = render_changelog(feed['notes'])
    groups = [
        ('Marco！', QQ_GROUP_CODE, QQ_GROUP_URL),
        ('Marco！1', QQ_GROUP2_CODE, QQ_GROUP2_URL),
        ('Marco！2', QQ_GROUP3_CODE, QQ_GROUP3_URL),
        ('Marco！3', QQ_GROUP4_CODE, QQ_GROUP4_URL),
        ('Marco！4', QQ_GROUP5_CODE, QQ_GROUP5_URL),
        ('Marco！5', QQ_GROUP6_CODE, QQ_GROUP6_URL),
        ('Marco！6', QQ_GROUP7_CODE, QQ_GROUP7_URL),
        ('Marco！7', QQ_GROUP8_CODE, QQ_GROUP8_URL),
    ]
    group_rows = ''.join(
        '    <div class="group-row reveal">\n'
        f'      <span class="name">官方交流群 {i}\ufe0f\u20e3：{name}</span><span class="num">群号 {code}</span>\n'
        f'      <a href="{escaped(url)}" target="_blank" rel="noopener">加入 QQ 群</a>\n'
        '    </div>\n'
        for i, (name, code, url) in enumerate(groups, 1))
    page = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Marco Movie · 多端自适应播放器 · Pilipala</title>
<meta name="description" content="Marco Movie 是 Pilipala 开发的免费开源多端播放器：Android 电视、手机、iOS、Apple TV、HarmonyOS、Windows、macOS 各端独立适配。本站为镜像站，最新版以 GitHub Releases 为准。">
<link rel="icon" type="image/png" href="/assets/movie-icon-512.png">
<link rel="apple-touch-icon" href="/assets/movie-icon-512.png">
<style>{PAGE_CSS}</style>
{NOSCRIPT_BLOCK}
</head>
<body>

<nav>
  <div class="nav-inner">
    <a class="nav-brand" href="/"><img src="/assets/marco-symbol.png" alt="" width="22" height="22">Marco</a>
    <div class="nav-links">
      <a href="/tv/">Marco TV</a>
      <span class="current">Marco Movie</span>
      <a href="https://github.com/{REPO}" target="_blank" rel="noopener">GitHub</a>
    </div>
  </div>
</nav>

<header class="hero">
  <h1 class="hero-el" style="--d:0s"><img class="hero-wordmark" src="assets/movie-wordmark-dark.png" alt="Marco Movie" width="1872" height="422"></h1>
  <p class="lead hero-el" style="--d:0.1s">支持 Android 电视大屏遥控、手机与平板 64 位专属触控，Apple TV（tvOS 16.0+）、HarmonyOS NEXT（纯血鸿蒙手机 / 平板 / 智慧屏），以及 Windows / macOS / iOS（iOS 14.0+ 巨魔与自签）多端独立适配的开源播放器。</p>
  <div class="actions hero-el" style="--d:0.2s">
    <a class="textlink" href="#download">全部平台</a>
    <a class="textlink" href="#group">交流群</a>
    <a class="textlink" href="#donate">捐赠支持</a>
  </div>
  <p class="meta hero-el" style="--d:0.3s"><b>{stars} Stars</b> · GPL-3.0-only · 作者 Pilipala</p>
  <p class="free hero-el" style="--d:0.4s">本软件免费开源。如果你付费购买了本软件，请尽快向购买平台申请退款。</p>
</header>

<p class="notice reveal">本产品仅为工具，不内置、不提供、不托管任何影视资源或配置地址。内容与配置请自行合法获取，数据保存在本机。</p>

<main>
  <section class="util" id="download">
    <h2 class="reveal">下载与安装</h2>
    <p class="intro reveal" style="--d:0.1s">安装包同时托管在本站镜像；点击下载将跳转至夸克网盘。校验值以 GitHub Release 为准。</p>
    {platforms_note}
    <div class="dl-grid reveal" style="--d:0.3s">
{''.join(download_cards)}
    </div>
    {fallback_link}
    <div class="steps reveal">
      <ol>
        <li><strong>下载核对</strong><br><span>按设备选对应安装包，下载后核对 SHA-256 再安装。</span></li>
        <li><strong>安装</strong><br><span>Android 电视 / 手机直接安装；Apple TV 自签或巨魔安装 IPA；鸿蒙 NEXT 签名安装 HAP；Windows 运行向导或解压；macOS 拖入应用程序。</span></li>
        <li><strong>导入配置</strong><br><span>按应用内提示导入自己的配置，自行合法获取内容与配置。</span></li>
      </ol>
    </div>
  </section>

  <!-- 捐赠区：纯静态内容，同步脚本不改写。 -->
  <section class="util reveal" id="donate">
    <h2>捐赠支持</h2>
    <p class="intro">MarcoMovie 完全免费开源，捐赠全凭自愿，不影响任何功能。感谢你的支持。</p>
    <div class="donate-grid">
      <figure class="donate-card">
        <img src="/assets/donate-wechat.jpg" alt="微信捐赠收款码" width="260" height="260">
        <figcaption>微信收款码</figcaption>
      </figure>
      <figure class="donate-card">
        <img src="/assets/donate-alipay.jpg" alt="支付宝捐赠收款码" width="260" height="260">
        <figcaption>支付宝收款码</figcaption>
      </figure>
    </div>
  </section>

  <section class="util" id="features">
    <h2 class="reveal">文字介绍与功能</h2>
    <p class="intro reveal" style="--d:0.1s">覆盖六大系统生态，按大屏遥控器、移动触屏与桌面键鼠分别原生适配，互通同步与备份。</p>
    <div class="feat reveal" style="--d:0.2s">
      <p><strong>Android 电视端：</strong>专为遥控器与 10 英尺大屏打造：5–8 列 2:3 海报墙、右侧悬浮图标 Dock、内置遥控全拼 / 首拼搜索、左固定海报 + 右独立滚动选集、小屏返回续播、DLNA 投屏接收与局域网扫码导入配置。</p>
      <p><strong>Android 手机 / 平板端：</strong>完全独立的移动端触控 UI：支持滑动切换的玻璃 Dock、横竖屏自适应导航，保留系统状态栏、去除遥控白框；首页直接支持剪贴板一键粘贴与原生输入法导入；支持 50 集分组触控选集与全屏横屏手势播放。</p>
      <p><strong>Apple TV（tvOS）端：</strong>原生 SwiftUI + AVKit 大屏客户端（tvOS 16.0+）：适配 Siri Remote 焦点引擎与顶部导航，内嵌 QuickJS-NG 脚本宿主，支持 4K / 杜比视界 / HDR10 画质识别、多音轨与内封字幕切换、四盘扫码登录、6 路并发分片代理及局域网 / WebDAV 同步。</p>
      <p><strong>HarmonyOS NEXT（鸿蒙）端：</strong>纯血鸿蒙通用客户端（API 12+）：手机、平板 / 2in1 与鸿蒙智慧屏单包自适应（智慧屏自动切换 10 英尺遥控焦点界面）；封装原生 ArkTS AVPlayer + XComponent GPU 硬件纹理播放、系统安全凭据存储、四盘扫码 + 6 路分片代理及全端同步备份互通。</p>
      <p><strong>iPhone / iPad（iOS）端：</strong>适配 iOS / iPadOS 14.0+（支持巨魔与自签安装）：独立竖屏触控与平板侧栏布局、全屏手势与防误触锁屏、本机脚本宿主、4K 网盘双通道登录与 6 路并发分片代理、WebDAV 及 JSON 备份导入导出。</p>
      <p><strong>Windows 与 macOS 桌面端：</strong>覆盖 Windows x64（安装向导与绿色便携包）及 macOS 桌面端：柔光沉浸式导航、内置 libmpv 硬件加速播放内核、键鼠滚轮快捷键、离线下载与全平台 marco-movie-sync v2 网络同步互通。</p>
    </div>
  </section>

  <section class="util" id="changelog">
    <h2 class="reveal">版本特性 · {version}</h2>
    <p class="intro reveal" style="--d:0.1s">{published_date} 发布 · 更新内容来自 GitHub Release 原文，改写为列表。</p>
{changelog}
  </section>

  <section class="util" id="group">
    <h2 class="reveal">官方交流群</h2>
    <p class="intro reveal" style="--d:0.1s">通用群，不分软件，Marco TV 和 Marco Movie 都可以在这里交流。点开会跳到 QQ 加群。</p>
{group_rows}
  </section>
</main>

<footer>
  <div class="inner">
    <p class="proj">原项目：<a href="https://github.com/{REPO}" target="_blank" rel="noopener">Pilipala9919 / MarcoMovie</a> · 协议 GPL-3.0-only · 版权 © 2026 Pilipala</p>
    <p>本站为镜像站，只做展示和下载中转，方便国内访问；最新版本、问题反馈和源码以 GitHub 原仓库为准。</p>
    <p>作者：Pilipala · <a href="LICENSE">GPL-3.0-only</a> · <a href="NOTICE">署名与许可</a> · <a href="https://github.com/{REPO}/blob/main/docs/USER_GUIDE.md">使用指南</a> · <a href="/tv/">Marco TV</a></p>
  </div>
</footer>

<script>{PAGE_JS}</script>

</body>
</html>'''
    files = {apk_name + '.sha256': (sha + '  ' + apk_name + '\n').encode(),
             source_name: source, source_name + '.sha256': (source_sha + '  ' + source_name + '\n').encode(),
             'LICENSE': license_text, 'NOTICE': notice, 'index.html': page.encode()}
    if apk is not None and len(apk) <= LIMIT:
        files[apk_name] = apk
    for name, _, _, _, _, digest, body in platforms:
        if body is None:
            continue
        files[name] = body
        files[name + '.sha256'] = (digest + '  ' + name + '\n').encode()
    # Versions are immutable and written before the channel pointer; Git/Pages publishes one complete snapshot.
    output.mkdir(parents=True, exist_ok=True)
    for name, data in files.items():
        target = output / name
        if target.exists() and target.suffix in ('.apk', '.zip', '.ipa') and target.read_bytes() != data:
            raise ValueError('Immutable asset already differs')
        target.write_bytes(data)
    for channel in feed_paths:
        channel.parent.mkdir(exist_ok=True)
        temporary = channel.with_suffix('.tmp')
        temporary.write_text(json.dumps(feed, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
        temporary.replace(channel)
    print(f'Synced {version}: {apk_size} bytes, SHA-256 {sha}; deployment must be verified separately.')
    return feed


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    sync(args.output)

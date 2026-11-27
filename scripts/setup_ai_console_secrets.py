#!/usr/bin/env python3
"""Offline helper to generate Cloudflare Pages Encrypted Secrets for /ai-console/.

Generates:
  1. AI_LAB_ADMIN_PASSWORD_HASH (PBKDF2-SHA256, 100,000 iterations — CF Workers compatible)
  2. AI_LAB_TOTP_SECRET (160-bit RFC 4648 Base32 secret + otpauth:// URI for Apple Passwords / Google Authenticator)
  3. Verifies local private/ai-lab-ed25519.key format without printing the key unless requested.

Zero third-party dependencies. Never writes secrets into tracked repo files.
"""

from __future__ import annotations

import argparse
import base64
import getpass
import hashlib
import os
import secrets
import urllib.parse
from pathlib import Path

PBKDF2_ITERATIONS = 100_000


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def hash_password_pbkdf2(password: str, *, salt: bytes | None = None) -> str:
    if len(password) < 12:
        raise ValueError("管理员密码长度建议至少 12 位（包含字母与数字/符号）")
    raw_salt = salt if salt is not None else os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), raw_salt, PBKDF2_ITERATIONS, dklen=32)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${_b64url(raw_salt)}${_b64url(dk)}"


def generate_totp_secret() -> str:
    # 20 bytes = 160 bits -> 32 Base32 characters (standard RFC 6238).
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def build_otpauth_uri(secret_b32: str, *, issuer: str = "Marco AI Console", account: str = "admin@marcotv") -> str:
    label = urllib.parse.quote(f"{issuer}:{account}", safe="")
    params = urllib.parse.urlencode({
        "secret": secret_b32,
        "issuer": issuer,
        "algorithm": "SHA1",
        "digits": "6",
        "period": "30",
    })
    return f"otpauth://totp/{label}?{params}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate Cloudflare Pages Secrets for Marco AI Console")
    parser.add_argument("--issuer", default="Marco AI Console", help="TOTP Authenticator display name")
    parser.add_argument("--account", default="admin@marcotv", help="TOTP account label")
    parser.add_argument("--key-file", default="", help="Optional path to ai-lab-ed25519.key to validate format")
    args = parser.parse_args()

    print("=== Marco AI Console · Cloudflare 加密环境变量生成向导 ===\n")
    pw1 = getpass.getpass("1) 请设置后台管理员强密码（至少 12 位，输入不可见）：")
    pw2 = getpass.getpass("   请再次输入确认密码：")
    if pw1 != pw2:
        print("错误：两次输入的密码不一致。")
        return 1
    try:
        pw_hash = hash_password_pbkdf2(pw1)
    except ValueError as exc:
        print(f"错误：{exc}")
        return 1

    totp_secret = generate_totp_secret()
    otpauth = build_otpauth_uri(totp_secret, issuer=args.issuer, account=args.account)

    print("\n=== 请将以下 3 项逐一填入 Cloudflare Pages → Settings → Variables and Secrets（全部勾选 Encrypt）===\n")
    print("变量名 1: AI_LAB_ED25519_KEY")
    if args.key_file:
        p = Path(args.key_file)
        if p.is_file():
            raw = "".join(
                ln.strip() for ln in p.read_text(encoding="utf-8").splitlines()
                if ln.strip() and not ln.lstrip().startswith("#")
            )
            ok = len(raw) == 64 and all(c in "0123456789abcdefABCDEF" for c in raw)
            print(f"  -> 已校验私钥文件 {p}（格式{'有效 · 64位Hex' if ok else '无效！'}），请直接复制其 64 位内容填入")
        else:
            print(f"  -> 未找到 {p}，请复制本机 private/ai-lab-ed25519.key 的 64 位十六进制内容填入")
    else:
        print("  -> 复制本机 private/ai-lab-ed25519.key 里的 64 位十六进制内容填入")

    print("\n变量名 2: AI_LAB_ADMIN_PASSWORD_HASH")
    print(f"  {pw_hash}")

    print("\n变量名 3: AI_LAB_TOTP_SECRET")
    print(f"  {totp_secret}")

    print("\n=== 手机验证器绑定信息（Apple 密码 / Google Authenticator / 1Password）===")
    print(f"  手动输入密钥（Base32）：{totp_secret}")
    print(f"  标准 otpauth URI：{otpauth}")
    print("\n提示：配置完上述 3 项加密变量并重新部署后，访问 https://marcotv.wlj9919.top/ai-console/ 即可使用。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

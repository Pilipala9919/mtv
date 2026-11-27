// Copyright (C) 2026 Pilipala
// SPDX-License-Identifier: GPL-3.0-only
//
// End-to-end cryptographic, protocol, and HTTP security tests for /api/ai-console/.
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

import {
  OFFICIAL_PUBKEY_HEX,
  base32Decode,
  bytesToHex,
  ed25519PublicKeyFromSeed,
  ed25519Sign,
  ed25519Verify,
  generateTotpCode,
  handle,
  hashPasswordPbkdf2,
  hexToBytes,
  issueAiLabToken,
  resetRuntimeGuardsForTest,
  verifyAiLabToken,
  verifyAdminPassword,
  verifyTotp,
} from '../functions/api/ai-console/_handler.mjs';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(__dirname, '..');

function makeReq(urlPath, { method = 'GET', body, cookie, origin = 'https://marcotv.wlj9919.top', csrf = true, ip = '203.0.113.10', contentType = 'application/json' } = {}) {
  const headers = new Headers();
  if (origin !== null) headers.set('Origin', origin);
  if (csrf) headers.set('X-Requested-With', 'MarcoAiConsole');
  if (cookie) headers.set('Cookie', cookie);
  if (ip) headers.set('CF-Connecting-IP', ip);
  if (body !== undefined && contentType) headers.set('Content-Type', contentType);
  return new Request(`https://marcotv.wlj9919.top${urlPath}`, {
    method,
    headers,
    body: body === undefined ? undefined : (typeof body === 'string' ? body : JSON.stringify(body)),
  });
}

// 1. Static CSP & safety checks on /ai-console/ assets.
{
  const html = await readFile(path.join(REPO_ROOT, 'ai-console/index.html'), 'utf8');
  const js = await readFile(path.join(REPO_ROOT, 'ai-console/app.js'), 'utf8');
  const headersFile = await readFile(path.join(REPO_ROOT, '_headers'), 'utf8');
  assert.doesNotMatch(html, /<script(?![^>]*src=)/i, 'index.html must not contain inline scripts');
  assert.doesNotMatch(html, /\son[a-z]+\s*=/i, 'index.html must not contain inline event handlers');
  assert.match(html, /noindex,\s*nofollow/i, 'index.html must include noindex robots meta');
  assert.doesNotMatch(js, /\.innerHTML\s*=/, 'app.js must never assign innerHTML');
  assert.match(headersFile, /\/ai-console\/\*/, '_headers must protect /ai-console/*');
  assert.match(headersFile, /X-Robots-Tag:\s*noindex/, '_headers must include X-Robots-Tag');
}

// 2. RFC 6238 TOTP known test vector (SHA-1, 6 digits, secret = "12345678901234567890").
{
  // Base32("12345678901234567890") = GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ
  const secretB32 = 'GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ';
  const secretBytes = base32Decode(secretB32);
  assert.equal(new TextDecoder().decode(secretBytes), '12345678901234567890');
  // RFC 6238 Appendix B: T=59s -> step 1 -> 94287082 -> 6-digit "287082"
  assert.equal(await generateTotpCode(secretBytes, 1), '287082');
  // T=1111111109s -> step 37037036 -> 07081804 -> 6-digit "081804"
  assert.equal(await generateTotpCode(secretBytes, 37037036), '081804');

  const vExact = await verifyTotp(secretB32, '287082', 59 * 1000);
  assert.equal(vExact.ok, true);
  assert.equal(vExact.matchedStep, 1);
  // ±1 step skew accepted:
  const vSkew = await verifyTotp(secretB32, '287082', 65 * 1000);
  assert.equal(vSkew.ok, true);
  assert.equal(vSkew.matchedStep, 1);
  // 2 steps away rejected:
  const vFar = await verifyTotp(secretB32, '287082', 120 * 1000);
  assert.equal(vFar.ok, false);
}

// 3. Cross-language PBKDF2-SHA256 verification (Python setup script -> JS Cloudflare handler).
{
  const pyOut = execFileSync(
    'python',
    [
      '-X', 'utf8', '-c',
      'import sys; sys.path.insert(0, "scripts"); '
      + 'from setup_ai_console_secrets import hash_password_pbkdf2; '
      + 'print(hash_password_pbkdf2("TestStrongPass!2026"))',
    ],
    { cwd: REPO_ROOT, encoding: 'utf8' },
  ).trim();
  assert.match(pyOut, /^pbkdf2_sha256\$100000\$/);
  assert.equal(await verifyAdminPassword('TestStrongPass!2026', { AI_LAB_ADMIN_PASSWORD_HASH: pyOut }), true);
  assert.equal(await verifyAdminPassword('WrongStrongPass!2026', { AI_LAB_ADMIN_PASSWORD_HASH: pyOut }), false);
}

// 4. Ed25519 RFC 8032 test vector & MMAILAB1 cross-verification.
{
  // RFC 8032 Section 7.1 Test 1: empty message
  const rfcSeed = hexToBytes('9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60');
  const expectedPub = 'd75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a';
  const expectedSig =
    'e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e06522490155'
    + '5fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b';
  const derivedPub = await ed25519PublicKeyFromSeed(rfcSeed);
  assert.equal(bytesToHex(derivedPub), expectedPub);
  const sig = await ed25519Sign(rfcSeed, new Uint8Array(0));
  assert.equal(bytesToHex(sig), expectedSig);
  assert.equal(await ed25519Verify(derivedPub, new Uint8Array(0), sig), true);

  // Also explicitly test pure-JS BigInt fallback when WebCrypto Ed25519 is unavailable.
  const origImportKey = crypto.subtle.importKey.bind(crypto.subtle);
  crypto.subtle.importKey = async (fmt, keyData, alg, extractable, usages) => {
    if (alg === 'Ed25519' || (alg && alg.name === 'Ed25519')) {
      throw new Error('Simulated missing WebCrypto Ed25519');
    }
    return origImportKey(fmt, keyData, alg, extractable, usages);
  };
  try {
    const fallbackSig = await ed25519Sign(rfcSeed, new Uint8Array(0));
    assert.equal(bytesToHex(fallbackSig), expectedSig);
    assert.equal(await ed25519Verify(derivedPub, new Uint8Array(0), fallbackSig), true);
    const tamperedSig = new Uint8Array(fallbackSig);
    tamperedSig[63] ^= 1;
    assert.equal(await ed25519Verify(derivedPub, new Uint8Array(0), tamperedSig), false);
  } finally {
    crypto.subtle.importKey = origImportKey;
  }

  // Issue MMAILAB1 token and verify both inline & wrapped in chat prose.
  const issued = await issueAiLabToken(rfcSeed, {
    plat: 'ios',
    days: 30,
    tag: 'cross-check',
    expOAuth: true,
    shared: true,
    nowEpoch: 1795000000,
    nonce: 'a1b2c3',
  });
  assert.match(issued.token, /^MMAILAB1\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]{86}$/);
  const wrapped = `口令如下：\n${issued.token.slice(0, 30)}\n${issued.token.slice(30)}\n请粘贴解锁`;
  const vOk = await verifyAiLabToken(wrapped, derivedPub, { nowEpoch: 1795000100, platform: 'ios' });
  assert.equal(vOk.valid, true);
  assert.equal(vOk.claims.exp_oauth, true);
  assert.equal(vOk.claims.shared, true);
  assert.equal(vOk.claims.tag, 'cross-check');
  const vWrongPlat = await verifyAiLabToken(issued.token, derivedPub, { nowEpoch: 1795000100, platform: 'windows' });
  assert.equal(vWrongPlat.valid, false);
  assert.equal(vWrongPlat.reason, 'platform_mismatch');
  const vExpired = await verifyAiLabToken(issued.token, derivedPub, { nowEpoch: 1795000000 + 31 * 86400, platform: 'ios' });
  assert.equal(vExpired.valid, false);
  assert.equal(vExpired.reason, 'expired');
  const tampered = issued.token.slice(0, -2) + (issued.token.endsWith('AA') ? 'BB' : 'AA');
  const vTampered = await verifyAiLabToken(tampered, derivedPub, { nowEpoch: 1795000100 });
  assert.equal(vTampered.valid, false);
  assert.equal(vTampered.reason, 'bad_signature');

  // Verify non-Android rejects min_vc > 0:
  await assert.rejects(
    () => issueAiLabToken(rfcSeed, { plat: 'ios', days: 7, minVc: 105 }),
    /min_vc/,
  );
  const androidMinVc = await issueAiLabToken(rfcSeed, { plat: 'android', days: 7, minVc: 105, nowEpoch: 1795000000 });
  assert.equal(androidMinVc.claims.min_vc, 105);
}

// 5. Full HTTP handler security & lifecycle tests.
{
  resetRuntimeGuardsForTest();
  const testSeedHex = '9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60';
  const totpSecret = 'GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ';
  const pwHash = await hashPasswordPbkdf2('MyUltraStrongPass#2026', new Uint8Array(16).fill(7), 100000);
  const env = {
    AI_LAB_ED25519_KEY: testSeedHex,
    AI_LAB_ADMIN_PASSWORD_HASH: pwHash,
    AI_LAB_TOTP_SECRET: totpSecret,
  };
  const nowMs = 1795000000 * 1000;
  const step = Math.floor(nowMs / 30000);
  const validTotp = await generateTotpCode(base32Decode(totpSecret), step);

  // 5a) Unconfigured status
  const unconf = await handle(makeReq('/api/ai-console/status'), {}, { nowMs, skipFailureDelay: true });
  assert.equal(unconf.status, 200);
  const unconfBody = await unconf.json();
  assert.equal(unconfBody.configured, false);
  assert.deepEqual(unconfBody.missingSecrets, ['AI_LAB_ED25519_KEY', 'AI_LAB_ADMIN_PASSWORD_HASH', 'AI_LAB_TOTP_SECRET']);
  assert.match(unconf.headers.get('Cache-Control'), /no-store/);
  assert.match(unconf.headers.get('X-Robots-Tag'), /noindex/);

  // 5b) CSRF & Origin guards
  const badOrigin = await handle(
    makeReq('/api/ai-console/login', { method: 'POST', body: {}, origin: 'https://evil.invalid' }),
    env,
    { nowMs, skipFailureDelay: true },
  );
  assert.equal(badOrigin.status, 403);

  const noCsrf = await handle(
    makeReq('/api/ai-console/login', { method: 'POST', body: {}, csrf: false }),
    env,
    { nowMs, skipFailureDelay: true },
  );
  assert.equal(noCsrf.status, 403);

  // 5c) Unauthenticated /issue rejected
  const unauthIssue = await handle(
    makeReq('/api/ai-console/issue', { method: 'POST', body: { plat: 'ios', days: 7 } }),
    env,
    { nowMs, skipFailureDelay: true },
  );
  assert.equal(unauthIssue.status, 401);

  // 5d) Rate limit after 5 bad logins from attacker IP
  for (let i = 0; i < 5; i++) {
    const r = await handle(
      makeReq('/api/ai-console/login', {
        method: 'POST',
        body: { password: 'wrong', totp: validTotp },
        ip: '198.51.100.99',
      }),
      env,
      { nowMs, skipFailureDelay: true },
    );
    assert.equal(r.status, 401);
  }
  const blocked = await handle(
    makeReq('/api/ai-console/login', {
      method: 'POST',
      body: { password: 'MyUltraStrongPass#2026', totp: validTotp },
      ip: '198.51.100.99',
    }),
    env,
    { nowMs, skipFailureDelay: true },
  );
  assert.equal(blocked.status, 429);
  assert.ok(Number(blocked.headers.get('Retry-After')) > 0);

  // 5e) Legitimate 2FA login from admin IP succeeds & sets HttpOnly Secure SameSite=Strict cookie
  const loginRes = await handle(
    makeReq('/api/ai-console/login', {
      method: 'POST',
      body: { password: 'MyUltraStrongPass#2026', totp: validTotp },
      ip: '203.0.113.42',
    }),
    env,
    { nowMs, skipFailureDelay: true },
  );
  assert.equal(loginRes.status, 200);
  const setCookie = loginRes.headers.get('Set-Cookie');
  assert.match(setCookie, /marco_ai_console=/);
  assert.match(setCookie, /HttpOnly/);
  assert.match(setCookie, /Secure/);
  assert.match(setCookie, /SameSite=Strict/);
  const cookiePair = setCookie.split(';')[0];

  // 5f) Replaying the exact same TOTP code in the same 30s window is rejected
  const replayRes = await handle(
    makeReq('/api/ai-console/login', {
      method: 'POST',
      body: { password: 'MyUltraStrongPass#2026', totp: validTotp },
      ip: '203.0.113.42',
    }),
    env,
    { nowMs: nowMs + 2000, skipFailureDelay: true },
  );
  assert.equal(replayRes.status, 401);
  const replayBody = await replayRes.json();
  assert.equal(replayBody.error, 'totp_replayed');

  // 5g) Authenticated /status reports authenticated: true
  const statusRes = await handle(
    makeReq('/api/ai-console/status', { cookie: cookiePair }),
    env,
    { nowMs, skipFailureDelay: true },
  );
  const statusBody = await statusRes.json();
  assert.equal(statusBody.authenticated, true);
  assert.equal(statusBody.keyMatchesOfficial, false);

  // 5h) Non-official key is blocked by default (409 key_mismatch)
  const mismatchRes = await handle(
    makeReq('/api/ai-console/issue', {
      method: 'POST',
      cookie: cookiePair,
      body: { plat: 'ios', days: 30, tag: 'beta', expOAuth: true },
    }),
    env,
    { nowMs, skipFailureDelay: true },
  );
  assert.equal(mismatchRes.status, 409);

  // 5i) Explicit test override issues 5 unique batch tokens
  const issueRes = await handle(
    makeReq('/api/ai-console/issue', {
      method: 'POST',
      cookie: cookiePair,
      body: { plat: 'all', days: 30, tag: 'batch-test', expOAuth: true, count: 5, allowNonOfficialKey: true },
    }),
    env,
    { nowMs, skipFailureDelay: true },
  );
  assert.equal(issueRes.status, 200);
  const issueBody = await issueRes.json();
  assert.equal(issueBody.tokens.length, 5);
  assert.equal(new Set(issueBody.tokens.map((t) => t.token)).size, 5);

  // 5j) Tampered cookie rejected
  const tamperedCookie = cookiePair.slice(0, -2) + (cookiePair.endsWith('aa') ? 'bb' : 'aa');
  const badCookieRes = await handle(
    makeReq('/api/ai-console/issue', {
      method: 'POST',
      cookie: tamperedCookie,
      body: { plat: 'all', days: 7 },
    }),
    env,
    { nowMs, skipFailureDelay: true },
  );
  assert.equal(badCookieRes.status, 401);

  // 5k) Expired session rejected
  const expiredRes = await handle(
    makeReq('/api/ai-console/issue', {
      method: 'POST',
      cookie: cookiePair,
      body: { plat: 'all', days: 7 },
    }),
    env,
    { nowMs: nowMs + 13 * 3600 * 1000, skipFailureDelay: true },
  );
  assert.equal(expiredRes.status, 401);

  // 5l) Logout clears cookie
  const logoutRes = await handle(
    makeReq('/api/ai-console/logout', { method: 'POST', cookie: cookiePair }),
    env,
    { nowMs, skipFailureDelay: true },
  );
  assert.equal(logoutRes.status, 200);
  assert.match(logoutRes.headers.get('Set-Cookie'), /Max-Age=0/);
}

console.log(`PASS ai-console crypto, TOTP, PBKDF2, and HTTP security tests (official pubkey=${OFFICIAL_PUBKEY_HEX.slice(0, 12)}...)`);

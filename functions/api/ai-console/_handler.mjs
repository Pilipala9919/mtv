// Copyright (C) 2026 Pilipala
// SPDX-License-Identifier: GPL-3.0-only
//
// Cloudflare Pages Function backend for Marco Movie AI Lab offline passcode console.
// Zero external dependencies; secrets stay exclusively in Cloudflare Encrypted Env Vars.

export const OFFICIAL_PUBKEY_HEX =
  '1dbeaed851b873d7c327d30d718fca0ac1509ef5ac4061b9bd1aa90c841c6929';
export const AI_LAB_TOKEN_PREFIX = 'MMAILAB1.';
export const AI_LAB_SIGN_DOMAIN = 'marco-ai-lab-v1:';
const SESSION_COOKIE_NAME = 'marco_ai_console';
const CSRF_HEADER_NAME = 'x-requested-with';
const CSRF_HEADER_VALUE = 'MarcoAiConsole';
const MAX_BODY_BYTES = 8192;
const MAX_BATCH_COUNT = 50;
const LOGIN_WINDOW_MS = 15 * 60 * 1000;
const MAX_LOGIN_FAILURES = 5;
const DEFAULT_SESSION_TTL_SEC = 12 * 3600;
const SHORT_SESSION_TTL_SEC = 30 * 60;
const MIN_PLAINTEXT_PASSWORD_LEN = 12;

const encoder = new TextEncoder();
const decoder = new TextDecoder();

// Pure-JS RFC 8032 Ed25519 constants (exact match with scripts/sign_manifest.py).
const ED_Q = (1n << 255n) - 19n;
const ED_L = (1n << 252n) + 27742317777372353535851937790883648493n;

function mod(a, m) {
  const r = a % m;
  return r >= 0n ? r : r + m;
}

function modPow(base, exp, m) {
  let result = 1n;
  let b = mod(base, m);
  let e = exp;
  while (e > 0n) {
    if (e & 1n) result = (result * b) % m;
    b = (b * b) % m;
    e >>= 1n;
  }
  return result;
}

function modInv(x) {
  return modPow(x, ED_Q - 2n, ED_Q);
}

const ED_D = mod(-121665n * modInv(121666n), ED_Q);
const ED_I = modPow(2n, (ED_Q - 1n) / 4n, ED_Q);

function recoverX(y) {
  const y2 = (y * y) % ED_Q;
  const xx = mod((y2 - 1n) * modInv(mod(ED_D * y2 + 1n, ED_Q)), ED_Q);
  let x = modPow(xx, (ED_Q + 3n) / 8n, ED_Q);
  if (mod(x * x - xx, ED_Q) !== 0n) {
    x = (x * ED_I) % ED_Q;
  }
  if (mod(x * x - xx, ED_Q) !== 0n) {
    return null;
  }
  if (x % 2n !== 0n) {
    x = ED_Q - x;
  }
  return x;
}

const ED_BY = mod(4n * modInv(5n), ED_Q);
const ED_BX = recoverX(ED_BY);
// Extended homogeneous coordinates (X, Y, Z, T) for fast constant-formula addition.
const ED_BASE = [ED_BX, ED_BY, 1n, (ED_BX * ED_BY) % ED_Q];
const ED_IDENT = [0n, 1n, 1n, 0n];

function edAdd(p, q) {
  const [X1, Y1, Z1, T1] = p;
  const [X2, Y2, Z2, T2] = q;
  const A = mod((Y1 - X1) * (Y2 - X2), ED_Q);
  const B = mod((Y1 + X1) * (Y2 + X2), ED_Q);
  const C = mod(2n * ED_D * T1 * T2, ED_Q);
  const D = mod(2n * Z1 * Z2, ED_Q);
  const E = mod(B - A, ED_Q);
  const F = mod(D - C, ED_Q);
  const G = mod(D + C, ED_Q);
  const H = mod(B + A, ED_Q);
  return [
    (E * F) % ED_Q,
    (G * H) % ED_Q,
    (F * G) % ED_Q,
    (E * H) % ED_Q,
  ];
}

function edScalarMult(point, scalar) {
  let q = ED_IDENT;
  let p = point;
  let e = scalar;
  while (e > 0n) {
    if (e & 1n) q = edAdd(q, p);
    p = edAdd(p, p);
    e >>= 1n;
  }
  return q;
}

function edEncodePoint(extPoint) {
  const [X, Y, Z] = extPoint;
  const zInv = modInv(Z);
  const x = (X * zInv) % ED_Q;
  const y = (Y * zInv) % ED_Q;
  const out = new Uint8Array(32);
  let tmp = y;
  for (let i = 0; i < 32; i++) {
    out[i] = Number(tmp & 0xffn);
    tmp >>= 8n;
  }
  if (x & 1n) out[31] |= 0x80;
  return out;
}

function edDecodePoint(bytes) {
  if (!(bytes instanceof Uint8Array) || bytes.length !== 32) return null;
  const signBit = (bytes[31] >> 7) & 1;
  let y = 0n;
  for (let i = 31; i >= 0; i--) {
    const b = i === 31 ? bytes[i] & 0x7f : bytes[i];
    y = (y << 8n) | BigInt(b);
  }
  if (y >= ED_Q) return null;
  let x = recoverX(y);
  if (x === null) return null;
  if (x === 0n && signBit === 1) return null;
  if (Number(x & 1n) !== signBit) x = ED_Q - x;
  return [x, y, 1n, (x * y) % ED_Q];
}

function bytesToLittleEndianBigInt(bytes) {
  let v = 0n;
  for (let i = bytes.length - 1; i >= 0; i--) {
    v = (v << 8n) | BigInt(bytes[i]);
  }
  return v;
}

function bigIntToLittleEndian32(v) {
  const out = new Uint8Array(32);
  let tmp = v;
  for (let i = 0; i < 32; i++) {
    out[i] = Number(tmp & 0xffn);
    tmp >>= 8n;
  }
  return out;
}

function concatBytes(...arrays) {
  let total = 0;
  for (const arr of arrays) total += arr.length;
  const out = new Uint8Array(total);
  let offset = 0;
  for (const arr of arrays) {
    out.set(arr, offset);
    offset += arr.length;
  }
  return out;
}

async function sha512(bytes) {
  return new Uint8Array(await crypto.subtle.digest('SHA-512', bytes));
}

async function sha256(bytes) {
  return new Uint8Array(await crypto.subtle.digest('SHA-256', bytes));
}

export function bytesToHex(bytes) {
  let hex = '';
  for (let i = 0; i < bytes.length; i++) {
    hex += bytes[i].toString(16).padStart(2, '0');
  }
  return hex;
}

export function hexToBytes(hex) {
  const clean = (hex || '').replace(/[\s#].*$/gm, '').replace(/\s+/g, '');
  if (!clean || clean.length % 2 !== 0 || !/^[0-9a-fA-F]+$/.test(clean)) {
    return null;
  }
  const out = new Uint8Array(clean.length / 2);
  for (let i = 0; i < out.length; i++) {
    out[i] = parseInt(clean.slice(i * 2, i * 2 + 2), 16);
  }
  return out;
}

export function b64urlEncode(bytes) {
  let binary = '';
  for (let i = 0; i < bytes.length; i++) {
    binary += String.fromCharCode(bytes[i]);
  }
  return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

export function b64urlDecode(str) {
  if (typeof str !== 'string' || !/^[A-Za-z0-9_-]*$/.test(str)) return null;
  const padLen = (4 - (str.length % 4)) % 4;
  const b64 = str.replace(/-/g, '+').replace(/_/g, '/') + '='.repeat(padLen);
  try {
    const bin = atob(b64);
    const out = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
    return out;
  } catch {
    return null;
  }
}

function timingSafeEqualBytes(a, b) {
  if (!(a instanceof Uint8Array) || !(b instanceof Uint8Array) || a.length !== b.length) {
    return false;
  }
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a[i] ^ b[i];
  return diff === 0;
}

function timingSafeEqualStrings(a, b) {
  const ba = encoder.encode(String(a ?? ''));
  const bb = encoder.encode(String(b ?? ''));
  if (ba.length !== bb.length) return false;
  return timingSafeEqualBytes(ba, bb);
}

// RFC 8410 PKCS#8 header for a 32-byte Ed25519 private seed.
const ED25519_PKCS8_PREFIX = new Uint8Array([
  0x30, 0x2e, 0x02, 0x01, 0x00, 0x30, 0x05, 0x06,
  0x03, 0x2b, 0x65, 0x70, 0x04, 0x22, 0x04, 0x20,
]);

export async function ed25519PublicKeyFromSeed(seed) {
  if (!(seed instanceof Uint8Array) || seed.length !== 32) {
    throw new Error('Ed25519 private seed must be 32 bytes');
  }
  const h = await sha512(seed);
  const clamped = h.slice(0, 32);
  clamped[0] &= 248;
  clamped[31] &= 63;
  clamped[31] |= 64;
  const a = bytesToLittleEndianBigInt(clamped);
  return edEncodePoint(edScalarMult(ED_BASE, a));
}

export async function ed25519Sign(seed, message) {
  if (!(seed instanceof Uint8Array) || seed.length !== 32) {
    throw new Error('Ed25519 private seed must be 32 bytes');
  }
  // Prefer native Web Crypto Ed25519 when available (~0.1ms in BoringSSL), with exact RFC 8032 JS fallback.
  try {
    const pkcs8 = concatBytes(ED25519_PKCS8_PREFIX, seed);
    const key = await crypto.subtle.importKey('pkcs8', pkcs8, { name: 'Ed25519' }, false, ['sign']);
    const sig = new Uint8Array(await crypto.subtle.sign({ name: 'Ed25519' }, key, message));
    if (sig.length === 64) return sig;
  } catch {
    // Fall back to deterministic pure-JS RFC 8032 Ed25519 below.
  }
  const h = await sha512(seed);
  const clamped = h.slice(0, 32);
  clamped[0] &= 248;
  clamped[31] &= 63;
  clamped[31] |= 64;
  const a = bytesToLittleEndianBigInt(clamped);
  const pubBytes = edEncodePoint(edScalarMult(ED_BASE, a));

  const rHash = await sha512(concatBytes(h.slice(32, 64), message));
  const r = mod(bytesToLittleEndianBigInt(rHash), ED_L);
  const rBytes = edEncodePoint(edScalarMult(ED_BASE, r));

  const kHash = await sha512(concatBytes(rBytes, pubBytes, message));
  const k = mod(bytesToLittleEndianBigInt(kHash), ED_L);
  const s = mod(r + k * a, ED_L);
  return concatBytes(rBytes, bigIntToLittleEndian32(s));
}

export async function ed25519Verify(pubBytes, message, sigBytes) {
  if (
    !(pubBytes instanceof Uint8Array) || pubBytes.length !== 32 ||
    !(sigBytes instanceof Uint8Array) || sigBytes.length !== 64
  ) {
    return false;
  }
  try {
    const key = await crypto.subtle.importKey('raw', pubBytes, { name: 'Ed25519' }, false, ['verify']);
    return await crypto.subtle.verify({ name: 'Ed25519' }, key, sigBytes, message);
  } catch {
    // Fall back to pure-JS RFC 8032 Ed25519 verification below.
  }
  const rBytes = sigBytes.slice(0, 32);
  const sBytes = sigBytes.slice(32, 64);
  const s = bytesToLittleEndianBigInt(sBytes);
  if (s >= ED_L) return false;
  const R = edDecodePoint(rBytes);
  const A = edDecodePoint(pubBytes);
  if (!R || !A) return false;
  const kHash = await sha512(concatBytes(rBytes, pubBytes, message));
  const k = mod(bytesToLittleEndianBigInt(kHash), ED_L);
  const lhs = edEncodePoint(edScalarMult(ED_BASE, s));
  const rhs = edEncodePoint(edAdd(R, edScalarMult(A, k)));
  return timingSafeEqualBytes(lhs, rhs);
}

// Canonical compact JSON matching scripts/sign_manifest.py::canonicalize_json.
export function canonicalizeJson(obj) {
  if (obj === null) return 'null';
  if (typeof obj === 'boolean') return obj ? 'true' : 'false';
  if (typeof obj === 'number') return String(obj);
  if (typeof obj === 'string') return JSON.stringify(obj);
  if (Array.isArray(obj)) return '[' + obj.map((x) => canonicalizeJson(x)).join(',') + ']';
  if (typeof obj === 'object') {
    const keys = Object.keys(obj).sort();
    return '{' + keys.map((k) => JSON.stringify(String(k)) + ':' + canonicalizeJson(obj[k])).join(',') + '}';
  }
  return JSON.stringify(obj);
}

// RFC 4648 Base32 decoding for TOTP secrets.
const BASE32_ALPHABET = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567';

export function base32Decode(raw) {
  const clean = String(raw || '').toUpperCase().replace(/[\s-]+/g, '').replace(/=+$/, '');
  if (!clean || clean.length < 16) return null;
  let bits = 0;
  let value = 0;
  const bytes = [];
  for (let i = 0; i < clean.length; i++) {
    const idx = BASE32_ALPHABET.indexOf(clean[i]);
    if (idx < 0) return null;
    value = (value << 5) | idx;
    bits += 5;
    if (bits >= 8) {
      bits -= 8;
      bytes.push((value >>> bits) & 0xff);
    }
  }
  return new Uint8Array(bytes);
}

export async function generateTotpCode(secretBytes, stepCounter) {
  const counterBytes = new Uint8Array(8);
  let c = BigInt(stepCounter);
  for (let i = 7; i >= 0; i--) {
    counterBytes[i] = Number(c & 0xffn);
    c >>= 8n;
  }
  const key = await crypto.subtle.importKey(
    'raw',
    secretBytes,
    { name: 'HMAC', hash: 'SHA-1' },
    false,
    ['sign'],
  );
  const mac = new Uint8Array(await crypto.subtle.sign('HMAC', key, counterBytes));
  const offset = mac[mac.length - 1] & 0x0f;
  const binCode =
    ((mac[offset] & 0x7f) << 24) |
    ((mac[offset + 1] & 0xff) << 16) |
    ((mac[offset + 2] & 0xff) << 8) |
    (mac[offset + 3] & 0xff);
  return String(binCode % 1000000).padStart(6, '0');
}

export async function verifyTotp(secretBase32, codeInput, nowMs = Date.now()) {
  const code = String(codeInput || '').replace(/[\s-]+/g, '');
  if (!/^\d{6}$/.test(code)) return { ok: false, matchedStep: null };
  const secretBytes = base32Decode(secretBase32);
  if (!secretBytes || secretBytes.length < 10) return { ok: false, matchedStep: null };
  const currentStep = Math.floor(nowMs / 30000);
  let matchedStep = null;
  // Evaluate all three steps without early exit to avoid timing leakage.
  for (const delta of [-1, 0, 1]) {
    const step = currentStep + delta;
    const expected = await generateTotpCode(secretBytes, step);
    if (timingSafeEqualStrings(code, expected)) {
      matchedStep = step;
    }
  }
  return { ok: matchedStep !== null, matchedStep };
}

export async function hashPasswordPbkdf2(password, saltBytes, iterations = 100000) {
  const baseKey = await crypto.subtle.importKey(
    'raw',
    encoder.encode(password),
    'PBKDF2',
    false,
    ['deriveBits'],
  );
  const bits = await crypto.subtle.deriveBits(
    { name: 'PBKDF2', salt: saltBytes, iterations, hash: 'SHA-256' },
    baseKey,
    256,
  );
  return `pbkdf2_sha256$${iterations}$${b64urlEncode(saltBytes)}$${b64urlEncode(new Uint8Array(bits))}`;
}

export async function verifyAdminPassword(candidate, env) {
  if (typeof candidate !== 'string' || candidate.length === 0 || candidate.length > 256) {
    return false;
  }
  const hashSpec = String(env.AI_LAB_ADMIN_PASSWORD_HASH || '').trim();
  if (hashSpec) {
    const parts = hashSpec.split('$');
    if (parts.length !== 4 || parts[0] !== 'pbkdf2_sha256') return false;
    const iterations = Number(parts[1]);
    const salt = b64urlDecode(parts[2]);
    const expected = b64urlDecode(parts[3]);
    if (!Number.isInteger(iterations) || iterations < 50000 || iterations > 100000 || !salt || !expected || expected.length !== 32) {
      return false;
    }
    const baseKey = await crypto.subtle.importKey(
      'raw',
      encoder.encode(candidate),
      'PBKDF2',
      false,
      ['deriveBits'],
    );
    const derived = new Uint8Array(
      await crypto.subtle.deriveBits(
        { name: 'PBKDF2', salt, iterations, hash: 'SHA-256' },
        baseKey,
        256,
      ),
    );
    return timingSafeEqualBytes(derived, expected);
  }
  const plain = String(env.AI_LAB_ADMIN_PASSWORD || '');
  if (plain.length < MIN_PLAINTEXT_PASSWORD_LEN) return false;
  const h1 = await sha256(encoder.encode('marco-ai-console-pw:' + candidate));
  const h2 = await sha256(encoder.encode('marco-ai-console-pw:' + plain));
  return timingSafeEqualBytes(h1, h2);
}

function parseSeedFromEnv(env) {
  const raw = String(env.AI_LAB_ED25519_KEY || '').trim();
  if (!raw) return null;
  const seed = hexToBytes(raw);
  if (!seed || seed.length !== 32) return null;
  return seed;
}

function hasValidPasswordConfig(env) {
  const hashSpec = String(env.AI_LAB_ADMIN_PASSWORD_HASH || '').trim();
  if (hashSpec) {
    const parts = hashSpec.split('$');
    const iters = Number(parts[1]);
    return (
      parts.length === 4 &&
      parts[0] === 'pbkdf2_sha256' &&
      Number.isInteger(iters) &&
      iters >= 50000 &&
      iters <= 100000 &&
      !!b64urlDecode(parts[2]) &&
      b64urlDecode(parts[3])?.length === 32
    );
  }
  const plain = String(env.AI_LAB_ADMIN_PASSWORD || '');
  return plain.length >= MIN_PLAINTEXT_PASSWORD_LEN;
}

function getMissingConfigNames(env) {
  const missing = [];
  if (!parseSeedFromEnv(env)) missing.push('AI_LAB_ED25519_KEY');
  if (!hasValidPasswordConfig(env)) missing.push('AI_LAB_ADMIN_PASSWORD_HASH');
  if (!base32Decode(env.AI_LAB_TOTP_SECRET)) missing.push('AI_LAB_TOTP_SECRET');
  return missing;
}

async function getSessionHmacKey(env) {
  const explicit = String(env.AI_LAB_SESSION_SECRET || '').trim();
  const seedMaterial = explicit.length >= 32
    ? encoder.encode('marco-ai-console-session-v1:' + explicit)
    : encoder.encode(
        'marco-ai-console-session-v1:' +
        String(env.AI_LAB_ED25519_KEY || '') + ':' +
        String(env.AI_LAB_TOTP_SECRET || '') + ':' +
        String(env.AI_LAB_ADMIN_PASSWORD_HASH || env.AI_LAB_ADMIN_PASSWORD || ''),
      );
  const keyBytes = await sha256(seedMaterial);
  return crypto.subtle.importKey('raw', keyBytes, { name: 'HMAC', hash: 'SHA-256' }, false, ['sign', 'verify']);
}

async function createSessionToken(env, ttlSec, nowSec) {
  const nonceBytes = new Uint8Array(12);
  crypto.getRandomValues(nonceBytes);
  const payload = {
    v: 1,
    iat: nowSec,
    exp: nowSec + ttlSec,
    jti: bytesToHex(nonceBytes),
  };
  const payloadB64 = b64urlEncode(encoder.encode(canonicalizeJson(payload)));
  const key = await getSessionHmacKey(env);
  const mac = new Uint8Array(await crypto.subtle.sign('HMAC', key, encoder.encode(payloadB64)));
  return { token: `${payloadB64}.${b64urlEncode(mac)}`, payload };
}

async function verifySessionToken(token, env, nowSec) {
  if (typeof token !== 'string') return null;
  const parts = token.split('.');
  if (parts.length !== 2) return null;
  const [payloadB64, sigB64] = parts;
  const sigBytes = b64urlDecode(sigB64);
  const payloadBytes = b64urlDecode(payloadB64);
  if (!sigBytes || sigBytes.length !== 32 || !payloadBytes) return null;
  const key = await getSessionHmacKey(env);
  const expectedMac = new Uint8Array(await crypto.subtle.sign('HMAC', key, encoder.encode(payloadB64)));
  if (!timingSafeEqualBytes(sigBytes, expectedMac)) return null;
  try {
    const claims = JSON.parse(decoder.decode(payloadBytes));
    if (!claims || claims.v !== 1 || typeof claims.exp !== 'number' || typeof claims.iat !== 'number') {
      return null;
    }
    if (nowSec > claims.exp || claims.iat > nowSec + 60) return null;
    return claims;
  } catch {
    return null;
  }
}

function parseCookie(cookieHeader, name) {
  if (!cookieHeader) return null;
  for (const part of cookieHeader.split(';')) {
    const idx = part.indexOf('=');
    if (idx < 0) continue;
    if (part.slice(0, idx).trim() === name) {
      return part.slice(idx + 1).trim();
    }
  }
  return null;
}

// Per-isolate brute-force & TOTP replay guard.
const loginFailures = new Map();
let lastUsedTotpStep = -1;

export function resetRuntimeGuardsForTest() {
  loginFailures.clear();
  lastUsedTotpStep = -1;
}

function checkRateLimit(bucket, nowMs) {
  const entry = loginFailures.get(bucket);
  if (!entry) return { blocked: false, retryAfterSec: 0 };
  const recent = entry.filter((t) => nowMs - t < LOGIN_WINDOW_MS);
  if (recent.length === 0) {
    loginFailures.delete(bucket);
    return { blocked: false, retryAfterSec: 0 };
  }
  loginFailures.set(bucket, recent);
  if (recent.length >= MAX_LOGIN_FAILURES) {
    const oldest = recent[0];
    const retryAfterSec = Math.max(1, Math.ceil((LOGIN_WINDOW_MS - (nowMs - oldest)) / 1000));
    return { blocked: true, retryAfterSec };
  }
  return { blocked: false, retryAfterSec: 0 };
}

function recordLoginFailure(bucket, nowMs) {
  const entry = loginFailures.get(bucket) || [];
  const recent = entry.filter((t) => nowMs - t < LOGIN_WINDOW_MS);
  recent.push(nowMs);
  loginFailures.set(bucket, recent);
}

function clearLoginFailures(bucket) {
  loginFailures.delete(bucket);
}

export function normalizeSinglePlatform(raw) {
  const v = String(raw || 'all').trim().toLowerCase();
  if (v === '' || v === 'all' || v === '*') return 'all';
  if (v === 'ios' || v === 'iphone' || v === 'ipad') return 'ios';
  if (v === 'windows' || v === 'win' || v === 'pc') return 'windows';
  if (v === 'android' || v === 'android-mobile' || v === 'mobile') return 'android';
  return null;
}

export function matchesPlatform(platClaim, targetPlatform) {
  if (!targetPlatform) return true;
  const target = normalizeSinglePlatform(targetPlatform);
  if (!target || target === 'all') return true;
  const claim = String(platClaim || 'all').trim().toLowerCase();
  if (!claim || claim === 'all' || claim === '*') return true;
  for (const part of claim.split(/[,;/\s]+/)) {
    if (!part) continue;
    const norm = normalizeSinglePlatform(part);
    if (norm === 'all' || norm === target) return true;
  }
  return false;
}

export async function issueAiLabToken(seed, opts = {}) {
  const plat = normalizeSinglePlatform(opts.plat ?? 'all');
  if (!plat) throw new Error('无效的目标平台（仅支持 all / ios / windows / android）');

  const days = Number(opts.days ?? 0);
  if (!Number.isInteger(days) || days < 0 || days > 3650) {
    throw new Error('有效天数必须为 0（永久）到 3650 之间的整数');
  }

  const tag = String(opts.tag ?? 'PILIPALA').trim();
  if (!tag || tag.length > 48 || /[\r\n]/.test(tag)) {
    throw new Error('标签长度需为 1–48 字符且不可包含换行');
  }

  const shared = Boolean(opts.shared);
  const expOAuth = Boolean(opts.expOAuth);
  const minVc = Number(opts.minVc ?? 0);
  if (!Number.isInteger(minVc) || minVc < 0 || minVc > 9999999) {
    throw new Error('最低版本码必须为非负整数');
  }
  if (minVc > 0 && plat !== 'android') {
    throw new Error('仅 Android 单端定向口令允许设置最低版本码（min_vc）');
  }

  const iat = opts.nowEpoch !== undefined ? Math.floor(opts.nowEpoch) : Math.floor(Date.now() / 1000);
  const exp = days <= 0 ? 0 : iat + days * 86400;

  let nonce;
  if (typeof opts.nonce === 'string' && opts.nonce.trim()) {
    nonce = opts.nonce.trim();
  } else {
    const nBytes = new Uint8Array(3);
    crypto.getRandomValues(nBytes);
    nonce = bytesToHex(nBytes);
  }

  const claims = {
    exp,
    iat,
    n: nonce,
    plat,
    tag,
    v: 1,
  };
  if (shared) claims.shared = true;
  if (expOAuth) claims.exp_oauth = true;
  if (minVc > 0) claims.min_vc = minVc;

  const payloadBytes = encoder.encode(canonicalizeJson(claims));
  const signInput = concatBytes(encoder.encode(AI_LAB_SIGN_DOMAIN), payloadBytes);
  const sig = await ed25519Sign(seed, signInput);

  // Self-verify every generated token before returning it.
  const pub = await ed25519PublicKeyFromSeed(seed);
  const ok = await ed25519Verify(pub, signInput, sig);
  if (!ok) throw new Error('Ed25519 self-verification failed');

  const token = `${AI_LAB_TOKEN_PREFIX}${b64urlEncode(payloadBytes)}.${b64urlEncode(sig)}`;
  return {
    token,
    claims,
    expiresAtIso: exp > 0 ? new Date(exp * 1000).toISOString() : null,
  };
}

export function extractTokenFromText(rawText) {
  const text = String(rawText || '');
  // Try clean single-line exact match first (matches Windows 0.7.3).
  const direct = text.match(/MMAILAB1\.([A-Za-z0-9_-]+)\.([A-Za-z0-9_-]{86})(?![A-Za-z0-9_-])/);
  if (direct) return { payloadB64: direct[1], sigB64: direct[2], canonicalToken: direct[0] };
  // Fall back to whitespace-collapsed extraction (supports wrapped tokens).
  const collapsed = text.replace(/\s+/g, '');
  const wrapped = collapsed.match(/MMAILAB1\.([A-Za-z0-9_-]+)\.([A-Za-z0-9_-]{86})/);
  if (wrapped) return { payloadB64: wrapped[1], sigB64: wrapped[2], canonicalToken: wrapped[0] };
  return null;
}

export async function verifyAiLabToken(rawText, pubBytes, opts = {}) {
  const extracted = extractTokenFromText(rawText);
  if (!extracted) {
    return { valid: false, reason: 'format_not_found', message: '未识别到有效的 MMAILAB1 口令格式' };
  }
  const payloadBytes = b64urlDecode(extracted.payloadB64);
  const sigBytes = b64urlDecode(extracted.sigB64);
  if (!payloadBytes || !sigBytes || sigBytes.length !== 64) {
    return { valid: false, reason: 'invalid_encoding', message: '口令 Base64URL 编码或签名长度无效' };
  }
  const signInput = concatBytes(encoder.encode(AI_LAB_SIGN_DOMAIN), payloadBytes);
  const sigOk = await ed25519Verify(pubBytes, signInput, sigBytes);
  if (!sigOk) {
    return { valid: false, reason: 'bad_signature', message: 'Ed25519 签名验证失败（非官方私钥签发或内容被篡改）' };
  }
  let claims;
  try {
    claims = JSON.parse(decoder.decode(payloadBytes));
  } catch {
    return { valid: false, reason: 'invalid_json', message: '载荷 JSON 解析失败' };
  }
  if (!claims || typeof claims !== 'object' || claims.v !== 1) {
    return { valid: false, reason: 'unsupported_version', message: '不支持的口令协议版本' };
  }
  const nowSec = opts.nowEpoch !== undefined ? Math.floor(opts.nowEpoch) : Math.floor(Date.now() / 1000);
  const exp = Number(claims.exp || 0);
  const expired = exp > 0 && nowSec > exp;
  const platOk = matchesPlatform(claims.plat, opts.platform);
  return {
    valid: !expired && platOk,
    signatureValid: true,
    expired,
    platformMatched: platOk,
    reason: expired ? 'expired' : (!platOk ? 'platform_mismatch' : 'ok'),
    message: expired
      ? '签名有效，但该口令已过期'
      : (!platOk ? `签名有效，但平台不匹配（口令仅限 ${claims.plat}）` : '官方 Ed25519 签名有效，可正常激活'),
    canonicalToken: extracted.canonicalToken,
    claims,
    issuedAtIso: claims.iat ? new Date(claims.iat * 1000).toISOString() : null,
    expiresAtIso: exp > 0 ? new Date(exp * 1000).toISOString() : null,
  };
}

function jsonResponse(data, status = 200, extraHeaders = {}) {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      'Content-Type': 'application/json; charset=utf-8',
      'Cache-Control': 'no-store, max-age=0',
      'Pragma': 'no-cache',
      'X-Content-Type-Options': 'nosniff',
      'X-Robots-Tag': 'noindex, nofollow, noarchive',
      'Referrer-Policy': 'no-referrer',
      ...extraHeaders,
    },
  });
}

function buildCookieHeader(value, maxAge, isHttps) {
  const parts = [
    `${SESSION_COOKIE_NAME}=${value}`,
    'Path=/api/ai-console',
    'HttpOnly',
    'SameSite=Strict',
    `Max-Age=${maxAge}`,
  ];
  if (isHttps) parts.push('Secure');
  return parts.join('; ');
}

async function readBoundedJson(request) {
  const ct = request.headers.get('Content-Type') || '';
  if (!ct.toLowerCase().startsWith('application/json')) {
    return { error: 'json_required', status: 415 };
  }
  const reader = request.body?.getReader();
  if (!reader) return { error: 'empty_body', status: 400 };
  let size = 0;
  let text = '';
  try {
    const streamDecoder = new TextDecoder();
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      size += value.byteLength;
      if (size > MAX_BODY_BYTES) {
        await reader.cancel();
        return { error: 'body_too_large', status: 413 };
      }
      text += streamDecoder.decode(value, { stream: true });
    }
    text += streamDecoder.decode();
    const data = JSON.parse(text);
    if (!data || typeof data !== 'object' || Array.isArray(data)) {
      return { error: 'invalid_json', status: 400 };
    }
    return { data };
  } catch {
    return { error: 'invalid_json', status: 400 };
  }
}

function verifySameOriginAndCsrf(request, url) {
  const origin = request.headers.get('Origin');
  if (origin && origin !== url.origin) {
    return { ok: false, error: 'origin_rejected', status: 403 };
  }
  const csrf = request.headers.get(CSRF_HEADER_NAME);
  if (csrf !== CSRF_HEADER_VALUE) {
    return { ok: false, error: 'csrf_header_required', status: 403 };
  }
  return { ok: true };
}

export async function handle(request, env = {}, runtimeOpts = {}) {
  const url = new URL(request.url);
  const path = url.pathname.replace(/\/+$/, '');
  const nowMs = runtimeOpts.nowMs !== undefined ? runtimeOpts.nowMs : Date.now();
  const nowSec = Math.floor(nowMs / 1000);
  const isHttps = url.protocol === 'https:';
  const missing = getMissingConfigNames(env);
  const configured = missing.length === 0;

  let seed = null;
  let pubBytes = null;
  let pubHex = '';
  let keyMatchesOfficial = false;
  if (configured) {
    seed = parseSeedFromEnv(env);
    pubBytes = await ed25519PublicKeyFromSeed(seed);
    pubHex = bytesToHex(pubBytes);
    keyMatchesOfficial = pubHex === OFFICIAL_PUBKEY_HEX;
  }

  // 1) Status check (GET /api/ai-console/status)
  if (path === '/api/ai-console/status' && request.method === 'GET') {
    if (!configured) {
      return jsonResponse({
        configured: false,
        authenticated: false,
        missingSecrets: missing,
        officialPubkeyPrefix: OFFICIAL_PUBKEY_HEX.slice(0, 12),
        serverTime: nowSec,
      });
    }
    const rawCookie = parseCookie(request.headers.get('Cookie'), SESSION_COOKIE_NAME);
    const session = rawCookie ? await verifySessionToken(rawCookie, env, nowSec) : null;
    return jsonResponse({
      configured: true,
      authenticated: !!session,
      expiresAt: session ? session.exp : null,
      pubkeyPrefix: pubHex.slice(0, 12),
      keyMatchesOfficial,
      serverTime: nowSec,
    });
  }

  // All remaining routes require POST + same-origin + CSRF header.
  if (request.method !== 'POST') {
    return jsonResponse({ error: 'method_not_allowed' }, 405);
  }
  const guard = verifySameOriginAndCsrf(request, url);
  if (!guard.ok) {
    return jsonResponse({ error: guard.error }, guard.status);
  }

  // 2) Logout (POST /api/ai-console/logout)
  if (path === '/api/ai-console/logout') {
    return jsonResponse(
      { ok: true },
      200,
      { 'Set-Cookie': buildCookieHeader('', 0, isHttps) },
    );
  }

  if (!configured) {
    return jsonResponse({
      error: 'not_configured',
      message: '后台环境变量尚未配置完成，请先在 Cloudflare Pages 控制台添加必需 Secret。',
      missingSecrets: missing,
    }, 503);
  }

  // 3) Login (POST /api/ai-console/login)
  if (path === '/api/ai-console/login') {
    const ip = request.headers.get('CF-Connecting-IP') || request.headers.get('X-Forwarded-For') || 'unknown';
    const rl = checkRateLimit(ip, nowMs);
    if (rl.blocked) {
      return jsonResponse(
        {
          error: 'rate_limited',
          message: `失败次数过多，请 ${rl.retryAfterSec} 秒后重试`,
          retryAfterSec: rl.retryAfterSec,
        },
        429,
        { 'Retry-After': String(rl.retryAfterSec) },
      );
    }

    const parsed = await readBoundedJson(request);
    if (parsed.error) return jsonResponse({ error: parsed.error }, parsed.status);

    const { password, totp, shortSession } = parsed.data;
    const pwOk = await verifyAdminPassword(password, env);
    const totpCheck = await verifyTotp(env.AI_LAB_TOTP_SECRET, totp, nowMs);
    const replayed = totpCheck.ok && totpCheck.matchedStep <= lastUsedTotpStep;

    if (!pwOk || !totpCheck.ok || replayed) {
      recordLoginFailure(ip, nowMs);
      if (!runtimeOpts.skipFailureDelay) {
        await new Promise((r) => setTimeout(r, 350));
      }
      return jsonResponse(
        {
          error: replayed ? 'totp_replayed' : 'invalid_credentials',
          message: replayed
            ? '该 6 位动态验证码刚使用过，请等待下一轮（约 30 秒）新码后重试'
            : '管理员密码或 6 位动态验证码不正确',
        },
        401,
      );
    }

    lastUsedTotpStep = totpCheck.matchedStep;
    clearLoginFailures(ip);
    const ttlSec = shortSession ? SHORT_SESSION_TTL_SEC : DEFAULT_SESSION_TTL_SEC;
    const { token, payload } = await createSessionToken(env, ttlSec, nowSec);
    return jsonResponse(
      {
        ok: true,
        expiresAt: payload.exp,
        pubkeyPrefix: pubHex.slice(0, 12),
        keyMatchesOfficial,
      },
      200,
      { 'Set-Cookie': buildCookieHeader(token, ttlSec, isHttps) },
    );
  }

  // Protected endpoints require a valid signed session cookie.
  const rawCookie = parseCookie(request.headers.get('Cookie'), SESSION_COOKIE_NAME);
  const session = rawCookie ? await verifySessionToken(rawCookie, env, nowSec) : null;
  if (!session) {
    return jsonResponse({ error: 'unauthorized', message: '登录会话已失效，请重新验证密码与动态码' }, 401);
  }

  // 4) Issue passcodes (POST /api/ai-console/issue)
  if (path === '/api/ai-console/issue') {
    const parsed = await readBoundedJson(request);
    if (parsed.error) return jsonResponse({ error: parsed.error }, parsed.status);

    const {
      plat = 'all',
      days = 30,
      tag = 'PILIPALA',
      shared = false,
      expOAuth = false,
      minVc = 0,
      count = 1,
      allowNonOfficialKey = false,
    } = parsed.data;

    if (!keyMatchesOfficial && !allowNonOfficialKey) {
      return jsonResponse(
        {
          error: 'key_mismatch',
          message: `当前配置的私钥对应公钥 (${pubHex.slice(0, 12)}...) 与官方内置公钥不一致，已阻止签发`,
        },
        409,
      );
    }

    const batchCount = Number(count);
    if (!Number.isInteger(batchCount) || batchCount < 1 || batchCount > MAX_BATCH_COUNT) {
      return jsonResponse(
        { error: 'invalid_count', message: `单次签发数量需为 1–${MAX_BATCH_COUNT} 之间的整数` },
        400,
      );
    }

    try {
      const tokens = [];
      for (let i = 0; i < batchCount; i++) {
        const issued = await issueAiLabToken(seed, {
          plat,
          days: Number(days),
          tag,
          shared: Boolean(shared),
          expOAuth: Boolean(expOAuth),
          minVc: Number(minVc || 0),
          nowEpoch: nowSec,
        });
        tokens.push(issued);
      }
      return jsonResponse({
        ok: true,
        issuedAt: nowSec,
        pubkeyPrefix: pubHex.slice(0, 12),
        keyMatchesOfficial,
        tokens,
      });
    } catch (err) {
      return jsonResponse({ error: 'invalid_params', message: err.message || '参数校验失败' }, 400);
    }
  }

  // 5) Verify passcode (POST /api/ai-console/verify)
  if (path === '/api/ai-console/verify') {
    const parsed = await readBoundedJson(request);
    if (parsed.error) return jsonResponse({ error: parsed.error }, parsed.status);

    const { tokenText, platform } = parsed.data;
    const officialPubBytes = hexToBytes(OFFICIAL_PUBKEY_HEX);
    const result = await verifyAiLabToken(tokenText, officialPubBytes, {
      nowEpoch: nowSec,
      platform: platform || null,
    });
    return jsonResponse({ ok: true, result });
  }

  return jsonResponse({ error: 'not_found' }, 404);
}

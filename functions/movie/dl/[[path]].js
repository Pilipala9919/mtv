// Copyright (C) 2026 Pilipala
// SPDX-License-Identifier: GPL-3.0-only

const TAG_RE = /^(?:(?:ios|windows|macos|android-tv|android-mobile|android-lite)-)?v\d+\.\d+\.\d+(?:-preview)?$/;
const FILE_RE = /^MarcoMovie-\d+\.\d+\.\d+-[A-Za-z0-9._-]+(?:\.apk|\.ipa|\.exe|\.zip)(?:\.sha256)?$/;
const PASSTHROUGH_HEADERS = [
  'accept-ranges',
  'content-length',
  'content-range',
  'etag',
  'last-modified',
];

function contentTypeFor(file) {
  if (file.endsWith('.sha256')) return 'text/plain; charset=utf-8';
  if (file.endsWith('.apk')) return 'application/vnd.android.package-archive';
  if (file.endsWith('.zip')) return 'application/zip';
  return 'application/octet-stream';
}

export async function onRequest({ request, params }) {
  if (request.method !== 'GET' && request.method !== 'HEAD') {
    return new Response('Method Not Allowed', { status: 405 });
  }
  const segments = Array.isArray(params.path) ? params.path : [];
  if (segments.length !== 2) {
    return new Response('Not Found', { status: 404 });
  }
  const [tag, file] = segments;
  if (!TAG_RE.test(tag) || !FILE_RE.test(file)) {
    return new Response('Not Found', { status: 404 });
  }
  const upstreamUrl = `https://github.com/Pilipala9919/MarcoMovie/releases/download/${tag}/${file}`;
  const reqHeaders = new Headers({
    'User-Agent': 'MarcoMovie-Mirror-Edge/1.0',
  });
  for (const h of ['range', 'if-range', 'if-none-match', 'if-modified-since']) {
    const v = request.headers.get(h);
    if (v) reqHeaders.set(h, v);
  }
  const upstream = await fetch(upstreamUrl, {
    method: request.method,
    headers: reqHeaders,
    redirect: 'follow',
    cf: { cacheEverything: true, cacheTtlByStatus: { '200-299': 86400, 404: 60 } },
  });
  if (!upstream.ok && upstream.status !== 206 && upstream.status !== 304) {
    return Response.redirect(upstreamUrl, 302);
  }
  const resHeaders = new Headers();
  for (const h of PASSTHROUGH_HEADERS) {
    const v = upstream.headers.get(h);
    if (v) resHeaders.set(h, v);
  }
  resHeaders.set('Content-Type', contentTypeFor(file));
  resHeaders.set('Content-Disposition', `attachment; filename="${file}"`);
  resHeaders.set('Cache-Control', 'public, max-age=31536000, immutable');
  resHeaders.set('X-Content-Type-Options', 'nosniff');
  return new Response(request.method === 'HEAD' ? null : upstream.body, {
    status: upstream.status,
    headers: resHeaders,
  });
}

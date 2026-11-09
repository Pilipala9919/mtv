// Copyright (C) 2026 Pilipala
// SPDX-License-Identifier: GPL-3.0-only

const REPO = 'Pilipala9919/MarcoMovie';
const FILE_RE = /^MarcoMovie-(\d+\.\d+\.\d+)-([A-Za-z0-9._-]+)\.(apk|ipa|exe|zip)(\.sha256)?$/;
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

function candidateTargets(version, rest, ext, shaSuffix) {
  const stem = `${rest}.${ext}`;
  const requested = `MarcoMovie-${version}-${stem}${shaSuffix}`;
  if (stem === 'android-tv.apk' || stem === 'preview.apk') {
    const editionFile = `MarcoMovie-${version}-android-tv.apk${shaSuffix}`;
    const legacyFile = `MarcoMovie-${version}-preview.apk${shaSuffix}`;
    return [
      ['android-tv-v' + version, editionFile],
      ['android-tv-v' + version + '-preview', editionFile],
      ['v' + version + '-preview', legacyFile],
      ['v' + version, legacyFile],
    ];
  }
  if (stem === 'android-mobile.apk' || stem === 'mobile.apk') {
    const editionFile = `MarcoMovie-${version}-android-mobile.apk${shaSuffix}`;
    const legacyFile = `MarcoMovie-${version}-mobile.apk${shaSuffix}`;
    return [
      ['android-mobile-v' + version, editionFile],
      ['android-mobile-v' + version + '-preview', editionFile],
      ['v' + version + '-preview', legacyFile],
      ['v' + version, legacyFile],
    ];
  }
  if (stem === 'android-lite.apk' || stem === 'lite.apk') {
    const editionFile = `MarcoMovie-${version}-android-lite.apk${shaSuffix}`;
    const legacyFile = `MarcoMovie-${version}-lite.apk${shaSuffix}`;
    return [
      ['android-lite-v' + version, requested],
      ['android-lite-v' + version, editionFile],
      ['v' + version + '-preview', legacyFile],
      ['v' + version, legacyFile],
    ];
  }
  if (stem.startsWith('windows-')) {
    return [
      ['windows-v' + version, requested],
      ['windows-v' + version + '-preview', requested],
      ['v' + version + '-preview', requested],
      ['v' + version, requested],
    ];
  }
  if (stem.startsWith('macos')) {
    return [
      ['macos-v' + version, requested],
      ['macos-v' + version + '-preview', requested],
      ['v' + version + '-preview', requested],
      ['v' + version, requested],
    ];
  }
  if (stem.startsWith('ios')) {
    return [
      ['ios-v' + version + '-preview', requested],
      ['ios-v' + version, requested],
      ['v' + version + '-preview', requested],
      ['v' + version, requested],
    ];
  }
  return [
    ['v' + version + '-preview', requested],
    ['v' + version, requested],
  ];
}

export async function onRequest(context) {
  const { request, params, next } = context;
  const file = typeof params.file === 'string' ? params.file : '';
  const match = FILE_RE.exec(file);
  if (!match) {
    return next();
  }
  if (request.method !== 'GET' && request.method !== 'HEAD') {
    return new Response('Method Not Allowed', { status: 405 });
  }
  if (
    file.endsWith('.sha256') ||
    file.includes('-lite.apk') ||
    file.includes('-android-lite.apk') ||
    file.includes('-source.zip')
  ) {
    const staticResp = await next();
    if (staticResp.ok || staticResp.status === 206 || staticResp.status === 304) {
      return staticResp;
    }
  }
  const [, version, rest, ext, shaPart] = match;
  const shaSuffix = shaPart || '';
  const reqHeaders = new Headers({
    'User-Agent': 'MarcoMovie-Mirror-Edge/1.0',
    'Accept-Encoding': 'identity',
  });
  for (const h of ['range', 'if-range', 'if-none-match', 'if-modified-since']) {
    const v = request.headers.get(h);
    if (v) reqHeaders.set(h, v);
  }
  const targets = candidateTargets(version, rest, ext, shaSuffix);
  const seen = new Set();
  for (const [tag, targetFile] of targets) {
    const upstreamUrl = `https://github.com/${REPO}/releases/download/${tag}/${targetFile}`;
    if (seen.has(upstreamUrl)) continue;
    seen.add(upstreamUrl);
    const upstream = await fetch(upstreamUrl, {
      method: request.method,
      headers: reqHeaders,
      redirect: 'follow',
      cf: { cacheEverything: true, cacheTtlByStatus: { '200-299': 86400, 404: 60 } },
    });
    if (upstream.ok || upstream.status === 206 || upstream.status === 304) {
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
  }
  return new Response('Not Found', { status: 404 });
}

// Copyright (C) 2026 Pilipala
// SPDX-License-Identifier: GPL-3.0-only

// Mirror-edge proxy for Marco TV dynamic wallpapers.
// Serves /wallpapers/dl/<tag>/<file> by fetching the matching asset from
// the MarcoTV GitHub Release, so the TV app downloads over the mirror
// domain instead of github.com. Only the allow-listed wallpaper releases
// and HEVC files are proxied; everything else is a 404. The 4K60 HEVC
// files are ~62 MB each, over the 25 MB Pages static-file limit, so they
// cannot live in the repo itself.
const REPO = 'Pilipala9919/MarcoTV';
const TAG_RE = /^wallpapers-3d-pets-v\d+$/;
const FILE_RE = /^(GoldenRetriever|Panda|AlaskanMalamute|Westie|BlackMameShiba|BrownMameShiba)_4K60_Loop_HEVC\.mp4$/;
const PASSTHROUGH_HEADERS = [
  'accept-ranges',
  'content-length',
  'content-range',
  'etag',
  'last-modified',
];

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
  const upstreamUrl = `https://github.com/${REPO}/releases/download/${tag}/${file}`;
  const reqHeaders = new Headers({
    'User-Agent': 'MarcoTV-Mirror-Edge/1.0',
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
  resHeaders.set('Content-Type', 'video/mp4');
  resHeaders.set('Cache-Control', 'public, max-age=31536000, immutable');
  resHeaders.set('X-Content-Type-Options', 'nosniff');
  return new Response(request.method === 'HEAD' ? null : upstream.body, {
    status: upstream.status,
    headers: resHeaders,
  });
}

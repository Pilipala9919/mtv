// Exercise the real edge handler without network access.
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';

const source = await readFile(new URL('../functions/movie/[file].js', import.meta.url), 'utf8');
const { onRequest } = await import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`);
const originalFetch = globalThis.fetch;
let checks = 0;
try {
  for (const method of ['GET', 'HEAD']) {
    for (const suffix of ['', '.sha256']) {
      for (const names of [
        ['ios-unsigned.ipa', 'ios-iphone-ipad-unsigned.ipa'],
        ['ios-iphone-ipad-unsigned.ipa', 'ios-unsigned.ipa'],
      ]) {
        const file = `MarcoMovie-0.5.14-${names[0]}${suffix}`;
        const alternate = `MarcoMovie-0.5.14-${names[1]}${suffix}`;
        const calls = [];
        globalThis.fetch = async (url, options) => {
          calls.push({ url, options });
          return calls.length === 1
            ? new Response(null, { status: 404 })
            : new Response(method === 'HEAD' ? null : 'verified-package', {
              status: 206,
              headers: { 'content-range': 'bytes 0-15/16' },
            });
        };
        const response = await onRequest({
          request: new Request(`https://example.invalid/movie/${file}`, {
            method, headers: { range: 'bytes=0-15' },
          }),
          params: { file },
          next: async () => new Response(null, { status: 404 }),
        });
        assert.equal(response.status, 206);
        assert.equal(calls.length, 2);
        assert.equal(calls[0].url, `https://github.com/Pilipala9919/MarcoMovie/releases/download/ios-v0.5.14/${file}`);
        assert.equal(calls[1].url, `https://github.com/Pilipala9919/MarcoMovie/releases/download/ios-v0.5.14/${alternate}`);
        assert.equal(calls[1].options.method, method);
        assert.equal(calls[1].options.headers.get('range'), 'bytes=0-15');
        assert.equal(response.headers.get('content-range'), 'bytes 0-15/16');
        if (method === 'HEAD') assert.equal(await response.text(), '');
        checks++;
      }
    }
  }
} finally {
  globalThis.fetch = originalFetch;
}
console.log(`Movie proxy: ${checks} alias, checksum, range and HEAD checks passed.`);

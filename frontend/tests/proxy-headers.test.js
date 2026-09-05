import test from 'node:test';
import assert from 'node:assert/strict';

import { proxyRequestHeaders } from '../scripts/proxy-headers.mjs';

test('the proxy preserves the content length for requests with a body', () => {
  assert.deepEqual(
    proxyRequestHeaders({
      'content-type': 'application/json',
      'content-length': '72',
      authorization: 'not-forwarded',
    }),
    {
      'Content-Type': 'application/json',
      'Content-Length': '72',
    },
  );
});

test('the proxy does not invent body headers for bodyless requests', () => {
  assert.deepEqual(proxyRequestHeaders({ accept: 'application/json' }), {});
});

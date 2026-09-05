import test from 'node:test';
import assert from 'node:assert/strict';

import { requestJSON } from '../public/backend-client.js';


test('requestJSON preserves structured stock conflicts', async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => ({
    ok: false,
    status: 409,
    json: async () => ({
      detail: {
        code: 'stock_unavailable',
        message: 'Not enough stock for chicken_rice.',
        item_id: 'chicken_rice',
        requested_quantity: 3,
        available_quantity: 2,
      },
    }),
  });

  try {
    await assert.rejects(
      requestJSON('/stock'),
      error => error.message === 'Not enough stock for chicken_rice.'
        && error.status === 409
        && error.code === 'stock_unavailable'
        && error.itemId === 'chicken_rice'
        && error.requestedQuantity === 3
        && error.availableQuantity === 2,
    );
  } finally {
    globalThis.fetch = originalFetch;
  }
});

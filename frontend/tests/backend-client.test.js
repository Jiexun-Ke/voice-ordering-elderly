import test from 'node:test';
import assert from 'node:assert/strict';

import {
  BackendOrder,
  canCancelLine,
  isMenuItemAvailable,
  kitchenStatusClass,
  kitchenStatusLabel,
  requestJSON,
} from '../public/backend-client.js';


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

test('menu availability helpers mark zero stock unavailable', () => {
  assert.equal(isMenuItemAvailable({ available: true, remaining_stock: 4 }), true);
  assert.equal(isMenuItemAvailable({ available: true, remaining_stock: 0 }), false);
  assert.equal(isMenuItemAvailable({ available: false, remaining_stock: 4 }), false);
});

test('kitchen status labels and cancellation controls follow the backend state', () => {
  assert.equal(kitchenStatusLabel('received'), 'ORDER RECEIVED');
  assert.equal(kitchenStatusLabel('preparing'), 'IN PREPARATION');
  assert.equal(kitchenStatusLabel('done'), 'DONE');
  assert.equal(kitchenStatusClass('preparing'), 'preparing');
  assert.equal(canCancelLine({ sent: false }), true);
  assert.equal(canCancelLine({ sent: true, kitchen_status: 'received' }), true);
  assert.equal(canCancelLine({ sent: true, kitchen_status: 'preparing' }), false);
  assert.equal(canCancelLine({ sent: true, kitchen_status: 'done' }), false);
});

test('BackendOrder refreshMenu replaces stale availability', async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async path => {
    assert.equal(path, '/api/order/menu');
    return {
      ok: true,
      status: 200,
      json: async () => ({
        items: [{
          id: 'kopi', name: 'Kopi', price: 1.4, category: 'Drinks', modifier_groups: [],
          available: false, remaining_stock: 0,
        }],
      }),
    };
  };

  try {
    const order = new BackendOrder();
    order.items = [{ id: 'kopi', available: true, remaining_stock: 1 }];
    await order.refreshMenu();
    assert.equal(order.items[0].available, false);
    assert.equal(order.items[0].remaining_stock, 0);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

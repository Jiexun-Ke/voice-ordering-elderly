import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { DemoOrder, interpret, prepareMenu } from '../public/demo-model.js';

const items = prepareMenu(JSON.parse(readFileSync(new URL('../public/sample-menu.json', import.meta.url))));

test('menu and chat choices use one total in exact cents', () => {
  const order = new DemoOrder(items);
  order.add('CHICKEN_RICE');
  const intent = interpret('one kopi, less sweet', items);
  assert.equal(intent.type, 'add');
  for (const line of intent.additions) order.add(line.id, line.quantity, line.options);
  assert.equal(order.total, 570);
  assert.equal(order.count, 2);
  assert.equal(order.lines[1].options.sweetness, 'less');
});

test('longer drink names win over the plain kopi alias', () => {
  const result = interpret('two kopi c, less sweet', items);
  assert.deepEqual(result.additions.map(i => [i.id, i.quantity]), [['KOPI_C', 2]]);
});

test('multi-item and Chinese requests keep quantities and preferences', () => {
  assert.deepEqual(interpret('two chicken rice and one kopi c, less sweet', items).additions.map(i=>[i.id,i.quantity]), [['CHICKEN_RICE',2],['KOPI_C',1]]);
  const result=interpret('我要一杯咖啡，少糖',items);
  assert.equal(result.additions[0].options.sweetness,'less');
  assert.equal(result.additions[0].quantity,1);
});

test('questions, commentary and uncertain interest never add food', () => {
  for (const text of ['What is kopi?', 'How much is chicken rice?', 'I have had two kopi today', 'Maybe one kopi', 'Do not add one kopi', 'I am not sure about one kopi']) {
    assert.notEqual(interpret(text,items).type,'add',text);
  }
});

test('budget queries use listed prices and respect an exclusive limit', () => {
  const result=interpret('under $5',items);
  assert.equal(result.type,'list');
  assert.ok(result.ids.includes('CHICKEN_RICE'));
  assert.ok(!result.ids.includes('CHAR_KWAY_TEOW'));
  assert.ok(!result.ids.includes('LAKSA'));
});

test('preference edits merge matching lines without losing quantities', () => {
  const order=new DemoOrder(items);
  const first=order.add('KOPI',1,{sweetness:'less'});
  order.add('KOPI',2);
  order.edit(first,1,{sweetness:'normal',temperature:'hot'});
  assert.equal(order.lines.length,1);
  assert.equal(order.count,3);
  assert.equal(order.total,360);
});

test('invalid quantities and options preserve existing cart state', () => {
  const order=new DemoOrder(items);
  const key=order.add('KOPI',20);
  const before=JSON.stringify(order.lines);
  assert.throws(()=>order.add('KOPI',1));
  assert.throws(()=>order.edit(key,0,{}));
  assert.throws(()=>order.add('KOPI',1,{chilli:'no'}));
  assert.throws(()=>order.add('UNKNOWN'));
  assert.equal(JSON.stringify(order.lines),before);
  assert.equal(interpret('0 kopi',items).type,'quantityError');
  assert.equal(interpret('99 kopi',items).type,'quantityError');
});

test('confirmation requires a nonempty order and changes return it to draft', () => {
  const order=new DemoOrder(items);
  assert.throws(()=>order.confirm());
  const key=order.add('CHICKEN_RICE');order.confirm();
  assert.equal(order.confirmed,true);
  order.edit(key,2,{chilli:'regular'});
  assert.equal(order.confirmed,false);
  assert.equal(order.total,900);
  order.remove(key);
  assert.equal(order.total,0);
  assert.equal(order.count,0);
});

test('dietary questions do not invent reliable ingredient claims', () => {
  assert.equal(interpret('Is chicken rice safe for a peanut allergy?',items).type,'unknownDetails');
});

test('an unknown extra dish does not result in a partially added order', () => {
  assert.notEqual(interpret('one kopi and one burger',items).type,'add');
});

test('negative spice preferences do not remove a dish', () => {
  for (const text of ['one chicken rice dont want chilli', '我要一份鸡饭，不要辣']) {
    // The Chinese name in the demo is 海南鸡饭; the English source catalogue
    // does not have a 鸡饭 alias, so the shorter phrase can safely fall back.
    assert.notEqual(interpret(text,items).type,'remove');
  }
  const result=interpret('one chicken rice dont want chilli',items);
  assert.equal(result.type,'add');
  assert.equal(result.additions[0].options.chilli,'no');
});

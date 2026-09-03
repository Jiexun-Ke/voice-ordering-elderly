import test from 'node:test';
import assert from 'node:assert/strict';
import { encodeWav } from '../public/audio-wav.js';

test('48 kHz microphone chunks become bounded 16 kHz mono PCM WAV',async()=>{
  const blob=encodeWav([new Float32Array(24000).fill(.5),new Float32Array(24000).fill(-.5)],48000);
  const data=new DataView(await blob.arrayBuffer());
  assert.equal(data.getUint32(24,true),16000);
  assert.equal(data.getUint16(22,true),1);
  assert.equal(data.getUint16(34,true),16);
  assert.equal(data.getUint32(40,true),32000);
  assert.equal(data.getInt16(44,true),16383);
  assert.equal(data.getInt16(44+16000,true),-16384);
});

test('short clips cannot be mistaken for speech and long captures are capped',async()=>{
  assert.throws(()=>encodeWav([new Float32Array(100)],48000),/no-speech/);
  const blob=encodeWav([new Float32Array(16000*46)],16000);
  assert.equal(blob.size,44+45*16000*2);
});

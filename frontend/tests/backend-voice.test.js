import test from 'node:test';
import assert from 'node:assert/strict';
import { createBackendVoice } from '../public/backend-voice.js';

function setup(t, {getMedia, respond}={}) {
  const saved=Object.fromEntries(['window','navigator','AudioContext','AudioWorkletNode','fetch'].map(key=>[key,Object.getOwnPropertyDescriptor(globalThis,key)]));
  t.after(()=>{for(const [key,descriptor] of Object.entries(saved)){if(descriptor)Object.defineProperty(globalThis,key,descriptor);else delete globalThis[key];}});
  const track={stopped:false,stop(){this.stopped=true;}}, stream={getTracks:()=>[track],getAudioTracks:()=>[track]}, nodes=[], calls=[];
  class Context {
    constructor(){this.sampleRate=16000;this.audioWorklet={addModule:async()=>{}};}
    async resume(){} async close(){}
    createMediaStreamSource(){return {connect(){},disconnect(){}};}
  }
  class Worklet {constructor(){this.port={};nodes.push(this);}connect(){}disconnect(){}}
  const values={window:{AudioContext:Context},AudioContext:Context,AudioWorkletNode:Worklet,navigator:{mediaDevices:{getUserMedia:getMedia||async function(){return stream;}}},fetch:async(path,options)=>{
    calls.push({path,options});return respond?respond():{ok:true,json:async()=>({text:'hello',low_confidence:false})};
  }};
  for(const [key,value] of Object.entries(values))Object.defineProperty(globalThis,key,{configurable:true,writable:true,value});
  const states=[],voice=createBackendVoice({onChange:state=>states.push(state)});
  t.after(()=>voice.cancel());
  return {voice,states,track,stream,nodes,calls};
}

test('microphone PCM is uploaded to STT and the returned hello stays reviewable',async t=>{
  const {voice,track,nodes,calls}=setup(t);
  await voice.start({initialText:'draft'});
  assert.equal(voice.state.phase,'listening');
  nodes[0].port.onmessage({data:new Float32Array(16000)});
  await voice.stop();
  assert.equal(track.stopped,true);
  assert.equal(calls.length,1);
  assert.equal(calls[0].path,'/api/stt/transcribe');
  assert.equal(calls[0].options.body.get('audio').type,'audio/wav');
  assert.equal(voice.state.phase,'ready');
  assert.equal(voice.state.transcript,'draft hello');
});

test('permission denial gives an error without sending audio',async t=>{
  const {voice,calls}=setup(t,{getMedia:async()=>{throw Object.assign(new Error(),{name:'NotAllowedError'});}});
  await voice.start();
  assert.equal(voice.state.error,'not-allowed');
  assert.equal(calls.length,0);
});

test('cancelling while permission is pending stops the eventual stream',async t=>{
  let grant;
  const permission=new Promise(resolve=>{grant=resolve;});
  const {voice,stream,track,calls}=setup(t,{getMedia:()=>permission});
  const starting=voice.start();await Promise.resolve();voice.cancel();grant(stream);await starting;
  assert.equal(track.stopped,true);
  assert.equal(voice.state.phase,'idle');
  assert.equal(calls.length,0);
});

test('a missing speech backend preserves typed text and releases the microphone',async t=>{
  const {voice,nodes,track}=setup(t,{respond:()=>({ok:false,status:503,json:async()=>({detail:'engine not ready'})})});
  await voice.start({initialText:'one kopi'});nodes[0].port.onmessage({data:new Float32Array(16000)});await voice.stop();
  assert.equal(voice.state.error,'backend-unavailable');
  assert.equal(voice.state.transcript,'one kopi');
  assert.equal(track.stopped,true);
});

test('cancelling transcription ignores a late backend reply',async t=>{
  let respond;const pending=new Promise(resolve=>{respond=resolve;});
  let began;const uploading=new Promise(resolve=>{began=resolve;});
  const {voice,nodes,calls}=setup(t,{respond:()=>{began();return pending;}});
  await voice.start();nodes[0].port.onmessage({data:new Float32Array(16000)});
  const stopped=voice.stop();await uploading;
  voice.cancel();respond({ok:true,json:async()=>({text:'unwanted late result'})});await stopped;
  assert.equal(calls[0].options.signal.aborted,true);
  assert.equal(voice.state.phase,'idle');
  assert.equal(voice.state.transcript,'');
});

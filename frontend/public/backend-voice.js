import { encodeWav } from './audio-wav.js';

export function createBackendVoice({onChange}) {
  let state={phase:'idle',transcript:'',error:null}, session=null, generation=0;
  const publish=patch=>{state={...state,...patch};onChange({...state});};
  function release(current){
    if(!current)return;
    clearTimeout(current.timer);current.controller.abort();
    current.stream?.getTracks().forEach(track=>track.stop());
    if(current.node){current.node.port.onmessage=null;current.node.disconnect();}
    current.source?.disconnect();
    current.context?.close().catch(()=>{});
  }
  function cancel(){generation++;release(session);session=null;publish({phase:'idle',error:null});}
  function fail(error,current){
    if(current!==session)return;
    generation++;release(current);session=null;publish({phase:'error',error});
  }
  async function start({initialText=''}={}){
    cancel();const token=++generation;
    const current={controller:new AbortController(),chunks:[],prefix:initialText.trim()};session=current;
    publish({phase:'starting',transcript:initialText,error:null,lowConfidence:false});
    if(!navigator.mediaDevices?.getUserMedia||!window.AudioContext){fail('unsupported',current);return;}
    current.timer=setTimeout(()=>fail('start-timeout',current),30000);
    try{
      // Resume inside the user's click gesture, before awaiting permission.
      current.context=new AudioContext();await current.context.resume();
      const stream=await navigator.mediaDevices.getUserMedia({audio:{channelCount:1,echoCancellation:true,noiseSuppression:true},video:false});
      if(token!==generation){stream.getTracks().forEach(track=>track.stop());return;}
      current.stream=stream;
      await current.context.audioWorklet.addModule('/pcm-recorder.js');
      if(token!==generation)return;
      current.source=current.context.createMediaStreamSource(stream);
      current.node=new AudioWorkletNode(current.context,'pcm-recorder');
      current.node.port.onmessage=event=>{if(token===generation)current.chunks.push(event.data);};
      // The processor emits silence, so the microphone is never played back.
      current.source.connect(current.node);current.node.connect(current.context.destination);
      stream.getAudioTracks()[0].onended=()=>{if(state.phase==='listening')fail('audio-capture',current);};
      clearTimeout(current.timer);current.timer=setTimeout(stop,45000);
      publish({phase:'listening'});
    }catch(error){if(token===generation)fail(error.name==='NotAllowedError'?'not-allowed':error.name==='NotFoundError'?'audio-capture':'unknown',current);}
  }
  async function stop(){
    if(state.phase!=='listening'||!session)return;
    const current=session, token=generation;
    publish({phase:'processing'});clearTimeout(current.timer);
    current.stream.getTracks().forEach(track=>track.stop());
    current.source.disconnect();current.node.port.onmessage=null;current.node.disconnect();
    const rate=current.context.sampleRate;await current.context.close().catch(()=>{});
    if(token!==generation)return;
    try{
      const audio=encodeWav(current.chunks,rate);current.chunks=[];
      const form=new FormData();form.append('audio',audio,'message.wav');
      current.timer=setTimeout(()=>fail('timeout',current),120000);
      const response=await fetch('/api/stt/transcribe',{method:'POST',body:form,signal:current.controller.signal});
      if(token!==generation)return;
      const result=await response.json();
      if(!response.ok){fail(response.status===503?'backend-unavailable':response.status===502?'backend-offline':'backend-error',current);return;}
      const transcript=result.text?.trim();
      if(!transcript){fail('no-speech',current);return;}
      clearTimeout(current.timer);session=null;
      publish({phase:'ready',transcript:[current.prefix,transcript].filter(Boolean).join(' ').slice(0,400),error:null,lowConfidence:!!result.low_confidence});
    }catch(error){if(token===generation)fail(error.message==='no-speech'?'no-speech':'backend-offline',current);}
  }
  return {start,stop,cancel,get state(){return {...state};}};
}

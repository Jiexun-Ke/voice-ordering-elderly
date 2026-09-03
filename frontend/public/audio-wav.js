// Encode captured mono PCM as 16 kHz WAV; the backend needs no ffmpeg.
export function encodeWav(chunks, sampleRate) {
  const length=chunks.reduce((total,chunk)=>total+chunk.length,0);
  const samples=new Float32Array(length);let offset=0;
  for(const chunk of chunks){samples.set(chunk,offset);offset+=chunk.length;}
  if(length/sampleRate<.35)throw new Error('no-speech');
  const frames=Math.min(45*16000,Math.floor(length*16000/sampleRate));
  const buffer=new ArrayBuffer(44+frames*2), view=new DataView(buffer);
  const text=(offset,value)=>{for(let i=0;i<value.length;i++)view.setUint8(offset+i,value.charCodeAt(i));};
  text(0,'RIFF');view.setUint32(4,36+frames*2,true);text(8,'WAVE');text(12,'fmt ');
  view.setUint32(16,16,true);view.setUint16(20,1,true);view.setUint16(22,1,true);
  view.setUint32(24,16000,true);view.setUint32(28,32000,true);view.setUint16(32,2,true);view.setUint16(34,16,true);
  text(36,'data');view.setUint32(40,frames*2,true);
  for(let i=0;i<frames;i++){
    const source=i*sampleRate/16000, index=Math.floor(source), blend=source-index;
    const value=Math.max(-1,Math.min(1,samples[index]*(1-blend)+(samples[Math.min(index+1,length-1)]||0)*blend));
    view.setInt16(44+i*2,value*(value<0?32768:32767),true);
  }
  return new Blob([buffer],{type:'audio/wav'});
}

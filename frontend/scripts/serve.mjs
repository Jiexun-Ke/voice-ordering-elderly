import http from 'node:http';
import { readFile } from 'node:fs/promises';
import { proxyRequestHeaders } from './proxy-headers.mjs';
const built = process.argv.includes('--built');
const root = new URL(built ? '../dist/' : '../', import.meta.url);
const routes = {
  '/': new URL('index.html', root),
  '/index.html': new URL('index.html', root),
  '/styles.css': new URL('styles.css', root),
  '/app.js': new URL('app.js', root),
  '/ordering.js': new URL(built ? 'ordering.js' : 'public/ordering.js', root),
  '/demo-model.js': new URL(built ? 'demo-model.js' : 'public/demo-model.js', root),
  ...Object.fromEntries(['backend-client.js','backend-voice.js','audio-wav.js','pcm-recorder.js'].map(file=>['/'+file,new URL(built?file:'public/'+file,root)])),
  '/ordering.css': new URL(built ? 'ordering.css' : 'public/ordering.css', root),
  '/favicon.svg': new URL(built ? 'favicon.svg' : 'public/favicon.svg', root),
  '/og.png': new URL(built ? 'og.png' : 'public/og.png', root),
  '/sample-menu.json': new URL(built ? 'sample-menu.json' : '../data/catalogues/hawker.json', root),
};
const types = { html: 'text/html; charset=utf-8', css: 'text/css; charset=utf-8', js: 'text/javascript; charset=utf-8', json: 'application/json; charset=utf-8', svg: 'image/svg+xml', png: 'image/png' };
const port = Number(process.env.PORT || 5173);
const server = http.createServer(async (req, res) => {
  const requested = new URL(req.url, 'http://localhost');
  if(requested.pathname.startsWith('/api/')){
    const ordering=requested.pathname.startsWith('/api/order/');
    const speech=requested.pathname.startsWith('/api/stt/');
    if(!ordering&&!speech){res.writeHead(404).end();return;}
    const prefix=ordering?'/api/order':'/api/stt';
    const path=requested.pathname.slice(prefix.length);
    if(speech&&!['/health','/transcribe'].includes(path)){res.writeHead(404).end();return;}
    const upstream=http.request({hostname:'127.0.0.1',port:ordering?8001:8000,path:path+requested.search,method:req.method,headers:proxyRequestHeaders(req.headers),timeout:150000},response=>{
      res.writeHead(response.statusCode,{'Content-Type':response.headers['content-type']||'application/json','Cache-Control':'no-store'});response.pipe(res);
    });
    upstream.on('timeout',()=>upstream.destroy(new Error('Backend timed out')));
    upstream.on('error',()=>{if(!res.headersSent)res.writeHead(502,{'Content-Type':'application/json'}).end(JSON.stringify({detail:ordering?'The ordering backend is offline. Start it on port 8001 and retry.':'The speech backend is offline. Start it on port 8000 and retry.'}));else res.end();});
    let bytes=0;
    req.on('data',chunk=>{bytes+=chunk.length;if(bytes>8*1024*1024){if(!res.headersSent)res.writeHead(413,{'Content-Type':'application/json'}).end(JSON.stringify({detail:'Recording is too large. Please keep it under 45 seconds.'}));upstream.destroy();}});
    req.on('aborted',()=>upstream.destroy());req.pipe(upstream);return;
  }
  if (!['GET', 'HEAD'].includes(req.method)) { res.writeHead(405, { Allow: 'GET, HEAD' }).end(); return; }
  const path = new URL(req.url, 'http://localhost').pathname;
  const file = routes[path];
  if (!file) { res.writeHead(404).end('Not found'); return; }
  try {
    const body = await readFile(file);
    const type = types[file.pathname.split('.').pop()] || 'application/octet-stream';
    res.writeHead(200, { 'Content-Type': type, 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff' });
    res.end(req.method === 'HEAD' ? undefined : body);
  } catch {
    if (path === '/sample-menu.json' && !built) {
      try { const body = await readFile(new URL('public/sample-menu.json', root)); res.writeHead(200, { 'Content-Type': types.json, 'Cache-Control': 'no-store' }); res.end(req.method === 'HEAD' ? undefined : body); return; } catch { /* No catalogue snapshot. */ }
    }
    res.writeHead(404).end('Not found');
  }
});
server.listen(port, '127.0.0.1', () => console.log(`Local: http://localhost:${port}`));

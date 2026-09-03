import http from 'node:http';
import { readFile } from 'node:fs/promises';
const built = process.argv.includes('--built');
const root = new URL(built ? '../dist/' : '../', import.meta.url);
const routes = {
  '/': new URL('index.html', root),
  '/index.html': new URL('index.html', root),
  '/styles.css': new URL('styles.css', root),
  '/app.js': new URL('app.js', root),
  '/favicon.svg': new URL(built ? 'favicon.svg' : 'public/favicon.svg', root),
  '/og.png': new URL(built ? 'og.png' : 'public/og.png', root),
  '/sample-menu.json': new URL(built ? 'sample-menu.json' : '../data/catalogues/hawker.json', root),
};
const types = { html: 'text/html; charset=utf-8', css: 'text/css; charset=utf-8', js: 'text/javascript; charset=utf-8', json: 'application/json; charset=utf-8', svg: 'image/svg+xml', png: 'image/png' };
const port = Number(process.env.PORT || 5173);
const server = http.createServer(async (req, res) => {
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

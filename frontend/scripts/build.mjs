import { mkdir, copyFile, cp } from 'node:fs/promises';
const root = new URL('../', import.meta.url);
// Keep a source snapshot so the frontend can also build independently.
try {
  await copyFile(new URL('../data/catalogues/hawker.json', root), new URL('public/sample-menu.json', root));
} catch (error) {
  if (error.code !== 'ENOENT') throw error;
}
await mkdir(new URL('dist/', root), { recursive: true });
for (const file of ['index.html', 'styles.css', 'app.js']) {
  await copyFile(new URL(file, root), new URL(`dist/${file}`, root));
}
await cp(new URL('public/', root), new URL('dist/', root), { recursive: true });
console.log('Built frontend/dist with the project’s sample hawker catalogue.');

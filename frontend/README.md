# Menu helper frontend

The first, responsive **Open a menu** page. No package installation is needed; it uses browser-native HTML, CSS and JavaScript with a small Node development server.

```bash
cd frontend
npm run dev
```

Open http://localhost:5173. Keep this terminal running while using the preview.

```bash
npm run build
npm run preview
```

The build produces `dist/`, ready for static hosting. Both development and the build read the existing `../data/catalogues/hawker.json`; prices are not hardcoded in frontend code. The build refreshes `public/sample-menu.json` from that catalogue. This snapshot lets the frontend also run and build independently when the parent project is absent.

## Available now

- Responsive landing page, English/Chinese interface, keyboard navigation and accessible dialogs.
- Sample menu with the existing catalogue's dishes and prices.
- Menu link validation and local photo preview (nothing is uploaded).
- QR camera scanning on browsers with native `BarcodeDetector` QR support; a phone-camera/link fallback elsewhere. Camera use requires localhost or HTTPS and permission. Streams stop when the dialog closes or the page is hidden.
- Spoken help using the browser's available voices.

## Next integration step

Photo/link menu extraction, AI translation, conversational ordering and cart review are not connected. The first-page dialogs explain this rather than presenting an imported menu. The language switch translates interface labels only. No AI key or speech model is needed for this page.

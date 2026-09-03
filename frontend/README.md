# Menu helper frontend

The Open a menu page leads to **Menu / Chat / Order**, connected to the project's local speech service and ordering backend. The UI uses browser-native HTML, CSS and JavaScript; no npm dependency installation is needed.

## Start the connected website

Run these from the repository root, in three terminals:

```bash
# Terminal 1: local speech recognition (first run downloads Whisper Small)
STT_ENGINE=whisper .venv/bin/python -m uvicorn stt.server:app --host 127.0.0.1 --port 8000
```

```bash
# Terminal 2: ordering API, using the existing dialogue manager
.venv/bin/python -m uvicorn backend.server:app --host 127.0.0.1 --port 8001
```

```bash
# Terminal 3: website and local API proxy
cd frontend
npm run dev
```

Open [Chat](http://localhost:5173/#chat) or [Menu](http://localhost:5173/#menu). Keep all three terminals running. Refresh after editing source files; the development server has no hot reload.

For a fresh machine, create a virtual environment and install the Python requirements first:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt -r backend/requirements-web.txt
```

## What is connected

- **Menu:** fetched from the ordering backend's 12-item sample menu, including its actual modifier options. Its menu differs from the STT catalogue. Kopi-C and Kopi-O are milk choices under Kopi, not separate dishes. Optional choices affect server-calculated prices.
- **Voice:** Tap to speak → allow microphone access → wait for Listening → speak → Done speaking. AudioWorklet captures mono PCM, and the frontend uploads a 16 kHz WAV to `/api/stt/transcribe`. This avoids reliance on the browser's speech-recognition service and on ffmpeg. Recordings stop after 45 seconds and when you leave the page/tab; cancellation releases the microphone. Low-confidence text is marked for careful review.
- **Chat:** review/edit the transcript, then press Send. The text goes to the existing backend dialogue manager. Text and menu actions share one backend order. The STT service's parsed order is not silently applied; the reviewed transcript goes to the dialogue service, which owns the menu, follow-up questions, quantities and prices.
- **Order:** server-backed quantities, preference changes, removals and totals. Confirmation includes dine-in/takeaway and reaches the backend's **mock kitchen**. It does not submit to a real restaurant or charge money. Confirmed lines cannot be edited using the cart controls.
- **Listen:** uses the browser's installed text-to-speech voices to read menu items, replies and the order.
- **Sessions:** a session identifier in sessionStorage lets refreshes restore this tab's order and conversation. Backend sessions are in memory and are lost when its process restarts. The page reports an expired session and starts a fresh one on reload.
- **Failures:** visible backend errors retain the draft and last known cart. Retry connection reuses the same request ID, so retrying a lost response does not add the item twice. Audio errors keep typing available.

The interface and curated menu descriptions support English/Chinese. The dialogue manager currently understands English and Singlish; it is rule-based, not a general AI chatbot. Arbitrary menu-link/photo extraction and AI menu translation are still future work. The existing link/photo/QR opening page remains available.

## Try it

1. In Chat, send `hello` and check the backend reply.
2. Say or type `two kopi c, siew dai, takeaway`, review the text and send it. Order should show two Kopi with evaporated milk and less sugar, totalling **$2.80**.
3. Add Hainanese Chicken Rice from Menu. The shared total becomes **$7.30**.
4. Change quantities/preferences in Order, then review and confirm with the local demo kitchen.
5. Try `one fishball noodles` in a fresh session and answer the helper's question about noodle type.

If Voice ready is absent, use Check connection and inspect the speech terminal. Model loading may take time on the first run. Microphone access requires localhost or HTTPS and browser/OS permission. The default generic Whisper model may mishear Singlish, so always review the transcript.

## Checks and build

```bash
# From frontend/
npm test
npm run build
npm run preview
```

The build copies static assets to `dist/`. The included preview server provides the same local API proxy. A standalone static host needs its own `/api/order/*` and `/api/stt/*` routing to the Python services; deploying only `dist/` does not deploy those services.

```bash
# From the repository root
.venv/bin/python -m pytest tests/ -q
.venv/bin/python backend/test_features.py
```

Checks cover backend session isolation, shared menu/chat prices, clarification, idempotent retries, confirmation, WAV encoding, microphone cleanup, denied permission, unavailable services and cancellation races. Simulated microphone tests are separate from a real model transcription check; they do not establish recognition accuracy for a person's microphone.

## Files

- `public/ordering.js`: three-tab UI, preferences, transcript review and interactions.
- `public/backend-client.js`: menu/session API client; all cart mutations use the server.
- `public/backend-voice.js`, `public/pcm-recorder.js`, `public/audio-wav.js`: microphone capture and STT upload.
- `public/demo-model.js`: curated menu descriptions and the earlier standalone demo model; its parser does not handle connected orders.
- `scripts/serve.mjs`: local static server and same-origin API proxy to ports 8000/8001.
- `../backend/server.py`: HTTP adapter around the existing backend dialogue and mock-kitchen logic.

Photos are illustrative, externally hosted, and fall back to icons if unavailable. Credits are available from the Menu screen.

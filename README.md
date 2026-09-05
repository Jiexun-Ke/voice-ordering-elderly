# voice-ordering-elderly
Our Minimal viable product for the Agentic AI Hackathon - Developing a speech-based food ordering system for the less tech-savvy elderly

---

## Where the project is now

The website now connects **Menu / Chat / Order** to the local speech and ordering backends. Microphone recordings go to `POST /transcribe`; after the diner reviews the transcript and presses Send, the existing dialogue manager handles the message and updates the shared server order. Menu buttons, quantities, preferences and confirmation also use the ordering API. Draft cart changes are checked against live stock, confirmation rechecks stock before sending new lines to the kitchen, and accepted lines expose the `received` → `preparing` → `done` lifecycle. Kitchen submission remains a local mock. Photo/link menu analysis and AI translation are future work.

```
[Menu / Chat / Order] -> frontend API proxy -> [STT :8000] + [Ordering :8001]
                                             local model    dialogue + mock kitchen
```

See [frontend setup](frontend/README.md#start-the-connected-website) for the three local processes required to try the connected website.

Measured on an M4 Mac, speaking *"wo yao two kopi-c siew dai, da bao"*:

```
heard : Oh Yaw two Kopi C Siew Dai, Da Bao
order : 2x Kopi-C (siew dai) — takeaway        every field correct, ~2.6s
```

## Start here

- **Frontend:** start the speech and ordering services using the setup above, then run `cd frontend` and `npm run dev`, and open
  [localhost:5173](http://localhost:5173). No package installation is needed.
  See [`frontend/README.md`](frontend/README.md) for the available interactions.
- **Running it / API contract:** [`README_stt.md`](README_stt.md)
- **Picking up a task:** [Extension points](README_stt.md#extension-points-for-other-teammates)
- **The original CLI prototype:** `voice_ordering.py` (unchanged, still works)

Quick check that your machine is set up — no model download needed:

```bash
python -m pytest tests/ -q          # expect 100 passed
```

The complete stock/status walkthrough, including the local mock controls for
setting stock and advancing a kitchen ticket, is documented in the [backend
README](backend/README.md#local-stock-and-kitchen-status-demo).

## How the pieces fit

```
audio in
   |
   v
ASR engine        stt/engines/     swappable: singlish (default) | whisper | polyglot
   |                               the model is a config value, not a rewrite
   v
catalogue bias    stt/catalogue.py menu terms fed to the model BEFORE it decodes
   |
   v
fuzzy correction  stt/correct.py   "char kuey teow" -> CHAR_KWAY_TEOW after decoding
   |
   v
order parsing     stt/parse.py     quantity + item + modifiers + takeaway
   |
   v
order JSON        stt/server.py    what the backend consumes
```

The two layers that actually decide accuracy on menu terms are `catalogue.py`
and `correct.py`, not the model choice. Both are ours to improve, and neither
needs a GPU.

## What the STT service gives the rest of the team

**Frontend:** `POST /transcribe` with an audio blob. Show `readback` to the
diner for confirmation. Re-ask when `low_confidence` is `true`.

**Backend:** consume the `order` object — `{lines: [{canonical, display,
quantity, modifiers, price}], takeaway, total}`.

Full contract with an example response: [`README_stt.md`](README_stt.md#api-contract).
Both of you can build against it right now — start the service and it responds
even before anyone downloads a model.

## Highest-value job that needs no coding

`data/catalogues/hawker.json` is currently an **invented menu**. Replacing it
with the real one — every item plus every way an elderly diner might say it
(*kopi-o, kopi-c, siew dai, gah dai, tapao, dabao*) — improves accuracy on two
paths at once, because the same file feeds both the model biasing and the fuzzy
matcher. No Python required.

# Elderly-Friendly Voice Ordering — Order Matching & Dialogue Service

Replaces a QR-code / touchscreen menu with speech. This module sits between
two other pieces of the system and owns everything in the middle:

```
[ Elderly customer speaks ]
          |
          v
[ Speech-to-text ]        <-- built by teammate
          |  EITHER a plain transcript string
          |  OR their structured /transcribe order object (see Adapter below)
          v
[ THIS MODULE ]
  - matches transcript to menu items/modifiers
  - keeps ONE running tab per table, across many rounds of ordering
  - asks follow-up questions when unclear (e.g. "what noodle type?")
  - confirms before adding anything the customer only hinted at
  - handles "remove", "change", "cancel", "that's all", "bill"
  - clears the table only once the bill is paid
          |  (new lines only -> JSON payload)
          v
[ Kitchen service ]       <-- built by teammate
  - checks/decrements stock, confirms availability
  - tracks each line: received -> preparing -> done
```

## Web API

The website uses `server.py` as a small HTTP adapter around the existing dialogue manager, menu, order models and mock kitchen. From the repository root:

```bash
.venv/bin/python -m uvicorn backend.server:app --host 127.0.0.1 --port 8001
```

The frontend server proxies `/api/order/*` to this service and `/api/stt/*` to the separate STT service on port 8000. The browser uses the ordering menu's 12 items and server-calculated prices. Sessions are isolated and held in memory; restarting this web API clears its demo sessions. The CLI's file-backed table sessions remain separate.

Routes: `GET /health`, `GET /menu`, `POST /sessions`, `GET /sessions/{id}`, `POST /sessions/{id}/messages`, `POST /sessions/{id}/lines`, `PATCH` or `DELETE /sessions/{id}/lines/{line_id}`, and `POST /sessions/{id}/confirm`. All order-changing requests include a UUID `request_id` for idempotent retries. The response includes a complete cart snapshot and conversation. Only confirmed orders reach the existing mock kitchen. See `/docs` on port 8001 for request schemas.

Deleting an unconfirmed line removes it immediately. Deleting a confirmed line first asks the kitchen module to cancel it and succeeds only while its status is `received`; a line in `preparing` or `done` remains on the bill.

This is a local development API bound to loopback, with no public authentication or production persistence. Full startup and test instructions are in [the frontend README](../frontend/README.md).

## Running it

```bash
pip install -r requirements.txt
python main.py                 # type transcripts interactively, like a live demo
python demo_conversations.py   # scripted conversations, no typing needed
python test_features.py        # 36 assertion checks over the behaviour below
```

## The table lifecycle

A table keeps **one running tab** from the moment someone sits down until they
pay. Ordering more food appends to that tab; it never starts over.

```
sit down -> order -> confirm (new lines go to kitchen) -> order more -> confirm
         -> "bill please" -> read back total -> confirm -> PAID, table cleared
```

- **Confirming sends only the new lines.** Food already with the kitchen is
  never re-sent, and the total keeps accumulating.
- **Payment is the only thing that clears a table.** Without that, one
  customer's bill would follow the next person who sits down. `mark_paid()`
  archives a receipt and seats the table fresh at $0.00.
- **Clearing a table always takes an explicit yes.** An unclear reply ("hmm",
  "not sure", "dunno") leaves the table open — that's recoverable, wiping a
  bill isn't.
- **Tables are independent**, and tabs survive a restart (JSON-backed).

## Project layout

- `app/menu_data.py` — the dummy menu (13 items across Noodles/Rice/Snacks/Drinks).
  Each item has a canonical name plus **3 aliases** covering common alternate
  phrasings/dialect terms. Add new dishes here.
- `app/matcher.py` — turns transcript text into candidate menu items / modifier
  options. Exact-phrase match first (highest confidence), then a whole-word
  category check ("noodles" -> ask which noodle dish), then fuzzy matching
  (rapidfuzz) as a last resort for typos/STT mishearings.
- `app/intent.py` — keyword spotting for control phrases: cancel / confirm /
  remove / change. Deliberately simple and rule-based rather than a trained
  classifier — transparent and easy to tune.
- `app/dialogue_manager.py` — the conversation state machine. One call to
  `handle_utterance(session, transcript)` per STT turn; returns a
  `DialogueResponse` (text to speak back, whether it's still a question, and
  a cart snapshot).
- `app/session_store.py` — per-table sessions, JSON persistence, and
  `mark_paid()` (the one operation that clears a table).
- `app/stt_adapter.py` — maps the STT teammate's canonical codes
  (`KOPI_C`, `SIEW_DAI`, …) onto our menu, so their structured output can be
  consumed directly instead of only raw text.
- `app/kitchen_interface.py` — the **only** file that talks to the kitchen.
  Currently a mock (in-memory stock dict) so the whole thing runs standalone;
  see the contract docstring at the top of the file for what to replace when
  the real kitchen service is ready.
- `app/models.py` — shared dataclasses (MenuItem, Order, Session, etc).

## Singlish and dialect handling

Elderly customers don't speak formal English, so the matcher and intent
lists are built around how they actually order. Sources consulted for the
lingo are listed at the bottom of this file.

**Speech patterns accounted for**

- Sentence-final particles (`lah`, `leh`, `lor`, `hor`, `ah`, `meh`, `one`) —
  harmless filler that the matcher ignores rather than trips on.
- Dropped articles and copula: "want one kopi", "noodle got soup or not".
- `already` as a perfective marker: "I dun want already", "done already".
- Dialect food words as first-class aliases: `mee`, `bee hoon`, `kway teow`,
  `wan tan mee`, `epok epok`, `tau huay water`.
- Reduplication and self-correction: "wait wait", "aiya", "eh no", "i mean".
- Hyphenated drink spellings (`kopi-o`, `teh-c`) normalized to match the
  space-separated aliases.
- Singular/plural slippage ("fishball noodle" vs "Fishball Noodles") handled
  by registering both forms, not by loosening the fuzzy threshold.

**Kopitiam drink lingo — combinatorial, not hardcoded**

Kopi and Teh each carry four independent modifier groups, so every real
combination resolves without a menu entry per permutation:

| Dimension | Options (with aliases) | Price effect |
|---|---|---|
| Milk type | plain (condensed milk) · `-O` = black, no milk · `-C` = evaporated milk | −$0.10 for `-O`, +$0.20 for `-C` |
| Sweetness | normal · `siew dai` (less) · `kosong` (none) · `gah dai` (extra) | — |
| Strength | normal · `gao`/`kaw`/`gau` (strong) · `poh`/`po` (weak) | — |
| Temperature | hot · `peng`/`iced` | — |

So a Kopi-O is $1.10, a plain Kopi $1.20, a Kopi-C $1.40 — matching the STT
teammate's catalogue, which prices those as three separate items. We keep one
menu item plus a `price_delta` per option, which expresses the same prices
while still letting any combination be spoken naturally.

**Order of details never matters.** Each dimension is matched independently
against the whole utterance, so `kopi-o kosong gao peng`, `peng kosong kopi-o
gao`, and every other arrangement produce an identical order. (All 24
permutations of those four terms are covered by a test.)

**Drinks are taken at face value — no interrogation.** "One kopi" is added
straight away as a plain hot kopi; if they want it iced they can say `peng`
themselves. Being asked four questions for one coffee is the experience this
system exists to replace.

Only **two** things are still asked for, because the alternative is worse:

| Still asked | Why |
|---|---|
| Noodle type | The kitchen physically cannot make the dish without knowing yellow noodle vs kway teow vs bee hoon. |
| Chilli, on sambal/curry dishes | Some elderly customers genuinely cannot take spice, and these dishes arrive spicy by default. |

When something *is* asked, it's asked once, combined:

> For your Fishball Noodles, please tell me the noodle (yellow noodle, kway
> teow, bee hoon, or instant noodle); and chilli (no chilli, a little, or
> normal). You can say them all together.

They can answer all at once, a few at a time, or say "normal lah" / "anything
can" to take the plain defaults. A correction spoken mid-question ("aiya wait
wait, make it kway teow instead") is applied and read back. Only after repeated
non-answers does it fall back to defaults, and it says which ones it picked.

**Spice level** is a first-class choice, since many elderly customers can't
take chilli at all:

| Level | Aliases |
|---|---|
| No chilli | `mai hiam`, `no chilli`, `not spicy`, `no sambal`, `cannot take spicy` |
| Less chilli | `little bit chilli`, `not too spicy`, `mild` |
| Normal chilli | `normal chilli`, `with chilli` |
| Extra chilli | `extra chilli`, `very spicy`, `extra sambal` |

Dishes that arrive spicy by default (Nasi Lemak's sambal, Curry Puff, Roti
Prata's curry) **always ask**. Dishes where chilli is a side condiment
(noodles, fried rice, chicken rice) accept it if mentioned but default to no
chilli — the safe choice for this group.

**Two traps specifically handled**

1. *Talking about food is not ordering it — and nothing is ever added
   without a clear yes.* There are three distinct cases:

   | What they say | What happens |
   |---|---|
   | "I've had too much coffee today" | Pure commentary — nothing added, nothing asked |
   | "...but I don't mind another kopi-o lah" | Hedged interest — **asks** "Would you like me to add one Kopi?" and waits |
   | "give me one kopi-o" | A plain request — added |

   Hedged phrasing ("don't mind", "maybe", "thinking of", "why not") is
   treated as *interest*, never as a decision, so a customer musing aloud
   never gets charged for something they didn't ask for. Any modifiers
   mentioned in the original hedged sentence are carried through when they
   say yes. If the reply is unclear ("hmm", "not sure", "dunno") it is asked
   again, and after repeated non-answers the item is **dropped rather than
   added** — a wrongly added item costs the customer money, so uncertainty
   always resolves toward adding nothing. Note that "not sure" is explicitly
   prevented from being read as "sure".

2. *Off-topic chit-chat.* "Later I wanna go cycling with my grandson" matches
   no menu item **and** carries no ordering phrasing, so it's treated as
   small talk: acknowledged warmly ("Alright!") and the conversation
   continues, rather than being answered with "sorry, not on the menu". The
   distinction is `has_order_intent()` — "I want a burger" (an actual order
   we can't fill) still gets a proper apology.

Two structural quirks also needed handling: commas that separate *modifiers*
rather than dishes ("wan tan mee, dry lah, yellow noodle can" is one order,
not three), and topic-comment fronting ("eh the kopi ah, i want kopi-c gao"
names one drink, not two).

## How matching works

1. **Exact whole-word match** against an item's name + aliases. Most speech
   for a known dish will hit this — it's why aliases matter more than fuzzy
   thresholds. This is also why *"Write 2-3 aliases per item"* was the right
   call: the alias list is the main defense against garbage matches, not the
   fuzzy fallback. Matching is on **word boundaries, not raw substrings** —
   short dialect aliases hide inside ordinary words ("tea" sits inside
   "ins-**tea**-d", "any" inside "comp-**any**"), and a substring test turns
   those into phantom orders.
2. **Category fallback.** If nothing matches exactly but the sentence
   contains a bare category word ("noodles", "a drink"), we ask which
   specific dish rather than letting a coincidental fuzzy score silently pick
   one. (Concretely: "I want noodles" almost fuzzy-matched "Wonton Noodles"
   for the wrong reason — "want" vs "wonton" — before this fallback was added.)
3. **Fuzzy fallback** (rapidfuzz `token_set_ratio`, threshold 75) for typos or
   STT mishearings of a specific dish name.
4. If nothing matches at all, the response depends on whether they were
   actually trying to order: an unavailable request gets an apology, while
   small talk just gets acknowledged. The order is never silently guessed.

## Handling ambiguity, missing info, and changes of mind

This was the main design ask, so here's how each case is handled — all via
`PendingClarification` on the `Session`, so only one question is ever open
at a time:

| Situation | Example | Behavior |
|---|---|---|
| Drink details left out | "one kopi" | Taken at face value — added as a plain hot kopi, no questions asked |
| Required choice missing | "fishball noodles" / "one nasi lemak" | Asks noodle type / chilli in one combined question before adding |
| Details given in any order | "peng kosong kopi-o gao" | Each dimension is matched independently, so sequence never matters |
| "Give me the usual" | "normal lah" / "anything can" / "up to you" | Fills every remaining choice with the plain default in one go |
| Correction mid-question | "aiya wait wait, make it kway teow instead" | Overwrites the already-settled choice and reads the change back |
| Spice level | "one nasi lemak" | Always asked for sambal/curry dishes; defaults to no chilli elsewhere |
| Ambiguous item | "I want noodles" | Asks "which one: Beef Noodle Soup or Fishball Noodles or Wonton Noodles?" |
| Ambiguous modifier | text matches 2+ noodle types | Asks the customer to pick between the close matches |
| Repeated unclear answers | "I don't know" x2 to a required question | After 2 retries, defaults to the first option and tells the customer, rather than looping forever |
| Mid-order change | "aiya wait wait, make it kway teow instead" | Detected via `change_item` intent keywords; updates the right line (asks which one first if there's more than one candidate) |
| Multiple changes at once | "actually make it kopi-c kosong" | Every named modifier is applied together, not just the first one matched |
| Removing an item | "eh the prata i dun want already" | Matches against what's actually in the cart; asks "all of them or just one?" if there are duplicates |
| Full cancel | "cancel" / "never mind" | Mid-clarification: cancels just that one item. With no pending question: clears the whole cart. |
| Trailing content after answering | "kway teow, and also a kopi" (said while answering a noodle-type question) | The answer is consumed for the question; anything said after it is queued and processed as a new item, not dropped |
| Extra modifiers in an answer | "bee hoon, dry" (answering a noodle-type question) | The answer resolves the open question *and* the additional modifier is applied, rather than being discarded |
| Mentioning food without ordering | "I've had too much coffee today" | Recognized as commentary — nothing is added to the cart |
| Hedged interest | "I don't mind another coffee" | Asks "shall I add one?" and waits — never added on the customer's behalf |
| Unclear yes/no | "hmm" / "not sure" / "dunno" | Re-asks, then drops the item rather than risk charging for it |
| Finishing mid-question | "that's all" while a choice is still open | Settles the open item with safe defaults, says which, and checks out |
| Off-topic chit-chat | "later I wanna go cycling with my grandson" | Acknowledged and passed over; not treated as a failed menu lookup |
| Confirming | "ok lah" / "that's all" / "done already" / "settle" | Sends only the NEW lines to the kitchen, reports the running total. A confirm phrase that also names food ("no more sugar") is treated as a modifier request instead |
| Asking to pay | "bill please" / "how much" / "mai tan" | Reads the itemised bill back and asks to close the table. Checked *before* confirm, so "settle the bill" isn't mistaken for "settle" |
| Cancelling cooked food | "the nasi lemak also dont want" (kitchen already started) | Refused with an explanation — it stays on the bill rather than the shop losing the food |
| Takeaway | "tapao" anywhere, or asked once at confirmation | Order-level flag, matching the STT teammate's `takeaway` field |
| Item sold out | kitchen reports unavailable | Line is removed from the bill, named out loud, and same-category alternatives suggested |

## Stock, kitchen status, and cancellation

Each line the kitchen accepts moves through **`received` → `preparing` → `done`**,
and that status decides whether the customer can still change their mind:

- Not yet sent → removed immediately.
- Sent but still `received` → cancelled with the kitchen, then removed.
- `preparing` or `done` → **refused**, plainly: *"Sorry, the kitchen has already
  started on your Nasi Lemak, so I can't cancel that one."* The food exists and
  someone has to pay for it.

If the kitchen reports an item is out of stock, that line is **removed from the
bill** (so the customer is never charged for food that can't be made), named
explicitly, and alternatives from the same category are offered.

## Integration contracts

### Input — two supported shapes

**1. Plain transcript string** (the standalone path, always works):
```python
response = dm.handle_utterance(session, "two beef noodles with kway teow")
```

**2. The STT teammate's structured `/transcribe` response:**
```python
response = dm.handle_stt_order(session, stt_payload)   # their {"order": {...}}
```
`app/stt_adapter.py` maps their canonical codes onto our menu. Their side
supplies the item match; ours still adds the clarification, confirmation,
running tab, and kitchen handoff they don't do.

| Theirs | Ours |
|---|---|
| `KOPI` / `KOPI_O` / `KOPI_C` | `kopi` + `milk_type` = condensed / black / evaporated |
| `TEH` / `TEH_O` / `TEH_C` | `teh` + same |
| `SIEW_DAI` / `GAH_DAI` / `KOSONG` | `sweetness` |
| `GAU` / `PO` | `strength` |
| `PENG` | `temperature` |
| `NO_CHILLI` / `EXTRA_CHILLI` | `spice` |
| `TAKEAWAY` | order-level `takeaway` flag |

Their modifier lists carry *display* strings (`"siew dai"`), not canonicals, so
both spellings are accepted. Items with no equivalent on our menu (Milo, Laksa,
Char Kway Teow, Kaya Toast, …) fall back to text matching and then to a plain
"not on the menu" — never silently dropped.

Either way, `response.message` is the text to speak back (TTS is their side) and
`response.needs_clarification` says whether to expect another customer utterance.

### Output (to the kitchen teammate)
See the docstring at the top of `app/kitchen_interface.py` for the full JSON
shape. Short version: `send_order_to_kitchen(order, lines=order.new_lines)`
sends `{order_id, lines: [{line_id, item_id, name, quantity, modifiers,
unit_price}, ...]}` and expects back `{order_id, accepted, line_results:
[{line_id, item_id, available, remaining_stock, status}, ...]}`.

Two additions the kitchen side needs to implement:
- echo `line_id` back (names aren't unique per line), and report `status`;
- support `cancel_line(order_id, line_id)`, which succeeds only while the line
  is still `received`.

Everything upstream of that one file only ever deals with `Order`/`OrderLine`
objects, so swapping the mock for a real REST call, an AWS SQS `send_message`,
or a direct function import is a one-file change.

## Open questions for the team

1. **`TAU_HUAY` vs Soya Bean Milk.** Their catalogue prices Tau Huay (beancurd
   dessert) at $2.00; ours has Soya Bean Milk at $1.70. These are different
   products, so they are deliberately *not* mapped to each other. Someone should
   decide whether both belong on the menu.
2. **Menu divergence.** Their catalogue has 8 items ours doesn't (Milo, Laksa,
   Char Kway Teow, Kaya Toast, Half-Boiled Eggs, Mee Goreng, Carrot Cake, Bee
   Hoon) and ours has 5 theirs doesn't. The adapter bridges this, but the real
   fix is one shared menu file.
3. **Prices** for overlapping items now follow their `hawker.json`. Their own
   README calls that menu "invented", so it should be replaced with the real
   hawker's prices before any demo that shows money.

## Possible AWS extensions (not implemented — flagging since AWS is available)

- **SQS** between this service and the kitchen, instead of a direct call —
  useful if they end up as separate deployed services.
- **DynamoDB** for `Session` storage if this runs as stateless Lambda
  invocations per utterance rather than one long-lived process per kiosk.
- **Lex / Comprehend** as an alternative to `matcher.py`'s rapidfuzz-based
  matching, if the alias-list approach stops scaling as the menu grows.

None of these are needed for the current scope — the mock/local versions are
enough to build and demo the full flow end-to-end.

## Sources for the Singlish / kopitiam lingo

- [How to Order Kopi and Teh Like a Local: The Ultimate Lingo Guide](https://donsignaturecrab.sg/articles/guide-to-ordering-kopi-teh-singapore/)
- [Kopi Glossary: Local Coffee Terms Explained](https://singaporefoodfestival.org/kopi-glossary-local-coffee-terms-explained/)
- [How To Order Like A Local — Hawker Centre Lingo](https://wak-wak-hawker.com/en/read/17/)
- [Singlish 101: A dictionary of common Singlish words and local slang](https://thehoneycombers.com/singapore/singlish-101/)
- [Singapore English (Singlish): Unique Words and Grammar](https://wordopedia.org/singapore-english)

Worth validating the alias lists with actual elderly users before deploying —
regional and dialect-group variation is real, and the alias list is the single
biggest lever on match quality.

"""
Assertion-based checks for the table/payment/kitchen/adapter behaviour.

Plain asserts rather than a test framework, so it runs anywhere with
`python test_features.py` and prints a readable pass/fail summary.
"""
import os
import tempfile

from app import kitchen_interface as kitchen
from app.dialogue_manager import DialogueManager
from app.menu_data import MENU
from app.session_store import SessionStore

RESULTS = []


def check(name, condition, detail=""):
    RESULTS.append((name, bool(condition), detail))


def fresh(path=None):
    kitchen.reset_kitchen()
    store = SessionStore(path)
    return store, DialogueManager(MENU, session_store=store)


def say(dm, store, table, *turns):
    last = None
    for t in turns:
        last = dm.handle_utterance(store.get(table), t)
    return last


# ---------------------------------------------------------------- prices
store, dm = fresh()
say(dm, store, "1", "one kopi")
check("plain kopi is $1.20", store.get("1").order.lines[0].unit_price == 1.20,
      str(store.get("1").order.lines[0].unit_price))

store, dm = fresh()
say(dm, store, "1", "kopi-o")
check("kopi-o is $1.10", store.get("1").order.lines[0].unit_price == 1.10)

store, dm = fresh()
say(dm, store, "1", "kopi-c")
check("kopi-c is $1.40", store.get("1").order.lines[0].unit_price == 1.40)

store, dm = fresh()
say(dm, store, "1", "chicken rice")
check("chicken rice is $4.50", store.get("1").order.lines[0].unit_price == 4.50)

# ------------------------------------------------- no drink interrogation
store, dm = fresh()
r = say(dm, store, "1", "one kopi")
check("bare 'kopi' asks nothing", not r.needs_clarification and len(store.get("1").order.lines) == 1)

store, dm = fresh()
r = say(dm, store, "1", "one nasi lemak")
check("nasi lemak still asks chilli", r.needs_clarification and "chilli" in r.message.lower())

store, dm = fresh()
r = say(dm, store, "1", "fishball noodles")
check("noodle dish still asks noodle type", r.needs_clarification and "noodle" in r.message.lower())

# ------------------------------------------------------------ running tab
store, dm = fresh()
say(dm, store, "5", "one kopi-o", "that's all", "eat here")
first_total = store.get("5").order.total
say(dm, store, "5", "one prata no chilli", "confirm")
check("tab accumulates across rounds", store.get("5").order.total == round(first_total + 1.50, 2),
      f"{first_total} -> {store.get('5').order.total}")
check("earlier line is not re-sent", len(store.get("5").order.new_lines) == 0)

# tables are independent
say(dm, store, "3", "one teh")
check("tables are independent",
      store.get("3").order.total == 1.20 and store.get("5").order.total > 1.20)

# ------------------------------------------------------------- payment
say(dm, store, "5", "bill", "yes")
check("paying clears the table", store.get("5").order.lines == [])
check("paying archives a receipt", len(store.receipts) == 1)
check("paying does not touch other tables", store.get("3").order.total == 1.20)

# empty tab can't be paid
store, dm = fresh()
r = say(dm, store, "1", "bill please")
check("cannot pay an empty tab", "nothing to pay" in r.message.lower())

# unclear answers never clear a table
store, dm = fresh()
say(dm, store, "1", "one kopi", "that's all", "eat here")
say(dm, store, "1", "bill", "hmm", "not sure", "dunno")
check("unclear yes/no keeps the table open", len(store.get("1").order.lines) == 1)

# declining keeps it open too
say(dm, store, "1", "bill")
say(dm, store, "1", "no not yet")
check("declining keeps the table open", len(store.get("1").order.lines) == 1)

# ------------------------------------------------------------ persistence
path = os.path.join(tempfile.gettempdir(), "test_tabs.json")
if os.path.exists(path):
    os.remove(path)
store, dm = fresh(path)
say(dm, store, "5", "one kopi-o and one prata", "no chilli", "that's all", "eat here")
before = store.get("5").order.total
reloaded = SessionStore(path)
check("tab survives a restart", reloaded.get("5").order.total == before,
      f"{before} vs {reloaded.get('5').order.total}")
dm2 = DialogueManager(MENU, session_store=reloaded)
say(dm2, reloaded, "5", "bill", "yes")
after_pay = SessionStore(path)
check("paid table is empty after restart", after_pay.get("5").order.lines == [])
check("receipt survives a restart", len(after_pay.receipts) == 1)
os.remove(path)

# ------------------------------------------------------- cancellation gate
store, dm = fresh()
say(dm, store, "2", "one nasi lemak no chilli and one prata no chilli", "that's all", "eat here")
session = store.get("2")
nasi = next(l for l in session.order.lines if l.item_id == "nasi_lemak")
r = say(dm, store, "2", "the prata i dun want already")
check("can cancel while still 'received'",
      all(l.item_id != "roti_prata" for l in session.order.lines))
kitchen.advance_line_status(nasi.line_id)   # -> preparing
r = say(dm, store, "2", "actually the nasi lemak also dont want")
check("cannot cancel once 'preparing'",
      any(l.item_id == "nasi_lemak" for l in session.order.lines)
      and "already being prepared" in r.message.lower(), r.message)

# ------------------------------------------------------------ out of stock
store, dm = fresh()
kitchen.set_stock("nasi_lemak", 0)
r = say(dm, store, "1", "one nasi lemak and one chicken rice", "no chilli", "that's all", "eat here")
items = [l.item_name for l in store.get("1").order.lines]
check("sold-out line is removed from the bill", "Nasi Lemak" not in items, str(items))
check("sold-out item is named", "run out of nasi lemak" in r.message.lower(), r.message)
check("alternatives are suggested", "instead" in r.message.lower())
check("rest of order still charged", store.get("1").order.total == 4.50)

# --------------------------------------------------------------- takeaway
store, dm = fresh()
r = say(dm, store, "1", "one kopi", "that's all")
check("asks about takeaway when unstated", "taking away" in r.message.lower())
r = say(dm, store, "1", "tapao")
check("takeaway answer is recorded", store.get("1").order.takeaway is True)

store, dm = fresh()
r = say(dm, store, "1", "one kopi tapao", "that's all")
check("never asks when tapao already said",
      store.get("1").order.takeaway is True and "taking away" not in r.message.lower())

store, dm = fresh()
say(dm, store, "1", "one prata no chilli", "that's all", "eat here")
r = say(dm, store, "1", "take away the prata")
check("'take away the prata' means remove, not tapao",
      len(store.get("1").order.lines) == 0 or "cancel" in r.message.lower(), r.message)

# ------------------------------------------------------------ STT adapter
store, dm = fresh()
payload = {
    "corrected_text": "two Kopi-C siew dai tapao",
    "order": {
        "lines": [{"canonical": "KOPI_C", "display": "Kopi-C", "quantity": 2,
                   "modifiers": ["siew dai"], "price": 1.4}],
        "takeaway": True, "total": 2.8,
    },
}
dm.handle_stt_order(store.get("2"), payload)
line = store.get("2").order.lines[0]
check("adapter maps KOPI_C -> kopi + evaporated milk",
      line.item_id == "kopi" and line.modifiers["milk_type"] == "evaporated_milk")
check("adapter maps 'siew dai' display string", line.modifiers["sweetness"] == "less_sweet")
check("adapter total matches their payload total", store.get("2").order.total == 2.8)
check("adapter picks up takeaway", store.get("2").order.takeaway is True)

# still asks for a required choice their side doesn't model
store, dm = fresh()
r = dm.handle_stt_order(store.get("2"), {"order": {"lines": [
    {"canonical": "NASI_LEMAK", "display": "Nasi Lemak", "quantity": 1, "modifiers": []}]}})
check("adapter still asks for chilli", r.needs_clarification and "chilli" in r.message.lower())

# an unmapped dish is reported, not silently dropped
store, dm = fresh()
dm.handle_stt_order(store.get("2"), {"order": {"lines": [
    {"canonical": "NASI_LEMAK", "display": "Nasi Lemak", "quantity": 1, "modifiers": []},
    {"canonical": "LAKSA", "display": "Laksa", "quantity": 1, "modifiers": []}]}})
r = say(dm, store, "2", "no chilli")
check("unmapped dish is reported", "laksa" in r.message.lower(), r.message)

# raw text still works alongside the adapter
store, dm = fresh()
r = say(dm, store, "2", "one kopi-o kosong peng")
check("raw text path still works", len(store.get("2").order.lines) == 1)


# ------------------------------------------------------------------ report
passed = sum(1 for _, ok, _ in RESULTS if ok)
print(f"\n{passed}/{len(RESULTS)} checks passed\n")
for name, ok, detail in RESULTS:
    if not ok:
        print(f"  FAIL  {name}" + (f"  [{detail}]" if detail else ""))
if passed == len(RESULTS):
    print("  all good")

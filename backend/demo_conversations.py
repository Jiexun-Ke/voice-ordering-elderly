"""
Scripted conversations that exercise the tricky paths without needing a
live mic or manual typing — useful for a demo/presentation.

The transcripts are written the way elderly Singaporean customers actually
speak rather than in formal English, since that's what the speech-to-text
side will realistically hand us:

  - Sentence-final particles: lah, leh, lor, hor, ah, meh, one
  - Dropped articles/copula: "want one kopi", "noodle got soup or not"
  - "already" as a perfective marker: "I eat already", "done already"
  - Kopitiam drink lingo: kopi-o / kopi-c, kosong, siew dai, gah dai,
    gao (strong), poh (weak), peng (iced)
  - Hokkien/Malay/dialect food words: mee, bee hoon, kway teow, dabao
  - Reduplication and self-correction mid-sentence
  - Addressing staff as "boss", "uncle", "auntie"

Run: python demo_conversations.py
"""
import uuid

from app import kitchen_interface as kitchen
from app.dialogue_manager import DialogueManager
from app.menu_data import MENU
from app.models import Order, Session
from app.session_store import SessionStore

SCRIPTS = {
    # Everyday order in heavy Singlish, with particles and dropped articles.
    "Singlish basics - particles and dropped articles": [
        "eh boss, want one beef noodle lah",
        "kway teow, dry",
        "then one kopi-o kosong gao hot",
        "ok lah that's all",
        "eat here",
    ],

    # Drinks are never interrogated: say it once and it's taken at face value.
    "Kopitiam drink lingo - taken at face value": [
        "auntie one kopi-c siew dai",
        "then teh-o gao peng one, kosong",
        "and one plain kopi",
        "done already",
        "tapao",
    ],

    # Comma-separated modifiers after the dish, not separate dishes.
    "Modifiers strung after the dish": [
        "wan tan mee, dry lah, yellow noodle can",
        "and barley peng",
        "settle",
        "eating here",
    ],

    # Elderly changing their mind mid-order, Singlish style.
    "Change mind halfway - aiya, wait wait": [
        "give me two fishball noodle, bee hoon",
        "aiya wait wait, make it kway teow instead",
        "eh the kopi ah, i want kopi-c gao",
        "ok can already",
        "dine in",
    ],

    # THE OFF-TOPIC CASE: unrelated chit-chat mixed into the ordering session.
    "Off-topic chit-chat mid-order": [
        "later i wanna go cycling with my grandson at east coast",
        "oh anyway, one chicken rice",
        "my knee not so good these days lor",
        "and one teh peng",
        "ok lah enough already",
        "eat here",
    ],

    # Hedged interest is never banked as an order without an explicit yes.
    "Negation trap - musing out loud is never an order": [
        "i have had too much coffee today already",
        "but i dont mind going for another kopi-o kosong peng lah",
        "ya ok can",
        "that's all",
        "eat here",
    ],

    # SPICINESS: sambal/curry dishes always ask, since many elderly can't
    # take spice. "mai hiam" is the standard hawker term for no chilli.
    "Spice level - asked, not assumed": [
        "one nasi lemak",
        "mai hiam, cannot take spicy",
        "and one curry puff, little bit chilli only",
        "that's all",
        "tapao",
    ],
}


def run_script(name, turns):
    print(f"\n=== {name} ===")
    kitchen.reset_kitchen()
    dm = DialogueManager(MENU)
    session = Session(session_id=str(uuid.uuid4()), order=Order(order_id=str(uuid.uuid4())))
    for transcript in turns:
        response = dm.handle_utterance(session, transcript)
        print(f"You:    {transcript}")
        print(f"System: {response.message}")


# ---------------------------------------------------------------------- #
# The scenarios below need a table/store, a kitchen state, or the STT
# adapter, so each drives things directly rather than reading from SCRIPTS.
# ---------------------------------------------------------------------- #
def demo_running_tab_and_payment():
    print("\n=== Running tab: order twice, pay once, table clears ===")
    kitchen.reset_kitchen()
    store = SessionStore(None)
    dm = DialogueManager(MENU, session_store=store)

    for transcript in ["one kopi-o and one curry puff", "no chilli",
                       "that's all", "eat here"]:
        print(f"You:    {transcript}")
        print(f"System: {dm.handle_utterance(store.get('5'), transcript).message}")

    print("   ... customer eats, then orders a second round ...")
    for transcript in ["uncle, one more teh-c peng", "confirm"]:
        print(f"You:    {transcript}")
        print(f"System: {dm.handle_utterance(store.get('5'), transcript).message}")

    for transcript in ["boss, bill please", "yes can"]:
        print(f"You:    {transcript}")
        print(f"System: {dm.handle_utterance(store.get('5'), transcript).message}")

    print(f"   [table 5 after paying] lines={len(store.get('5').order.lines)} "
          f"total=${store.get('5').order.total:.2f}  receipts={len(store.receipts)}")


def demo_cancellation_gate():
    print("\n=== Cancelling depends on what the kitchen has started ===")
    kitchen.reset_kitchen()
    store = SessionStore(None)
    dm = DialogueManager(MENU, session_store=store)
    session = store.get("3")

    for transcript in ["one nasi lemak, no chilli, and one prata, no chilli",
                       "that's all", "eat here"]:
        print(f"You:    {transcript}")
        print(f"System: {dm.handle_utterance(session, transcript).message}")

    # The kitchen starts cooking the nasi lemak but not the prata.
    nasi = next(l for l in session.order.lines if l.item_id == "nasi_lemak")
    kitchen.advance_line_status(nasi.line_id)
    print("   ... kitchen starts preparing the Nasi Lemak ...")

    for transcript in ["eh, the prata i dun want already",
                       "actually the nasi lemak also dont want"]:
        print(f"You:    {transcript}")
        print(f"System: {dm.handle_utterance(session, transcript).message}")


def demo_out_of_stock():
    print("\n=== Sold out: taken off the bill, alternatives offered ===")
    kitchen.reset_kitchen()
    kitchen.set_stock("nasi_lemak", 0)
    store = SessionStore(None)
    dm = DialogueManager(MENU, session_store=store)
    session = store.get("9")

    for transcript in ["one nasi lemak and one chicken rice", "no chilli",
                       "that's all", "eat here"]:
        print(f"You:    {transcript}")
        print(f"System: {dm.handle_utterance(session, transcript).message}")
    print(f"   [bill] total=${session.order.total:.2f} "
          f"items={[l.item_name for l in session.order.lines]}")


def demo_stt_adapter():
    print("\n=== Structured input from the STT teammate's service ===")
    kitchen.reset_kitchen()
    store = SessionStore(None)
    dm = DialogueManager(MENU, session_store=store)
    session = store.get("2")

    payload = {
        "text": "two kopi c siew dai tapao",
        "corrected_text": "two Kopi-C siew dai tapao",
        "order": {
            "lines": [
                {"canonical": "KOPI_C", "display": "Kopi-C", "quantity": 2,
                 "modifiers": ["siew dai"], "price": 1.4},
                {"canonical": "NASI_LEMAK", "display": "Nasi Lemak", "quantity": 1,
                 "modifiers": []},
            ],
            "takeaway": True,
            "total": 6.8,
        },
    }
    print(f"[STT payload] {payload['corrected_text']} + Nasi Lemak")
    print(f"System: {dm.handle_stt_order(session, payload).message}")
    for transcript in ["mai hiam", "that's all"]:
        print(f"You:    {transcript}")
        print(f"System: {dm.handle_utterance(session, transcript).message}")
    print(f"   [takeaway={session.order.takeaway}] total=${session.order.total:.2f}")


if __name__ == "__main__":
    for name, turns in SCRIPTS.items():
        run_script(name, turns)
    demo_running_tab_and_payment()
    demo_cancellation_gate()
    demo_out_of_stock()
    demo_stt_adapter()

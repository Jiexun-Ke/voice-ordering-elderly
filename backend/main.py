"""
Interactive CLI — stand-in for the real speech-to-text pipeline.

Each line you type simulates one finalized transcript coming from the
STT teammate's module, for whichever table is currently seated.

Commands (these are operator commands, not things a customer would say):
    table <id>   switch to another table
    bill         show the current table's tab without asking to pay
    tables       list every table with an open tab
    kitchen      show kitchen status for this table's lines
    ready        advance this table's oldest line: received -> preparing -> done
    quit         exit

Everything else is treated as customer speech.
"""
from app import kitchen_interface as kitchen
from app.dialogue_manager import DialogueManager
from app.menu_data import MENU
from app.session_store import SessionStore

STORE_PATH = "table_sessions.json"


def show_bill(store, table_id):
    bill = store.bill_for(table_id)
    if not bill["lines"]:
        print(f"[table {table_id}] nothing ordered yet.")
        return
    print(f"[table {table_id}] current tab:")
    for line in bill["lines"]:
        mods = ", ".join(line["modifiers"].values())
        status = line["kitchen_status"] or "not sent"
        print(f"    {line['quantity']} x {line['item']}"
              f"{f' ({mods})' if mods else ''}  ${line['subtotal']:.2f}   [{status}]")
    if bill["takeaway"] is not None:
        print(f"    ({'takeaway' if bill['takeaway'] else 'dine in'})")
    print(f"    TOTAL: ${bill['total']:.2f}")


def main():
    store = SessionStore(STORE_PATH)
    dm = DialogueManager(MENU, session_store=store)
    table_id = "1"

    print("Welcome! Type an order, or 'quit' to exit.")
    print("Operator commands: table <id> | bill | tables | kitchen | ready\n")
    print(f"--- now serving table {table_id} ---")

    while True:
        try:
            text = input(f"[table {table_id}] You: ").strip()
        except EOFError:
            break
        if not text:
            continue

        lowered = text.lower()
        if lowered in ("quit", "exit"):
            break

        if lowered.startswith("table "):
            table_id = text.split(None, 1)[1].strip()
            print(f"--- now serving table {table_id} ---")
            show_bill(store, table_id)
            continue

        if lowered == "bill":
            show_bill(store, table_id)
            continue

        if lowered == "tables":
            open_tabs = [t for t in store.tables() if store.get(t).order.lines]
            print("Open tabs:" if open_tabs else "No open tabs.")
            for t in open_tabs:
                print(f"    table {t}: ${store.get(t).order.total:.2f}")
            continue

        if lowered == "kitchen":
            session = store.get(table_id)
            for line in session.order.lines:
                status = kitchen.get_line_status(session.order.order_id, line.line_id)
                print(f"    {line.item_name}: {status or 'not sent'}")
            continue

        if lowered == "ready":
            session = store.get(table_id)
            pending_lines = [l for l in session.order.lines if l.sent]
            if not pending_lines:
                print("    nothing with the kitchen yet.")
                continue
            line = pending_lines[0]
            new_status = kitchen.advance_line_status(line.line_id)
            line.kitchen_status = new_status
            store.save()
            print(f"    {line.item_name} -> {new_status}")
            continue

        response = dm.handle_utterance(store.get(table_id), text)
        print(f"System: {response.message}")
        if response.receipt:
            print(f"[receipt] table {response.receipt['table_id']} "
                  f"${response.receipt['total']:.2f} at {response.receipt['paid_at']}")
        print()


if __name__ == "__main__":
    main()

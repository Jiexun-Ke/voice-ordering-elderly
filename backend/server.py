"""Local HTTP adapter for the existing dialogue and mock-kitchen modules.

Run from the repository root: .venv/bin/python -m uvicorn backend.server:app --port 8001
Sessions are isolated, in memory, and lost on server restart.
"""
from copy import deepcopy
from dataclasses import asdict
from threading import RLock
from uuid import UUID, uuid4
import re

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from .app.dialogue_manager import DialogueManager
from .app.menu_data import MENU
from .app.models import DraftLine, serialize_kitchen_status
from .app.session_store import SessionStore
from .app.stock_validation import check_draft_availability, check_draft_line

app = FastAPI(title="Menu Helper Ordering", version="0.1.0")
store = SessionStore()
manager = DialogueManager(MENU)
lock = RLock()
sessions = {}
menu_by_id = {item.id: item for item in MENU}


class Mutation(BaseModel):
    request_id: UUID


class Message(Mutation):
    text: str = Field(min_length=1, max_length=400)


class Choice(Mutation):
    item_id: str
    quantity: int = Field(default=1, ge=1, le=20, strict=True)
    options: dict[str, str] = Field(default_factory=dict)


class Confirmation(Mutation):
    takeaway: bool


def session_for(session_id):
    if session_id not in sessions:
        raise HTTPException(404, "This ordering session has expired. Open a new menu to start again.")
    return sessions[session_id]


def snapshot(entry):
    session = entry["session"]
    return {
        "session_id": session.session_id,
        "order_id": session.order.order_id,
        "takeaway": session.order.takeaway,
        "confirmed": bool(session.order.lines) and not session.order.new_lines,
        "pending": session.pending.question if session.pending else None,
        "lines": [{
            "key": line.line_id, "id": line.item_id, "quantity": line.quantity,
            "options": line.modifiers, "option_names": line.modifier_names,
            "unit_cents": round(line.unit_price * 100),
            "subtotal_cents": round(line.subtotal * 100), "sent": line.sent,
            "kitchen_status": serialize_kitchen_status(line.kitchen_status),
        } for line in session.order.lines],
        "total_cents": round(session.order.total * 100),
        "messages": entry["messages"], "kitchen_mode": "mock",
    }


def mutate(session_id, request, action, resource=""):
    with lock:
        entry = session_for(session_id)
        request_id = str(request.request_id)
        fingerprint = request.model_dump_json() + action.__name__ + resource
        if request_id in entry["requests"]:
            previous, result = entry["requests"][request_id]
            if previous != fingerprint:
                raise HTTPException(409, "Request ID was already used for a different change.")
            return result
        result = action(entry)
        result["snapshot"] = snapshot(entry)
        # A lost HTTP reply can be retried without adding food twice.
        entry["requests"][request_id] = (fingerprint, deepcopy(result))
        return result


def reply(entry, message, **extra):
    entry["messages"].append({"role": "assistant", "text": message, **extra})
    return {"message": message}


def checked_choices(choice):
    item = menu_by_id.get(choice.item_id)
    if item is None:
        raise HTTPException(422, "This item is not on the ordering menu.")
    groups = {group.type.value: group for group in item.modifier_groups}
    if set(choice.options) - groups.keys():
        raise HTTPException(422, "That preference is not available for this item.")
    options, names = {}, {}
    for key, group in groups.items():
        selected = choice.options.get(key)
        if selected is None and group.required:
            raise HTTPException(422, group.prompt)
        selected = selected or group.default
        option = next((option for option in group.options if option.id == selected), None)
        if option is None:
            raise HTTPException(422, group.prompt)
        options[key], names[key] = selected, option.name
    return item, options, names


def line_for(entry, line_id):
    line = next((line for line in entry["session"].order.lines if line.line_id == line_id), None)
    if line is None:
        raise HTTPException(404, "This item is no longer in your order.")
    if line.sent:
        raise HTTPException(409, "This item is already confirmed. Please ask staff about changes.")
    return line


@app.get("/health")
def health():
    return {"status": "ok", "dialogue_ready": True, "kitchen_mode": "mock"}


@app.get("/menu")
def menu():
    return {"items": [asdict(item) for item in MENU], "kitchen_mode": "mock"}


@app.post("/sessions")
def create_session():
    with lock:
        session = store.get(str(uuid4()))
        entry = {"session": session, "messages": [], "requests": {}}
        sessions[session.session_id] = entry
        reply(entry, "Hello! I can help you order from this menu. Try ‘two kopi c, siew dai, takeaway’. The kitchen is a local demo.")
        return {"snapshot": snapshot(entry)}


@app.get("/sessions/{session_id}")
def get_session(session_id: UUID):
    with lock:
        return {"snapshot": snapshot(session_for(str(session_id)))}


@app.post("/sessions/{session_id}/messages")
def message(session_id: UUID, request: Message):
    def send(entry):
        text = request.text.strip()
        if not text:
            raise HTTPException(422, "Please enter a message.")
        session = entry["session"]
        # Menu questions and greetings should not become a guessed food order.
        # Leave pending answers to the existing dialogue state machine.
        response = None
        ids = []
        lowered = text.lower()
        if re.fullmatch(r"(?:hello|hi|hey|你好|您好)[\s!.！。?？]*", lowered):
            response = "Hello! What would you like to eat or drink?"
            if session.pending:
                response += " " + session.pending.question
        elif not session.pending:
            budget = re.fullmatch(r"(?:under|below)\s*\$?(\d+(?:\.\d+)?)", lowered)
            if lowered in ("show drinks", "drinks", "看看饮料"):
                ids = [item.id for item in MENU if item.category == "Drinks"]
            elif lowered in ("show food", "show menu", "menu", "看看食物", "菜单"):
                ids = [item.id for item in MENU if item.category != "Drinks"]
            elif budget:
                ids = [item.id for item in MENU if item.price < float(budget[1])]
            if ids:
                response = "Here are some choices from the menu."
            elif budget:
                response = "There are no items in that price range."
            elif re.search(r"allerg|ingredient|halal|diabet|过敏|成分", lowered):
                response = "This sample menu has no verified ingredient or allergy information. Please ask restaurant staff."
            elif re.match(r"(?:what is|what's|tell me about|how much is)\b", lowered):
                from .app.matcher import match_item
                matches = match_item(text, MENU, fuzzy=False)
                if len(matches) == 1:
                    item = matches[0][0]
                    response = f"{item.name} starts at ${item.price:.2f}."
                    if item.modifier_groups:
                        response += " You can choose " + ", ".join(group.type.value.replace('_', ' ') for group in item.modifier_groups) + "."
                    ids = [item.id]
                else:
                    response = "Which menu item would you like to know about?"
        trial = deepcopy(session)
        if response is None:
            before_line_ids = {line.line_id for line in trial.order.lines}
            result = manager.handle_utterance(trial, text)
            if any(line.quantity < 1 or line.quantity > 20 for line in trial.order.lines):
                raise HTTPException(422, "Please choose a quantity from 1 to 20.")
            added_line_ids = {
                line.line_id for line in trial.order.lines
            } - before_line_ids
            if result.stock_conflicts and not added_line_ids and not trial.pending:
                raise HTTPException(409, detail=result.stock_conflicts[0])
            response = result.message
            entry["session"] = trial
        entry["messages"].append({"role": "user", "text": text})
        return reply(entry, response, **({"ids": ids} if ids else {}))
    return mutate(str(session_id), request, send)


@app.post("/sessions/{session_id}/lines")
def add_line(session_id: UUID, request: Choice):
    def add(entry):
        item, options, names = checked_choices(request)
        session = entry["session"]
        line = manager._draft_to_orderline(item, DraftLine(item.id, item.name, request.quantity, options, names))
        conflict = check_draft_line(session.order, line)
        if conflict:
            raise HTTPException(409, detail=conflict.detail)
        session.order.lines.append(line)
        return reply(entry, f"Added {line.quantity} × {item.name}. Total: ${session.order.total:.2f}.")
    return mutate(str(session_id), request, add)


@app.patch("/sessions/{session_id}/lines/{line_id}")
def edit_line(session_id: UUID, line_id: UUID, request: Choice):
    def edit(entry):
        line = line_for(entry, str(line_id))
        if request.item_id != line.item_id:
            raise HTTPException(422, "Remove this item and add the replacement from the menu.")
        item, options, names = checked_choices(request)
        conflict = check_draft_availability(
            entry["session"].order,
            item.id,
            request.quantity,
            exclude_line_id=line.line_id,
        )
        if conflict:
            raise HTTPException(409, detail=conflict.detail)
        line.quantity, line.modifiers, line.modifier_names = request.quantity, options, names
        line.unit_price = manager._unit_price(item, options)
        return reply(entry, f"Updated {item.name}. Total: ${entry['session'].order.total:.2f}.")
    return mutate(str(session_id), request, edit, str(line_id))


@app.delete("/sessions/{session_id}/lines/{line_id}")
def remove_line(session_id: UUID, line_id: UUID, request: Mutation):
    def remove(entry):
        line = line_for(entry, str(line_id))
        entry["session"].order.lines.remove(line)
        return reply(entry, f"Removed {line.item_name}.")
    return mutate(str(session_id), request, remove, str(line_id))


@app.post("/sessions/{session_id}/confirm")
def confirm(session_id: UUID, request: Confirmation):
    def confirm_order(entry):
        session = entry["session"]
        if session.pending:
            raise HTTPException(409, "Please answer the question in Chat before confirming: " + session.pending.question)
        if not session.order.lines:
            raise HTTPException(422, "Add something to your order first.")
        session.order.takeaway = request.takeaway
        result = manager._confirm_order(session)
        return reply(entry, result.message)
    return mutate(str(session_id), request, confirm_order)

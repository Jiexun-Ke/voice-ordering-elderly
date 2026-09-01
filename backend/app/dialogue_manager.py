"""
The conversational state machine.

One call to `DialogueManager.handle_utterance(session, transcript)` per
speech-to-text turn. It owns:
  - matching transcript text to menu items / modifiers
  - asking follow-up questions when the elderly customer is ambiguous or
    leaves out a required choice (e.g. noodle type)
  - handling "actually change it to..." / "remove the..." / "cancel" / "that's all"
  - handing the finished order to the kitchen interface

Everything it returns is a DialogueResponse — plain text meant to be spoken
back to the customer (TTS is out of scope here, owned by the STT teammate),
plus a snapshot of the cart for logging/UI/kitchen display.
"""
import re
import uuid

from .intent import (
    ORDER_INTENT_WORDS,
    detect_control_intent,
    detect_takeaway,
    detect_yes_no,
    has_negative_framing,
    has_order_intent,
    is_tentative,
    wants_default,
)
from .kitchen_interface import cancel_line, send_order_to_kitchen
from .matcher import (
    extract_quantity,
    match_category,
    match_item,
    match_options,
    split_into_chunks,
    strip_matched_form,
)
from .menu_data import CATEGORY_ALIASES
from .models import DialogueResponse, DraftLine, PendingClarification

MAX_RETRIES = 2
AMBIGUITY_MARGIN = 15  # if top-2 item scores are this close, treat as ambiguous


class DialogueManager:
    def __init__(self, menu, category_aliases=None, session_store=None):
        self.menu = menu
        self.menu_by_id = {item.id: item for item in menu}
        self.category_aliases = category_aliases if category_aliases is not None else CATEGORY_ALIASES
        # Optional: without a store the manager still works standalone (payment
        # just clears the in-memory order), which keeps the demo self-contained.
        self.session_store = session_store

    def _get_item(self, item_id):
        return self.menu_by_id[item_id]

    def _mentions_any_modifier(self, text: str) -> bool:
        for item in self.menu:
            for group in item.modifier_groups:
                if match_options(text, group.options, fuzzy=False):
                    return True
        return False

    def _mentions_any_item(self, text: str) -> bool:
        return bool(match_item(text, self.menu, fuzzy=False))

    def _merge_modifier_only_chunks(self, chunks: list) -> list:
        """
        Singlish uses commas to string modifiers after a dish, not only to
        separate dishes: "wan tan mee, dry lah, yellow noodle can" is ONE
        order, not three. A chunk naming no item but naming a modifier is
        folded back into the dish before it, so those modifiers aren't
        orphaned into questions the customer already answered.

        Precedence matters: an exact modifier match beats a category match,
        because modifier values contain category words ("yellow NOODLE" is a
        noodle-type choice, not a request for a noodle dish).
        """
        if not chunks:
            return chunks
        merged = [chunks[0]]
        for chunk in chunks[1:]:
            if match_item(chunk, self.menu, fuzzy=False):
                merged.append(chunk)
            elif self._mentions_any_modifier(chunk):
                merged[-1] = f"{merged[-1]} {chunk}"
            else:
                merged.append(chunk)
        return self._collapse_topic_mentions(merged)

    def _collapse_topic_mentions(self, chunks: list) -> list:
        """
        Singlish often front-loads the topic then comments on it: "eh the kopi
        ah, i want kopi-c gao" names one drink, not two. When a bare mention of
        an item is immediately followed by a chunk naming the SAME item with
        actual detail, the bare topic mention is dropped so the customer isn't
        charged twice.
        """
        if len(chunks) < 2:
            return chunks
        result = []
        for i, chunk in enumerate(chunks):
            matches = match_item(chunk, self.menu, fuzzy=False)
            is_bare_topic = (
                len(matches) == 1
                and not has_order_intent(chunk)
                and extract_quantity(chunk)[0] == 1
                and not self._mentions_any_modifier(chunk)
            )
            if is_bare_topic and i + 1 < len(chunks):
                next_matches = match_item(chunks[i + 1], self.menu, fuzzy=False)
                if len(next_matches) == 1 and next_matches[0][0].id == matches[0][0].id:
                    continue
            result.append(chunk)
        return result

    # ------------------------------------------------------------------ #
    # Entry point
    # ------------------------------------------------------------------ #
    def handle_utterance(self, session, transcript: str) -> DialogueResponse:
        session.history.append(transcript)
        transcript = (transcript or "").strip()
        if not transcript:
            return DialogueResponse(
                message="Sorry, I didn't catch that. Could you say it again?",
                needs_clarification=True,
                order_snapshot=self._snapshot(session),
            )

        # Takeaway can be mentioned at any point ("one kopi, tapao") — pick it
        # up wherever it lands so we never have to ask about it later.
        stated_takeaway = detect_takeaway(transcript)
        if stated_takeaway is not None:
            session.order.takeaway = stated_takeaway

        if session.pending:
            return self._resolve_pending(session, transcript)

        intent = detect_control_intent(transcript)
        if intent == "pay_bill":
            return self._handle_pay_bill(session)
        if intent == "cancel_order":
            session.order.lines.clear()
            session.chunk_queue.clear()
            return DialogueResponse(
                message="Okay, I've cleared your order. What would you like to start with?",
                needs_clarification=False,
                order_snapshot=self._snapshot(session),
            )
        if intent == "confirm_order":
            # A confirm phrase that also names food isn't a confirmation:
            # "no more sugar" / "no need chilli" are modifier requests that
            # happen to contain "no more" / "no need". Only treat it as
            # "I'm finished" when nothing orderable is mentioned.
            if not self._mentions_any_item(transcript) and not self._mentions_any_modifier(transcript):
                return self._confirm_order(session)
        if intent == "remove_item":
            return self._handle_remove(session, transcript)
        if intent == "change_item":
            # "actually" is a common, generic speech connector — if there's
            # nothing in the cart yet, there's nothing to change, so treat
            # this as a normal add-item utterance instead of dead-ending.
            if session.order.lines:
                return self._handle_change(session, transcript)

        session.chunk_queue.extend(self._merge_modifier_only_chunks(split_into_chunks(transcript)))
        return self._process_chunk_queue(session)

    # ------------------------------------------------------------------ #
    # Alternative input: the STT teammate's already-structured order
    # ------------------------------------------------------------------ #
    def handle_stt_order(self, session, stt_payload: dict) -> DialogueResponse:
        """
        Accept the STT service's `/transcribe` response instead of raw text.

        Their side has already matched items and modifiers; ours still adds
        everything they don't do — asking for a missing required choice,
        confirming, the running tab, and the kitchen handoff. Pass either the
        full response or just its "order" object.

        `handle_utterance()` remains the raw-text path and is unaffected.
        """
        from .stt_adapter import CANONICAL_TO_MENU, map_modifiers, option_name

        order_obj = stt_payload.get("order", stt_payload) or {}
        raw_text = stt_payload.get("corrected_text") or stt_payload.get("text") or ""
        session.history.append(f"[stt] {raw_text}" if raw_text else "[stt payload]")

        if order_obj.get("takeaway"):
            session.order.takeaway = True

        added, not_found = [], []
        raw_lines = order_obj.get("lines", [])
        for index, raw_line in enumerate(raw_lines):
            canonical = str(raw_line.get("canonical", "")).upper()
            quantity = max(1, int(raw_line.get("quantity", 1) or 1))

            mapping = CANONICAL_TO_MENU.get(canonical)
            if mapping:
                item = self.menu_by_id.get(mapping[0])
                implied = dict(mapping[1])
            else:
                # Not in our mapping table — fall back to matching their display
                # name through our own matcher, so an unmapped dish is never
                # silently dropped.
                display = raw_line.get("display") or canonical.replace("_", " ")
                matches = match_item(display, self.menu, fuzzy=False) or match_item(display, self.menu)
                item, implied = (matches[0][0], {}) if matches else (None, {})

            if item is None:
                not_found.append(raw_line.get("display") or canonical.title())
                continue

            explicit, takeaway_seen = map_modifiers(raw_line.get("modifiers"), item)
            if takeaway_seen:
                session.order.takeaway = True

            draft = DraftLine(item_id=item.id, item_name=item.name, quantity=quantity)
            for gtype, opt_id in {**implied, **explicit}.items():
                draft.modifiers[gtype] = opt_id
                draft.modifier_names[gtype] = option_name(item, gtype, opt_id)

            # Reuse the normal path, so a still-missing required choice (noodle
            # type, chilli) is asked for exactly as it is for spoken input.
            kind, payload = self._fill_modifiers_or_finalize(item, draft, "")
            if kind == "pending":
                session.pending = payload
                # Anything after this line still has to be ordered. Queue it as
                # text so it survives the clarification instead of being lost.
                leftovers = [
                    self._stt_line_as_text(rest) for rest in raw_lines[index + 1:]
                ]
                session.chunk_queue = [t for t in leftovers if t] + session.chunk_queue
                msg = (self._added_message(added) + " " if added else "") + payload.question
                return DialogueResponse(
                    message=msg.strip(),
                    needs_clarification=True,
                    order_snapshot=self._snapshot(session),
                )
            session.order.lines.append(payload)
            added.append(payload)

        parts = []
        if added:
            parts.append(self._added_message(added))
        if not_found:
            parts.append(f"Sorry, we don't have {', '.join(not_found)} on the menu.")
        if not added and not not_found:
            parts.append("Sorry, I didn't catch an item there.")
        parts.append("Anything else, or shall I confirm your order?")
        self._persist(session)
        return DialogueResponse(
            message=" ".join(parts),
            needs_clarification=False,
            order_snapshot=self._snapshot(session),
        )

    @staticmethod
    def _stt_line_as_text(raw_line: dict) -> str:
        """Render a not-yet-processed STT line back to text for the chunk queue."""
        display = raw_line.get("display") or str(raw_line.get("canonical", "")).replace("_", " ")
        if not display:
            return ""
        quantity = raw_line.get("quantity", 1) or 1
        modifiers = " ".join(str(m) for m in (raw_line.get("modifiers") or []))
        # "i want" is deliberate: a queued STT line IS a request, so if the dish
        # turns out to be off our menu the customer gets a proper apology rather
        # than having it silently written off as small talk.
        return f"i want {quantity} {display} {modifiers}".strip()

    # ------------------------------------------------------------------ #
    # Adding items
    # ------------------------------------------------------------------ #
    def _process_chunk_queue(self, session, prior_added=None, prefix_note="") -> DialogueResponse:
        added = list(prior_added) if prior_added else []
        not_found = []
        off_topic_seen = False

        while session.chunk_queue:
            chunk = session.chunk_queue.pop(0)
            kind, payload = self._resolve_chunk_into_line(chunk)
            if kind == "pending":
                session.pending = payload
                msg = prefix_note
                if added:
                    msg += self._added_message(added) + " "
                msg += payload.question
                return DialogueResponse(
                    message=msg.strip(),
                    needs_clarification=True,
                    order_snapshot=self._snapshot(session),
                )
            elif kind == "not_found":
                not_found.append(payload)
            elif kind in ("skip", "off_topic"):
                # Either commentary about an item rather than a request for it
                # ("I've had too much coffee already"), or unrelated small talk.
                # Neither is a menu miss — acknowledge warmly, don't apologize.
                off_topic_seen = True
            else:
                session.order.lines.append(payload)
                added.append(payload)

        msg = prefix_note
        if added:
            msg += self._added_message(added) + " "
        if off_topic_seen and not added and not not_found:
            msg += "Alright! "
        if not_found:
            msg += f"Sorry, we don't have '{', '.join(not_found)}' on the menu. "
        if not added and not not_found and not off_topic_seen:
            msg += "Sorry, I didn't catch an item there. "
        msg += "Anything else, or shall I confirm your order?"
        return DialogueResponse(
            message=msg.strip(),
            needs_clarification=False,
            order_snapshot=self._snapshot(session),
        )

    def _resolve_chunk_into_line(self, chunk: str):
        """
        Returns ('line', OrderLine) | ('pending', PendingClarification)
        | ('not_found' | 'skip' | 'off_topic', str | None).
        """
        qty, remainder = extract_quantity(chunk)

        # 1. Exact phrase match against our curated aliases — highest confidence,
        #    tried before fuzzy so a coincidental fuzzy collision can never win
        #    over a genuine exact hit (or a category question, tried next).
        exact_matches = match_item(remainder, self.menu, fuzzy=False)
        category_items = match_category(remainder, self.menu, self.category_aliases) if not exact_matches else []
        # 3. Fuzzy fallback, for typos / STT mishearings of a specific dish name.
        fuzzy_matches = (
            match_item(remainder, self.menu) if not exact_matches and not category_items else []
        )
        mentions_food = bool(exact_matches or category_items or fuzzy_matches)

        if mentions_food:
            # An item mentioned only in passing ("I've had too much coffee
            # today") isn't a request for it — skip it entirely.
            if has_negative_framing(remainder) and not is_tentative(remainder):
                return "skip", None

            # Hedged interest ("I don't mind another coffee", "maybe a kopi")
            # is NOT a decision. Never add it on the customer's behalf — ask a
            # plain yes/no question and only add it once they actually agree.
            if is_tentative(remainder):
                item_matches = exact_matches or fuzzy_matches
                if item_matches and len(item_matches) == 1:
                    item = item_matches[0][0]
                    draft = DraftLine(item_id=item.id, item_name=item.name, quantity=qty)
                    how_many = "one" if qty == 1 else str(qty)
                    pending = PendingClarification(
                        kind="confirm_item",
                        question=f"Would you like me to add {how_many} {item.name} to your order?",
                        item_candidates=[item],
                        draft=draft,
                        modifier_candidates=[remainder],  # re-scanned for modifiers on "yes"
                    )
                    return "pending", pending

        if exact_matches:
            return self._handle_item_matches(exact_matches, qty, remainder)

        # 2. A bare category word ("noodles", "a drink") is genuinely ambiguous —
        #    ask which dish rather than letting a fuzzy score pick one by luck.
        if category_items:
            names = " or ".join(i.name for i in category_items)
            pending = PendingClarification(
                kind="item_ambiguous",
                question=f"Sure - which one would you like: {names}?",
                item_candidates=category_items,
                draft=DraftLine(item_id=None, item_name=None, quantity=qty),
            )
            return "pending", pending

        if fuzzy_matches:
            return self._handle_item_matches(fuzzy_matches, qty, remainder)

        # Nothing matched at all. If they were clearly trying to order
        # something, apologize; otherwise it's just unrelated chatter mixed
        # into the conversation — acknowledge and move on, don't scold them
        # for it not being on the menu.
        if not has_order_intent(remainder):
            return "off_topic", chunk.strip()
        return "not_found", self._clean_item_phrase(remainder)

    @staticmethod
    def _clean_item_phrase(text: str) -> str:
        """
        Strip request scaffolding so an unavailable item is echoed back by name
        ("Laksa"), not as the whole sentence ("i want 1 laksa").
        """
        cleaned = text.strip()
        # Longest first, so "can i have" is removed before "can".
        for phrase in sorted(ORDER_INTENT_WORDS, key=len, reverse=True):
            cleaned = re.sub(rf"\b{re.escape(phrase)}\b", " ", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\b(i|a|an|the|some|please|me)\b", " ", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,.?!")
        return cleaned or text.strip()

    def _handle_item_matches(self, matches, qty, remainder):
        if len(matches) > 1 and matches[0][1] < 100 and (matches[0][1] - matches[1][1]) < AMBIGUITY_MARGIN:
            candidates = [m[0] for m in matches[:3]]
            names = " or ".join(c.name for c in candidates)
            pending = PendingClarification(
                kind="item_ambiguous",
                question=f"Just to confirm, did you mean {names}?",
                item_candidates=candidates,
                draft=DraftLine(item_id=None, item_name=None, quantity=qty),
            )
            return "pending", pending

        item = matches[0][0]
        draft = DraftLine(item_id=item.id, item_name=item.name, quantity=qty)
        stripped = strip_matched_form(remainder, item)
        return self._fill_modifiers_or_finalize(item, draft, remainder, stripped)

    def _fill_modifiers_or_finalize(self, item, draft: DraftLine, full_text: str, stripped_text: str = None):
        """
        Returns ('line', OrderLine) | ('pending', PendingClarification).

        Two-phase per modifier group:
          1. Exact phrase match against `full_text` (item name left in). This is
             what lets compound kopitiam terms like "kopi o" / "teh c" resolve
             correctly — the milk-type alias IS "kopi o", so it needs the item's
             own name still present in the text to be found as a substring.
          2. Fuzzy fallback against `stripped_text` (item name removed) only if
             (1) found nothing — using the item's own name for fuzzy matching is
             what caused "beef noodle" to misfire against the "noodle_type"
             options earlier (both share the generic word "noodle").
        """
        if stripped_text is None:
            stripped_text = full_text

        # Pass 1: fill in every group the customer DID mention, whatever order
        # they said them in. Each group is matched independently against the
        # whole utterance, so "kopi-o kosong peng" and "peng kosong kopi-o"
        # resolve identically — sequence never matters.
        missing_required = []
        for group in item.modifier_groups:
            if group.type.value in draft.modifiers:
                continue
            opt_matches = match_options(full_text, group.options, fuzzy=False)
            if not opt_matches:
                opt_matches = match_options(stripped_text, group.options)
            if len(opt_matches) == 1:
                opt = opt_matches[0][0]
                draft.modifiers[group.type.value] = opt.id
                draft.modifier_names[group.type.value] = opt.name
            elif len(opt_matches) > 1:
                names = " or ".join(o.name for o, _ in opt_matches)
                pending = PendingClarification(
                    kind="modifier_ambiguous",
                    question=f"For your {item.name}, did you mean {names}?",
                    modifier_group=group,
                    modifier_candidates=[o for o, _ in opt_matches],
                    draft=draft,
                )
                return "pending", pending
            elif group.required:
                missing_required.append(group)
            else:
                default_opt = next((o for o in group.options if o.id == group.default), None)
                draft.modifiers[group.type.value] = group.default
                draft.modifier_names[group.type.value] = default_opt.name if default_opt else str(group.default)
                draft.defaulted.add(group.type.value)

        # Pass 2: ask for everything still missing in ONE question rather than
        # one question per dimension — being interrogated four times for a
        # single kopi is exactly the experience this system exists to replace.
        if missing_required:
            return "pending", self._build_modifier_pending(item, draft, missing_required)

        return "line", self._draft_to_orderline(item, draft)

    def _build_modifier_pending(self, item, draft, groups):
        if len(groups) == 1:
            group = groups[0]
            return PendingClarification(
                kind="modifier_batch",
                question=f"For your {item.name}, {group.prompt}",
                modifier_group=group,
                modifier_candidates=group.options,
                modifier_groups=groups,
                draft=draft,
            )
        parts = [f"{g.label} ({g.short_prompt})" for g in groups]
        listed = "; ".join(parts[:-1]) + f"; and {parts[-1]}"
        return PendingClarification(
            kind="modifier_batch",
            question=(
                f"For your {item.name}, please tell me the {listed}. "
                "You can say them all together."
            ),
            modifier_groups=groups,
            draft=draft,
        )

    def _unit_price(self, item, modifiers: dict) -> float:
        """Base price plus any per-option adjustment (a Kopi-C costs more than a Kopi-O)."""
        price = item.price
        for group in item.modifier_groups:
            chosen_id = modifiers.get(group.type.value)
            if chosen_id is None:
                continue
            for opt in group.options:
                if opt.id == chosen_id:
                    price += opt.price_delta
                    break
        return round(price, 2)

    def _draft_to_orderline(self, item, draft: DraftLine):
        from .models import OrderLine
        return OrderLine(
            line_id=str(uuid.uuid4()),
            item_id=item.id,
            item_name=item.name,
            quantity=draft.quantity,
            unit_price=self._unit_price(item, draft.modifiers),
            modifiers=dict(draft.modifiers),
            modifier_names=dict(draft.modifier_names),
        )

    # ------------------------------------------------------------------ #
    # Resolving a pending clarification
    # ------------------------------------------------------------------ #
    def _resolve_pending(self, session, transcript: str) -> DialogueResponse:
        pending = session.pending

        # These two own their whole turn: a yes/no about payment, or a
        # dine-in/takeaway answer, must not be reinterpreted as anything else.
        if pending.kind == "confirm_payment":
            return self._resolve_confirm_payment(session, transcript)
        if pending.kind == "takeaway_choice":
            return self._resolve_takeaway_choice(session, transcript)

        # "never mind" mid-clarification cancels just this item, not the whole cart.
        control = detect_control_intent(transcript)
        if control == "cancel_order":
            session.pending = None
            session.chunk_queue.clear()
            return DialogueResponse(
                message="Okay, never mind that one. Anything else you'd like?",
                needs_clarification=False,
                order_snapshot=self._snapshot(session),
            )

        # "that's all" while a question is open — the customer wants to finish,
        # not answer. Settle the open item sensibly and check out, rather than
        # trapping them in a loop of the same question.
        if control == "confirm_order" and not self._mentions_any_modifier(transcript):
            if pending.kind in ("modifier_missing", "modifier_ambiguous", "modifier_batch"):
                note = self._finalize_pending_with_defaults(session)
                confirmation = self._confirm_order(session)
                confirmation.message = note + confirmation.message
                return confirmation
            if pending.kind == "confirm_item":
                # "ok lah, that's all" carries a real yes — honour it. Anything
                # weaker is not consent, so the tentative item is dropped.
                if detect_yes_no(transcript) == "yes":
                    note = self._finalize_pending_with_defaults(session)
                    confirmation = self._confirm_order(session)
                    confirmation.message = note + confirmation.message
                    return confirmation
                session.pending = None
                confirmation = self._confirm_order(session)
                confirmation.message = "Okay, I left that one out. " + confirmation.message
                return confirmation

        if pending.kind == "confirm_item":
            return self._resolve_confirm_item(session, transcript)
        if pending.kind == "item_ambiguous":
            return self._resolve_item_ambiguous(session, transcript)
        if pending.kind in ("modifier_missing", "modifier_ambiguous", "modifier_batch"):
            return self._resolve_modifier_pending(session, transcript)
        if pending.kind == "remove_ambiguous":
            return self._resolve_remove_ambiguous(session, transcript)
        if pending.kind == "change_ambiguous":
            return self._resolve_change_ambiguous(session, transcript)
        if pending.kind == "change_item_target":
            return self._resolve_change_item_target(session, transcript)

        # Shouldn't happen, but fail safe rather than crash the conversation.
        session.pending = None
        return DialogueResponse(
            message="Sorry, let's start again - what would you like to order?",
            needs_clarification=False,
            order_snapshot=self._snapshot(session),
        )

    def _finalize_pending_with_defaults(self, session) -> str:
        """
        Close out a half-specified item using each group's default, add it to
        the cart, and return a short note naming what was chosen so the
        customer can still correct it before paying.
        """
        pending = session.pending
        draft = pending.draft
        session.pending = None
        if draft is None or draft.item_id is None:
            return ""
        item = self._get_item(draft.item_id)
        chosen = []
        for group in item.modifier_groups:
            if group.type.value in draft.modifiers:
                continue
            default_opt = next((o for o in group.options if o.id == group.default), group.options[0])
            draft.modifiers[group.type.value] = default_opt.id
            draft.modifier_names[group.type.value] = default_opt.name
            chosen.append(default_opt.name)
        session.order.lines.append(self._draft_to_orderline(item, draft))
        if chosen:
            return f"For the {item.name} I've gone with {', '.join(chosen)}. "
        return ""

    def _resolve_confirm_item(self, session, transcript) -> DialogueResponse:
        """Yes/no answer to 'would you like me to add X?' after a hedged mention."""
        pending = session.pending
        answer = detect_yes_no(transcript)

        if answer == "no":
            session.pending = None
            return DialogueResponse(
                message="No problem, I won't add it. Anything else?",
                needs_clarification=False,
                order_snapshot=self._snapshot(session),
            )

        if answer is None:
            pending.retries += 1
            if pending.retries > MAX_RETRIES:
                # Never resolve an unclear answer into an order — when in doubt,
                # add nothing. A wrongly added item costs the customer money.
                session.pending = None
                return DialogueResponse(
                    message="I'll leave that one out for now. You can ask for it again anytime. Anything else?",
                    needs_clarification=False,
                    order_snapshot=self._snapshot(session),
                )
            return DialogueResponse(
                message=pending.question,
                needs_clarification=True,
                order_snapshot=self._snapshot(session),
            )

        item = pending.item_candidates[0]
        draft = pending.draft
        session.pending = None
        # Re-scan the ORIGINAL hedged sentence plus this reply, so modifiers
        # mentioned back then ("...another kopi-o peng") aren't lost.
        original_text = pending.modifier_candidates[0] if pending.modifier_candidates else ""
        combined = f"{original_text} {transcript}"
        stripped = strip_matched_form(combined, item)
        kind, payload = self._fill_modifiers_or_finalize(item, draft, combined, stripped)
        if kind == "pending":
            session.pending = payload
            return DialogueResponse(
                message=payload.question,
                needs_clarification=True,
                order_snapshot=self._snapshot(session),
            )
        session.order.lines.append(payload)
        return self._process_chunk_queue(session, prior_added=[payload])

    def _resolve_item_ambiguous(self, session, transcript) -> DialogueResponse:
        pending = session.pending
        # Only the first chunk answers "which item did you mean" — anything the
        # elderly tacks on after ("...and also a kopi") gets queued as a new item
        # rather than silently discarded.
        chunks = self._merge_modifier_only_chunks(split_into_chunks(transcript))
        answer_chunk, trailing_chunks = chunks[0], chunks[1:]

        matches = match_item(answer_chunk, pending.item_candidates, threshold=60)
        if matches:
            item = matches[0][0]
        else:
            pending.retries += 1
            if pending.retries > MAX_RETRIES:
                item = pending.item_candidates[0]
            else:
                names = " or ".join(c.name for c in pending.item_candidates)
                return DialogueResponse(
                    message=f"Sorry, I didn't quite get that - did you mean {names}?",
                    needs_clarification=True,
                    order_snapshot=self._snapshot(session),
                )

        draft = pending.draft
        draft.item_id, draft.item_name = item.id, item.name
        session.pending = None
        session.chunk_queue = trailing_chunks + session.chunk_queue
        stripped = strip_matched_form(answer_chunk, item)
        kind, payload = self._fill_modifiers_or_finalize(item, draft, answer_chunk, stripped)
        if kind == "pending":
            session.pending = payload
            return DialogueResponse(
                message=payload.question,
                needs_clarification=True,
                order_snapshot=self._snapshot(session),
            )
        session.order.lines.append(payload)
        return self._process_chunk_queue(session, prior_added=[payload])

    def _resolve_modifier_pending(self, session, transcript) -> DialogueResponse:
        pending = session.pending
        draft = pending.draft
        chunks = self._merge_modifier_only_chunks(split_into_chunks(transcript))

        # Split the reply into "answer material" and "a genuinely new order".
        # Naming the SAME item again is a restatement, not a second order:
        # answering "hot, normal strength, teh-o" is one teh with three
        # details, so "teh-o" must feed the open question rather than start
        # another drink. Only a DIFFERENT dish begins a new line, and
        # everything after it is treated as belonging to that new dish.
        answer_parts, trailing_chunks = [], []
        for chunk in chunks:
            if trailing_chunks:
                trailing_chunks.append(chunk)
                continue
            matches = match_item(chunk, self.menu, fuzzy=False)
            is_other_item = matches and not (len(matches) == 1 and matches[0][0].id == draft.item_id)
            if is_other_item:
                trailing_chunks.append(chunk)
            else:
                answer_parts.append(chunk)
        answer_chunk = " ".join(answer_parts).strip() or transcript.strip()
        # Queue any genuinely-new dish immediately, BEFORE the early returns
        # below. If the customer names another dish while a question is still
        # open, it must survive the re-ask instead of being dropped.
        if trailing_chunks:
            session.chunk_queue = trailing_chunks + session.chunk_queue
            trailing_chunks = []

        # Groups still open. For a batch this is all of them; for the older
        # single-group kinds it's just the one.
        open_groups = pending.modifier_groups or ([pending.modifier_group] if pending.modifier_group else [])

        # Match the answer against EVERY open group, so one reply can settle
        # several dimensions at once and in any order ("kopi-o kosong peng").
        answered_any = False
        for group in open_groups:
            if group.type.value in draft.modifiers:
                continue
            opt_matches = match_options(answer_chunk, group.options)
            if len(opt_matches) == 1:
                opt = opt_matches[0][0]
                draft.modifiers[group.type.value] = opt.id
                draft.modifier_names[group.type.value] = opt.name
                answered_any = True

        # A correction can arrive mid-question: "aiya wait wait, make it kway
        # teow instead" names a choice that was already settled. Re-open that
        # group and overwrite it rather than rejecting the answer.
        draft_item = self._get_item(draft.item_id)
        corrected = []
        for group in draft_item.modifier_groups:
            if group.type.value not in draft.modifiers:
                continue
            opt_matches = match_options(answer_chunk, group.options, fuzzy=False)
            if len(opt_matches) == 1 and opt_matches[0][0].id != draft.modifiers[group.type.value]:
                opt = opt_matches[0][0]
                was_defaulted = group.type.value in draft.defaulted
                draft.modifiers[group.type.value] = opt.id
                draft.modifier_names[group.type.value] = opt.name
                draft.defaulted.discard(group.type.value)
                # Overwriting a silent default is them answering, not changing
                # their mind — only a real correction gets read back.
                if not was_defaulted:
                    corrected.append(opt.name)
                answered_any = True
        # Say the correction out loud — a silent change is one the customer
        # can't catch before it reaches the kitchen.
        correction_note = f"Okay, changed to {', '.join(corrected)}. " if corrected else ""

        # "normal lah" / "anything can" settles every remaining choice with
        # the plain default in one go.
        if not answered_any and wants_default(answer_chunk):
            for group in open_groups:
                if group.type.value in draft.modifiers:
                    continue
                default_opt = next((o for o in group.options if o.id == group.default), group.options[0])
                draft.modifiers[group.type.value] = default_opt.id
                draft.modifier_names[group.type.value] = default_opt.name
                answered_any = True

        # The customer's reply to a modifier_ambiguous question may just name
        # one of the offered options directly.
        if not answered_any and pending.kind == "modifier_ambiguous" and pending.modifier_candidates:
            opt_matches = match_options(answer_chunk, pending.modifier_candidates)
            if opt_matches:
                group = pending.modifier_group
                opt = opt_matches[0][0]
                draft.modifiers[group.type.value] = opt.id
                draft.modifier_names[group.type.value] = opt.name
                answered_any = True

        fallback_note = correction_note
        if not answered_any:
            pending.retries += 1
            if pending.retries <= MAX_RETRIES:
                return DialogueResponse(
                    message=f"Sorry, could you let me know - {pending.question}",
                    needs_clarification=True,
                    order_snapshot=self._snapshot(session),
                )
            # Out of retries: fall back to each group's default so the customer
            # isn't stuck in a loop. Defaults are the safe/plain choice
            # (no chilli, normal sweetness), and we say what we picked.
            chosen = []
            for group in open_groups:
                if group.type.value in draft.modifiers:
                    continue
                default_opt = next((o for o in group.options if o.id == group.default), group.options[0])
                draft.modifiers[group.type.value] = default_opt.id
                draft.modifier_names[group.type.value] = default_opt.name
                chosen.append(default_opt.name)
            if chosen:
                fallback_note += f"No worries - I'll go with {', '.join(chosen)} for now. "

        session.pending = None
        session.chunk_queue = trailing_chunks + session.chunk_queue

        item = self._get_item(draft.item_id)
        # Re-scan the same answer for any OTHER modifiers named alongside it —
        # "bee hoon, dry" answers the noodle-type question and specifies the
        # soup style in one breath, so "dry" must not be thrown away here.
        kind, payload = self._fill_modifiers_or_finalize(item, draft, answer_chunk)
        if kind == "pending":
            session.pending = payload
            return DialogueResponse(
                message=(fallback_note + payload.question).strip(),
                needs_clarification=True,
                order_snapshot=self._snapshot(session),
            )
        session.order.lines.append(payload)
        return self._process_chunk_queue(session, prior_added=[payload], prefix_note=fallback_note)

    def _resolve_remove_ambiguous(self, session, transcript) -> DialogueResponse:
        pending = session.pending
        lines = [l for l in session.order.lines if l.line_id in pending.target_line_id]
        session.pending = None
        t = transcript.lower()
        targets = lines if any(w in t for w in ("all", "both", "every")) else lines[:1]

        removed, blocked = 0, []
        for line in targets:
            ok, _ = self._try_remove_line(session, line)
            if ok:
                removed += 1
            else:
                blocked.append(line.item_name)

        parts = []
        if removed:
            parts.append(f"Okay, removed {removed} of them." if removed > 1 else "Okay, removed one of them.")
        if blocked:
            parts.append(
                f"The kitchen has already started on {', '.join(dict.fromkeys(blocked))}, "
                "so that one stays on your bill."
            )
        parts.append("Anything else?")
        return DialogueResponse(
            message=" ".join(parts),
            needs_clarification=False,
            order_snapshot=self._snapshot(session),
        )

    def _resolve_change_ambiguous(self, session, transcript) -> DialogueResponse:
        pending = session.pending
        candidate_lines = [l for l in session.order.lines if l.line_id in pending.target_line_id]
        target = self._match_line_by_text(transcript, candidate_lines)
        session.pending = None
        if target is None:
            return DialogueResponse(
                message="Sorry, I couldn't tell which one - could you say the dish name again?",
                needs_clarification=False,
                order_snapshot=self._snapshot(session),
            )
        blocked = self._change_blocked_reason(session, target)
        if blocked:
            return DialogueResponse(
                message=blocked,
                needs_clarification=False,
                order_snapshot=self._snapshot(session),
            )
        # modifier_candidates holds (group, option) pairs — one utterance can
        # name more than one change at once (e.g. "kopi c kosong").
        for group, opt in pending.modifier_candidates:
            target.modifiers[group.type.value] = opt.id
            target.modifier_names[group.type.value] = opt.name
        self._reprice(target)
        names = " and ".join(opt.name for _, opt in pending.modifier_candidates)
        return DialogueResponse(
            message=f"Got it, changed to {names} for your {target.item_name}.",
            needs_clarification=False,
            order_snapshot=self._snapshot(session),
        )

    def _resolve_change_item_target(self, session, transcript) -> DialogueResponse:
        pending = session.pending
        candidate_lines = [l for l in session.order.lines if l.line_id in pending.target_line_id]
        target = self._match_line_by_text(transcript, candidate_lines)
        session.pending = None
        if target is None:
            return DialogueResponse(
                message="Sorry, could you tell me again which item to change?",
                needs_clarification=False,
                order_snapshot=self._snapshot(session),
            )
        new_item = pending.item_candidates[0]
        qty = target.quantity
        session.order.lines.remove(target)
        draft = DraftLine(item_id=new_item.id, item_name=new_item.name, quantity=qty)
        stripped = strip_matched_form(transcript, new_item)
        kind, payload = self._fill_modifiers_or_finalize(new_item, draft, transcript, stripped)
        if kind == "pending":
            session.pending = payload
            return DialogueResponse(
                message=payload.question,
                needs_clarification=True,
                order_snapshot=self._snapshot(session),
            )
        session.order.lines.append(payload)
        return DialogueResponse(
            message=f"Changed it to {new_item.name}.",
            needs_clarification=False,
            order_snapshot=self._snapshot(session),
        )

    # ------------------------------------------------------------------ #
    # Remove / change / confirm
    # ------------------------------------------------------------------ #
    def _handle_remove(self, session, transcript) -> DialogueResponse:
        if not session.order.lines:
            return DialogueResponse(
                message="You don't have anything in your order yet.",
                needs_clarification=False,
                order_snapshot=self._snapshot(session),
            )
        present_items = {l.item_id: self._get_item(l.item_id) for l in session.order.lines}
        matches = match_item(transcript, list(present_items.values()))
        if not matches:
            return DialogueResponse(
                message="I'm not sure which item you'd like to remove. Could you say the dish name?",
                needs_clarification=True,
                order_snapshot=self._snapshot(session),
            )
        target_item = matches[0][0]
        matching_lines = [l for l in session.order.lines if l.item_id == target_item.id]
        if len(matching_lines) > 1:
            pending = PendingClarification(
                kind="remove_ambiguous",
                question=f"You have {len(matching_lines)} orders of {target_item.name}. Should I remove all of them, or just one?",
                target_line_id=[l.line_id for l in matching_lines],
            )
            session.pending = pending
            return DialogueResponse(
                message=pending.question,
                needs_clarification=True,
                order_snapshot=self._snapshot(session),
            )
        line = matching_lines[0]
        removed, reason = self._try_remove_line(session, line)
        return DialogueResponse(
            message=(f"Okay, removed {line.item_name} from your order. Anything else?"
                     if removed else reason),
            needs_clarification=False,
            order_snapshot=self._snapshot(session),
        )

    def _try_remove_line(self, session, line) -> tuple:
        """
        Remove a line if the kitchen hasn't started on it.

        Returns (removed, reason). Once cooking has begun the food exists and
        someone has to pay for it, so the line stays on the bill and we say so
        plainly rather than silently failing.
        """
        if not line.sent:
            session.order.lines.remove(line)
            self._persist(session)
            return True, ""

        result = cancel_line(session.order.order_id, line.line_id)
        if result["cancelled"]:
            session.order.lines.remove(line)
            self._persist(session)
            return True, ""

        stage = "already being prepared" if result["status"] == "preparing" else "already ready"
        return False, (
            f"Sorry, your {line.item_name} is {stage}, so I can't cancel that one. "
            "It'll still be on your bill. Anything else?"
        )

    def _handle_change(self, session, transcript) -> DialogueResponse:
        if not session.order.lines:
            return DialogueResponse(
                message="You haven't ordered anything yet - what would you like?",
                needs_clarification=False,
                order_snapshot=self._snapshot(session),
            )

        # 1. Try modifier-only changes first, e.g. "actually change the noodles to
        #    kway teow" or "make it kopi c kosong" (more than one change at once —
        #    every matching modifier group is collected, not just the first hit).
        groups_in_cart = {}
        for l in session.order.lines:
            item = self._get_item(l.item_id)
            for g in item.modifier_groups:
                groups_in_cart.setdefault(g.type.value, g)

        found_changes = []  # [(gtype, group, ModifierOption), ...]
        for gtype, group in groups_in_cart.items():
            opt_matches = match_options(transcript, group.options)
            if opt_matches:
                found_changes.append((gtype, group, opt_matches[0][0]))

        if found_changes:
            # Only a line that has every one of the mentioned modifier types is
            # a plausible target (e.g. "kopi c kosong" can't apply to a noodle line).
            candidate_lines = session.order.lines
            for gtype, _, _ in found_changes:
                candidate_lines = [l for l in candidate_lines if gtype in l.modifiers]

            if len(candidate_lines) == 1:
                line = candidate_lines[0]
                blocked = self._change_blocked_reason(session, line)
                if blocked:
                    return DialogueResponse(
                        message=blocked,
                        needs_clarification=False,
                        order_snapshot=self._snapshot(session),
                    )
                for gtype, _, opt in found_changes:
                    line.modifiers[gtype] = opt.id
                    line.modifier_names[gtype] = opt.name
                self._reprice(line)
                names = " and ".join(opt.name for _, _, opt in found_changes)
                return DialogueResponse(
                    message=f"Got it, changed to {names} for your {line.item_name}.",
                    needs_clarification=False,
                    order_snapshot=self._snapshot(session),
                )
            if len(candidate_lines) > 1:
                names = " or ".join(l.item_name for l in candidate_lines)
                opt_names = " and ".join(opt.name for _, _, opt in found_changes)
                pending = PendingClarification(
                    kind="change_ambiguous",
                    question=f"You have a few items with that choice - which one should I change to {opt_names}: {names}?",
                    modifier_candidates=[(group, opt) for _, group, opt in found_changes],
                    target_line_id=[l.line_id for l in candidate_lines],
                )
                session.pending = pending
                return DialogueResponse(
                    message=pending.question,
                    needs_clarification=True,
                    order_snapshot=self._snapshot(session),
                )

        # 2. Otherwise treat it as a whole-item swap, e.g. "change it to fried rice instead".
        matches = match_item(transcript, self.menu)
        if matches:
            new_item = matches[0][0]
            if len(session.order.lines) == 1:
                line = session.order.lines[0]
                qty = line.quantity
                session.order.lines.remove(line)
                draft = DraftLine(item_id=new_item.id, item_name=new_item.name, quantity=qty)
                stripped = strip_matched_form(transcript, new_item)
                kind, payload = self._fill_modifiers_or_finalize(new_item, draft, transcript, stripped)
                if kind == "pending":
                    session.pending = payload
                    return DialogueResponse(
                        message=f"Sure, changing to {new_item.name}. {payload.question}",
                        needs_clarification=True,
                        order_snapshot=self._snapshot(session),
                    )
                session.order.lines.append(payload)
                return DialogueResponse(
                    message=f"Changed your order to {new_item.name}.",
                    needs_clarification=False,
                    order_snapshot=self._snapshot(session),
                )
            names = " or ".join(l.item_name for l in session.order.lines)
            pending = PendingClarification(
                kind="change_item_target",
                question=f"Which item would you like to change: {names}?",
                item_candidates=[new_item],
                target_line_id=[l.line_id for l in session.order.lines],
            )
            session.pending = pending
            return DialogueResponse(
                message=pending.question,
                needs_clarification=True,
                order_snapshot=self._snapshot(session),
            )

        return DialogueResponse(
            message="Sorry, I'm not sure what you'd like to change it to. Could you tell me the dish or the type again?",
            needs_clarification=True,
            order_snapshot=self._snapshot(session),
        )

    def _confirm_order(self, session) -> DialogueResponse:
        if not session.order.lines:
            return DialogueResponse(
                message="You haven't ordered anything yet. What would you like?",
                needs_clarification=False,
                order_snapshot=self._snapshot(session),
            )

        new_lines = session.order.new_lines
        if not new_lines:
            # Everything on the tab is already with the kitchen — nothing to send.
            return DialogueResponse(
                message=(
                    f"Everything's already with the kitchen. Your total so far is "
                    f"${session.order.total:.2f}. Anything else?"
                ),
                needs_clarification=False,
                order_snapshot=self._snapshot(session),
            )

        # Ask about takeaway once, if they never said. Order-level, so it only
        # ever gets asked a single time per table.
        if session.order.takeaway is None:
            session.pending = PendingClarification(
                kind="takeaway_choice",
                question="Will you be eating here, or taking away?",
            )
            return DialogueResponse(
                message=session.pending.question,
                needs_clarification=True,
                order_snapshot=self._snapshot(session),
            )

        # Only the new lines go to the kitchen — a running tab must never
        # re-send food the kitchen already has.
        kitchen_resp = send_order_to_kitchen(session.order, lines=new_lines)
        by_line = {r["line_id"]: r for r in kitchen_resp["line_results"]}

        unavailable_names = []
        for line in list(new_lines):
            result = by_line.get(line.line_id)
            if result is None:
                continue
            if result["available"]:
                line.sent = True
                line.kitchen_status = result.get("status") or "received"
            else:
                # Drop it from the bill so they're never charged for food that
                # can't be made.
                unavailable_names.append(line.item_name)
                session.order.lines.remove(line)

        session.order.status = "sent_to_kitchen"

        parts = []
        if unavailable_names:
            names = ", ".join(dict.fromkeys(unavailable_names))
            parts.append(f"I'm sorry, we've just run out of {names}, so I've taken that off your bill.")
            suggestions = self._suggest_alternatives(unavailable_names)
            if suggestions:
                parts.append(f"Would you like {suggestions} instead?")
        if any(l.sent for l in session.order.lines):
            parts.append("The rest of your order has been sent to the kitchen."
                         if unavailable_names else "Your order has been sent to the kitchen.")
        parts.append(f"Your total so far is ${session.order.total:.2f}.")
        if not unavailable_names:
            parts.append("Just say 'bill' when you're ready to pay.")

        self._persist(session)
        return DialogueResponse(
            message=" ".join(parts),
            needs_clarification=bool(unavailable_names),
            order_confirmed=not bool(unavailable_names),
            order_snapshot=self._snapshot(session),
            kitchen_response=kitchen_resp,
        )

    # ------------------------------------------------------------------ #
    # Paying the bill — the only thing that clears a table
    # ------------------------------------------------------------------ #
    def _handle_pay_bill(self, session) -> DialogueResponse:
        if not session.order.lines:
            return DialogueResponse(
                message="You haven't ordered anything yet, so there's nothing to pay. What would you like?",
                needs_clarification=False,
                order_snapshot=self._snapshot(session),
            )

        itemised = "; ".join(
            f"{l.quantity} x {l.item_name} ${l.subtotal:.2f}" for l in session.order.lines
        )
        still_cooking = [l.item_name for l in session.order.lines
                         if l.kitchen_status in ("received", "preparing")]
        note = ""
        if still_cooking:
            names = list(dict.fromkeys(still_cooking))
            verb = "is" if len(names) == 1 else "are"
            note = f" Do note your {', '.join(names)} {verb} still being prepared."

        question = (
            f"Here's your bill: {itemised}. That comes to "
            f"${session.order.total:.2f}.{note} Shall I close the table?"
        )
        # Clearing a table can't be undone, so it always takes an explicit yes.
        session.pending = PendingClarification(kind="confirm_payment", question=question)
        return DialogueResponse(
            message=question,
            needs_clarification=True,
            order_snapshot=self._snapshot(session),
        )

    def _resolve_confirm_payment(self, session, transcript) -> DialogueResponse:
        pending = session.pending
        answer = detect_yes_no(transcript)

        if answer == "no":
            session.pending = None
            return DialogueResponse(
                message="No problem, I'll keep your table open. Anything else?",
                needs_clarification=False,
                order_snapshot=self._snapshot(session),
            )

        if answer is None:
            pending.retries += 1
            if pending.retries > MAX_RETRIES:
                # Never clear a table on an unclear answer — leaving it open is
                # recoverable, wiping someone's bill is not.
                session.pending = None
                return DialogueResponse(
                    message="I'll leave your table open for now. Just say 'bill' when you're ready.",
                    needs_clarification=False,
                    order_snapshot=self._snapshot(session),
                )
            return DialogueResponse(
                message=f"Sorry, could you confirm - {pending.question}",
                needs_clarification=True,
                order_snapshot=self._snapshot(session),
            )

        total = session.order.total
        session.pending = None
        receipt = None
        if self.session_store is not None:
            receipt = self.session_store.mark_paid(session.table_id)
        else:
            # Standalone mode: no store, so settle the in-memory order directly.
            session.order.status = "paid"
            session.order.lines.clear()

        return DialogueResponse(
            message=(
                f"Thank you! ${total:.2f} received. Your table is now closed - "
                "please come again!"
            ),
            needs_clarification=False,
            order_confirmed=True,
            order_snapshot=self._snapshot(session),
            receipt=receipt,
        )

    def _resolve_takeaway_choice(self, session, transcript) -> DialogueResponse:
        choice = detect_takeaway(transcript)
        if choice is None:
            # A bare yes/no to "eating here or taking away?" is genuinely
            # ambiguous, so only clear phrasing counts.
            session.pending.retries += 1
            if session.pending.retries > MAX_RETRIES:
                session.order.takeaway = False   # dine-in is the safe default in-store
                session.pending = None
                return self._confirm_order(session)
            return DialogueResponse(
                message="Sorry - will you be eating here, or taking away?",
                needs_clarification=True,
                order_snapshot=self._snapshot(session),
            )
        session.order.takeaway = choice
        session.pending = None
        return self._confirm_order(session)

    def _persist(self, session) -> None:
        if self.session_store is not None:
            self.session_store.save()

    def _reprice(self, line) -> None:
        """Re-apply price deltas after a modifier changes (Kopi-O -> Kopi-C costs more)."""
        line.unit_price = self._unit_price(self._get_item(line.item_id), line.modifiers)

    def _change_blocked_reason(self, session, line) -> str:
        """
        Empty string if the line may still be changed. Once the kitchen has
        started cooking it, changing the order is no longer possible.
        """
        if not line.sent:
            return ""
        from .kitchen_interface import get_line_status
        status = get_line_status(session.order.order_id, line.line_id)
        if status in ("preparing", "done"):
            stage = "already being prepared" if status == "preparing" else "already ready"
            return (
                f"Sorry, your {line.item_name} is {stage}, so I can't change that one now. "
                "Would you like to order something else instead?"
            )
        return ""

    def _suggest_alternatives(self, unavailable_names, limit: int = 2) -> str:
        """Other dishes from the same category, so a sold-out item isn't a dead end."""
        gone = set(unavailable_names)
        categories = {i.category for i in self.menu if i.name in gone}
        picks = [
            i.name for i in self.menu
            if i.category in categories and i.name not in gone
        ][:limit]
        return " or ".join(picks)

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    def _match_line_by_text(self, text, lines):
        items = [self._get_item(l.item_id) for l in lines]
        matches = match_item(text, items, threshold=60)
        if not matches:
            return None
        chosen_id = matches[0][0].id
        for l in lines:
            if l.item_id == chosen_id:
                return l
        return None

    def _added_message(self, lines) -> str:
        parts = []
        for l in lines:
            mods = ", ".join(l.modifier_names.values())
            mod_str = f" ({mods})" if mods else ""
            parts.append(f"{l.quantity} x {l.item_name}{mod_str}")
        return "Added " + ", ".join(parts) + "."

    def _snapshot(self, session) -> dict:
        lines = session.order.lines
        return {
            "table_id": session.table_id,
            "order_id": session.order.order_id,
            "status": session.order.status,
            "takeaway": session.order.takeaway,
            "lines": [
                {
                    "item": l.item_name,
                    "quantity": l.quantity,
                    "modifiers": l.modifier_names,
                    "unit_price": l.unit_price,
                    "subtotal": l.subtotal,
                    "sent": l.sent,
                    "kitchen_status": l.kitchen_status,
                }
                for l in lines
            ],
            "total": session.order.total,
        }

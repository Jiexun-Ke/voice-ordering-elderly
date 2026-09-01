"""
Rule-based control-intent spotting.

Elderly customers tend to speak in short, plain sentences ("cancel that",
"no more", "actually change it"), so keyword spotting is deliberately used
here instead of a full intent classifier — it's transparent, easy to tune,
and doesn't need training data. The STT+LLM side only ever hands us raw
transcript text, so this module owns all intent detection.

Checked in this order because a single utterance could contain overlapping
words (e.g. "actually" implies change even if "cancel" isn't present).
"""
from typing import Optional

# Each list carries both standard-English and Singlish/dialect phrasings,
# since elderly customers rarely use the formal forms ("don't want already",
# "dun want", "sian", "bo ai" are all far likelier than "please remove").
CANCEL_KEYWORDS = [
    "cancel", "forget it", "never mind", "nevermind", "start over",
    "scrap that", "scratch that", "dont want already", "don't want already",
    "bo ai", "all cancel", "clear all",
]
CHANGE_KEYWORDS = [
    "change to", "change it", "change my", "instead of", "make that",
    "make it", "switch to", "actually", "aiya", "wait wait", "eh no",
    "no no", "i mean",
]
REMOVE_KEYWORDS = [
    "remove", "take out", "take away the", "delete", "don't want", "dont want",
    "dun want", "no longer want", "dont need", "don't need", "cut the",
    "skip the", "no need the",
]
CONFIRM_KEYWORDS = [
    "that's all", "thats all", "that is all", "that's it", "thats it",
    "that is it", "confirm", "that's everything", "thats everything",
    "no more", "i'm done", "im done", "finish", "finish already", "done already",
    "enough already", "can already", "ok lah", "okay lah", "oklah",
    "like that can already", "settle", "that's enough", "thats enough",
]
# Asking for the bill is NOT the same as finishing an order — one sends food
# to the kitchen, the other ends the meal and clears the table. Checked BEFORE
# confirm so "settle the bill" isn't swallowed by the bare "settle" above.
PAY_KEYWORDS = [
    "bill", "the bill", "pay", "paying", "pay now", "how much", "how much altogether",
    "how much in total", "check please", "settle the bill", "settle up",
    "mai tan", "maidan", "buay dan", "receipt", "checkout", "check out",
]


def detect_control_intent(text: str) -> Optional[str]:
    t = text.lower()
    if any(k in t for k in PAY_KEYWORDS):
        return "pay_bill"
    if any(k in t for k in CANCEL_KEYWORDS):
        return "cancel_order"
    # Removal is checked BEFORE change: "actually the nasi lemak also dont want"
    # contains both, but "dont want" is an explicit instruction while "actually"
    # is just a filler connector Singlish speakers open half their sentences with.
    if any(k in t for k in REMOVE_KEYWORDS):
        return "remove_item"
    if any(k in t for k in CHANGE_KEYWORDS):
        return "change_item"
    if any(k in t for k in CONFIRM_KEYWORDS):
        return "confirm_order"
    return None


# ---------------------------------------------------------------------- #
# Takeaway vs dine-in. Order-level, matching the STT teammate's `takeaway`
# field. Note the absence of a bare "here" — it appears in far too many
# ordinary sentences ("what do you have here?") to be a safe signal.
# ---------------------------------------------------------------------- #
TAKEAWAY_WORDS = [
    "tapao", "ta pao", "dabao", "da bao", "takeaway", "take away", "take-away",
    "to go", "pack it", "pack up", "bungkus", "wrap it up",
]
DINE_IN_WORDS = [
    "eat here", "eating here", "dine in", "dine-in", "have here", "having here",
    "makan here", "sit here", "stay here", "not takeaway", "no takeaway",
]


# "take away the prata" is a removal, not a request to tapao the order. The
# trailing article is what separates the two senses.
_REMOVAL_SENSE = ["take away the", "take away my", "take out the", "take out my"]


def detect_takeaway(text: str) -> Optional[bool]:
    """Returns True (takeaway), False (dine in), or None if not stated."""
    t = " " + text.lower().strip() + " "
    if any(w in t for w in _REMOVAL_SENSE):
        return None
    # Dine-in first: "not takeaway" contains "takeaway".
    if any(w in t for w in DINE_IN_WORDS):
        return False
    if any(w in t for w in TAKEAWAY_WORDS):
        return True
    return None


# ---------------------------------------------------------------------- #
# "I've had too much coffee today, but I don't mind another" — an elderly
# customer thinking out loud about a food item isn't the same as ordering
# it. These lists are a narrow, explainable heuristic (not real
# sentiment/negation NLU) for telling the three cases apart:
#
#   negative framing, no override  -> pure commentary, ignore entirely
#   tentative / hedged             -> ASK before adding ("shall I add one?")
#   plain request                  -> add it
#
# Nothing tentative is ever added to the cart on its own: "I don't mind
# another coffee" is musing aloud, not a decision, so it always gets an
# explicit yes/no question first.
# ---------------------------------------------------------------------- #
NEGATIVE_FRAMING = [
    "too much", "too many", "already had", "already drank", "already ate",
    "already eaten", "cannot take", "can't take", "no need", "not in the mood",
    "shouldn't", "enough already", "had enough", "sian of",
]

# Hedged/musing phrasing — recognised as *interest*, never as an order.
TENTATIVE_PHRASES = [
    "don't mind", "dont mind", "wouldn't mind", "wouldnt mind", "won't mind",
    "why not", "maybe", "perhaps", "might", "thinking of", "thinking about",
    "could go for", "feel like", "how about", "what about", "shall i",
    "should i", "can consider", "quite like", "tempted",
]


def has_negative_framing(text: str) -> bool:
    t = text.lower()
    return any(k in t for k in NEGATIVE_FRAMING)


def is_tentative(text: str) -> bool:
    t = text.lower()
    return any(k in t for k in TENTATIVE_PHRASES)


# Short yes/no replies, including Singlish forms, for confirming a tentative
# mention ("Would you like me to add a Kopi for you?").
YES_WORDS = [
    "yes", "yes lah", "yah", "yeah", "ya", "yup", "yep", "ok", "okay", "ok lah",
    "okay lah", "oklah", "can", "can lah", "sure", "alright", "please", "want",
    "add", "correct", "right", "confirm", "good", "why not", "of course",
]
NO_WORDS = [
    "no", "nope", "no lah", "dont", "don't", "dun", "no need", "never mind",
    "nevermind", "skip", "forget it", "not want", "dont want", "don't want",
    "no thanks", "no thank you", "bo ai", "cancel",
]


# Checked BEFORE yes/no: "not sure" contains "sure", "dunno" contains no
# yes-word but reads as hesitation. Treating either as agreement would add
# something the customer never asked for, so these always resolve to "unclear".
UNCLEAR_PHRASES = [
    "not sure", "dont know", "don't know", "dunno", "no idea", "cannot decide",
    "cannot make up", "let me think", "hmm", "hmmm", "erm", "uh", "up to you",
    "anything also can", "you choose", "whatever",
]


def detect_yes_no(text: str) -> Optional[str]:
    """Returns 'yes' | 'no' | None (unclear). Hesitation and 'no' both beat 'yes'."""
    t = " " + text.lower().strip() + " "
    if any(p in t for p in UNCLEAR_PHRASES):
        return None
    for w in NO_WORDS:
        if f" {w} " in t or t.strip() == w:
            return "no"
    for w in YES_WORDS:
        if f" {w} " in t or t.strip() == w:
            return "yes"
    return None


# Words/phrases that signal "I'm trying to order something" even when it
# doesn't match anything on the menu — used to tell "I want a burger" (not
# found, apologize) apart from pure small talk like "going cycling later"
# (off-topic, acknowledge and move on) when neither matches the menu.
ORDER_INTENT_WORDS = [
    "want", "give me", "can i have", "get me", "order", "i'll have",
    "ill have", "i would like", "can i get", "please give", "make it",
]


def has_order_intent(text: str) -> bool:
    t = text.lower()
    return any(w in t for w in ORDER_INTENT_WORDS)


# "normal lah", "anything can", "up to you" — a real answer meaning "give me
# the usual". Lets a customer settle every remaining choice at once instead
# of being walked through each one.
GENERIC_DEFAULT_WORDS = [
    "normal", "regular", "standard", "usual", "anything", "any", "whatever",
    "up to you", "you decide", "you choose", "same as usual", "as usual",
]


def wants_default(text: str) -> bool:
    t = " " + text.lower().strip() + " "
    return any(f" {w} " in t or t.strip() == w for w in GENERIC_DEFAULT_WORDS)

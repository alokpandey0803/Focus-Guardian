"""
Lock-in mode helpers.
Generates a random, hard-to-type password and validates user input.
"""
import random
import string


_ALPHABET = string.ascii_letters + string.digits + "!@#$%^&*()-_=+[]{}|;:,.<>?"
PASSWORD_LENGTH = 30


def generate_password() -> str:
    """Return a new random 30-character password."""
    return "".join(random.choices(_ALPHABET, k=PASSWORD_LENGTH))


def verify_password(entered: str, expected: str) -> bool:
    """Case-sensitive exact match."""
    return entered == expected


# ── "Are you sure?" prompts shown right before an early manual unlock ──────
# The goal isn't to guilt-trip someone with a genuine emergency — it's to
# put one honest speed bump between an impulsive "just gonna check
# Instagram real quick" and actually typing that 30-character password out.
RETHINK_QUOTES = [
    "You didn't lock yourself in for no reason. Is this actually urgent —\n"
    "or is that just the distraction talking?",
    "The version of you who started this session needed this time.\n"
    "Don't let a five-minute impulse overrule them.",
    "If it's genuinely urgent, go ahead. If it's just boredom or a notification,\n"
    "quitting now only proves the distraction is stronger than you are.",
    "You typed all 30 characters to prove you meant it. Do you still mean it —\n"
    "or did something just get more interesting than your goal?",
    "Nobody regrets finishing a focus session. Almost everyone regrets\n"
    "the one they quit ten minutes early.",
    "Discipline is doing this even when a part of you wants out.\n"
    "That part talking right now isn't your future self.",
    "Ask yourself honestly: is this a real emergency, or an excuse\n"
    "dressed up as one?",
    "You can't get this time back once you break focus. Make sure\n"
    "whatever's pulling you away is actually worth that trade.",
]


def random_rethink_quote() -> str:
    return random.choice(RETHINK_QUOTES)

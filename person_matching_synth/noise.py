"""Noise-injection functions. Each is pure: (value: str, rng: random.Random) -> mutated_value."""

import random
from typing import Callable

from .config import ErrorType


class NoiseNotApplicable(Exception):
    """Raised when a noise function cannot meaningfully mutate the given input."""
    pass


# QWERTY adjacency map for TYPO: each key -> list of adjacent keys (including itself for convenience)
_QWERTY_ADJACENCY: dict[str, list[str]] = {
    'q': ['q', 'w', 'a', 's'],
    'w': ['w', 'q', 'e', 'a', 's', 'd'],
    'e': ['e', 'w', 'r', 'd', 's', 'f'],
    'r': ['r', 'e', 't', 'f', 'g', 'd'],
    't': ['t', 'r', 'y', 'g', 'h', 'f'],
    'y': ['y', 't', 'u', 'h', 'j', 'g'],
    'u': ['u', 'y', 'i', 'j', 'k', 'h'],
    'i': ['i', 'u', 'o', 'k', 'l', 'j'],
    'o': ['o', 'i', 'p', 'l', 'k'],
    'p': ['p', 'o', 'l'],
    'a': ['a', 'q', 'w', 's', 'z', 'x'],
    's': ['s', 'q', 'w', 'e', 'a', 'z', 'x', 'd'],
    'd': ['d', 'w', 'e', 'r', 's', 'x', 'c', 'f'],
    'f': ['f', 'e', 'r', 't', 'd', 'c', 'v', 'g'],
    'g': ['g', 'r', 't', 'y', 'f', 'v', 'b', 'h'],
    'h': ['h', 't', 'y', 'u', 'g', 'b', 'n', 'j'],
    'j': ['j', 'y', 'u', 'i', 'h', 'n', 'm', 'k'],
    'k': ['k', 'u', 'i', 'o', 'j', 'm', 'l'],
    'l': ['l', 'i', 'o', 'p', 'k'],
    'z': ['z', 'a', 's', 'x'],
    'x': ['x', 'a', 's', 'd', 'z', 'c'],
    'c': ['c', 's', 'd', 'f', 'x', 'v'],
    'v': ['v', 'd', 'f', 'g', 'c', 'b'],
    'b': ['b', 'f', 'g', 'h', 'v', 'n'],
    'n': ['n', 'g', 'h', 'j', 'b', 'm'],
    'm': ['m', 'h', 'j', 'k', 'n'],
}

# Common UK forename abbreviations for ABBREVIATION
_UK_FORENAME_SHORT_FORMS: dict[str, str] = {
    "alexander": "alex",
    "alexandra": "alex",
    "anthony": "tony",
    "catherine": "cathy",
    "christopher": "chris",
    "daniel": "dan",
    "david": "dave",
    "deborah": "deb",
    "elizabeth": "liz",
    "elizabeth": "beth",
    "geoffrey": "jeff",
    "gregory": "greg",
    "jennifer": "jen",
    "joseph": "joe",
    "katherine": "kate",
    "margaret": "maggie",
    "matthew": "matt",
    "michael": "mike",
    "nicholas": "nick",
    "patricia": "pat",
    "robert": "rob",
    "stephen": "steve",
    "steven": "steve",
    "theodore": "ted",
    "thomas": "tom",
    "william": "bill",
    "winston": "win",
}


def apply_typo(value: str, rng: random.Random) -> str:
    if not value:
        return value
    pos = rng.randint(0, len(value) - 1)
    ch = value[pos].lower()
    if ch not in _QWERTY_ADJACENCY:
        # Pick a random letter different from the original
        orig_lower = value[pos].lower()
        choices = [c for c in "abcdefghijklmnopqrstuvwxyz" if c != orig_lower]
        replacement = rng.choice(choices) if choices else orig_lower
    else:
        # Exclude the original character from adjacency choices to guarantee a change
        adjacents = [c for c in _QWERTY_ADJACENCY[ch] if c != ch]
        if not adjacents:
            # Fallback: pick any different letter
            orig_lower = value[pos].lower()
            choices = [c for c in "abcdefghijklmnopqrstuvwxyz" if c != orig_lower]
            replacement = rng.choice(choices) if choices else orig_lower
        else:
            replacement = rng.choice(adjacents)
    # Preserve original case
    if value[pos].isupper():
        replacement = replacement.upper()
    return value[:pos] + replacement + value[pos + 1:]


def apply_transposition(value: str, rng: random.Random) -> str:
    if len(value) < 2:
        raise NoiseNotApplicable("transposition requires at least 2 characters")
    pos = rng.randint(0, len(value) - 2)
    # swap pos and pos+1
    lst = list(value)
    lst[pos], lst[pos + 1] = lst[pos + 1], lst[pos]
    return "".join(lst)


def apply_abbreviation(value: str, rng: random.Random) -> str:
    if not value:
        return value
    low = value.lower()
    if low in _UK_FORENAME_SHORT_FORMS:
        abbr = _UK_FORENAME_SHORT_FORMS[low]
    else:
        # Fallback: first initial only
        abbr = value[0]
    # Preserve case: if original was all caps or title case, adapt
    if value.isupper():
        return abbr.upper()
    if value.istitle():
        return abbr.capitalize()
    return abbr


def apply_missing_token(value: str, rng: random.Random) -> str:
    tokens = value.split()
    if len(tokens) <= 1:
        raise NoiseNotApplicable("missing_token requires at least 2 tokens")
    drop_idx = rng.randint(0, len(tokens) - 1)
    new_tokens = tokens[:drop_idx] + tokens[drop_idx + 1:]
    return " ".join(new_tokens)


def apply_blank(value: str, rng: random.Random) -> str:
    return ""


def apply_digit_swap(value: str, rng: random.Random) -> str:
    # Find all digit positions
    digit_positions = [i for i, ch in enumerate(value) if ch.isdigit()]
    if not digit_positions:
        raise NoiseNotApplicable("digit_swap requires at least one digit")
    pos = rng.choice(digit_positions)
    old_digit = value[pos]
    # Choose a different digit
    new_digit = rng.choice([d for d in "0123456789" if d != old_digit])
    return value[:pos] + new_digit + value[pos + 1:]


def apply_case_flip(value: str, rng: random.Random) -> str:
    if not value:
        return value
    # Flip case of one or more characters; pick 1-3 positions at random
    n = min(len(value), rng.randint(1, 3))
    positions = rng.sample(range(len(value)), n)
    lst = list(value)
    for pos in positions:
        ch = lst[pos]
        if ch.islower():
            lst[pos] = ch.upper()
        elif ch.isupper():
            lst[pos] = ch.lower()
        # else leave non-letters unchanged
    return "".join(lst)


def apply_whitespace(value: str, rng: random.Random) -> str:
    # Insert leading or trailing space
    if rng.random() < 0.5:
        return " " + value
    else:
        return value + " "


# Dispatch table: ErrorType -> function
NOISE_DISPATCH: dict[ErrorType, Callable[[str, random.Random], str]] = {
    ErrorType.TYPO: apply_typo,
    ErrorType.TRANSPOSITION: apply_transposition,
    ErrorType.ABBREVIATION: apply_abbreviation,
    ErrorType.MISSING_TOKEN: apply_missing_token,
    ErrorType.BLANK: apply_blank,
    ErrorType.DIGIT_SWAP: apply_digit_swap,
    ErrorType.CASE_FLIP: apply_case_flip,
    ErrorType.WHITESPACE: apply_whitespace,
}

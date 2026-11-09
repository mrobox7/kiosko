"""Helper functions for menu text: how dish and option names are written for the model, and compared
when it sends them back."""

import re


def dish_name(raw: str) -> str:
    """A dish name as the customer would say it: no ®, ™ or *, and a long combo name cut before its
    '(' or '+' ('Spicy Paneer Burger(Any 2)+1 Med Fries' becomes 'Spicy Paneer Burger')."""
    plain = re.sub(r"\s+", " ", re.sub(r"[®™*]", "", raw))
    return re.split(r"\s*[(+]", plain)[0].strip()


def option_name(raw: str) -> str:
    """An option name with only the symbols removed. Its parentheses stay: 'Coke Zero (Can)' and
    'Coke Zero' are different drinks."""
    return re.sub(r"\s+", " ", re.sub(r"[®™*]", "", raw)).strip()


def normalise(text: str) -> str:
    """Lower case, words only: 'Coke® Zero Can' and 'coke zero can' compare equal."""
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()

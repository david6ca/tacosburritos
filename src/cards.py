"""Card definitions and deck builder for Taco vs. Burrito.

Counts per David's wiki (verified from physical box):
  knowledge/taco-vs-burrito-rules.md
- 24 ingredients: 8x +1, 8x +2, 8x +3  (we split across named ingredients)
- 8 Tummy Ache: 2x -1, 3x -2, 3x -3
- 2 Hot Sauce Boss
- 2 Health Inspector
- 6 No Bueno
- 4 Crafty Crow
- 4 Trash Panda
- 4 Food Fight
- 2 Order Envy
Total: 56 cards.
"""
from __future__ import annotations

from models import Card

# 24 ingredients spread across thematic names; total points distribution = 8x1 + 8x2 + 8x3
# (name, count, points)
INGREDIENT_SPEC: list[tuple[str, int, int]] = [
    # +3 ingredients (8 cards)
    ("Steak", 2, 3),
    ("Carnitas", 2, 3),
    ("Guacamole", 2, 3),
    ("Cheese", 2, 3),
    # +2 ingredients (8 cards)
    ("Chicken", 2, 2),
    ("Beans", 2, 2),
    ("Rice", 2, 2),
    ("Salsa", 2, 2),
    # +1 ingredients (8 cards)
    ("Lettuce", 2, 1),
    ("Tomato", 2, 1),
    ("Onion", 2, 1),
    ("Corn", 2, 1),
]

# Tummy Aches with variable negative point values per wiki
# (label, count, points)
TUMMY_ACHE_SPEC: list[tuple[str, int, int]] = [
    ("Tummy Ache -1", 2, -1),
    ("Tummy Ache -2", 3, -2),
    ("Tummy Ache -3", 3, -3),
]

# (name, count, kind)
ACTION_SPEC: list[tuple[str, int, str]] = [
    ("Hot Sauce Boss", 2, "HOT_SAUCE_BOSS"),
    ("Health Inspector", 2, "ACTION"),
    ("No Bueno", 6, "ACTION"),
    ("Crafty Crow", 4, "ACTION"),
    ("Trash Panda", 4, "ACTION"),
    ("Food Fight", 4, "ACTION"),
    ("Order Envy", 2, "ACTION"),
]


def _slug(name: str) -> str:
    return name.lower().replace(" ", "_").replace("-", "neg")


def build_deck() -> list[Card]:
    deck: list[Card] = []
    for name, count, pts in INGREDIENT_SPEC:
        for i in range(count):
            deck.append(Card(
                id=f"ing_{_slug(name)}_{i:02d}",
                name=name, kind="INGREDIENT", points=pts,
                text=f"{name} (+{pts}).",
            ))
    for label, count, pts in TUMMY_ACHE_SPEC:
        for i in range(count):
            deck.append(Card(
                id=f"act_{_slug(label)}_{i:02d}",
                name="Tummy Ache", kind="TUMMY_ACHE", points=pts,
                text=f"Tummy Ache ({pts}).",
            ))
    for name, count, kind in ACTION_SPEC:
        for i in range(count):
            cid = f"act_{_slug(name)}_{i:02d}"
            deck.append(Card(id=cid, name=name, kind=kind, points=None, text=name))
    return deck

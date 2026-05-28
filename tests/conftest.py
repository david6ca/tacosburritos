"""Shared fixtures for Taco vs. Burrito test suite."""
from __future__ import annotations

import random
import pytest

pytest.importorskip("engine")

import cards as cards_mod  # noqa: E402
import engine as engine_mod  # noqa: E402
import models as models_mod  # noqa: E402


@pytest.fixture
def seed() -> int:
    return 0xC0FFEE


@pytest.fixture
def rng(seed: int) -> random.Random:
    return random.Random(seed)


@pytest.fixture
def full_deck():
    return cards_mod.build_deck()


def _card_by_name(deck, name: str):
    for c in deck:
        if c.name == name:
            return c
    raise KeyError(f"No card named {name!r}")


@pytest.fixture
def card_by_name(full_deck):
    return lambda name: _card_by_name(full_deck, name)


@pytest.fixture
def make_card(full_deck):
    counter = {"n": 0}

    def _factory(name: str, **overrides):
        proto = _card_by_name(full_deck, name)
        counter["n"] += 1
        data = proto.model_dump()
        data["id"] = f"{data['id']}_t{counter['n']}"
        data.update(overrides)
        return models_mod.Card(**data)

    return _factory


@pytest.fixture
def make_engine():
    def _factory(num_players: int = 2, seed: int = 1234, ai: list[str] | None = None):
        eng = engine_mod.GameEngine()
        players = []
        for i in range(num_players):
            players.append({
                "id": f"p{i}", "name": f"P{i}", "seat": i,
                "isAI": bool(ai and ai[i]),
                "aiDifficulty": (ai[i] if ai else None),
            })
        eng.start_game(players, seed=seed)
        return eng

    return _factory


@pytest.fixture
def make_player():
    Player = models_mod.Player
    Meal = models_mod.Meal

    def _factory(pid="p1", seat=0, name=None, slots=None, hand=None,
                 is_ai=False, ai_difficulty=None, connected=True):
        return Player(
            id=pid, seat=seat, name=name or pid,
            isAI=is_ai, aiDifficulty=ai_difficulty, connected=connected,
            meal=Meal(slots=list(slots or [])),
            handCount=len(hand or []),
            hand=list(hand or []),
        )
    return _factory

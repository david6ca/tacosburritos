"""AI behavior tests for Taco vs. Burrito."""
from __future__ import annotations

import pytest

from ai import EasyAI, HardAI
from models import Move


def test_easy_ai_returns_legal_move(make_engine):
    eng = make_engine(num_players=2, seed=1)
    legal = eng.legal_moves("p0")
    ai = EasyAI(seed=0)
    state = eng.current_state(viewer_id="p0")
    me = next(p for p in state.players if p.id == "p0")
    move = ai.decide(state, me.hand or [], legal)
    assert move in legal


def test_hard_ai_returns_legal_move(make_engine):
    eng = make_engine(num_players=2, seed=1)
    legal = eng.legal_moves("p0")
    ai = HardAI(seed=0)
    state = eng.current_state(viewer_id="p0")
    me = next(p for p in state.players if p.id == "p0")
    move = ai.decide(state, me.hand or [], legal)
    assert move in legal


def test_easy_ai_passes_in_response_window(make_engine, make_card):
    eng = make_engine(num_players=2, seed=1)
    # Force a response window
    pid = "p0"
    oe = make_card("Order Envy")
    eng._hands[pid] = [oe, make_card("Beans")]
    eng.state.players[0].handCount = 2
    eng.state.players[0].hand = list(eng._hands[pid])
    eng._hands["p1"] = [make_card("No Bueno")]
    eng.state.players[1].handCount = 1
    eng.state.players[1].hand = list(eng._hands["p1"])
    eng.state.players[1].meal.slots = [make_card("Carnitas")]
    eng.apply_move(pid, Move(kind="PLAY_ACTION", cardId=oe.id, targetPlayerId="p1"))
    assert eng.state.phase == "RESPONSE_WINDOW"
    legal = eng.legal_moves("p1")
    ai = EasyAI(seed=0)
    state = eng.current_state(viewer_id="p1")
    move = ai.decide(state, list(eng._hands["p1"]), legal)
    assert move.kind == "RESPOND_PASS"


def test_hard_ai_avoids_health_inspector_on_self(make_engine, make_card):
    eng = make_engine(num_players=2, seed=1)
    pid = "p0"
    hi = make_card("Health Inspector")
    ing = make_card("Steak")
    eng.state.players[0].meal.slots = [make_card("Steak"), make_card("Cheese")]
    eng._hands[pid] = [hi, ing]
    eng.state.players[0].handCount = 2
    eng.state.players[0].hand = list(eng._hands[pid])
    legal = eng.legal_moves(pid)
    ai = HardAI(seed=0)
    state = eng.current_state(viewer_id=pid)
    move = ai.decide(state, list(eng._hands[pid]), legal)
    # Should not play Health Inspector when meal has value
    assert not (move.kind == "PLAY_ACTION" and move.cardId == hi.id)


def test_easy_ai_falls_back_to_health_inspector_when_only_option(make_engine, make_card):
    eng = make_engine(num_players=2, seed=1)
    pid = "p0"
    hi = make_card("Health Inspector")
    eng._hands[pid] = [hi]
    eng.state.players[0].handCount = 1
    eng.state.players[0].hand = [hi]
    legal = eng.legal_moves(pid)
    ai = EasyAI(seed=0)
    state = eng.current_state(viewer_id=pid)
    move = ai.decide(state, [hi], legal)
    assert move in legal

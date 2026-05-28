"""Rules engine tests for Taco vs. Burrito faithful clone."""
from __future__ import annotations

import pytest

import cards as cards_mod
import engine as engine_mod
from engine import GameEngine, IllegalMoveError
from models import Card, Meal, Move, Player, ScoreBreakdown


# ---------------------------------------------------------------------------
# Deck composition
# ---------------------------------------------------------------------------
def test_deck_total_is_56():
    deck = cards_mod.build_deck()
    assert len(deck) == 56


def test_deck_has_24_ingredients_8_tummy_and_24_other_actions():
    deck = cards_mod.build_deck()
    ing = [c for c in deck if c.kind == "INGREDIENT"]
    ta = [c for c in deck if c.kind == "TUMMY_ACHE"]
    hsb = [c for c in deck if c.kind == "HOT_SAUCE_BOSS"]
    act = [c for c in deck if c.kind == "ACTION"]
    assert len(ing) == 24
    assert len(ta) == 8
    assert len(hsb) == 2
    assert len(act) == 22  # 2 HI + 6 NB + 4 CC + 4 TP + 4 FF + 2 OE


def test_deck_card_counts_by_name():
    deck = cards_mod.build_deck()
    counts = {}
    for c in deck:
        counts[c.name] = counts.get(c.name, 0) + 1
    assert counts["Tummy Ache"] == 8
    assert counts["Hot Sauce Boss"] == 2
    assert counts["No Bueno"] == 6
    assert counts["Health Inspector"] == 2
    assert counts["Trash Panda"] == 4
    assert counts["Crafty Crow"] == 4
    assert counts["Food Fight"] == 4
    assert counts["Order Envy"] == 2
    # Instant Replay removed
    assert "Instant Replay" not in counts


def test_ingredient_point_distribution_8_each_of_1_2_3():
    deck = cards_mod.build_deck()
    ing = [c for c in deck if c.kind == "INGREDIENT"]
    by_pts = {1: 0, 2: 0, 3: 0}
    for c in ing:
        by_pts[c.points] = by_pts.get(c.points, 0) + 1
    assert by_pts == {1: 8, 2: 8, 3: 8}


def test_tummy_ache_distribution_2x_neg1_3x_neg2_3x_neg3():
    deck = cards_mod.build_deck()
    ta = [c for c in deck if c.kind == "TUMMY_ACHE"]
    by_pts = {}
    for c in ta:
        by_pts[c.points] = by_pts.get(c.points, 0) + 1
    assert by_pts == {-1: 2, -2: 3, -3: 3}


def test_ingredient_points_positive_and_tummy_ache_negative():
    deck = cards_mod.build_deck()
    for c in deck:
        if c.kind == "INGREDIENT":
            assert c.points and c.points > 0
        if c.kind == "TUMMY_ACHE":
            assert c.points is not None and c.points < 0


def test_all_card_ids_unique():
    deck = cards_mod.build_deck()
    assert len({c.id for c in deck}) == len(deck)


# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------
def test_start_game_deals_five_to_each(make_engine):
    eng = make_engine(num_players=3, seed=1)
    # Each player dealt 5; the current player has auto-drawn 1 so has 6
    cur = eng.state.players[eng.state.currentSeat]
    for p in eng.state.players:
        if p.id == cur.id:
            assert p.handCount in (5, 6)
        else:
            assert p.handCount == 5


def test_start_game_phase_is_act(make_engine):
    eng = make_engine(num_players=2, seed=1)
    assert eng.state.phase == "ACT"


def test_start_game_first_seat_is_zero(make_engine):
    eng = make_engine(num_players=2, seed=1)
    assert eng.state.currentSeat == 0


def test_empty_meals_at_start(make_engine):
    eng = make_engine(num_players=2, seed=1)
    for p in eng.state.players:
        assert p.meal.slots == []


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------
def test_score_pure_ingredients(make_engine, make_card):
    eng = make_engine(num_players=2, seed=1)
    p = eng.state.players[0]
    p.meal.slots = [make_card("Steak"), make_card("Beans")]  # 3+2 = 5
    s = eng.score()
    assert s[p.id].total == 5
    assert s[p.id].ingredientPoints == 5
    assert s[p.id].hotSauceMultiplierApplied is False


def test_score_tummy_ache_negative(make_engine, make_card):
    eng = make_engine(num_players=2, seed=1)
    p = eng.state.players[0]
    p.meal.slots = [make_card("Steak"), make_card("Tummy Ache")]
    s = eng.score()
    assert s[p.id].total == 2
    assert s[p.id].tummyAchePenalty == -1


def test_score_hot_sauce_doubles(make_engine, make_card):
    eng = make_engine(num_players=2, seed=1)
    p = eng.state.players[0]
    p.meal.slots = [make_card("Steak"), make_card("Cheese"), make_card("Hot Sauce Boss")]
    s = eng.score()
    assert s[p.id].total == (3 + 3) * 2
    assert s[p.id].hotSauceMultiplierApplied is True


def test_score_can_go_negative(make_engine, make_card):
    eng = make_engine(num_players=2, seed=1)
    p = eng.state.players[0]
    p.meal.slots = [make_card("Tummy Ache"), make_card("Tummy Ache")]
    s = eng.score()
    assert s[p.id].total == -2


def test_score_hot_sauce_doubles_negative(make_engine, make_card):
    eng = make_engine(num_players=2, seed=1)
    p = eng.state.players[0]
    p.meal.slots = [make_card("Tummy Ache"), make_card("Hot Sauce Boss")]
    s = eng.score()
    assert s[p.id].total == -2  # -1 * 2


# ---------------------------------------------------------------------------
# Turn structure
# ---------------------------------------------------------------------------
def test_slot_ingredient_advances_turn(make_engine, make_card):
    eng = make_engine(num_players=2, seed=1)
    pid = "p0"
    ing = make_card("Steak")
    eng._hands[pid] = [ing]
    eng.state.players[0].handCount = 1
    eng.state.players[0].hand = [ing]
    # Drain draw so the empty-hand triggers end-of-game per official rule
    eng._draw = []
    eng.state.drawPileCount = 0
    eng.apply_move(pid, Move(kind="SLOT_INGREDIENT", cardId=ing.id, targetPlayerId=pid))
    assert eng.state.phase == "GAME_OVER"


def test_slot_ingredient_appears_in_meal(make_engine, make_card):
    eng = make_engine(num_players=2, seed=1)
    pid = "p0"
    ing = make_card("Steak")
    other = make_card("Beans")
    eng._hands[pid] = [ing, other]
    eng.state.players[0].handCount = 2
    eng.state.players[0].hand = [ing, other]
    eng.apply_move(pid, Move(kind="SLOT_INGREDIENT", cardId=ing.id, targetPlayerId=pid))
    assert eng.state.players[0].meal.slots[-1].name == "Steak"


def test_slot_tummy_ache_into_self_is_legal_now(make_engine, make_card):
    # New rule: tummy ache can target any meal, including self
    eng = make_engine(num_players=2, seed=1)
    pid = "p0"
    ta = make_card("Tummy Ache")
    other = make_card("Steak")
    eng._hands[pid] = [ta, other]
    eng.state.players[0].handCount = 2
    eng.state.players[0].hand = [ta, other]
    eng.apply_move(pid, Move(kind="SLOT_TUMMY_ACHE", cardId=ta.id, targetPlayerId=pid))
    assert any(c.name == "Tummy Ache" for c in eng.state.players[0].meal.slots)


def test_slot_tummy_ache_into_opponent_meal(make_engine, make_card):
    eng = make_engine(num_players=2, seed=1)
    pid = "p0"
    ta = make_card("Tummy Ache")
    other = make_card("Steak")
    eng._hands[pid] = [ta, other]
    eng.state.players[0].handCount = 2
    eng.state.players[0].hand = [ta, other]
    eng.apply_move(pid, Move(kind="SLOT_TUMMY_ACHE", cardId=ta.id, targetPlayerId="p1"))
    assert any(c.name == "Tummy Ache" for c in eng.state.players[1].meal.slots)


def test_slot_hot_sauce_boss_self(make_engine, make_card):
    eng = make_engine(num_players=2, seed=1)
    pid = "p0"
    hs = make_card("Hot Sauce Boss")
    other = make_card("Steak")
    eng._hands[pid] = [hs, other]
    eng.state.players[0].handCount = 2
    eng.state.players[0].hand = [hs, other]
    eng.apply_move(pid, Move(kind="SLOT_HOT_SAUCE_BOSS", cardId=hs.id, targetPlayerId=pid))
    assert any(c.kind == "HOT_SAUCE_BOSS" for c in eng.state.players[0].meal.slots)


def test_second_hot_sauce_boss_in_meal_now_legal(make_engine, make_card):
    # New rule: HSB stacks, no limit
    eng = make_engine(num_players=2, seed=1)
    pid = "p0"
    eng.state.players[0].meal.slots = [make_card("Hot Sauce Boss")]
    hs2 = make_card("Hot Sauce Boss")
    extra = make_card("Steak")
    eng._hands[pid] = [hs2, extra]
    eng.state.players[0].handCount = 2
    eng.state.players[0].hand = [hs2, extra]
    legal = eng.legal_moves(pid)
    assert any(m.kind == "SLOT_HOT_SAUCE_BOSS" for m in legal)


def test_hot_sauce_boss_stacks_x4(make_engine, make_card):
    eng = make_engine(num_players=2, seed=1)
    p = eng.state.players[0]
    p.meal.slots = [make_card("Steak"), make_card("Cheese"),
                    make_card("Hot Sauce Boss"), make_card("Hot Sauce Boss")]
    s = eng.score()
    assert s[p.id].total == (3 + 3) * 4
    assert s[p.id].hotSauceCount == 2


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------
def test_no_bueno_not_in_act_legal_moves(make_engine, make_card):
    eng = make_engine(num_players=2, seed=1)
    pid = "p0"
    nb = make_card("No Bueno")
    ing = make_card("Steak")
    eng._hands[pid] = [nb, ing]
    eng.state.players[0].handCount = 2
    eng.state.players[0].hand = [nb, ing]
    legal = eng.legal_moves(pid)
    for m in legal:
        if m.kind == "PLAY_ACTION":
            assert m.cardId != nb.id


def test_trash_panda_illegal_with_empty_discard(make_engine, make_card):
    eng = make_engine(num_players=2, seed=1)
    pid = "p0"
    tp = make_card("Trash Panda")
    ing = make_card("Steak")
    eng._hands[pid] = [tp, ing]
    eng.state.players[0].handCount = 2
    eng.state.players[0].hand = [tp, ing]
    eng.state.discardPile = []
    legal = eng.legal_moves(pid)
    assert not any(m.kind == "PLAY_ACTION" and m.cardId == tp.id for m in legal)


def test_trash_panda_pulls_from_discard(make_engine, make_card):
    eng = make_engine(num_players=2, seed=1)
    pid = "p0"
    tp = make_card("Trash Panda")
    ing = make_card("Steak")
    eng._hands[pid] = [tp, ing]
    eng.state.players[0].handCount = 2
    eng.state.players[0].hand = [tp, ing]
    # Put one card in discard, ensure p1 has no No Bueno
    discarded = make_card("Carnitas")
    eng.state.discardPile = [discarded]
    # Make sure p1 has no No Bueno
    eng._hands["p1"] = [make_card("Lettuce")]
    eng.state.players[1].handCount = 1
    eng.state.players[1].hand = list(eng._hands["p1"])
    eng.apply_move(pid, Move(kind="PLAY_ACTION", cardId=tp.id))
    # Should be in PENDING_CHOICE
    assert eng.state.phase == "PENDING_CHOICE"
    eng.apply_move(pid, Move(kind="RESOLVE_CHOICE", pickFromDiscardId=discarded.id))
    # Carnitas should be in p0's hand
    assert any(c.id == discarded.id for c in eng._hands[pid])


def test_health_inspector_from_hand_trashes_own_meal(make_engine, make_card):
    eng = make_engine(num_players=2, seed=1)
    pid = "p0"
    hi = make_card("Health Inspector")
    extra = make_card("Steak")
    eng.state.players[0].meal.slots = [make_card("Steak"), make_card("Cheese")]
    eng._hands[pid] = [hi, extra]
    eng.state.players[0].handCount = 2
    eng.state.players[0].hand = [hi, extra]
    eng.apply_move(pid, Move(kind="PLAY_ACTION", cardId=hi.id))
    assert eng.state.players[0].meal.slots == []


def test_health_inspector_cannot_be_no_bueno_d(make_engine, make_card):
    eng = make_engine(num_players=2, seed=1)
    pid = "p0"
    hi = make_card("Health Inspector")
    eng._hands[pid] = [hi, make_card("Steak")]
    eng.state.players[0].handCount = 2
    eng.state.players[0].hand = list(eng._hands[pid])
    # Give opponent a No Bueno
    eng._hands["p1"] = [make_card("No Bueno")]
    eng.state.players[1].handCount = 1
    eng.state.players[1].hand = list(eng._hands["p1"])
    eng.state.players[0].meal.slots = [make_card("Steak")]
    eng.apply_move(pid, Move(kind="PLAY_ACTION", cardId=hi.id))
    # Should NOT open response window — meal already trashed
    assert eng.state.phase != "RESPONSE_WINDOW"
    assert eng.state.players[0].meal.slots == []


def test_order_envy_swaps_meals_and_hands(make_engine, make_card):
    eng = make_engine(num_players=2, seed=1)
    pid = "p0"
    oe = make_card("Order Envy")
    extra = make_card("Beans")  # keep hand non-empty (avoid unblockable last-card rule)
    eng._hands[pid] = [oe, extra]
    eng.state.players[0].handCount = 2
    eng.state.players[0].hand = list(eng._hands[pid])
    eng.state.players[0].meal.slots = [make_card("Steak")]  # 3
    eng._hands["p1"] = [make_card("Lettuce"), make_card("Tomato")]
    eng.state.players[1].handCount = 2
    eng.state.players[1].hand = list(eng._hands["p1"])
    eng.state.players[1].meal.slots = [make_card("Carnitas"), make_card("Guacamole")]  # 6
    eng.apply_move(pid, Move(kind="PLAY_ACTION", cardId=oe.id, targetPlayerId="p1"))
    # No No Bueno in p1's hand → resolves immediately
    p0_meal_names = sorted(c.name for c in eng.state.players[0].meal.slots)
    assert "Carnitas" in p0_meal_names
    # After swap, p0 now holds what p1 had
    p0_hand_names = sorted(c.name for c in eng._hands["p0"])
    assert "Lettuce" in p0_hand_names


def test_instant_replay_removed_from_deck():
    # Sanity: Instant Replay is no longer in the game.
    import cards as cm
    deck = cm.build_deck()
    assert not any(c.name == "Instant Replay" for c in deck)


# ---------------------------------------------------------------------------
# New rules: ingredient-to-any-meal
# ---------------------------------------------------------------------------
def test_slot_ingredient_into_opponent_meal(make_engine, make_card):
    eng = make_engine(num_players=2, seed=1)
    pid = "p0"
    ing = make_card("Steak")
    extra = make_card("Beans")
    eng._hands[pid] = [ing, extra]
    eng.state.players[0].handCount = 2
    eng.state.players[0].hand = [ing, extra]
    eng.apply_move(pid, Move(kind="SLOT_INGREDIENT", cardId=ing.id, targetPlayerId="p1"))
    assert any(c.name == "Steak" for c in eng.state.players[1].meal.slots)


# ---------------------------------------------------------------------------
# Health Inspector on DRAW ends turn
# ---------------------------------------------------------------------------
def test_health_inspector_on_draw_ends_turn(make_engine, make_card):
    eng = make_engine(num_players=2, seed=1)
    # Reset to a controlled state at start of p0's turn
    pid = "p0"
    eng.state.players[0].meal.slots = [make_card("Steak")]
    eng._hands[pid] = []
    eng.state.players[0].handCount = 0
    eng.state.players[0].hand = []
    # Plant HI as the next draw (top of pile is end of list)
    hi = make_card("Health Inspector")
    eng._draw = [make_card("Beans"), hi]  # hi drawn first by pop()
    eng.state.drawPileCount = 2
    eng.state.currentSeat = 0
    eng.state.phase = "DRAW"
    eng._begin_turn()
    # Meal trashed; turn should have advanced to p1
    assert eng.state.players[0].meal.slots == []
    assert eng.state.currentSeat == 1


# ---------------------------------------------------------------------------
# Crafty Crow steals from MEAL
# ---------------------------------------------------------------------------
def test_crafty_crow_steals_from_meal(make_engine, make_card):
    eng = make_engine(num_players=2, seed=1)
    pid = "p0"
    cc = make_card("Crafty Crow")
    eng._hands[pid] = [cc, make_card("Beans")]
    eng.state.players[0].handCount = 2
    eng.state.players[0].hand = list(eng._hands[pid])
    target_card = make_card("Carnitas")
    eng.state.players[1].meal.slots = [target_card]
    eng._hands["p1"] = [make_card("Lettuce")]
    eng.state.players[1].handCount = 1
    eng.state.players[1].hand = list(eng._hands["p1"])
    eng.apply_move(pid, Move(kind="PLAY_ACTION", cardId=cc.id,
                              targetPlayerId="p1", targetCardId=target_card.id))
    # Carnitas now in p0 meal, gone from p1 meal
    assert any(c.id == target_card.id for c in eng.state.players[0].meal.slots)
    assert not any(c.id == target_card.id for c in eng.state.players[1].meal.slots)


# ---------------------------------------------------------------------------
# Food Fight all-flip with PENDING_CHOICE pick
# ---------------------------------------------------------------------------
def test_food_fight_all_flip_and_winner_picks(make_engine, make_card):
    eng = make_engine(num_players=2, seed=1)
    pid = "p0"
    ff = make_card("Food Fight")
    eng._hands[pid] = [ff]
    eng.state.players[0].handCount = 1
    eng.state.players[0].hand = list(eng._hands[pid])
    eng._hands["p1"] = []
    eng.state.players[1].handCount = 0
    eng.state.players[1].hand = []
    # Plant 2 ingredients of distinct values; pop() takes from end
    big = make_card("Steak")     # 3
    small = make_card("Lettuce")  # 1
    eng._draw = [small, big]     # big popped first → for p0; small → p1
    eng.state.drawPileCount = 2
    # Need p0 not to have empty hand AFTER play, otherwise unblockable+endgame
    # ff is only card → hand empties → unblockable + final-card endgame triggers
    # IF draw is empty. After Food Fight pops both, draw is empty, but we want
    # the pending choice to still run; we hit FOOD_FIGHT_PICK before endgame check.
    eng.apply_move(pid, Move(kind="PLAY_ACTION", cardId=ff.id))
    assert eng.state.phase == "PENDING_CHOICE"
    pc = eng.state.pendingChoice
    assert pc["kind"] == "FOOD_FIGHT_PICK"
    assert pc["playerId"] == pid  # p0 wins (Steak > Lettuce)
    # Pick the Steak
    eng.apply_move(pid, Move(kind="RESOLVE_CHOICE", pickFromDiscardId=big.id))
    # Steak now in p0 hand; lettuce back in draw
    # (game may now be over since hand had been empty + draw fills back with 1)
    assert any(c.id == big.id for c in eng._hands[pid]) or eng.state.phase == "GAME_OVER"


def test_food_fight_no_ingredient_no_winner(make_engine, make_card):
    eng = make_engine(num_players=2, seed=1)
    pid = "p0"
    ff = make_card("Food Fight")
    extra = make_card("Beans")  # keep hand non-empty so no end-game/unblockable
    eng._hands[pid] = [ff, extra]
    eng.state.players[0].handCount = 2
    eng.state.players[0].hand = list(eng._hands[pid])
    eng._hands["p1"] = []
    eng.state.players[1].handCount = 0
    eng.state.players[1].hand = []
    eng._draw = [make_card("No Bueno"), make_card("Tummy Ache")]
    eng.state.drawPileCount = 2
    eng.apply_move(pid, Move(kind="PLAY_ACTION", cardId=ff.id))
    # No ingredient → no pending choice, all shuffled back
    assert eng.state.phase != "PENDING_CHOICE"
    # 2 flipped, both shuffled back, then p1's turn auto-draws one
    assert eng.state.drawPileCount in (1, 2)


# ---------------------------------------------------------------------------
# Discard-to-end-turn
# ---------------------------------------------------------------------------
def test_discard_card_ends_turn(make_engine, make_card):
    eng = make_engine(num_players=2, seed=1)
    pid = "p0"
    ing = make_card("Steak")
    extra = make_card("Beans")
    eng._hands[pid] = [ing, extra]
    eng.state.players[0].handCount = 2
    eng.state.players[0].hand = list(eng._hands[pid])
    eng.apply_move(pid, Move(kind="DISCARD_CARD", cardId=ing.id))
    # Card in discard; turn advanced
    assert any(c.id == ing.id for c in eng.state.discardPile)
    assert eng.state.currentSeat == 1


def test_discard_card_legal_during_act(make_engine, make_card):
    eng = make_engine(num_players=2, seed=1)
    pid = "p0"
    ing = make_card("Steak")
    eng._hands[pid] = [ing]
    eng.state.players[0].handCount = 1
    eng.state.players[0].hand = [ing]
    legal = eng.legal_moves(pid)
    assert any(m.kind == "DISCARD_CARD" and m.cardId == ing.id for m in legal)


# ---------------------------------------------------------------------------
# Final card unblockable
# ---------------------------------------------------------------------------
def test_final_card_unblockable(make_engine, make_card):
    eng = make_engine(num_players=2, seed=1)
    pid = "p0"
    oe = make_card("Order Envy")
    eng._hands[pid] = [oe]  # last card
    eng.state.players[0].handCount = 1
    eng.state.players[0].hand = list(eng._hands[pid])
    eng._hands["p1"] = [make_card("No Bueno"), make_card("Steak")]
    eng.state.players[1].handCount = 2
    eng.state.players[1].hand = list(eng._hands["p1"])
    eng.state.players[1].meal.slots = [make_card("Carnitas")]
    # Drain draw so end-game can trigger
    eng._draw = []
    eng.state.drawPileCount = 0
    eng.apply_move(pid, Move(kind="PLAY_ACTION", cardId=oe.id, targetPlayerId="p1"))
    # No response window — final card unblockable. Game over now.
    assert eng.state.phase == "GAME_OVER"


# ---------------------------------------------------------------------------
# Trash Panda 2x cap
# ---------------------------------------------------------------------------
def test_trash_panda_cap_prevents_third_HI_pick(make_engine, make_card):
    eng = make_engine(num_players=2, seed=1)
    pid = "p0"
    # Manually set tp pick counts to cap
    eng._tp_picks[pid] = {"Health Inspector": 2}
    eng.state.discardPile = [make_card("Health Inspector"), make_card("Steak")]
    # Pending choice already → use legal_resolve
    legal = eng._legal_resolve_choices(pid, {"kind": "TRASH_PANDA"})
    hi_ids = {c.id for c in eng.state.discardPile if c.name == "Health Inspector"}
    assert not any(m.pickFromDiscardId in hi_ids for m in legal)
    # Steak (ingredient) still pickable
    steak_id = next(c.id for c in eng.state.discardPile if c.name == "Steak")
    assert any(m.pickFromDiscardId == steak_id for m in legal)


# ---------------------------------------------------------------------------
# Counter stack / No Bueno
# ---------------------------------------------------------------------------
def test_no_bueno_counters_action(make_engine, make_card):
    eng = make_engine(num_players=2, seed=1)
    pid = "p0"
    oe = make_card("Order Envy")
    eng._hands[pid] = [oe, make_card("Beans")]
    eng.state.players[0].handCount = 2
    eng.state.players[0].hand = list(eng._hands[pid])
    eng._hands["p1"] = [make_card("No Bueno"), make_card("Steak")]
    eng.state.players[1].handCount = 2
    eng.state.players[1].hand = list(eng._hands["p1"])
    eng.state.players[1].meal.slots = [make_card("Carnitas")]
    eng.apply_move(pid, Move(kind="PLAY_ACTION", cardId=oe.id, targetPlayerId="p1"))
    assert eng.state.phase == "RESPONSE_WINDOW"
    # p1 plays No Bueno
    nb = next(c for c in eng._hands["p1"] if c.name == "No Bueno")
    eng.apply_move("p1", Move(kind="RESPOND_NO_BUENO", cardId=nb.id))
    # Meals should NOT have swapped
    assert any(c.name == "Carnitas" for c in eng.state.players[1].meal.slots)


def test_response_pass_resolves_action(make_engine, make_card):
    eng = make_engine(num_players=2, seed=1)
    pid = "p0"
    oe = make_card("Order Envy")
    eng._hands[pid] = [oe, make_card("Beans")]
    eng.state.players[0].handCount = 2
    eng.state.players[0].hand = list(eng._hands[pid])
    eng._hands["p1"] = [make_card("No Bueno"), make_card("Steak")]
    eng.state.players[1].handCount = 2
    eng.state.players[1].hand = list(eng._hands["p1"])
    eng.state.players[1].meal.slots = [make_card("Carnitas")]
    eng.apply_move(pid, Move(kind="PLAY_ACTION", cardId=oe.id, targetPlayerId="p1"))
    assert eng.state.phase == "RESPONSE_WINDOW"
    eng.apply_move("p1", Move(kind="RESPOND_PASS"))
    # Order Envy resolved → p0 has Carnitas now
    assert any(c.name == "Carnitas" for c in eng.state.players[0].meal.slots)


# ---------------------------------------------------------------------------
# End game
# ---------------------------------------------------------------------------
def test_empty_hand_triggers_endgame(make_engine, make_card):
    eng = make_engine(num_players=2, seed=1)
    pid = "p0"
    ing = make_card("Steak")
    eng._hands[pid] = [ing]
    eng.state.players[0].handCount = 1
    eng.state.players[0].hand = [ing]
    eng._draw = []
    eng.state.drawPileCount = 0
    eng.apply_move(pid, Move(kind="SLOT_INGREDIENT", cardId=ing.id, targetPlayerId=pid))
    assert eng.state.phase == "GAME_OVER"
    assert eng.state.winnerId is not None


def test_winner_has_highest_score(make_engine, make_card):
    eng = make_engine(num_players=2, seed=1)
    eng.state.players[0].meal.slots = [make_card("Steak"), make_card("Steak")]  # 6
    eng.state.players[1].meal.slots = [make_card("Lettuce")]  # 1
    pid = "p0"
    ing = make_card("Cheese")
    eng._hands[pid] = [ing]
    eng.state.players[0].handCount = 1
    eng.state.players[0].hand = [ing]
    eng._draw = []
    eng.state.drawPileCount = 0
    eng.apply_move(pid, Move(kind="SLOT_INGREDIENT", cardId=ing.id, targetPlayerId=pid))
    assert eng.state.winnerId == "p0"

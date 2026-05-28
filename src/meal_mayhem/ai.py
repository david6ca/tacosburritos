"""AI players for Taco vs. Burrito."""
from __future__ import annotations

import random
from typing import Optional

from .models import Card, GameState, Move


class EasyAI:
    difficulty = "easy"

    def __init__(self, seed: Optional[int] = None):
        self.rng = random.Random(seed)

    def decide(self, state: GameState, hand: list[Card], legal_moves: list[Move]) -> Move:
        if not legal_moves:
            return Move(kind="PASS_TURN")
        if state.phase == "RESPONSE_WINDOW":
            # Counter only if action targets me and I'd benefit from canceling it
            top = state.stack[-1] if state.stack else None
            if top and top.targetPlayerId == state.players[state.currentSeat].id:
                for m in legal_moves:
                    if m.kind == "RESPOND_NO_BUENO":
                        return m
            for m in legal_moves:
                if m.kind == "RESPOND_PASS":
                    return m
            return legal_moves[0]
        if state.phase == "PENDING_CHOICE":
            # Pick highest-value card available
            best = None; best_pts = -999
            for m in legal_moves:
                # Trash Panda / Food Fight pick: pickFromDiscardId
                cid = m.pickFromDiscardId or m.giveCardId
                if not cid:
                    continue
                # Look in discard pile for this card
                for c in state.discardPile:
                    if c.id == cid:
                        pts = c.points if c.points is not None else 0
                        if pts > best_pts: best_pts = pts; best = m
                        break
                # Food Fight options
                pc = state.pendingChoice or {}
                for opt in (pc.get("options") or []):
                    if opt.get("id") == cid:
                        pts = opt.get("points") or 0
                        if pts > best_pts: best_pts = pts; best = m
                        break
            return best or self.rng.choice(legal_moves)

        me = state.players[state.currentSeat]

        # Score helpers
        def meal_score(player) -> int:
            ing = sum(c.points or 0 for c in player.meal.slots if c.kind == "INGREDIENT")
            ta = sum(c.points or 0 for c in player.meal.slots if c.kind == "TUMMY_ACHE")
            hs = sum(1 for c in player.meal.slots if c.kind == "HOT_SAUCE_BOSS")
            return (ing + ta) * (2 ** hs if hs else 1)
        opponents = [p for p in state.players if p.id != me.id]
        my_score = meal_score(me)
        leader = max(opponents, key=meal_score) if opponents else None
        leader_score = meal_score(leader) if leader else 0
        behind = leader and leader_score > my_score

        hi_ids = {c.id for c in hand if c.name == "Health Inspector"}
        cards_by_id = {c.id: c for c in hand}

        def is_self_helping(m: Move) -> bool:
            if m.kind in ("SLOT_INGREDIENT", "SLOT_HOT_SAUCE_BOSS"):
                tgt = m.targetPlayerId or me.id
                return tgt != me.id
            return False
        def is_self_hurting(m: Move) -> bool:
            if m.kind == "SLOT_TUMMY_ACHE":
                return (m.targetPlayerId or "") == me.id
            return False

        pool = [m for m in legal_moves
                if not is_self_helping(m)
                and not is_self_hurting(m)
                and not (m.kind == "PLAY_ACTION" and m.cardId in hi_ids)]

        # Priority 1: slot ingredients / hot sauce boss into MY meal (always good)
        my_slots = [m for m in pool
                    if m.kind in ("SLOT_INGREDIENT", "SLOT_HOT_SAUCE_BOSS")
                    and (m.targetPlayerId or me.id) == me.id]
        # Priority 2: Tummy Ache on the leader (deduct from winner)
        ta_on_leader = []
        if leader:
            ta_on_leader = [m for m in pool
                            if m.kind == "SLOT_TUMMY_ACHE" and m.targetPlayerId == leader.id]
        # Priority 3: Crafty Crow stealing leader's best card
        crow_steal = []
        if leader and leader.meal.slots:
            best_card = max(leader.meal.slots, key=lambda c: c.points if c.points is not None else 0)
            crow_steal = [m for m in pool
                          if m.kind == "PLAY_ACTION"
                          and cards_by_id.get(m.cardId, Card(id="", name="", kind="ACTION")).name == "Crafty Crow"
                          and m.targetPlayerId == leader.id
                          and m.targetCardId == best_card.id]
        # Priority 4: Order Envy on leader when I'm behind (swap meal+hand)
        envy_leader = []
        if behind and leader:
            envy_leader = [m for m in pool
                           if m.kind == "PLAY_ACTION"
                           and cards_by_id.get(m.cardId, Card(id="", name="", kind="ACTION")).name == "Order Envy"
                           and m.targetPlayerId == leader.id]
        # Priority 5: Trash Panda — grab a good card from discard
        trash_panda = [m for m in pool
                       if m.kind == "PLAY_ACTION"
                       and cards_by_id.get(m.cardId, Card(id="", name="", kind="ACTION")).name == "Trash Panda"
                       and any((c.points or 0) >= 2 for c in state.discardPile)]
        # Priority 6: Food Fight when behind (chance to gain)
        food_fight = []
        if behind:
            food_fight = [m for m in pool
                          if m.kind == "PLAY_ACTION"
                          and cards_by_id.get(m.cardId, Card(id="", name="", kind="ACTION")).name == "Food Fight"]

        # Pick the highest-priority non-empty bucket
        for bucket in (my_slots, ta_on_leader, crow_steal, envy_leader, trash_panda, food_fight):
            if bucket:
                return self.rng.choice(bucket)

        non_discard = [m for m in pool if m.kind != "DISCARD_CARD"] or pool
        return self.rng.choice(non_discard or pool or legal_moves)


class HardAI:
    difficulty = "hard"

    def __init__(self, seed: Optional[int] = None):
        self.rng = random.Random(seed)

    def decide(self, state: GameState, hand: list[Card], legal_moves: list[Move]) -> Move:
        if not legal_moves:
            return Move(kind="PASS_TURN")
        if state.phase == "RESPONSE_WINDOW":
            for m in legal_moves:
                if m.kind == "RESPOND_PASS":
                    return m
            return legal_moves[0]
        if state.phase == "PENDING_CHOICE":
            return legal_moves[0]

        me = next((p for p in state.players if p.handCount == len(hand)), state.players[state.currentSeat])

        def meal_score(player) -> int:
            ing = sum(c.points or 0 for c in player.meal.slots if c.kind == "INGREDIENT")
            ta = sum(c.points or 0 for c in player.meal.slots if c.kind == "TUMMY_ACHE")
            hs = sum(1 for c in player.meal.slots if c.kind == "HOT_SAUCE_BOSS")
            return (ing + ta) * (2 ** hs)

        opp_scores = [(p, meal_score(p)) for p in state.players if p.id != me.id]
        leader = max(opp_scores, key=lambda x: x[1])[0] if opp_scores else None
        my_score = meal_score(me)

        def card_for(move: Move) -> Optional[Card]:
            return next((c for c in hand if c.id == move.cardId), None)

        def score(move: Move) -> float:
            s = 0.0
            c = card_for(move)
            if move.kind == "SLOT_INGREDIENT" and c:
                # Bonus if slotting into our own meal
                bonus = 10 if move.targetPlayerId == me.id else -5
                s += bonus + (c.points or 0) * (1 if move.targetPlayerId == me.id else -1)
            elif move.kind == "SLOT_TUMMY_ACHE" and c:
                if move.targetPlayerId == me.id:
                    s -= 50
                elif leader and move.targetPlayerId == leader.id:
                    s += 8
                else:
                    s += 3
            elif move.kind == "SLOT_HOT_SAUCE_BOSS":
                if move.targetPlayerId == me.id:
                    s += 6 + max(0, my_score)
                else:
                    s -= 10  # don't buff opponents
            elif move.kind == "PLAY_ACTION" and c:
                if c.name == "Health Inspector":
                    s -= 100 if my_score > 0 else -1
                elif c.name == "Order Envy" and leader:
                    if meal_score(leader) >= max(1, int(my_score * 1.5)):
                        s += 12
                    else:
                        s -= 3
                elif c.name == "Trash Panda":
                    s += 4
                elif c.name == "Crafty Crow":
                    s += 5
                elif c.name == "Food Fight":
                    s += 3
            elif move.kind == "DISCARD_CARD":
                s -= 30
            elif move.kind == "PASS_TURN":
                s -= 50
            if my_score > 0 and opp_scores and my_score >= max(o[1] for o in opp_scores) and len(hand) <= 2:
                if move.kind not in ("PASS_TURN", "DISCARD_CARD"):
                    s += 20
            return s + self.rng.uniform(-0.5, 0.5)

        return max(legal_moves, key=score)

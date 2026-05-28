"""Authoritative game engine for Taco vs. Burrito.

Implements the official Taco vs. Burrito rules per the wiki spec
(see knowledge/taco-vs-burrito-rules.md). Notable mechanics:

- Slot Ingredient / Tummy Ache / Hot Sauce Boss may target ANY meal.
- Hot Sauce Boss stacks: score = (ingredients - tummy) * 2^num_HSB.
- Health Inspector ON DRAW: trashes own meal AND immediately ends turn.
- Health Inspector from hand: same trash + uncounterable, then turn ends.
- Crafty Crow: steal one card from another player's MEAL (targetCardId).
- Food Fight: ALL players flip top of draw pile; highest-value Ingredient
  wins, winner picks one of the flipped cards (PENDING_CHOICE
  FOOD_FIGHT_PICK), rest are shuffled back.
- Order Envy: swap hand + meal with target.
- DISCARD_CARD: legal during ACT whenever you have a card; ends turn.
- Trash Panda: can grab Health Inspector or another Trash Panda only TWICE
  per game per card-name.
- Final card unblockable: a move that empties source's hand skips the
  response window and ends the game (Draw Pile must also be empty for
  the game to end normally; the final-card rule still triggers GAME_OVER
  regardless once the hand actually empties).
- End game: Draw Pile empty AND a player has emptied their hand.
"""
from __future__ import annotations

import random
from typing import Any, Optional

from . import cards as cards_mod
from .models import (
    Card,
    GameState,
    Meal,
    Move,
    Player,
    ScoreBreakdown,
    StackEntry,
)


class IllegalMoveError(Exception):
    def __init__(self, reason: str, attempted: Any = None):
        super().__init__(reason)
        self.reason = reason
        self.attempted = attempted


# Action card names
HEALTH_INSPECTOR = "Health Inspector"
NO_BUENO = "No Bueno"
TRASH_PANDA = "Trash Panda"
CRAFTY_CROW = "Crafty Crow"
FOOD_FIGHT = "Food Fight"
ORDER_ENVY = "Order Envy"
HOT_SAUCE_BOSS = "Hot Sauce Boss"
TUMMY_ACHE = "Tummy Ache"

ACTION_NAMES = {
    HEALTH_INSPECTOR, NO_BUENO, TRASH_PANDA, CRAFTY_CROW, FOOD_FIGHT,
    ORDER_ENVY,
}

# Per-game cap (per player) for these names when pulled via Trash Panda.
TRASH_PANDA_CAP = 2
TRASH_PANDA_CAPPED_NAMES = {HEALTH_INSPECTOR, TRASH_PANDA}


class GameEngine:
    def __init__(self) -> None:
        self.state: GameState = GameState()
        self._hands: dict[str, list[Card]] = {}
        self._draw: list[Card] = []
        self._rng: random.Random = random.Random()
        self._pending_responders: list[str] = []
        self._turn_player_id: Optional[str] = None
        # per-player Trash Panda pick counts: pid -> {cardName -> count}
        self._tp_picks: dict[str, dict[str, int]] = {}

    # ------------------------------------------------------------------ setup
    def start_game(self, players: list[dict], seed: int = 0) -> None:
        self._rng = random.Random(seed)
        # Double the deck for 5+ players so there's enough to go around.
        n_players = len(players)
        n_decks = 2 if n_players >= 5 else 1
        deck = []
        for _ in range(n_decks):
            deck.extend(cards_mod.build_deck())
        # Re-ID duplicates so cards remain unique across the combined deck
        if n_decks > 1:
            for i, c in enumerate(deck):
                c.id = f"{c.id}_d{i}"
        self._rng.shuffle(deck)
        plist: list[Player] = []
        for spec in players:
            p = Player(
                id=spec["id"],
                seat=spec["seat"],
                name=spec.get("name", spec["id"]),
                holder=spec.get("holder", "TACO"),
                isAI=bool(spec.get("isAI")),
                aiDifficulty=spec.get("aiDifficulty"),
                connected=spec.get("connected", True),
                meal=Meal(),
                handCount=0,
                hand=[],
            )
            plist.append(p)
            self._hands[p.id] = []
            self._tp_picks[p.id] = {}
        plist.sort(key=lambda x: x.seat)
        # Deal 5; per setup rule, if a player is dealt a Health Inspector,
        # shuffle it back into the deck and redraw.
        for p in plist:
            while len(self._hands[p.id]) < 5 and deck:
                c = deck.pop()
                if c.name == HEALTH_INSPECTOR:
                    deck.insert(0, c)
                    self._rng.shuffle(deck)
                    continue
                self._hands[p.id].append(c)
        for p in plist:
            p.handCount = len(self._hands[p.id])
            p.hand = list(self._hands[p.id])
        self._draw = deck
        self.state = GameState(
            players=plist,
            drawPileCount=len(deck),
            discardPile=[],
            currentSeat=0,
            phase="DRAW",
            turnNumber=1,
            rngSeed=str(seed),
        )
        self._turn_player_id = plist[0].id
        self._begin_turn()

    # ------------------------------------------------------------------ helpers
    def _cur_player(self) -> Player:
        return self.state.players[self.state.currentSeat]

    def _player_by_id(self, pid: str) -> Player:
        for p in self.state.players:
            if p.id == pid:
                return p
        raise IllegalMoveError(f"unknown player {pid}")

    def _sync_hand(self, pid: str) -> None:
        p = self._player_by_id(pid)
        p.hand = list(self._hands[pid])
        p.handCount = len(self._hands[pid])

    def _draw_one(self, pid: str) -> Optional[Card]:
        if not self._draw:
            return None
        c = self._draw.pop()
        self._hands[pid].append(c)
        self.state.drawPileCount = len(self._draw)
        self._sync_hand(pid)
        return c

    def _begin_turn(self) -> None:
        """Start-of-turn: auto-draw 1; handle Health Inspector on draw (which
        trashes the player's meal AND immediately ends their turn)."""
        if self.state.phase == "GAME_OVER":
            return
        cur = self._cur_player()
        self.state.phase = "DRAW"
        card = self._draw_one(cur.id)
        if card is not None and card.name == HEALTH_INSPECTOR:
            # remove from hand, trash meal, discard inspector, end turn
            self._hands[cur.id].remove(card)
            self._trash_meal(cur)
            self.state.discardPile.append(card)
            self._sync_hand(cur.id)
            # Record so clients can announce/overlay the trigger
            self.state.lastResolvedAction = StackEntry(
                cardId=card.id, cardName=HEALTH_INSPECTOR,
                sourcePlayerId=cur.id, targetPlayerId=cur.id,
            )
            self._advance_turn()
            return
        self.state.phase = "ACT"
        # End-game check: empty draw AND empty hand for some player triggers end.
        self._check_end_game()

    def _trash_meal(self, player: Player) -> None:
        for c in player.meal.slots:
            self.state.discardPile.append(c)
        player.meal.slots = []

    def _advance_turn(self) -> None:
        if self.state.phase == "GAME_OVER":
            return
        if self._check_end_game():
            return
        n = len(self.state.players)
        self.state.currentSeat = (self.state.currentSeat + 1) % n
        self.state.turnNumber += 1
        self._turn_player_id = self._cur_player().id
        self._begin_turn()

    def _check_end_game(self) -> bool:
        """End game iff Draw Pile is empty AND some player has empty hand."""
        if self.state.phase == "GAME_OVER":
            return True
        if self._draw:
            return False
        if any(p.handCount == 0 for p in self.state.players):
            self._end_game()
            return True
        return False

    def _end_game(self) -> None:
        self.state.phase = "GAME_OVER"
        self.state.endGameTriggered = True
        scores = self.score()
        self.state.scores = scores
        order = sorted(
            self.state.players,
            key=lambda p: (
                -scores[p.id].total,
                -sum(1 for c in p.meal.slots if c.kind == "INGREDIENT"),
                sum(1 for c in p.meal.slots if c.kind == "TUMMY_ACHE"),
                p.handCount,
            ),
        )
        self.state.winnerId = order[0].id

    # ------------------------------------------------------------------ scoring
    def score(self) -> dict[str, ScoreBreakdown]:
        out: dict[str, ScoreBreakdown] = {}
        for p in self.state.players:
            ing = sum(c.points or 0 for c in p.meal.slots if c.kind == "INGREDIENT")
            ta = sum(c.points or 0 for c in p.meal.slots if c.kind == "TUMMY_ACHE")
            hs_count = sum(1 for c in p.meal.slots if c.kind == "HOT_SAUCE_BOSS")
            total = (ing + ta) * (2 ** hs_count)
            out[p.id] = ScoreBreakdown(
                ingredientPoints=ing,
                tummyAchePenalty=ta,
                hotSauceMultiplierApplied=hs_count > 0,
                hotSauceCount=hs_count,
                total=total,
            )
        return out

    # ------------------------------------------------------------------ state view
    def current_state(self, viewer_id: Optional[str] = None) -> GameState:
        st = self.state.model_copy(deep=True)
        for p in st.players:
            if viewer_id is None or p.id != viewer_id:
                p.hand = None
                p.token = None
            else:
                p.hand = list(self._hands.get(p.id, []))
        return st

    # ------------------------------------------------------------------ legal
    def legal_moves(self, pid: str) -> list[Move]:
        if self.state.phase == "GAME_OVER":
            return []
        if self.state.phase == "RESPONSE_WINDOW":
            if pid not in self._pending_responders:
                return []
            moves: list[Move] = [Move(kind="RESPOND_PASS")]
            top = self.state.stack[-1] if self.state.stack else None
            if top and not top.unblockable and top.cardName != HEALTH_INSPECTOR:
                for c in self._hands.get(pid, []):
                    if c.name == NO_BUENO:
                        moves.append(Move(kind="RESPOND_NO_BUENO", cardId=c.id))
                        break
            return moves
        if self.state.phase == "PENDING_CHOICE":
            pc = self.state.pendingChoice or {}
            if pc.get("playerId") != pid:
                return []
            return self._legal_resolve_choices(pid, pc)
        if self.state.phase != "ACT":
            return []
        cur = self._cur_player()
        if cur.id != pid:
            return []
        moves: list[Move] = []
        hand = self._hands.get(pid, [])
        all_pids = [p.id for p in self.state.players]
        for c in hand:
            if c.kind == "INGREDIENT":
                # Any meal
                for tgt in all_pids:
                    moves.append(Move(kind="SLOT_INGREDIENT", cardId=c.id, targetPlayerId=tgt))
            elif c.kind == "TUMMY_ACHE":
                for tgt in all_pids:
                    moves.append(Move(kind="SLOT_TUMMY_ACHE", cardId=c.id, targetPlayerId=tgt))
            elif c.kind == "HOT_SAUCE_BOSS":
                for tgt in all_pids:
                    moves.append(Move(kind="SLOT_HOT_SAUCE_BOSS", cardId=c.id, targetPlayerId=tgt))
            elif c.kind == "ACTION":
                moves.extend(self._legal_action_moves(pid, c))
        # DISCARD_CARD always available if hand non-empty
        for c in hand:
            moves.append(Move(kind="DISCARD_CARD", cardId=c.id))
        if not hand:
            moves.append(Move(kind="PASS_TURN"))
        return moves

    def _legal_action_moves(self, pid: str, c: Card) -> list[Move]:
        opponents = [p for p in self.state.players if p.id != pid]
        if c.name == HEALTH_INSPECTOR:
            return [Move(kind="PLAY_ACTION", cardId=c.id)]
        if c.name == NO_BUENO:
            return []
        if c.name == TRASH_PANDA:
            if self.state.discardPile:
                return [Move(kind="PLAY_ACTION", cardId=c.id)]
            return []
        if c.name == CRAFTY_CROW:
            mv = []
            for opp in opponents:
                for mc in opp.meal.slots:
                    mv.append(Move(kind="PLAY_ACTION", cardId=c.id,
                                   targetPlayerId=opp.id, targetCardId=mc.id))
            return mv
        if c.name == FOOD_FIGHT:
            return [Move(kind="PLAY_ACTION", cardId=c.id)]
        if c.name == ORDER_ENVY:
            return [Move(kind="PLAY_ACTION", cardId=c.id, targetPlayerId=o.id) for o in opponents]
        return []

    def _legal_resolve_choices(self, pid: str, pc: dict) -> list[Move]:
        kind = pc.get("kind")
        if kind == "TRASH_PANDA":
            picks = self._tp_picks.get(pid, {})
            out = []
            for c in self.state.discardPile:
                if c.name in TRASH_PANDA_CAPPED_NAMES and picks.get(c.name, 0) >= TRASH_PANDA_CAP:
                    continue
                out.append(Move(kind="RESOLVE_CHOICE", pickFromDiscardId=c.id))
            return out
        if kind == "FOOD_FIGHT_PICK":
            opts = pc.get("options") or []
            return [Move(kind="RESOLVE_CHOICE", pickFromDiscardId=o["id"]) for o in opts]
        return []

    # ------------------------------------------------------------------ apply
    def apply_move(self, pid: str, move: Move) -> None:
        if self.state.phase == "GAME_OVER":
            raise IllegalMoveError("game over", move.model_dump())
        if self.state.phase == "RESPONSE_WINDOW":
            return self._apply_response(pid, move)
        if self.state.phase == "PENDING_CHOICE":
            return self._apply_choice(pid, move)
        cur = self._cur_player()
        if cur.id != pid:
            raise IllegalMoveError("not your turn", move.model_dump())
        if move.kind == "PASS_TURN":
            # Only legal when hand is truly empty (no DISCARD_CARD option exists).
            if self._hands.get(pid):
                raise IllegalMoveError("cannot pass with cards in hand", move.model_dump())
            self._advance_turn()
            return
        if move.kind == "DISCARD_CARD":
            c = self._take_from_hand(pid, move.cardId)
            self.state.discardPile.append(c)
            self._sync_hand(pid)
            # End the turn (also ends game if both conditions met)
            p = self._player_by_id(pid)
            if p.handCount == 0 and not self._draw:
                self._end_game()
                return
            self._advance_turn()
            return
        if move.kind == "SLOT_INGREDIENT":
            target = self._player_by_id(move.targetPlayerId) if move.targetPlayerId else cur
            c = self._take_from_hand(pid, move.cardId)
            if c.kind != "INGREDIENT":
                raise IllegalMoveError("not an ingredient", move.model_dump())
            target.meal.slots.append(c)
            self._post_play_advance(pid)
            return
        if move.kind == "SLOT_TUMMY_ACHE":
            target = self._player_by_id(move.targetPlayerId) if move.targetPlayerId else cur
            c = self._take_from_hand(pid, move.cardId)
            if c.kind != "TUMMY_ACHE":
                raise IllegalMoveError("not a tummy ache", move.model_dump())
            target.meal.slots.append(c)
            self._post_play_advance(pid)
            return
        if move.kind == "SLOT_HOT_SAUCE_BOSS":
            target = self._player_by_id(move.targetPlayerId) if move.targetPlayerId else cur
            c = self._take_from_hand(pid, move.cardId)
            if c.kind != "HOT_SAUCE_BOSS":
                raise IllegalMoveError("not hot sauce boss", move.model_dump())
            target.meal.slots.append(c)
            self._post_play_advance(pid)
            return
        if move.kind == "PLAY_ACTION":
            return self._begin_action(pid, move)
        raise IllegalMoveError(f"illegal move kind {move.kind}", move.model_dump())

    def _take_from_hand(self, pid: str, card_id: Optional[str]) -> Card:
        if not card_id:
            raise IllegalMoveError("no cardId", None)
        h = self._hands.get(pid, [])
        for i, c in enumerate(h):
            if c.id == card_id:
                return h.pop(i)
        raise IllegalMoveError(f"card {card_id} not in hand", None)

    def _peek_in_hand(self, pid: str, card_id: str) -> Card:
        for c in self._hands.get(pid, []):
            if c.id == card_id:
                return c
        raise IllegalMoveError(f"card {card_id} not in hand", None)

    def _post_play_advance(self, pid: str) -> None:
        self._sync_hand(pid)
        p = self._player_by_id(pid)
        if p.handCount == 0 and not self._draw:
            self._end_game()
            return
        self._advance_turn()

    # ------------------------------------------------------------------ actions
    def _begin_action(self, pid: str, move: Move) -> None:
        c = self._peek_in_hand(pid, move.cardId or "")
        if c.kind != "ACTION":
            raise IllegalMoveError("not an action card", move.model_dump())
        if c.name == NO_BUENO:
            raise IllegalMoveError("No Bueno only as response", move.model_dump())
        legal = self._legal_action_moves(pid, c)
        if not any(m.cardId == move.cardId
                   and m.targetPlayerId == move.targetPlayerId
                   and m.targetCardId == move.targetCardId
                   for m in legal):
            raise IllegalMoveError("illegal action target", move.model_dump())
        self._take_from_hand(pid, c.id)
        self._sync_hand(pid)
        src = self._player_by_id(pid)
        # Final card unblockable rule: if hand is now empty, this play
        # cannot be countered.
        unblockable = (src.handCount == 0)
        entry = StackEntry(
            cardId=c.id, cardName=c.name, sourcePlayerId=pid,
            targetPlayerId=move.targetPlayerId, targetCardId=move.targetCardId,
            giveCardId=move.giveCardId, unblockable=unblockable,
        )
        self.state.stack.append(entry)
        # Health Inspector and unblockable last-card plays resolve immediately
        if c.name == HEALTH_INSPECTOR or unblockable:
            self._resolve_top()
            return
        self._open_response_window(exclude=pid)

    def _open_response_window(self, exclude: str) -> None:
        responders = [p.id for p in self.state.players if p.id != exclude]
        self._pending_responders = [
            pid for pid in responders
            if any(c.name == NO_BUENO for c in self._hands.get(pid, []))
        ]
        if not self._pending_responders:
            self._resolve_top()
            return
        self.state.phase = "RESPONSE_WINDOW"

    def _apply_response(self, pid: str, move: Move) -> None:
        if pid not in self._pending_responders:
            raise IllegalMoveError("not in response window", move.model_dump())
        if move.kind == "RESPOND_PASS":
            self._pending_responders.remove(pid)
        elif move.kind == "RESPOND_NO_BUENO":
            top = self.state.stack[-1]
            if top.cardName == HEALTH_INSPECTOR or top.unblockable:
                raise IllegalMoveError("cannot counter this", move.model_dump())
            nb = next((c for c in self._hands[pid] if c.name == NO_BUENO
                       and (move.cardId is None or c.id == move.cardId)), None)
            if not nb:
                raise IllegalMoveError("no No Bueno in hand", move.model_dump())
            self._hands[pid].remove(nb)
            self._sync_hand(pid)
            countered_card = self._find_card_anywhere(top.cardId, fallback_name=top.cardName)
            top.countered = True
            self.state.stack.pop()
            self.state.discardPile.append(countered_card)
            nb_entry = StackEntry(cardId=nb.id, cardName=NO_BUENO, sourcePlayerId=pid)
            self.state.stack.append(nb_entry)
            self._open_response_window(exclude=pid)
            return
        if not self._pending_responders:
            self._resolve_top()

    def _find_card_anywhere(self, cid: str, fallback_name: str = "") -> Card:
        for h in self._hands.values():
            for c in h:
                if c.id == cid:
                    return c
        for p in self.state.players:
            for c in p.meal.slots:
                if c.id == cid:
                    return c
        for c in self.state.discardPile:
            if c.id == cid:
                return c
        return Card(id=cid, name=fallback_name or cid, kind="ACTION", text="")

    def _resolve_top(self) -> None:
        if not self.state.stack:
            self.state.phase = "ACT"
            return
        entry = self.state.stack.pop()
        if entry.cardName == NO_BUENO:
            self.state.discardPile.append(Card(id=entry.cardId, name=NO_BUENO, kind="ACTION"))
            self._after_resolution()
            return
        src = self._player_by_id(entry.sourcePlayerId)
        name = entry.cardName
        card_obj = Card(id=entry.cardId, name=name, kind="ACTION")
        if name == HEALTH_INSPECTOR:
            self._trash_meal(src)
            self.state.discardPile.append(card_obj)
            self.state.lastResolvedAction = entry
            self._after_resolution()
            return
        if name == ORDER_ENVY:
            target = self._player_by_id(entry.targetPlayerId or "")
            src.meal, target.meal = target.meal, src.meal
            self._hands[src.id], self._hands[target.id] = self._hands[target.id], self._hands[src.id]
            self._sync_hand(src.id)
            self._sync_hand(target.id)
            self.state.discardPile.append(card_obj)
            self.state.lastResolvedAction = entry
            self._after_resolution()
            return
        if name == TRASH_PANDA:
            self.state.discardPile.append(card_obj)
            # If discard empty (other than this card?), still allow choice; legal_choices filters caps.
            self.state.pendingChoice = {
                "kind": "TRASH_PANDA",
                "cardName": TRASH_PANDA,
                "playerId": src.id,
                "stackEntry": entry.model_dump(),
            }
            self.state.phase = "PENDING_CHOICE"
            return
        if name == CRAFTY_CROW:
            target = self._player_by_id(entry.targetPlayerId or "")
            # Steal targetCardId from target's meal into src's meal.
            stolen = None
            if entry.targetCardId:
                for i, mc in enumerate(target.meal.slots):
                    if mc.id == entry.targetCardId:
                        stolen = target.meal.slots.pop(i)
                        break
            if stolen is not None:
                src.meal.slots.append(stolen)
            self.state.discardPile.append(card_obj)
            self.state.lastResolvedAction = entry
            self._after_resolution()
            return
        if name == FOOD_FIGHT:
            self.state.discardPile.append(card_obj)
            self._resolve_food_fight(entry)
            return
        # default: discard the card
        self.state.discardPile.append(card_obj)
        self.state.lastResolvedAction = entry
        self._after_resolution()

    def _resolve_food_fight(self, entry: StackEntry) -> None:
        """Every player flips top of draw. Highest-value ingredient wins;
        winner picks one of the flipped cards via PENDING_CHOICE.
        Remaining flipped cards go back into the draw pile (shuffled)."""
        flipped: list[tuple[str, Card]] = []  # (pid, card)
        for p in self.state.players:
            if not self._draw:
                break
            c = self._draw.pop()
            flipped.append((p.id, c))
        self.state.drawPileCount = len(self._draw)
        # Determine winner: highest-value ingredient
        ingredients = [(pid, c) for (pid, c) in flipped if c.kind == "INGREDIENT"]
        if not ingredients:
            # nobody wins; shuffle all back
            for _, c in flipped:
                self._draw.append(c)
            self._rng.shuffle(self._draw)
            self.state.drawPileCount = len(self._draw)
            self.state.lastResolvedAction = entry
            self._after_resolution()
            return
        ingredients.sort(key=lambda x: (x[1].points or 0), reverse=True)
        winner_pid = ingredients[0][0]
        # Stash flipped list; offer winner a choice
        self.state.pendingChoice = {
            "kind": "FOOD_FIGHT_PICK",
            "cardName": FOOD_FIGHT,
            "playerId": winner_pid,
            "options": [c.model_dump() for _, c in flipped],
            "stackEntry": entry.model_dump(),
        }
        self.state.phase = "PENDING_CHOICE"

    def _apply_choice(self, pid: str, move: Move) -> None:
        pc = self.state.pendingChoice or {}
        if pc.get("playerId") != pid:
            raise IllegalMoveError("not your choice", move.model_dump())
        if move.kind != "RESOLVE_CHOICE":
            raise IllegalMoveError("expected RESOLVE_CHOICE", move.model_dump())
        kind = pc.get("kind")
        entry_dict = pc.get("stackEntry") or {}
        entry = StackEntry(**entry_dict) if entry_dict else None
        if kind == "TRASH_PANDA":
            cid = move.pickFromDiscardId
            # Skip pick: just resolve with no card taken
            if cid is None or cid == "" or cid == "__skip__":
                self.state.pendingChoice = None
                if entry:
                    self.state.lastResolvedAction = entry
                self._after_resolution()
                return
            picked = next((c for c in self.state.discardPile if c.id == cid), None)
            if not picked:
                raise IllegalMoveError("invalid discard pick", move.model_dump())
            # Enforce 2x cap for Health Inspector / Trash Panda
            if picked.name in TRASH_PANDA_CAPPED_NAMES:
                cnt = self._tp_picks.setdefault(pid, {}).get(picked.name, 0)
                if cnt >= TRASH_PANDA_CAP:
                    raise IllegalMoveError(f"Trash Panda cap reached for {picked.name}", move.model_dump())
                self._tp_picks[pid][picked.name] = cnt + 1
            self.state.discardPile.remove(picked)
            # SPECIAL: picking Health Inspector from trash triggers it on self → trash own meal, end turn
            if picked.name == HEALTH_INSPECTOR:
                src = self._player_by_id(pid)
                self._trash_meal(src)
                self.state.discardPile.append(picked)
                self.state.pendingChoice = None
                self.state.lastResolvedAction = StackEntry(
                    cardId=picked.id, cardName=HEALTH_INSPECTOR,
                    sourcePlayerId=pid, targetPlayerId=pid,
                )
                # End turn immediately
                if self.state.stack:
                    self.state.stack.pop()
                self._advance_turn()
                return
            self._hands[pid].append(picked)
            self._sync_hand(pid)
            self.state.pendingChoice = None
            if entry:
                self.state.lastResolvedAction = entry
            self._after_resolution()
            return
        if kind == "FOOD_FIGHT_PICK":
            opts = pc.get("options") or []
            cid = move.pickFromDiscardId
            picked = None
            picked_index = None
            for i, o in enumerate(opts):
                if o.get("id") == cid:
                    picked = Card(**o)
                    picked_index = i
                    break
            if picked is None:
                raise IllegalMoveError("invalid food-fight pick", move.model_dump())
            # Winner gets the picked card
            self._hands[pid].append(picked)
            self._sync_hand(pid)
            # Remaining go back into draw, shuffled
            for i, o in enumerate(opts):
                if i == picked_index:
                    continue
                self._draw.append(Card(**o))
            self._rng.shuffle(self._draw)
            self.state.drawPileCount = len(self._draw)
            self.state.pendingChoice = None
            if entry:
                self.state.lastResolvedAction = entry
            self._after_resolution()
            return
        raise IllegalMoveError("unknown choice", move.model_dump())

    def _after_resolution(self) -> None:
        src_id = self._turn_player_id
        if src_id:
            p = self._player_by_id(src_id)
            if p.handCount == 0 and not self._draw:
                self._end_game()
                return
        if self.state.stack:
            self.state.phase = "ACT"
            return
        self._advance_turn()

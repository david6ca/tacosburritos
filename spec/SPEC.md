# Taco vs. Burrito — Game Specification (Faithful Clone)

> **v2 NOTE (this revision):** Engine rewritten to match official rules per
> `~/Library/.../knowledge/taco-vs-burrito-rules.md`. Key changes:
> Instant Replay removed (deck now 54 cards, `[HOUSE RULE — pending David's
> verification]`); Slot Ingredient / Tummy Ache / Hot Sauce Boss may target
> ANY meal; Hot Sauce Boss stacks (×2^n); Health Inspector on draw ends
> turn; Crafty Crow steals from MEAL via `targetCardId`; Food Fight is
> all-flip with `FOOD_FIGHT_PICK` PENDING_CHOICE; Order Envy swaps hand+
> meal; `DISCARD_CARD` legal during ACT (end-turn affordance); end game
> requires draw pile empty AND a player's hand empty; final card is
> unblockable; Trash Panda limited to 2× per game per HI/TP name.

**Working title:** Taco vs. Burrito (digital adaptation of the real card game by Alex Butler / HotPatato Games, 2019).
**Package name (legacy, retained):** `meal_mayhem`.
**Status:** Draft v0.2 — faithful rewrite replacing the prior "Meal Mayhem" clean-room spec.
**Target stack:** Python 3.11+ (FastAPI + `websockets`) authoritative server, vanilla JS/HTML/CSS browser client.
**Deployment target:** example.com.

> **Sources consulted.**
> - Official site: https://www.tacovsburrito.com/pages/how-to-play (rules video + downloadable instructions)
> - UltraBoardGames rules digest: https://www.ultraboardgames.com/taco-vs-burrito/game-rules.php
> - Amazon product listing (component counts)
> - Multiple YouTube tutorials searched for "How to Play Taco vs Burrito"
> - BoardGameGeek listing (rule clarifications)
>
> **Legal note.** All card-text descriptions in this spec are short *functional paraphrases* in our own words. No copyrighted rulebook prose is reproduced. Where the published rules are silent or ambiguous, the spec marks `[HOUSE RULE]` and picks a reasonable digital default.

---

## 1. Game Overview

| Item | Value |
|---|---|
| Players | 2–4 (humans + AI fill) |
| Recommended age | 7+ |
| Average length | 10–15 minutes |
| Goal | Hold the highest-value Taco/Burrito (your "Meal") when the game ends |
| Turn order | Clockwise |
| Win condition | After end-game trigger, highest Meal point total wins |

**Core loop.** Each player has a private hand and a public Meal (the cards slotted into their Taco or Burrito card-holder). On your turn you **draw exactly 1 card**, then take **exactly 1 action** — either add an ingredient/modifier to a Meal, or play one Action card. The game ends instantly the moment any player empties their hand (or the draw pile runs out). Whoever has the highest Meal value wins.

---

## 2. Components & Card List

### 2.1 Physical Components (real game)

| Component | Count |
|---|---:|
| Ingredient cards | 24 |
| Action cards | 32 |
| Tortilla / Card-holder props (Taco or Burrito) | 4 |
| Quick-start reference cards | 4 |
| Rulebook | 1 |

**Playable deck = 56 cards** (24 ingredients + 32 actions). Tortilla holders are seat props, not drawable cards. Quick-start cards are reference aids, not gameplay cards.

### 2.2 Ingredient Cards (24)

Ingredients are the *only* cards that score positive points. They are slotted face-up into the player's Taco or Burrito card-holder (their "Meal"). Each ingredient has a printed point value. The published deck contains a mix of typical taco/burrito ingredients (proteins, rice, beans, salsa, cheese, lettuce, guacamole, sour cream, etc.).

`[HOUSE RULE — counts per name]` The published rulebook lists 24 ingredient cards but does not enumerate per-name counts in any source we could verify. The digital version uses the following distribution chosen to total 24 with a believable point spread (1–3 points each, average ~2):

| Name | Count | Points |
|---|---:|---:|
| Steak | 2 | 3 |
| Carnitas | 2 | 3 |
| Chicken | 2 | 2 |
| Beans | 2 | 2 |
| Rice | 2 | 2 |
| Cheese | 2 | 2 |
| Lettuce | 2 | 1 |
| Tomato | 2 | 1 |
| Onion | 1 | 1 |
| Corn | 1 | 1 |
| Salsa | 2 | 2 |
| Guacamole | 2 | 3 |
| Sour Cream | 2 | 2 |

Total: **24 cards**. All ingredient cards function identically — slot into Meal, score face value at game end. No type/class system in the real game.

### 2.3 Action Cards (32)

The published rulebook describes the following action cards. Counts within the 32-card action subset are not officially enumerated in any public source; the digital version uses the distribution below, chosen to match the relative frequency described in tutorials.

| Name | Count | Functional description (paraphrase) |
|---|---:|---|
| **Tummy Ache** | 6 | Slot into a target opponent's Meal. Acts as a **−1 ingredient** (negative value card occupying a Meal slot). Stays until removed by being trashed or replaced via other effects. |
| **Hot Sauce Boss** | 3 | Slot into your own Meal. **Doubles the total point value** of that Meal at scoring. One per Meal max. `[HOUSE RULE — stacking]` Additional copies are discarded. |
| **Trash Panda** | 4 | Look through the discard pile and take **one card** of your choice into your hand. |
| **Crafty Crow** | 3 | Choose another player; you each pick one card from your hand and trade them simultaneously. |
| **Food Fight** | 4 | Choose an opponent. Both reveal hands; trade one card each (you pick what you give; they pick what they give). `[HOUSE RULE — disambiguation vs. Crafty Crow]` Food Fight reveals hands; Crafty Crow is blind. |
| **Health Inspector** | 2 | When drawn from the deck OR played from hand, all ingredients currently in **your** Meal are sent to the discard pile. (Triggers on draw — see §7.) |
| **Order Envy** | 2 | Choose any other player. You **swap entire Meals AND entire hands** with that player. |
| **No Bueno** | 6 | Counter card. Cancels any Action card as it is being played, **except Health Inspector**. A No Bueno can itself be countered by another No Bueno. May be played out of turn. |
| **Instant Replay** | 2 | Repeat the effect of the most recently resolved Action card (you choose new targets). Cannot replay a Health Inspector that triggered on draw. |

Action subtotal: **32 cards**. Deck total: **24 + 32 = 56**.

---

## 3. Setup

1. Each player chooses a Taco or Burrito card-holder (purely cosmetic — they function identically). In the digital version this is a seat-selection cosmetic.
2. Shuffle the 56-card deck.
3. Deal **5 cards face-down** to each player as their starting hand.
4. Place the remaining cards face-down in the middle as the **Draw Pile**.
5. Create an empty **Discard Pile** beside it, face-up.
6. First player: youngest player (offline). Online: server picks random seat.

There is **no pre-dealt face-up Meal**. Every Meal starts empty.

---

## 4. Turn Structure

A turn is exactly two steps:

```
START_TURN
  └─ 1. DRAW       — draw exactly 1 card from the Draw Pile
                     (if Health Inspector is drawn, it triggers immediately — §7)
  └─ 2. ACT        — perform exactly ONE of:
                       (a) slot one Ingredient card into your own Meal
                       (b) slot one Tummy Ache into any opponent's Meal
                       (c) slot one Hot Sauce Boss into your own Meal
                       (d) play one Action card
                     If the player has no legal play, they pass.
  └─ END_TURN      — pass to next seat
```

**Limits.**
- Draw count per turn: **exactly 1**.
- Plays per turn: **exactly 1** (or pass if nothing is legal).
- **No discard step.** Hands are not capped. Cards accumulate naturally and the game ends when someone runs out (or the draw pile is exhausted).

**Out-of-turn plays.** Only `No Bueno` may be played out of turn, in direct response to an Action card resolving (see §5).

---

## 5. Action Card Resolution

### 5.1 Targeting

- Cards that target a player require a single chosen target at play time.
- A target is illegal if the action would have no effect (e.g. `Trash Panda` with empty discard pile, `Order Envy` with no other players). Illegal plays are rejected before the card leaves the hand.

### 5.2 The Counter Stack

- An Action card, when played, is pushed onto the resolution stack.
- Server opens a **response window** (default 5 seconds; configurable per room) during which any player holding `No Bueno` may play it.
- `No Bueno` is itself an Action card pushed on top; it opens another response window in which yet another `No Bueno` may counter it.
- When the window closes with no further responses, the top card resolves and is sent to discard.
- **Exception: Health Inspector cannot be countered by No Bueno.** It resolves immediately, including when drawn from the deck.

### 5.3 Slot Plays vs. Action Plays

- Slot plays (Ingredient, Tummy Ache, Hot Sauce Boss) **cannot be countered** — they are not Action cards. They resolve atomically with no response window.
- Only the 9 Action cards in §2.3 use the counter stack.

### 5.4 Instant Replay

- When played, `Instant Replay` references the most recent **fully resolved** action in the game log (not counters that fizzled, not slot plays).
- The replaying player picks fresh targets within the legal set. Replayed action also opens a normal response window (and can be `No Bueno`'d).
- If there is no prior resolved Action card, `Instant Replay` is an illegal play.

---

## 6. End Game and Scoring

### 6.1 End-Game Trigger

The game ends **immediately** when either:
1. Any player has zero cards in hand at the end of any play (this is the canonical official trigger — "once any player is out of cards, the game is instantly over").
2. The Draw Pile is exhausted AND no player can legally play. `[HOUSE RULE]` In digital play we additionally end the game when the Draw Pile is empty and every active player has passed once in a row.

There is no "finish the round" rule — the game stops the instant the trigger fires.

### 6.2 Scoring

For each player's Meal:

```
raw_total = sum(ingredient.points) + sum(tummy_ache.points)   # tummy aches = -1 each
final     = raw_total * 2  if Hot Sauce Boss is in the Meal else raw_total
```

A Meal containing only `Tummy Ache` cards (or nothing) scores `0` minimum is allowed to go negative `[HOUSE RULE]` — a deeply sabotaged Meal can finish with a negative score.

### 6.3 Tiebreakers (in order)

1. Most ingredient cards (excluding Tummy Aches) in Meal.
2. Fewest Tummy Aches in Meal.
3. Fewest cards still in hand at game end.
4. Server RNG coin flip (seed logged).

---

## 7. Edge Cases

| Case | Rule |
|---|---|
| `Health Inspector` drawn from deck | Trigger immediately at draw time: all ingredients in drawing player's Meal go to discard. `Hot Sauce Boss` and `Tummy Ache` cards in the Meal are **also** trashed `[HOUSE RULE — Inspector clears the entire Meal]`. The Health Inspector card itself goes to discard. The player then proceeds to their ACT step normally. `No Bueno` cannot prevent this. |
| `Health Inspector` played from hand | Same effect as on-draw, targeted at the **playing player** (the rules treat this as self-inflicted bad luck). Cannot be countered. `[HOUSE RULE]` We surface a "Why would you?" UI confirmation. |
| Draw pile empty mid-turn | Player skips their DRAW step and proceeds to ACT. If they cannot play, they pass. End-game trigger §6.1.2 may fire. |
| `Trash Panda` with empty discard | Illegal play; rejected. |
| `Crafty Crow` / `Food Fight` with empty opponent hand | Illegal play; rejected. |
| `Order Envy` with one player only | Illegal (no valid target). |
| `Tummy Ache` slotted but Meal is empty | Legal — Tummy Ache becomes the first "card" in the Meal. |
| `Hot Sauce Boss` already in own Meal | Second copy is illegal to slot; must play another way. |
| `No Bueno` against `Health Inspector` | Illegal — Health Inspector is uncounterable. |
| Two `No Bueno` in same window | Resolved LIFO: second counters first, original action resolves. |
| `Instant Replay` with no prior action | Illegal. |
| Player disconnects mid-resolution | Server holds for `RECONNECT_GRACE` (30s); on timeout AI takes over (§8.5). |
| Card text and code disagree | **Code is authoritative.** |

---

## 8. Online Multiplayer Architecture

### 8.1 Topology

- **Authoritative FastAPI + `websockets` server.** Server holds the only true `GameState`; clients render and submit moves.
- **Thin web client:** single `index.html` + `app.js` + `app.css`. No framework dependency. JSON over a single WebSocket per client.
- **One room = one game.** Rooms in-memory; no persistent DB.

### 8.2 State Sync

Two channels over the same socket:
1. **Snapshot** (`STATE_UPDATE` with `full: true`) on join/reconnect/inconsistency — full `GameState` with opponent hands redacted.
2. **Delta events** (`EVENT`) with monotonic `seq`; client requests a snapshot if it detects a gap.

### 8.3 Lobby Flow

```
[Landing]
  ├─ Create Room  → POST /rooms → {roomCode, hostToken} → /r/CODE, open WS
  └─ Join Room    → enter 4-letter code → /r/CODE, open WS

[Pre-game] host sees player list, "Add AI" (easy/hard), "Start"; players "Ready" toggle.
  Start enabled when 2 ≤ (humans + AI) ≤ 4 AND all humans ready.
  Each seat picks Taco or Burrito card-holder cosmetic (default: alternate).

[Game] turn loop.

[Game Over] final scoreboard; host may Play Again or Close Room.
```

Room codes: 4 uppercase A–Z letters, excluding `I O`. Collisions rerolled.

### 8.4 AI Fill

- Host fills empty seats with `easy` or `hard` bots.
- Bots act with 300–1500ms artificial delay.

### 8.5 Disconnect / Reconnect

| Event | Behavior |
|---|---|
| Client WS closes | Mark `disconnected`, start 30s `RECONNECT_GRACE`. |
| Reconnect within grace | Client re-opens WS with `playerToken`; server resumes, sends snapshot. |
| Grace expires | Seat converted to `hard` AI. |
| Host disconnects | Host role transfers to next connected seat. |
| All players disconnect | Room destroyed after 5 minutes idle. |

---

## 9. AI Player Specification

### 9.1 Interface

```ts
interface AIPlayer {
  difficulty: "easy" | "hard";
  decide(state: PublicGameState, hand: Card[], legalMoves: Move[]): Move;
}
```

- Decision must complete in < 500ms wall time.
- Server precomputes `legalMoves`; AI must return one element.
- AI is also asked separately for `No Bueno` decisions during response windows.

### 9.2 Easy AI

- Uniform random pick from `legalMoves`.
- Never plays `No Bueno` (always passes the response window).
- If holding `Health Inspector`, prefers to discard it via any other play first; if forced, plays it on self only as last resort.

### 9.3 Hard AI Heuristic

Score each candidate, pick argmax:

```
score(move) =
   + 10 * Δ(self_meal_projected_score_at_end)
   -  8 * Δ(leader_meal_projected_score_at_end)            # leader = highest current Meal value among opponents
   +  6 * (targets leader ? 1 : 0)                         # Tummy Ache, Order Envy, etc.
   +  5 * (slots Hot Sauce Boss when own Meal score ≥ 6)
   +  4 * (uses Trash Panda to retrieve a >2-point ingredient or a No Bueno)
   -  5 * (uses No Bueno on a low-impact action)
   +  3 * (Order Envy when opponent Meal score is ≥ 1.5× own AND own hand has ≥ 1 No Bueno to protect new Meal)
   -  10 * (would play Health Inspector on self when own Meal score > 0)
   + random_jitter(±0.5)
```

**Special policies:**
- Hold `No Bueno` for high-impact actions: `Order Envy`, `Tummy Ache` on big Meal, `Instant Replay` of same.
- Try to **end the game** (empty hand) when own Meal is the current leader. Specifically: if Meal score is highest at table and `hand.size ≤ 2`, weight any legal play that reduces hand size by +20.
- Avoid drawing if optional — N/A (draw is mandatory in real rules), but Hard AI factors deck composition into expected value (probability of `Health Inspector` next draw).

---

## 10. Data Model

```ts
type CardKind = "INGREDIENT" | "TUMMY_ACHE" | "HOT_SAUCE_BOSS" | "ACTION";

interface Card {
  id: string;          // e.g. "ing_steak_03", "act_no_bueno_01"
  name: string;        // "Steak", "No Bueno", "Tummy Ache", ...
  kind: CardKind;
  points?: number;     // INGREDIENT (+), TUMMY_ACHE (-1); undefined otherwise
  text: string;        // display rules text (our paraphrase)
}

interface Meal {
  // All slotted cards in play order. Includes ingredients, Tummy Aches, and at most one Hot Sauce Boss.
  slots: Card[];
}

interface Player {
  id: string;
  token?: string;            // sent only to that player
  seat: number;              // 0..3
  name: string;
  holder: "TACO" | "BURRITO";  // cosmetic only
  isAI: boolean;
  aiDifficulty?: "easy" | "hard";
  connected: boolean;
  meal: Meal;
  handCount: number;
  hand?: Card[];             // own snapshot only
}

type Phase =
  | "DRAW"
  | "ACT"
  | "RESPONSE_WINDOW"
  | "PENDING_CHOICE"          // e.g. Trash Panda: server awaits cardId pick
  | "GAME_OVER";

interface GameState {
  roomCode: string;
  seq: number;
  players: Player[];
  drawPileCount: number;
  discardPile: Card[];        // fully visible; top = last element
  currentSeat: number;
  phase: Phase;
  turnNumber: number;
  stack: StackEntry[];
  responseWindowDeadline?: number;
  lastResolvedAction?: StackEntry;  // for Instant Replay
  endGameTriggered: boolean;
  rngSeed: string;
  winnerId?: string;
  scores?: Record<string, ScoreBreakdown>;
}

interface StackEntry {
  cardId: string;
  cardName: string;
  sourcePlayerId: string;
  targetPlayerId?: string;
  // Sub-fields for trades:
  giveCardId?: string;        // Crafty Crow / Food Fight (source's give)
  takeCardId?: string;        // target's give, filled when target responds
  trashPandaPickId?: string;  // discard-pile card chosen
  countered: boolean;
}

interface ScoreBreakdown {
  ingredientPoints: number;
  tummyAchePenalty: number;
  hotSauceMultiplierApplied: boolean;
  total: number;
}

interface Move {
  kind:
    | "SLOT_INGREDIENT"
    | "SLOT_TUMMY_ACHE"
    | "SLOT_HOT_SAUCE_BOSS"
    | "PLAY_ACTION"
    | "RESOLVE_CHOICE"        // for Trash Panda, Crafty Crow, etc.
    | "RESPOND_NO_BUENO"
    | "RESPOND_PASS"
    | "PASS_TURN"
    | "END_TURN";
  cardId?: string;
  targetPlayerId?: string;
  // Multi-step choice payload:
  pickFromDiscardId?: string;   // Trash Panda
  giveCardId?: string;          // Crafty Crow / Food Fight (own card to trade)
  takeCardId?: string;          // Food Fight responder
  replayTarget?: { targetPlayerId?: string; pickFromDiscardId?: string; giveCardId?: string };
}
```

---

## 11. Server API (WebSocket)

All messages JSON `{type, ...payload}`. Server includes `seq` on every server→client message.

### 11.1 Client → Server

| Type | Payload |
|---|---|
| `JOIN` | `{roomCode, name, playerToken?}` |
| `LEAVE` | `{}` |
| `ADD_AI` | `{difficulty}` |
| `REMOVE_AI` | `{playerId}` |
| `READY` | `{ready: bool}` |
| `CHOOSE_HOLDER` | `{holder: "TACO"|"BURRITO"}` |
| `START_GAME` | `{}` |
| `PLAY` | `{move: Move}` |
| `REQUEST_SNAPSHOT` | `{}` |
| `CHAT` | `{text}` (≤200 chars) |

### 11.2 Server → Client

| Type | Payload |
|---|---|
| `WELCOME` | `{playerId, playerToken, roomCode}` |
| `STATE_UPDATE` | `{full: bool, seq, state}` |
| `EVENT` | `{seq, event: {...}}` |
| `RESPONSE_WINDOW_OPEN` | `{deadline, stackTop}` |
| `RESPONSE_WINDOW_CLOSED` | `{}` |
| `PENDING_CHOICE_OPEN` | `{playerId, cardName, kind, options}` — server tells the client to render a picker UI; `options` describes what choice is needed |
| `MOVE_REJECTED` | `{reason, attempted}` |
| `GAME_OVER` | `{winnerId, scores}` |
| `PLAYER_DISCONNECTED` / `PLAYER_RECONNECTED` / `AI_TAKEOVER` | as before |
| `CHAT` | `{from, text, ts}` |
| `ERROR` | `{code, message}` |

### 11.3 Event Kinds

`CARD_DRAWN`, `CARD_SLOTTED`, `CARD_PLAYED`, `CARD_DISCARDED`, `MEAL_TRASHED` (Health Inspector), `MEAL_SWAPPED`, `HAND_SWAPPED`, `CARDS_TRADED`, `DISCARD_PICKED` (Trash Panda), `STACK_PUSHED`, `STACK_COUNTERED`, `STACK_RESOLVED`, `TURN_ADVANCED`, `PHASE_CHANGED`, `END_GAME_TRIGGERED`.

### 11.4 HTTP Endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/` | Static client |
| `POST` | `/rooms` | Create room |
| `GET` | `/rooms/{code}` | Existence check |
| `GET` | `/health` | Liveness |
| `WS` | `/ws/{code}` | Game socket |

### 11.5 Redaction

- `players[*].hand` only in own snapshot.
- `players[*].token` only to that player.
- `drawPile` cards never sent; only `drawPileCount`.
- `discardPile` fully visible — required for `Trash Panda`.

---

## 12. Non-Goals

- User accounts / login / OAuth / profiles.
- Persistent history, replays, ELO.
- DB persistence beyond an active in-memory room.
- Native mobile apps (mobile web is fine).
- Spectator mode.
- Custom card editor / mods.
- Voice chat.
- Monetization.
- Localization beyond English.
- Cross-room matchmaking / tournaments.

---

## Appendix A — Glossary

- **Meal** — cards slotted face-up into a player's Taco/Burrito card-holder.
- **Slot play** — placing an Ingredient, Tummy Ache, or Hot Sauce Boss into a Meal (cannot be countered).
- **Action play** — playing one of the 9 Action card names; goes on the stack and can be `No Bueno`'d.
- **Counter stack** — LIFO list of Action cards awaiting resolution.
- **Response window** — short interval during stack resolution when `No Bueno` may be played.
- **Snapshot / Delta** — full vs. incremental state push.

## Appendix B — Player Interaction Matrix

For every card that requires a choice, this matrix lists: **who picks target**, **whether the target also picks something**, and **the UI affordance** the client must render.

| Card | Who picks target | Target picks something? | UI affordances required (active player) | UI affordances required (target) |
|---|---|---|---|---|
| Ingredient (slot) | Player (self only) | No | Hand-card picker → confirm slot into own Meal | — |
| Tummy Ache (slot) | Player picks any opponent | No | Hand-card picker + target-player picker | Notification toast |
| Hot Sauce Boss (slot) | Player (self only) | No | Hand-card picker → confirm slot into own Meal | — |
| Trash Panda | Player (no target player) | No | Hand-card picker; then **discard-pile picker** modal (full discard visible, click one) | — |
| Crafty Crow | Player picks an opponent | **Yes** — target picks own card to give | Hand-card picker; target-player picker; own-hand picker for `giveCardId`; UI then waits | Modal: "Choose a card to trade" (own-hand picker) |
| Food Fight | Player picks an opponent | **Yes** — target picks; both hands are revealed to each other | Hand-card picker; target-player picker; own-hand picker for `giveCardId`; **opponent-hand viewer** | Modal: opponent hand revealed; own-hand picker |
| Health Inspector (on draw) | Auto (drawing player) | No | Animated "Your meal is trashed" overlay; no input | — |
| Health Inspector (from hand) | Auto (self) | No | Confirmation modal "Are you sure?"; then trash animation | — |
| Order Envy | Player picks an opponent | No | Hand-card picker; target-player picker; swap animation | Notification + animated swap |
| No Bueno (response) | Any player holding it during window | No | **Response-window banner** with countdown + "Play No Bueno" / "Pass" buttons | — |
| Instant Replay | Player picks new targets equivalent to the replayed card | If replayed card required target choices, same rules apply | Hand-card picker; then re-render the picker UI of the action being replayed | Whatever the replayed action required |
| Pass turn | Player (when no legal play) | No | "Pass" button enabled only when `legalMoves` excludes all play actions | — |

---

## Appendix C — Phase-3 Implementation Clarifications (binding)

1. **Draw is automatic.** On `START_TURN` server draws 1 card. If it is `Health Inspector`, the Meal-trash effect resolves before phase advances to `ACT`.
2. **Move equality.** `Move` is a pydantic v2 model; deterministic field values; no random ids in `legal_moves()`.
3. **Illegal moves.** Engine raises `meal_mayhem.engine.IllegalMoveError(reason, attempted)`. Server catches → `MOVE_REJECTED` to the offending socket only.
4. **Pending-choice flow.** When `Trash Panda`, `Crafty Crow`, or `Food Fight` resolves, the engine enters `PENDING_CHOICE` with the **acting player** (or the target, for trade response) required to send a `RESOLVE_CHOICE` move before any other move from anyone is accepted. Default timeout: 20s; on timeout, server picks deterministically (lowest cardId).
5. **Instant Replay binding.** Engine maintains `lastResolvedAction`. `Instant Replay`'s payload must re-supply target/choice fields appropriate to the replayed card; the engine validates against the replayed card's schema.
6. **Order Envy atomic swap.** Meal and hand are swapped in a single transaction; attachments (Tummy Ache, Hot Sauce Boss are already part of `Meal.slots`) travel with the Meal.
7. **Health Inspector uncounterable.** Server rejects `No Bueno` moves whose `stackTop.cardName == "Health Inspector"`.

---

## Appendix D — UI Requirements (every interactive moment)

The client MUST implement the following discrete interactive widgets. Each is invoked by a specific server message or local game state.

| # | Widget | Triggered by | Inputs collected | Outgoing message |
|---|---|---|---|---|
| 1 | **Hand-card picker** | Local — own turn, ACT phase | One `cardId` from own hand | varies (`SLOT_*` / `PLAY_ACTION`) |
| 2 | **Target-player picker** | Local — chosen card requires a target | One `targetPlayerId` (opponent) | included in `Move` |
| 3 | **Discard-pile picker** | `PENDING_CHOICE_OPEN` for `Trash Panda` | One `cardId` from discard | `RESOLVE_CHOICE {pickFromDiscardId}` |
| 4 | **Own-hand picker (trade)** | `PENDING_CHOICE_OPEN` for Crafty Crow / Food Fight (both source and target) | One `cardId` from own hand | `RESOLVE_CHOICE {giveCardId}` |
| 5 | **Opponent-hand viewer** | `PENDING_CHOICE_OPEN` for Food Fight target | Read-only display of revealed opponent hand | — |
| 6 | **Response-window banner** | `RESPONSE_WINDOW_OPEN` | Countdown timer; "Play No Bueno" if held; "Pass" | `PLAY {RESPOND_NO_BUENO}` or `RESPOND_PASS` |
| 7 | **Health Inspector animation** | `EVENT MEAL_TRASHED` | None (cinematic) | — |
| 8 | **Meal/hand swap animation** | `EVENT MEAL_SWAPPED` / `HAND_SWAPPED` | None | — |
| 9 | **Self-target confirmation modal** | Playing `Health Inspector` from hand | Confirm / cancel | `PLAY` or abort |
| 10 | **Pass button** | Local — own turn with no legal play | Click | `PLAY {PASS_TURN}` |
| 11 | **Replay re-picker** | Playing `Instant Replay` | Re-invoke whichever picker the replayed card used | `PLAY {kind:"PLAY_ACTION", cardId:<replay>, replayTarget:{...}}` |
| 12 | **Holder cosmetic chooser** | Pre-game lobby | `"TACO"` or `"BURRITO"` | `CHOOSE_HOLDER` |
| 13 | **Score breakdown overlay** | `GAME_OVER` | None (read-only) | — |

All pickers MUST:
- be cancellable (Escape / outside click) returning the player to ACT phase with no move sent;
- visually highlight legal options and grey out illegal ones;
- be keyboard-navigable (Tab + Enter).

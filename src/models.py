"""Pydantic v2 data models for Tacos & Burritos."""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

CardKind = Literal["INGREDIENT", "TUMMY_ACHE", "HOT_SAUCE_BOSS", "ACTION"]
Phase = Literal["DRAW", "ACT", "RESPONSE_WINDOW", "PENDING_CHOICE", "GAME_OVER"]
MoveKind = Literal[
    "SLOT_INGREDIENT",
    "SLOT_TUMMY_ACHE",
    "SLOT_HOT_SAUCE_BOSS",
    "PLAY_ACTION",
    "RESOLVE_CHOICE",
    "RESPOND_NO_BUENO",
    "RESPOND_PASS",
    "PASS_TURN",
    "END_TURN",
    "DISCARD_CARD",
]


class _Base(BaseModel):
    model_config = ConfigDict(populate_by_name=True)


class Card(_Base):
    id: str
    name: str
    kind: CardKind
    points: Optional[int] = None
    text: str = ""


class Meal(_Base):
    slots: list[Card] = Field(default_factory=list)


class Player(_Base):
    id: str
    token: Optional[str] = None
    seat: int
    name: str
    holder: str = "TACO"
    isAI: bool = False
    aiDifficulty: Optional[str] = None
    connected: bool = True
    meal: Meal = Field(default_factory=Meal)
    handCount: int = 0
    hand: Optional[list[Card]] = None


class StackEntry(_Base):
    cardId: str
    cardName: str
    sourcePlayerId: str
    targetPlayerId: Optional[str] = None
    targetCardId: Optional[str] = None
    giveCardId: Optional[str] = None
    takeCardId: Optional[str] = None
    trashPandaPickId: Optional[str] = None
    countered: bool = False
    unblockable: bool = False


class ScoreBreakdown(_Base):
    ingredientPoints: int = 0
    tummyAchePenalty: int = 0
    hotSauceMultiplierApplied: bool = False
    hotSauceCount: int = 0
    total: int = 0


class Move(_Base):
    kind: MoveKind
    cardId: Optional[str] = None
    targetPlayerId: Optional[str] = None
    targetCardId: Optional[str] = None
    pickFromDiscardId: Optional[str] = None
    giveCardId: Optional[str] = None
    takeCardId: Optional[str] = None
    cardIds: Optional[list[str]] = None
    mode: Optional[str] = None

    def __hash__(self) -> int:
        return hash((
            self.kind, self.cardId, self.targetPlayerId, self.targetCardId,
            self.pickFromDiscardId, self.giveCardId, self.takeCardId,
        ))


class GameState(_Base):
    roomCode: str = ""
    seq: int = 0
    players: list[Player] = Field(default_factory=list)
    drawPileCount: int = 0
    discardPile: list[Card] = Field(default_factory=list)
    currentSeat: int = 0
    phase: Phase = "DRAW"
    turnNumber: int = 0
    stack: list[StackEntry] = Field(default_factory=list)
    pendingChoice: Optional[dict[str, Any]] = None
    responseWindowDeadline: Optional[float] = None
    lastResolvedAction: Optional[StackEntry] = None
    endGameTriggered: bool = False
    rngSeed: str = ""
    winnerId: Optional[str] = None
    scores: Optional[dict[str, ScoreBreakdown]] = None

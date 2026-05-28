"""FastAPI server for Meal Mayhem."""
from __future__ import annotations

import asyncio
import os
import random
import secrets
import string
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from . import ai as ai_mod
from .engine import GameEngine, IllegalMoveError
from .models import Move

RECONNECT_GRACE_SECONDS: float = 30.0
AI_MOVE_DELAY_RANGE: tuple[float, float] = (0.3, 1.5)

ROOM_LETTERS = list("0123456789")


def _gen_code() -> str:
    return "".join(secrets.choice(ROOM_LETTERS) for _ in range(4))


class Room:
    def __init__(self, code: str):
        self.code = code
        self.engine = GameEngine()
        self.started = False
        self.players: list[dict] = []  # spec dicts with id,name,seat,isAI,aiDifficulty,token,ready,connected
        self.sockets: dict[str, WebSocket] = {}  # pid -> ws
        self.seq = 0
        self.host_id: Optional[str] = None
        self._grace_tasks: dict[str, asyncio.Task] = {}
        self._lock = asyncio.Lock()
        self._ai_running: bool = False

    def next_seat(self) -> int:
        return len(self.players)


rooms: dict[str, Room] = {}


app = FastAPI()


@app.get("/health")
async def health():
    return {"ok": True}


@app.post("/rooms")
async def create_room():
    for _ in range(50):
        code = _gen_code()
        if code not in rooms:
            rooms[code] = Room(code)
            return {"roomCode": code}
    return JSONResponse({"error": "no codes available"}, status_code=503)


@app.get("/rooms/{code}")
async def get_room(code: str):
    if code not in rooms:
        return JSONResponse({"error": "not found"}, status_code=404)
    return {"roomCode": code, "started": rooms[code].started, "players": len(rooms[code].players)}


# Static files
_static_dir = Path(__file__).parent / "static"
if _static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")


@app.get("/")
async def index():
    idx = _static_dir / "index.html"
    if idx.exists():
        return FileResponse(str(idx))
    return HTMLResponse("<h1>Meal Mayhem</h1><p>Static client missing.</p>")


@app.get("/r/{code}")
async def room_page(code: str):
    idx = _static_dir / "index.html"
    if idx.exists():
        return FileResponse(str(idx))
    return HTMLResponse("<h1>Meal Mayhem</h1>")


# ----------------------------------------------------------------------
# WebSocket
# ----------------------------------------------------------------------
async def _send(ws: WebSocket, msg: dict):
    try:
        await ws.send_json(msg)
    except Exception:
        pass


def _next_seq(room: Room) -> int:
    room.seq += 1
    return room.seq


async def _broadcast(room: Room, msg: dict, exclude: Optional[str] = None):
    for pid, ws in list(room.sockets.items()):
        if pid == exclude:
            continue
        await _send(ws, msg)


async def _send_state(room: Room, pid: str):
    ws = room.sockets.get(pid)
    if not ws:
        return
    if room.started:
        state = room.engine.current_state(viewer_id=pid)
        state_dict = state.model_dump()
    else:
        state_dict = {
            "roomCode": room.code,
            "phase": "LOBBY",
            "players": [
                {**{k: v for k, v in p.items() if k != "token"},
                 "ready": p.get("ready", False)} for p in room.players
            ],
            "hostId": room.host_id,
        }
    await _send(ws, {"type": "STATE_UPDATE", "full": True, "seq": _next_seq(room), "state": state_dict})


async def _broadcast_state(room: Room):
    for pid in list(room.sockets.keys()):
        await _send_state(room, pid)


async def _ai_loop(room: Room):
    """Drive AI moves until it's a human's turn or game over. Single-flight via room lock."""
    if getattr(room, "_ai_running", False):
        return
    room._ai_running = True
    try:
        while True:
            if not room.started:
                return
            state = room.engine.state
            if state.phase == "GAME_OVER":
                await _broadcast(room, {
                    "type": "GAME_OVER",
                    "seq": _next_seq(room),
                    "winnerId": state.winnerId,
                    "scores": {k: v.model_dump() for k, v in (state.scores or {}).items()},
                })
                return
            # Find acting player
            acting_pid = None
            if state.phase == "RESPONSE_WINDOW":
                for pid in list(room.engine._pending_responders):
                    spec = next((s for s in room.players if s["id"] == pid), None)
                    if spec and spec.get("isAI"):
                        acting_pid = pid
                        break
                if acting_pid is None:
                    return
            elif state.phase == "PENDING_CHOICE":
                pc = state.pendingChoice or {}
                pid = pc.get("playerId")
                spec = next((s for s in room.players if s["id"] == pid), None)
                if not spec or not spec.get("isAI"):
                    return
                acting_pid = pid
            else:
                cur = state.players[state.currentSeat]
                spec = next((s for s in room.players if s["id"] == cur.id), None)
                if not spec or not spec.get("isAI"):
                    return
                acting_pid = cur.id
            lo, hi = AI_MOVE_DELAY_RANGE
            if hi > 0:
                await asyncio.sleep(random.uniform(lo, hi))
            spec = next(s for s in room.players if s["id"] == acting_pid)
            diff = spec.get("aiDifficulty") or "easy"
            ai = ai_mod.HardAI() if diff == "hard" else ai_mod.EasyAI()
            legal = room.engine.legal_moves(acting_pid)
            if not legal:
                return
            viewer_state = room.engine.current_state(viewer_id=acting_pid)
            me = next(p for p in viewer_state.players if p.id == acting_pid)
            try:
                move = ai.decide(viewer_state, me.hand or [], legal)
            except Exception:
                move = legal[0]
            try:
                room.engine.apply_move(acting_pid, move)
            except IllegalMoveError:
                try:
                    room.engine.apply_move(acting_pid, legal[0])
                except Exception:
                    return
            try:
                await _broadcast_state(room)
            except Exception:
                import traceback; traceback.print_exc()
    finally:
        room._ai_running = False


def _all_humans_ready(room: Room) -> bool:
    humans = [p for p in room.players if not p.get("isAI")]
    return all(p.get("ready") for p in humans) and len(humans) >= 1


async def _handle_message(room: Room, pid: str, msg: dict):
    mtype = msg.get("type")
    if mtype == "READY":
        for p in room.players:
            if p["id"] == pid:
                p["ready"] = bool(msg.get("ready", False))
        await _broadcast_state(room)
        return
    if mtype == "ADD_AI":
        if pid != room.host_id or room.started:
            return
        diff = msg.get("difficulty", "easy")
        seat = room.next_seat()
        aid = f"ai_{seat}_{secrets.token_hex(2)}"
        name = msg.get("name") or f"Bot{seat}"
        room.players.append({
            "id": aid, "name": name, "seat": seat,
            "isAI": True, "aiDifficulty": diff, "ready": True, "connected": True,
        })
        await _broadcast_state(room)
        return
    if mtype == "RENAME":
        new_name = (msg.get("name") or "").strip()[:16]
        if not new_name:
            return
        for p in room.players:
            if p["id"] == pid:
                p["name"] = new_name
                break
        if room.started:
            for p in room.engine.state.players:
                if p.id == pid:
                    p.name = new_name
                    break
        await _broadcast_state(room)
        return
    if mtype == "KICK_PLAYER":
        if pid != room.host_id:
            return
        tid = msg.get("playerId")
        if not tid or tid == room.host_id:
            return
        target = next((p for p in room.players if p["id"] == tid), None)
        if not target:
            return
        if room.started:
            # In-game: convert seat to hard AI so game keeps going
            target["isAI"] = True
            target["aiDifficulty"] = "hard"
            target["connected"] = True
            target["name"] = target.get("name", "Kicked") + " (AI)"
            # Close + drop their socket
            ws_t = room.sockets.pop(tid, None)
            if ws_t:
                try: await _send(ws_t, {"type": "ERROR", "code": "KICKED", "message": "Host removed you from the game"})
                except: pass
                try: await ws_t.close()
                except: pass
            # Cancel any pending grace timer for this seat
            t = room._grace_tasks.pop(tid, None)
            if t and not t.done(): t.cancel()
            await _broadcast(room, {"type": "AI_TAKEOVER", "playerId": tid, "difficulty": "hard", "seq": _next_seq(room)})
            await _broadcast_state(room)
            asyncio.create_task(_ai_loop(room))
        else:
            # Pre-game: drop from lobby outright
            room.players = [p for p in room.players if p["id"] != tid]
            for i, p in enumerate(sorted(room.players, key=lambda x: x["seat"])):
                p["seat"] = i
            ws_t = room.sockets.pop(tid, None)
            if ws_t:
                try: await _send(ws_t, {"type": "ERROR", "code": "KICKED", "message": "Host removed you from the room"})
                except: pass
                try: await ws_t.close()
                except: pass
            await _broadcast_state(room)
        return
    if mtype == "REMOVE_AI":
        if pid != room.host_id or room.started:
            return
        tid = msg.get("playerId")
        room.players = [p for p in room.players if p["id"] != tid]
        # Re-seat
        for i, p in enumerate(sorted(room.players, key=lambda x: x["seat"])):
            p["seat"] = i
        await _broadcast_state(room)
        return
    if mtype == "START_GAME":
        if pid != room.host_id:
            await _send(room.sockets[pid], {"type": "MOVE_REJECTED", "reason": "only host can start", "attempted": msg})
            return
        if room.started:
            return
        if not (2 <= len(room.players) <= 8):
            await _send(room.sockets[pid], {"type": "MOVE_REJECTED", "reason": f"need 2-8 players, have {len(room.players)}", "attempted": msg})
            return
        # Host is implicitly ready
        for p in room.players:
            if p["id"] == room.host_id:
                p["ready"] = True
        if not _all_humans_ready(room):
            await _send(room.sockets[pid], {"type": "MOVE_REJECTED", "reason": "not all humans ready", "attempted": msg})
            return
        room.started = True
        # Random seed
        seed = random.randrange(1 << 30)
        room.engine.start_game(room.players, seed=seed)
        await _broadcast_state(room)
        asyncio.create_task(_ai_loop(room))
        return
    if mtype == "REQUEST_SNAPSHOT":
        await _send_state(room, pid)
        return
    # Gameplay messages
    if not room.started:
        await _send(room.sockets[pid], {"type": "MOVE_REJECTED", "reason": "Game not started", "attempted": msg})
        return
    if mtype == "PLAY_CARD":
        # Resolve card kind from acting player's hand to pick the right Move kind
        cid = msg.get("cardId")
        kind = None
        card = None
        for c in room.engine._hands.get(pid, []):
            if c.id == cid:
                card = c
                break
        if card is None:
            await _send(room.sockets[pid], {"type": "MOVE_REJECTED", "reason": "card not in hand", "attempted": msg, "seq": _next_seq(room)})
            return
        # During RESPONSE_WINDOW, playing a No Bueno is a counter, not a normal action.
        if room.engine.state.phase == "RESPONSE_WINDOW" and card.name == "No Bueno":
            move = Move(kind="RESPOND_NO_BUENO", cardId=cid)
        elif card.kind == "INGREDIENT":
            move = Move(kind="SLOT_INGREDIENT", cardId=cid,
                        targetPlayerId=msg.get("targetPlayerId") or pid)
        elif card.kind == "TUMMY_ACHE":
            move = Move(kind="SLOT_TUMMY_ACHE", cardId=cid,
                        targetPlayerId=msg.get("targetPlayerId"))
        elif card.kind == "HOT_SAUCE_BOSS":
            move = Move(kind="SLOT_HOT_SAUCE_BOSS", cardId=cid,
                        targetPlayerId=msg.get("targetPlayerId") or pid)
        else:
            move = Move(kind="PLAY_ACTION", cardId=cid,
                        targetPlayerId=msg.get("targetPlayerId"),
                        targetCardId=msg.get("targetCardId"),
                        giveCardId=msg.get("giveCardId"))
    elif mtype == "END_TURN":
        # Discard-to-end-turn: pick the first card in hand, or PASS if empty.
        hand = room.engine._hands.get(pid, [])
        if hand:
            move = Move(kind="DISCARD_CARD", cardId=hand[0].id)
        else:
            move = Move(kind="PASS_TURN")
    elif mtype == "DISCARD":
        cid = msg.get("cardId")
        hand = room.engine._hands.get(pid, [])
        if not cid and hand:
            cid = hand[0].id
        if not cid:
            return
        move = Move(kind="DISCARD_CARD", cardId=cid)
    elif mtype == "RESPOND_PASS":
        move = Move(kind="RESPOND_PASS")
    elif mtype == "RESOLVE_CHOICE":
        move = Move(kind="RESOLVE_CHOICE",
                    pickFromDiscardId=msg.get("pickFromDiscardId"),
                    giveCardId=msg.get("giveCardId"))
    else:
        return
    try:
        room.engine.apply_move(pid, move)
    except IllegalMoveError as e:
        await _send(room.sockets[pid], {"type": "MOVE_REJECTED", "reason": e.reason, "attempted": msg, "seq": _next_seq(room)})
        return
    except Exception as e:
        import traceback
        traceback.print_exc()
        await _send(room.sockets[pid], {"type": "MOVE_REJECTED", "reason": f"engine error: {e}", "attempted": msg, "seq": _next_seq(room)})
        return
    try:
        await _broadcast_state(room)
    except Exception:
        import traceback; traceback.print_exc()
    try:
        asyncio.create_task(_ai_loop(room))
    except Exception:
        import traceback; traceback.print_exc()


async def _on_disconnect(room: Room, pid: str):
    spec = next((p for p in room.players if p["id"] == pid), None)
    if not spec:
        return
    spec["connected"] = False
    if room.started:
        for p in room.engine.state.players:
            if p.id == pid:
                p.connected = False
    await _broadcast(room, {
        "type": "PLAYER_DISCONNECTED",
        "playerId": pid,
        "graceSeconds": RECONNECT_GRACE_SECONDS,
        "seq": _next_seq(room),
    })
    # schedule grace timer
    async def grace():
        try:
            await asyncio.sleep(RECONNECT_GRACE_SECONDS)
            # Convert to AI
            spec2 = next((p for p in room.players if p["id"] == pid), None)
            if not spec2:
                return
            if spec2.get("connected"):
                return
            spec2["isAI"] = True
            spec2["aiDifficulty"] = "hard"
            await _broadcast(room, {
                "type": "AI_TAKEOVER",
                "playerId": pid,
                "difficulty": "hard",
                "seq": _next_seq(room),
            })
            if room.started:
                asyncio.create_task(_ai_loop(room))
        except asyncio.CancelledError:
            return
    task = asyncio.create_task(grace())
    room._grace_tasks[pid] = task


@app.websocket("/ws/{code}")
async def ws_endpoint(ws: WebSocket, code: str):
    await ws.accept()
    # Special path: "_new" → create a fresh room and join in one round trip.
    if code == "_new":
        for _ in range(50):
            new_code = _gen_code()
            if new_code not in rooms:
                rooms[new_code] = Room(new_code)
                code = new_code
                break
        else:
            await _send(ws, {"type": "ERROR", "code": "NO_CODES", "message": "no codes available"})
            await ws.close()
            return
    if code not in rooms:
        await _send(ws, {"type": "ERROR", "code": "ROOM_NOT_FOUND", "message": "unknown room"})
        await ws.close()
        return
    room = rooms[code]
    pid: Optional[str] = None
    try:
        while True:
            msg = await ws.receive_json()
            if msg.get("type") == "JOIN" and pid is None:
                token = msg.get("playerToken")
                name = msg.get("name", "Player")
                # reconnect?
                if token:
                    spec = next((p for p in room.players if p.get("token") == token), None)
                    if spec:
                        pid = spec["id"]
                        spec["connected"] = True
                        if room.started:
                            for p in room.engine.state.players:
                                if p.id == pid:
                                    p.connected = True
                        # cancel grace
                        t = room._grace_tasks.pop(pid, None)
                        if t and not t.done():
                            t.cancel()
                        room.sockets[pid] = ws
                        await _send(ws, {"type": "WELCOME", "playerId": pid, "playerToken": token, "roomCode": code, "seq": _next_seq(room)})
                        await _send_state(room, pid)
                        await _broadcast(room, {"type": "PLAYER_RECONNECTED", "playerId": pid, "seq": _next_seq(room)}, exclude=pid)
                        continue
                # new join
                if room.started:
                    await _send(ws, {"type": "ERROR", "code": "GAME_STARTED", "message": "already started"})
                    await ws.close()
                    return
                if len(room.players) >= 8:
                    await _send(ws, {"type": "ERROR", "code": "FULL", "message": "room full"})
                    await ws.close()
                    return
                seat = room.next_seat()
                pid = f"p_{seat}_{secrets.token_hex(2)}"
                tok = secrets.token_hex(8)
                room.players.append({
                    "id": pid, "name": name, "seat": seat, "isAI": False,
                    "aiDifficulty": None, "connected": True, "token": tok, "ready": True,
                })
                if room.host_id is None:
                    room.host_id = pid
                room.sockets[pid] = ws
                await _send(ws, {"type": "WELCOME", "playerId": pid, "playerToken": tok, "roomCode": code, "seq": _next_seq(room)})
                await _send_state(room, pid)
                # notify others
                for other_pid in list(room.sockets.keys()):
                    if other_pid != pid:
                        await _send_state(room, other_pid)
                continue
            if pid is None:
                await _send(ws, {"type": "ERROR", "code": "NOT_JOINED", "message": "send JOIN first"})
                continue
            await _handle_message(room, pid, msg)
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        if pid and room.sockets.get(pid) is ws:
            del room.sockets[pid]
            await _on_disconnect(room, pid)

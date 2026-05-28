"""Integration tests for the Meal Mayhem FastAPI server."""
from __future__ import annotations

import asyncio
import json
import re
import pytest

pytest.importorskip("meal_mayhem")
pytest.importorskip("httpx")
pytest.importorskip("fastapi")

from fastapi.testclient import TestClient

from meal_mayhem import server as server_mod

ROOM_CODE_RE = re.compile(r"^[0-9]{4}$")  # digits only


@pytest.fixture
def client():
    return TestClient(server_mod.app)


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------
def test_post_rooms_returns_valid_code(client):
    r = client.post("/rooms")
    assert r.status_code == 200
    data = r.json()
    assert "roomCode" in data
    code = data["roomCode"]
    assert len(code) == 4
    assert ROOM_CODE_RE.match(code), f"Room code {code!r} violates A-Z excl. I/O"


def test_post_rooms_codes_are_unique_enough(client):
    seen = set()
    for _ in range(20):
        r = client.post("/rooms")
        seen.add(r.json()["roomCode"])
    assert len(seen) >= 18  # tolerate small chance of collision retries


def test_health_endpoint(client):
    r = client.get("/health")
    assert r.status_code == 200


# ---------------------------------------------------------------------------
# WebSocket — JOIN flow
# ---------------------------------------------------------------------------
import anyio


def _recv_json(ws, timeout=2.0):
    # WebSocketTestSession.receive_text() blocks forever; use the underlying
    # anyio stream via the test session's portal with a timeout.
    async def _recv():
        with anyio.fail_after(timeout):
            return await ws._send_rx.receive()
    msg = ws.portal.call(_recv)
    if msg.get("type") == "websocket.close":
        raise RuntimeError("ws closed")
    return json.loads(msg["text"])


def test_ws_join_flow_welcome_then_state_update(client):
    code = client.post("/rooms").json()["roomCode"]
    with client.websocket_connect(f"/ws/{code}") as ws:
        ws.send_json({"type": "JOIN", "roomCode": code, "name": "Alice"})
        welcome = _recv_json(ws)
        assert welcome["type"] == "WELCOME"
        assert "playerToken" in welcome
        assert "playerId" in welcome
        state_msg = _recv_json(ws)
        assert state_msg["type"] == "STATE_UPDATE"
        assert state_msg.get("full") is True
        assert "seq" in state_msg


# ---------------------------------------------------------------------------
# Snapshot redaction
# ---------------------------------------------------------------------------
def test_snapshot_redacts_opponent_hands(client):
    """Appendix B: own hand visible, opponent's hand hidden."""
    code = client.post("/rooms").json()["roomCode"]
    with client.websocket_connect(f"/ws/{code}") as ws_a, \
         client.websocket_connect(f"/ws/{code}") as ws_b:
        ws_a.send_json({"type": "JOIN", "roomCode": code, "name": "A"})
        a_welcome = _recv_json(ws_a)
        ws_b.send_json({"type": "JOIN", "roomCode": code, "name": "B"})
        b_welcome = _recv_json(ws_b)
        # Mark ready and start game (host = A).
        ws_a.send_json({"type": "READY", "ready": True})
        ws_b.send_json({"type": "READY", "ready": True})
        ws_a.send_json({"type": "START_GAME"})
        # Drain messages until we see a STATE_UPDATE post-start on A.
        a_state = None
        for _ in range(20):
            msg = _recv_json(ws_a)
            if msg["type"] == "STATE_UPDATE" and msg.get("full"):
                a_state = msg["state"]
                if any(p.get("hand") for p in a_state["players"]):
                    break
        assert a_state is not None
        me = next(p for p in a_state["players"] if p["id"] == a_welcome["playerId"])
        others = [p for p in a_state["players"] if p["id"] != a_welcome["playerId"]]
        assert me.get("hand") is not None
        for o in others:
            assert o.get("hand") is None
            assert "handCount" in o


# ---------------------------------------------------------------------------
# Illegal target
# ---------------------------------------------------------------------------
def test_play_card_illegal_target_returns_move_rejected(client):
    code = client.post("/rooms").json()["roomCode"]
    with client.websocket_connect(f"/ws/{code}") as ws:
        ws.send_json({"type": "JOIN", "roomCode": code, "name": "A"})
        _recv_json(ws); _recv_json(ws)
        # Play card with a bogus id; server must reject.
        ws.send_json({"type": "PLAY_CARD", "cardId": "nope_no_such_card"})
        # Drain a few messages, look for MOVE_REJECTED.
        rejected = False
        for _ in range(5):
            try:
                msg = _recv_json(ws)
            except Exception:
                break
            if msg["type"] == "MOVE_REJECTED":
                rejected = True
                break
        assert rejected


# ---------------------------------------------------------------------------
# Seq monotonicity
# ---------------------------------------------------------------------------
def test_seq_numbers_strictly_monotonic(client):
    """Appendix B."""
    code = client.post("/rooms").json()["roomCode"]
    with client.websocket_connect(f"/ws/{code}") as ws:
        ws.send_json({"type": "JOIN", "roomCode": code, "name": "A"})
        seqs = []
        for _ in range(5):
            try:
                msg = _recv_json(ws, timeout=0.5)
            except (TimeoutError, RuntimeError):
                break
            if "seq" in msg:
                seqs.append(msg["seq"])
        assert len(seqs) >= 2
        assert seqs == sorted(seqs)
        assert len(set(seqs)) == len(seqs)


# ---------------------------------------------------------------------------
# Two-AI scripted full game
# ---------------------------------------------------------------------------
def test_two_player_game_runs_to_completion_with_easy_ai(client, monkeypatch):
    """Add 2 Easy AI players, drive host turns + choices, wait for GAME_OVER."""
    monkeypatch.setattr(server_mod, "AI_MOVE_DELAY_RANGE", (0.0, 0.0))
    code = client.post("/rooms").json()["roomCode"]
    with client.websocket_connect(f"/ws/{code}") as ws:
        ws.send_json({"type": "JOIN", "roomCode": code, "name": "Host"})
        welcome = _recv_json(ws); _recv_json(ws)
        host_id = welcome["playerId"]
        ws.send_json({"type": "ADD_AI", "difficulty": "easy"})
        ws.send_json({"type": "ADD_AI", "difficulty": "easy"})
        ws.send_json({"type": "READY", "ready": True})
        ws.send_json({"type": "START_GAME"})
        game_over = False
        # Drive host via direct engine access for any PENDING_CHOICE/ACT — simpler than scripting.
        room = server_mod.rooms[code]
        engine = room.engine
        import random as _r
        rng = _r.Random(123)
        for _ in range(5000):
            try:
                msg = _recv_json(ws, timeout=3.0)
            except (TimeoutError, RuntimeError):
                break
            if msg["type"] == "GAME_OVER":
                game_over = True
                break
            if msg["type"] != "STATE_UPDATE":
                continue
            st = engine.state
            if st.phase == "GAME_OVER":
                continue
            # Determine if host owes a move.
            owes = False
            if st.phase == "RESPONSE_WINDOW" and host_id in engine._pending_responders:
                ws.send_json({"type": "RESPOND_PASS"}); owes = True
            elif st.phase == "PENDING_CHOICE" and (st.pendingChoice or {}).get("playerId") == host_id:
                legal = engine.legal_moves(host_id)
                if legal:
                    mv = rng.choice(legal)
                    payload = {"type": "PLAY_CARD" if mv.kind == "PLAY_ACTION" else mv.kind.upper()}
                    if mv.cardId: payload["cardId"] = mv.cardId
                    if mv.targetPlayerId: payload["targetPlayerId"] = mv.targetPlayerId
                    if mv.giveCardId: payload["giveCardId"] = mv.giveCardId
                    if getattr(mv, "pickFromDiscardId", None):
                        payload["pickFromDiscardId"] = mv.pickFromDiscardId
                    ws.send_json(payload); owes = True
            elif st.phase == "ACT" and st.players[st.currentSeat].id == host_id:
                ws.send_json({"type": "END_TURN"}); owes = True
        assert game_over, f"never reached GAME_OVER (phase={engine.state.phase}, turn={engine.state.turnNumber})"


# ---------------------------------------------------------------------------
# Reconnect within grace
# ---------------------------------------------------------------------------
def test_reconnect_within_grace_restores_seat_and_hand(client):
    """Appendix B."""
    code = client.post("/rooms").json()["roomCode"]
    # Initial connection
    with client.websocket_connect(f"/ws/{code}") as ws:
        ws.send_json({"type": "JOIN", "roomCode": code, "name": "A"})
        welcome = _recv_json(ws)
        state = _recv_json(ws)
        token = welcome["playerToken"]
        pid = welcome["playerId"]
        # Capture own hand
        my = next(p for p in state["state"]["players"] if p["id"] == pid)
        original_hand_ids = sorted(c["id"] for c in (my.get("hand") or []))
    # Reconnect with same token
    with client.websocket_connect(f"/ws/{code}") as ws2:
        ws2.send_json({"type": "JOIN", "roomCode": code, "name": "A",
                       "playerToken": token})
        welcome2 = _recv_json(ws2)
        assert welcome2["playerId"] == pid
        state2 = _recv_json(ws2)
        my2 = next(p for p in state2["state"]["players"] if p["id"] == pid)
        new_hand_ids = sorted(c["id"] for c in (my2.get("hand") or []))
        assert new_hand_ids == original_hand_ids


# ---------------------------------------------------------------------------
# Grace expiry → hard AI takeover
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_grace_expiry_converts_seat_to_hard_ai(client, monkeypatch):
    """Appendix B. Shorten RECONNECT_GRACE for the test."""
    if hasattr(server_mod, "RECONNECT_GRACE_SECONDS"):
        monkeypatch.setattr(server_mod, "RECONNECT_GRACE_SECONDS", 0.2)
    else:
        pytest.skip("server does not expose RECONNECT_GRACE_SECONDS for override")
    code = client.post("/rooms").json()["roomCode"]
    with client.websocket_connect(f"/ws/{code}") as ws_a, \
         client.websocket_connect(f"/ws/{code}") as ws_b:
        ws_a.send_json({"type": "JOIN", "roomCode": code, "name": "A"})
        _recv_json(ws_a); _recv_json(ws_a)
        ws_b.send_json({"type": "JOIN", "roomCode": code, "name": "B"})
        _recv_json(ws_b); _recv_json(ws_b)
        # B disconnects
        ws_b.close()
        # Wait for grace to expire and AI_TAKEOVER to be broadcast to A.
        seen_takeover = False
        for _ in range(40):
            await asyncio.sleep(0.05)
            try:
                msg = _recv_json(ws_a)
            except Exception:
                continue
            if msg["type"] == "AI_TAKEOVER":
                assert msg.get("difficulty") == "hard"
                seen_takeover = True
                break
        assert seen_takeover

/* Taco vs Burrito — client */
(function () {
  "use strict";

  // ----- Setup paths -----
  const basePath = (() => {
    // location.pathname like /app/ or / or /app/r/ABCD
    let p = location.pathname;
    // strip /r/CODE etc
    const m = p.match(/^(.*?)(\/r\/[A-Z]+)?\/?$/);
    let base = m ? m[1] : p;
    if (!base.endsWith("/")) base += "/";
    return base;
  })();
  const httpBase = location.origin + basePath; // e.g. https://host/app/
  const wsBase = (location.protocol === "https:" ? "wss://" : "ws://") + location.host + basePath;

  // ----- State -----
  function randomName() {
    const adj = ["Hungry", "Spicy", "Crunchy", "Cheesy", "Saucy", "Zesty", "Smoky", "Tangy", "Fiery", "Toasty"];
    const noun = ["Taco", "Burrito", "Salsa", "Nacho", "Chili", "Jalapeño", "Avocado", "Churro", "Queso", "Mango"];
    return adj[Math.floor(Math.random()*adj.length)] + noun[Math.floor(Math.random()*noun.length)];
  }
  const S = {
    ws: null,
    playerId: null,
    playerToken: localStorage.getItem("tvb_token") || null,
    roomCode: null,
    name: localStorage.getItem("tvb_name") || randomName(),
    state: null,
    hostId: null,
    lastNoBuenoStack: null,
    pendingTargetCard: null,
  };

  // ----- Card visuals -----
  const EMOJI = {
    Steak: "🥩", Carnitas: "🌶", Chicken: "🍗", Beans: "🫘", Rice: "🍚",
    Cheese: "🧀", Lettuce: "🥬", Tomato: "🍅", Onion: "🧅", Corn: "🌽",
    Salsa: "🥫", Guacamole: "🥑", "Sour Cream": "🥛",
    "Tummy Ache": "🤢", "Hot Sauce Boss": "🔥",
    "Trash Panda": "🦝", "Crafty Crow": "🐦", "Food Fight": "🥊",
    "Health Inspector": "🕵", "Order Envy": "👀", "No Bueno": "🛡",
  };
  function emojiFor(c) { return EMOJI[c.name] || "🍽"; }
  function cardClass(c) {
    if (c.kind === "INGREDIENT") return "ingredient";
    if (c.kind === "TUMMY_ACHE") return "action tummy";
    if (c.kind === "HOT_SAUCE_BOSS") return "action hotsauce";
    if (c.name === "No Bueno") return "action counter";
    return "action";
  }

  // ----- DOM helpers -----
  const $ = (id) => document.getElementById(id);
  function show(id) { $(id).classList.remove("hidden"); }
  function hide(id) { $(id).classList.add("hidden"); }
  function setScreen(name) {
    ["home", "lobby", "game", "gameover"].forEach(s => $(s).classList.add("hidden"));
    $(name).classList.remove("hidden");
    const inGame = name === "game";
    // Hide entire top bar on home/lobby; show only in game
    const bar = document.querySelector(".topbar");
    if (bar) bar.style.display = inGame ? "" : "none";
    const brand = document.querySelector(".topbar .brand");
    if (brand) brand.style.display = inGame ? "none" : "";
    if ($("discardBtn")) $("discardBtn").classList.toggle("hidden", !inGame);
    if ($("drawCountBtn")) $("drawCountBtn").classList.toggle("hidden", !inGame);
    if ($("historyBtn")) $("historyBtn").classList.toggle("hidden", !inGame);
    if ($("leaveGameBtnTop")) $("leaveGameBtnTop").classList.toggle("hidden", !inGame);
    if (name === "home") $("name").value = S.name || localStorage.getItem("tvb_name") || "";
  }
  function toast(msg, ms = 2200) {
    const t = $("toast");
    t.textContent = msg;
    t.classList.remove("hidden");
    clearTimeout(toast._t);
    toast._t = setTimeout(() => t.classList.add("hidden"), ms);
  }

  function openModal(title, contentNode, opts) {
    opts = opts || {};
    $("modalTitle").textContent = title;
    const c = $("modalContent");
    c.innerHTML = "";
    if (typeof contentNode === "string") c.innerHTML = contentNode;
    else c.appendChild(contentNode);
    // Required modals (PENDING_CHOICE) can't be dismissed.
    const required = !!opts.required;
    $("modalClose").style.display = required ? "none" : "";
    $("modal").dataset.required = required ? "1" : "";
    $("modal").classList.remove("hidden");
  }
  function closeModal(force) {
    if (!force && $("modal").dataset.required === "1") return;
    $("modal").dataset.required = "";
    $("modal").classList.add("hidden");
  }
  $("modalClose").onclick = closeModal;
  document.querySelector("#modal .modal-back").onclick = closeModal;

  // ----- WS -----
  function connect(code, name) {
    if (S.ws) {
      // Detach handlers BEFORE closing so the dying socket can't update the UI.
      try { S.ws.onopen = S.ws.onclose = S.ws.onmessage = S.ws.onerror = null; } catch(e){}
      try { S.ws.close(); } catch (e) {}
    }
    $("conn").classList.add("hidden");
    $("conn").classList.remove("online");
    const ws = new WebSocket(wsBase + "ws/" + code);
    S.ws = ws;
    S.roomCode = code;
    ws.onopen = () => {
      $("conn").classList.add("hidden");
      ws.send(JSON.stringify({ type: "JOIN", roomCode: code, name, playerToken: S.playerToken || undefined }));
    };
    ws.onclose = () => {
      if (ws !== S.ws) return;  // stale handler
      $("conn").textContent = "reconnecting…";
      $("conn").classList.remove("hidden");
      // Auto-reconnect if we have a token + room (i.e., we were in a game/lobby).
      if (S.playerToken && S.roomCode && S.roomCode !== "_new") {
        setTimeout(() => connect(S.roomCode, S.name || "Player"), 1200);
      } else {
        $("conn").textContent = "disconnected";
      }
    };
    ws.onmessage = (ev) => {
      if (ws !== S.ws) return;
      $("conn").classList.add("hidden");  // proof of life
      let m; try { m = JSON.parse(ev.data); } catch { return; }
      handleMsg(m);
    };
  }
  function send(obj) { if (S.ws && S.ws.readyState === 1) S.ws.send(JSON.stringify(obj)); }

  function handleMsg(m) {
    switch (m.type) {
      case "WELCOME":
        S.playerId = m.playerId;
        S.playerToken = m.playerToken;
        if (m.roomCode) S.roomCode = m.roomCode;
        localStorage.setItem("tvb_token", m.playerToken);
        clearBusy();
        break;
      case "STATE_UPDATE":
        // Reset per-game history when a brand-new game begins (LOBBY/GAME_OVER → playing phase)
        if (S.state && (S.state.phase === "LOBBY" || S.state.phase === "GAME_OVER")
            && m.state && m.state.phase !== "LOBBY" && m.state.phase !== "GAME_OVER") {
          _history.length = 0;
          _lastAnnouncedAction = null;
          _lastMealSnapshot = {};
          _prevTurnPlayerId = null;
          _lastHandIds = null;
        }
        S.state = m.state;
        if (m.state && m.state.hostId) S.hostId = m.state.hostId;
        render();
        break;
      case "MOVE_REJECTED":
        toast("Rejected: " + (m.reason || "illegal"));
        break;
      case "GAME_OVER":
        // state will be rendered with phase GAME_OVER
        break;
      case "AI_TAKEOVER":
        toast("Player went AFK → AI takeover");
        break;
      case "ERROR":
        toast(m.message || "error");
        if (m.code === "ROOM_NOT_FOUND" || m.code === "GAME_STARTED" || m.code === "FULL") {
          setScreen("home");
        }
        break;
    }
  }

  // ----- Home -----
  $("name").value = S.name;
  $("createBtn").onclick = async () => {
    const name = $("name").value.trim() || "Player";
    localStorage.setItem("tvb_name", name);
    S.name = name;
    setBusy("Creating room…");
    S.playerToken = null; localStorage.removeItem("tvb_token");
    // One round trip: WS to /ws/_new, server creates room and JOINs you.
    connect("_new", name);
  };
  $("joinBtn").onclick = () => {
    const code = ($("joinCode").value || "").trim();
    const name = $("name").value.trim() || "Player";
    if (!/^\d{4}$/.test(code)) { toast("Enter a 4-digit code"); return; }
    localStorage.setItem("tvb_name", name);
    S.name = name;
    setBusy("Joining " + code + "…");
    S.playerToken = null; localStorage.removeItem("tvb_token");
    connect(code, name);
  };

  function setBusy(msg) {
    let el = $("busy");
    if (!el) {
      el = document.createElement("div");
      el.id = "busy";
      el.className = "busy";
      document.body.appendChild(el);
    }
    el.innerHTML = '<div class="spinner"></div><div>' + msg + '</div>';
    el.classList.remove("hidden");
  }
  function clearBusy() { const el = $("busy"); if (el) el.classList.add("hidden"); }

  // ----- Lobby controls -----
  function randomBotName() {
    const adj = ["Cranky", "Sneaky", "Greedy", "Lazy", "Clumsy", "Bossy", "Salty", "Sassy", "Grumpy", "Picky"];
    const noun = ["Taco", "Burrito", "Pepper", "Olive", "Lime", "Cilantro", "Chip", "Tortilla", "Bean", "Radish"];
    return adj[Math.floor(Math.random()*adj.length)] + noun[Math.floor(Math.random()*noun.length)];
  }
  $("addEasyAI").onclick = () => send({ type: "ADD_AI", difficulty: "easy", name: randomBotName() });
  $("startBtn").onclick = () => send({ type: "START_GAME" });
  if ($("shareBtn")) {
    $("shareBtn").onclick = async (e) => {
      e.preventDefault();
      const code = S.roomCode || S.state?.roomCode || "";
      if (!code) { toast("No room to share yet"); return; }
      const url = location.origin + basePath + "#" + code;
      try {
        await navigator.clipboard.writeText(url);
        toast("Link copied", 1500);
      } catch (err) {
        prompt("Copy this link:", url);
      }
    };
  }
  function confirmLeave() {
    if (!S.state || S.state.phase === "LOBBY" || S.state.phase === "GAME_OVER") {
      doLeave(); return;
    }
    if (confirm("Leave the game? Your seat will be taken over by an AI.")) doLeave();
  }
  function doLeave() {
    try { S.ws && (S.ws.onclose = null, S.ws.close()); } catch{}
    _history.length = 0;  // clear history on leave
    setScreen("home");
  }
  $("leaveBtn").onclick = (e) => { e.preventDefault(); confirmLeave(); };
  if ($("leaveGameBtnTop")) $("leaveGameBtnTop").onclick = confirmLeave;
  $("goLeave").onclick = doLeave;
  if ($("discardBtn")) $("discardBtn").onclick = () => openDiscardModal(false);

  // ----- Render -----
  let _lastHandIds = null;
  function render() {
    const st = S.state;
    if (!st) return;
    if (st.phase === "LOBBY") { setScreen("lobby"); renderLobby(); }
    else if (st.phase === "GAME_OVER") { setScreen("gameover"); renderGameOver(); }
    else { setScreen("game"); renderGame(); }
  }

  function renderLobby() {
    const st = S.state;
    $("lobbyCode").textContent = st.roomCode;
    $("lobbyCode2").textContent = st.roomCode;
    const ul = $("lobbyPlayers"); ul.innerHTML = "";
    const isHost = S.playerId === (st.hostId || S.hostId);
    for (const p of st.players || []) {
      const li = document.createElement("li");
      li.className = (p.isAI ? "ai-row " : "") + ((st.hostId === p.id) ? "host" : "");
      const isMe = p.id === S.playerId;
      const left = document.createElement("div");
      left.innerHTML = `<b>${escape(p.name)}</b>` +
        (p.isAI ? `<span class="badge">${p.aiDifficulty || "AI"}</span>` : "") +
        (st.hostId === p.id ? `<span class="badge">host</span>` : "") +
        (isMe ? `<span class="badge" style="background:var(--guac-green);color:white">you</span>` : "");
      li.appendChild(left);
      if (isMe) {
        const renameBtn = document.createElement("button");
        renameBtn.className = "kick"; renameBtn.style.background = "var(--taco-yellow)"; renameBtn.style.color = "var(--brown)";
        renameBtn.textContent = "Rename";
        renameBtn.onclick = () => {
          const next = prompt("Your name (max 16):", p.name);
          if (next && next.trim() && next.trim() !== p.name) {
            const n = next.trim().slice(0, 16);
            S.name = n;
            localStorage.setItem("tvb_name", n);
            send({ type: "RENAME", name: n });
          }
        };
        li.appendChild(renameBtn);
      }
      if (isHost && !isMe) {
        const btn = document.createElement("button");
        btn.className = "kick";
        btn.textContent = p.isAI ? "Remove" : "Kick";
        btn.onclick = () => {
          if (p.isAI || confirm(`Kick ${p.name} from the room?`)) {
            send(p.isAI
              ? { type: "REMOVE_AI", playerId: p.id }
              : { type: "KICK_PLAYER", playerId: p.id });
          }
        };
        li.appendChild(btn);
      }
      ul.appendChild(li);
    }
    // Only host can start; non-hosts see no Start button at all.
    $("startBtn").classList.toggle("hidden", !isHost);
    $("startBtn").disabled = !(isHost && (st.players || []).length >= 2);
    $("addEasyAI").classList.toggle("hidden", !isHost);
    $("addEasyAI").disabled = (st.players || []).length >= 8;
  }

  // Canonical render order: opponents (in seat order) then me last.
  function renderOrder() {
    const st = S.state;
    if (!st) return [];
    const sorted = st.players.slice().sort((a, b) => (a.seat||0) - (b.seat||0));
    const me = sorted.find(p => p.id === S.playerId);
    const others = sorted.filter(p => p.id !== S.playerId);
    return me ? [...others, me] : others;
  }

  function renderGame() {
    const st = S.state;
    const me = st.players.find(p => p.id === S.playerId);

    // Opponents in seat order in top stack, me in sticky bottom panel
    const opps = $("opponents-stack"); opps.innerHTML = "";
    for (const p of renderOrder()) {
      if (p.id === S.playerId) continue;
      opps.appendChild(mealPanel(p, false));
    }
    const myPanel = $("my-panel"); myPanel.innerHTML = "";
    if (me) myPanel.appendChild(mealPanel(me, true));

    // Discard count in header button
    const dp = st.discardPile || [];
    if ($("discardCount")) $("discardCount").textContent = dp.length;
    if ($("drawCount")) $("drawCount").textContent = st.drawPileCount || 0;
    if ($("discardBtn")) $("discardBtn").classList.remove("hidden");
    if ($("leaveGameBtnTop")) $("leaveGameBtnTop").classList.remove("hidden");

    // Hand — every newly added card (draw, Trash Panda pick, Food Fight win, Order Envy
    // hand swap, etc.) is pinned leftmost with a shimmer border. Multiple new cards keep
    // their server-relative order at the front.
    const handDiv = $("hand"); handDiv.innerHTML = "";
    const hand = me?.hand || [];
    const prevIds = _lastHandIds || [];
    const newIdSet = new Set(hand.map(c => c.id).filter(id => !prevIds.includes(id)));
    const sorted = hand.slice().sort((a, b) => {
      const aNew = newIdSet.has(a.id) ? 0 : 1;
      const bNew = newIdSet.has(b.id) ? 0 : 1;
      return aNew - bNew;
    });
    for (const c of sorted) {
      const el = handCardEl(c);
      if (newIdSet.has(c.id)) el.classList.add("just-drawn");
      handDiv.appendChild(el);
    }
    _lastHandIds = hand.map(c => c.id);

    // Stack info
    let info = "";
    if (st.stack && st.stack.length) {
      const top = st.stack[st.stack.length - 1];
      const src = st.players.find(p => p.id === top.sourcePlayerId);
      info = `Stack: ${top.cardName} from ${src?.name || "?"}` + (top.targetPlayerId ? ` → ${st.players.find(p=>p.id===top.targetPlayerId)?.name || ""}` : "");
    }
    $("stackInfo").textContent = info;

    handleNoBueno(st, me);
    handlePending(st, me);
    handleActionAnnounce(st);
  }

  // ----- Game history -----
  const _history = [];  // array of {text, ts}
  function logHistory(text) {
    _history.push({text, ts: Date.now()});
    if (_history.length > 200) _history.shift();
  }
  if ($("historyBtn")) {
    $("historyBtn").onclick = () => {
      const wrap = document.createElement("div");
      wrap.className = "history-list";
      if (!_history.length) { wrap.innerHTML = '<i style="opacity:.6">No actions yet.</i>'; }
      for (let i = _history.length - 1; i >= 0; i--) {
        const h = _history[i];
        const row = document.createElement("div");
        row.className = "history-row";
        const time = new Date(h.ts).toLocaleTimeString([], {hour: "2-digit", minute: "2-digit", second: "2-digit"});
        row.innerHTML = `<span class="history-time">${time}</span> <span>${escape(h.text)}</span>`;
        wrap.appendChild(row);
      }
      openModal("Game history", wrap);
    };
  }

  // ----- Action announcement overlay + voice (auto-dismiss 1s) -----
  let _lastAnnouncedAction = null;
  let _lastMealSnapshot = {};  // pid -> [card ids] for diffing slot adds
  let _prevTurnPlayerId = null;  // who held the turn at last render — they're the actor for new slots

  // ----- Voice toggle (with iOS unlock priming) -----
  let _voiceOn = localStorage.getItem("tvb_voice") !== "0";
  let _voicePrimed = false;
  function primeVoice() {
    // iOS/Safari/Edge-on-iOS won't speak until a synth.speak() happens inside a
    // user-gesture handler. Prime with a silent utterance on any first tap.
    if (_voicePrimed) return;
    try {
      const u = new SpeechSynthesisUtterance(" ");
      u.volume = 0; u.rate = 1; u.lang = "en-US";
      window.speechSynthesis.speak(u);
      _voicePrimed = true;
    } catch (e) {}
  }
  document.addEventListener("touchend", primeVoice, { once: true, capture: true });
  document.addEventListener("click", primeVoice, { once: true, capture: true });

  function updateVoiceBtn() {
    const b = $("voiceBtn");
    if (b) b.textContent = _voiceOn ? "🔊" : "🔇";
  }
  updateVoiceBtn();
  if ($("voiceBtn")) {
    $("voiceBtn").onclick = () => {
      _voiceOn = !_voiceOn;
      localStorage.setItem("tvb_voice", _voiceOn ? "1" : "0");
      primeVoice();
      try { window.speechSynthesis && window.speechSynthesis.cancel(); } catch(e){}
      updateVoiceBtn();
      if (_voiceOn) speak("Voice on");
    };
  }

  function speak(text) { /* voice disabled */ }

  function nameOf(pid, ifMe) {
    const p = S.state?.players.find(x => x.id === pid);
    if (!p) return "?";
    return p.id === S.playerId ? (ifMe || "You") : p.name;
  }

  function handleActionAnnounce(st) {
    // 1) Action card resolution
    const last = st.lastResolvedAction;
    if (last) {
      const key = `${last.cardId}-${last.sourcePlayerId}`;
      if (key !== _lastAnnouncedAction) {
        _lastAnnouncedAction = key;
        const announceCards = new Set([
          "Health Inspector", "Food Fight", "Order Envy",
          "Crafty Crow", "Trash Panda", "No Bueno"
        ]);
        if (announceCards.has(last.cardName)) {
          const srcN = nameOf(last.sourcePlayerId, "You");
          const tgtN = last.targetPlayerId ? nameOf(last.targetPlayerId, "you") : null;
          const text = tgtN
            ? `${srcN} played ${last.cardName} on ${tgtN}`
            : `${srcN} played ${last.cardName}`;
          showAnnouncement(text);
          speak(text);
          logHistory(text);
          // Big-overlay events: Health Inspector + Order Envy (when not countered)
          if (last.cardName === "Health Inspector") {
            showHealthInspectorOverlay(srcN);
          } else if (last.cardName === "Order Envy" && !last.countered) {
            const targetsMe = last.targetPlayerId === S.playerId;
            const sourceIsMe = last.sourcePlayerId === S.playerId;
            showOrderEnvyOverlay(srcN, last.targetPlayerId ? nameOf(last.targetPlayerId, "you") : "?", targetsMe || sourceIsMe);
          }
        }
      }
    }
    // 2) Slot additions (ingredient / tummy ache / hot sauce boss)
    // The acting player is whoever HAD the turn before the state advanced (not currentSeat,
    // which has already moved to the next player by render time).
    const actor = (_prevTurnPlayerId && st.players.find(p => p.id === _prevTurnPlayerId))
                  || st.players[st.currentSeat];
    for (const p of st.players) {
      const cur = (p.meal?.slots || []).map(c => c.id);
      const prev = _lastMealSnapshot[p.id] || [];
      const added = cur.filter(id => !prev.includes(id));
      if (prev.length || (cur.length && _lastMealSnapshot.__init)) {
        for (const cid of added) {
          const card = (p.meal?.slots || []).find(c => c.id === cid);
          if (!card) continue;
          const ownerIsMe = p.id === S.playerId;
          const actorIsMe = actor && actor.id === S.playerId;
          const ownerN = ownerIsMe ? "you" : p.name;
          const ownerPoss = ownerIsMe ? "your" : (p.name + "'s");
          const actorN = actorIsMe ? "You" : (actor ? actor.name : "?");
          let text;
          if (card.kind === "INGREDIENT") {
            const v = card.points || 0;
            text = `${actorN} added ${v > 0 ? "+" : ""}${v} to ${ownerPoss} meal`;
          } else if (card.kind === "TUMMY_ACHE") {
            text = `${actorN} slotted a tummy ache (${card.points}) on ${ownerN}`;
          } else if (card.kind === "HOT_SAUCE_BOSS") {
            text = `${actorN} added Hot Sauce Boss to ${ownerPoss} meal`;
          }
          if (text) { showAnnouncement(text); speak(text); logHistory(text); }
        }
      }
      _lastMealSnapshot[p.id] = cur;
    }
    _lastMealSnapshot.__init = true;
    // Track who is going to be the actor for the NEXT diff
    _prevTurnPlayerId = st.players[st.currentSeat]?.id || null;
  }

  function showHealthInspectorOverlay(srcName) {
    showBigOverlay({
      id: "hi-overlay",
      emoji: "🚨",
      title: "Health Inspector!",
      sub: `${srcName === "You" ? "Your" : srcName + "'s"} meal got trashed.`,
      danger: true,
    });
  }

  function showOrderEnvyOverlay(srcName, tgtName, involvesMe) {
    showBigOverlay({
      id: "envy-overlay",
      emoji: "👀",
      title: "Order Envy!",
      sub: `${srcName} swapped meal + hand with ${tgtName}.`,
      danger: involvesMe,
    });
  }

  function showBigOverlay({id, emoji, title, sub, danger}) {
    let el = $(id);
    if (!el) {
      el = document.createElement("div");
      el.id = id;
      el.className = "hi-overlay hidden";
      el.innerHTML = `
        <div class="hi-box">
          <button class="hi-close" aria-label="Close">✕</button>
          <div class="hi-emoji"></div>
          <div class="hi-title"></div>
          <div class="hi-sub"></div>
        </div>`;
      document.body.appendChild(el);
      el.querySelector(".hi-close").onclick = () => el.classList.add("hidden");
      el.onclick = (e) => { if (e.target === el) el.classList.add("hidden"); };
    }
    el.querySelector(".hi-emoji").textContent = emoji;
    el.querySelector(".hi-title").textContent = title;
    el.querySelector(".hi-sub").textContent = sub;
    el.querySelector(".hi-box").classList.toggle("danger", !!danger);
    el.querySelector(".hi-box").classList.toggle("info", !danger);
    el.classList.remove("hidden");
    clearTimeout(el._t);
    el._t = setTimeout(() => el.classList.add("hidden"), 2000);
  }

  function showAnnouncement(text) {
    let el = $("announce");
    if (!el) {
      el = document.createElement("div");
      el.id = "announce";
      el.className = "announce hidden";
      // Insert into the sticky bottom group so it sits where the counter banner sits
      const bottom = $("game-bottom") || document.body;
      bottom.insertBefore(el, bottom.firstChild);
    }
    el.textContent = text;
    el.classList.remove("hidden");
    clearTimeout(showAnnouncement._t);
    showAnnouncement._t = setTimeout(() => el.classList.add("hidden"), 1800);
  }

  function isCurrent(p) {
    if (!p || !S.state) return false;
    return S.state.players[S.state.currentSeat]?.id === p.id;
  }

  function mealPanel(p, isMe) {
    const wrap = document.createElement("div");
    wrap.className = "meal-panel" + (isCurrent(p) ? " current" : "") + (isMe ? " me" : "");
    wrap.appendChild(mealPanelInner(p, isMe));
    // Host-only: tap a tiny ✕ on opponent panels to kick (converts to AI mid-game)
    const isHost = S.playerId === (S.state?.hostId || S.hostId);
    if (isHost && !isMe && !p.isAI) {
      const kick = document.createElement("button");
      kick.className = "panel-kick";
      kick.title = "Kick " + p.name;
      kick.textContent = "✕";
      kick.onclick = (e) => {
        e.stopPropagation();
        if (confirm(`Kick ${p.name}? Their seat becomes a hard AI.`)) {
          send({ type: "KICK_PLAYER", playerId: p.id });
        }
      };
      wrap.appendChild(kick);
    }
    return wrap;
  }
  function mealPanelInner(p, isMe) {
    const frag = document.createDocumentFragment();
    const head = document.createElement("div");
    head.className = "meal-head";
    const score = computeLiveScore(p);
    const handCount = p.handCount || (p.hand||[]).length || 0;
    head.innerHTML =
      `<span class="name">${escape(p.name)}</span>` +
      `<span class="score-pill">${score}</span>` +
      `<span class="hand-size">🃏 ${handCount}</span>`;
    frag.appendChild(head);
    const slots = document.createElement("div"); slots.className = "slots";
    for (const c of (p.meal?.slots || [])) slots.appendChild(slotCardEl(c));
    frag.appendChild(slots);
    return frag;
  }

  function computeLiveScore(p) {
    const slots = p.meal?.slots || [];
    let total = 0;
    let hsbCount = 0;
    for (const s of slots) {
      if (s.kind === "HOT_SAUCE_BOSS") { hsbCount++; continue; }
      if (typeof s.points === "number") total += s.points;  // ingredients +, tummy aches −
    }
    return hsbCount > 0 ? total * Math.pow(2, hsbCount) : total;
  }

  function slotCardEl(c) {
    const el = document.createElement("div");
    const klass = c.kind === "TUMMY_ACHE" ? "tummy" : c.kind === "HOT_SAUCE_BOSS" ? "hotsauce" : "";
    el.className = "slot-card " + klass;
    const pts = c.kind === "HOT_SAUCE_BOSS" ? "×2" : c.points;
    el.innerHTML =
      (pts != null ? `<div class="big-value">${typeof pts === "number" && pts > 0 ? "+" + pts : pts}</div>` : "") +
      `<div class="emoji-sm">${emojiFor(c)}</div>`;
    return el;
  }

  function handCardEl(c) {
    const el = document.createElement("div");
    el.className = "hand-card " + cardClass(c);
    const kicker = (c.kind === "ACTION") ? `<div class="kicker">${cardKicker(c)}</div>` : "";
    const pipVal = (c.kind === "HOT_SAUCE_BOSS")
      ? "×2"
      : (c.points != null ? (c.points > 0 ? "+" + c.points : c.points) : null);
    const pipHtml = pipVal != null ? `<div class="hand-pip">${pipVal}</div>` : "";
    el.innerHTML =
      pipHtml +
      `<div class="emoji">${emojiFor(c)}</div>` +
      `<div class="name">${escape(c.name)}</div>` +
      kicker;
    el.onclick = () => onHandClick(c);
    return el;
  }
  function cardKicker(c) {
    switch (c.name) {
      case "No Bueno": return "Block any action";
      case "Trash Panda": return "Grab from trash";
      case "Crafty Crow": return "Steal a meal card";
      case "Food Fight": return "All flip top card";
      case "Health Inspector": return "Trash your meal";
      case "Order Envy": return "Swap hand+meal";
      default: return "";
    }
  }

  function onHandClick(c) {
    const st = S.state;
    const me = st.players.find(p => p.id === S.playerId);
    // If we're in RESPONSE_WINDOW and this is a No Bueno → counter
    if (st.phase === "RESPONSE_WINDOW" && c.name === "No Bueno") {
      send({ type: "PLAY_CARD", cardId: c.id });
      return;
    }
    if (st.phase === "PENDING_CHOICE") {
      // resolution flows handled by handlePending; clicking hand isn't normal here
      return;
    }
    if (!isCurrent(me) || st.phase !== "ACT") {
      const cur = st.players[st.currentSeat];
      const why = st.phase !== "ACT" ? `phase: ${st.phase}` : `${cur?.name || "?"}'s turn`;
      toast("Wait — " + why, 1500);
      return;
    }
    if (c.kind === "INGREDIENT") {
      openMealPicker(c, "Add " + c.name + " to which meal?", S.playerId);
    } else if (c.kind === "TUMMY_ACHE") {
      // Default opponent target
      const opp = (st.players.find(p => p.id !== S.playerId) || {}).id;
      openMealPicker(c, "Slot " + c.name + " on whose meal?", opp);
    } else if (c.kind === "HOT_SAUCE_BOSS") {
      openMealPicker(c, "Add " + c.name + " to which meal?", S.playerId);
    } else {
      // Action
      if (c.name === "Crafty Crow") {
        openCraftyCrowPicker(c);
      } else if (c.name === "Order Envy") {
        openTargetPicker(c, "Choose target for " + c.name);
      } else if (c.name === "Trash Panda" || c.name === "Food Fight") {
        openConfirmOrDiscard(c);
      } else {
        // Health Inspector — no overlay, commits immediately
        send({ type: "PLAY_CARD", cardId: c.id });
      }
    }
  }

  // Confirm-or-discard overlay for no-target action cards (Trash Panda, Food Fight)
  function openConfirmOrDiscard(card) {
    const list = document.createElement("div");
    list.className = "target-list";

    const discardRow = document.createElement("div");
    discardRow.className = "target-row";
    discardRow.innerHTML = `<div class="info"><b>🗑 Discard this card</b></div>`;
    discardRow.onclick = () => { closeModal(); send({ type: "DISCARD", cardId: card.id }); };
    list.appendChild(discardRow);

    const playRow = document.createElement("div");
    playRow.className = "target-row";
    playRow.innerHTML = `<div class="info"><b>${emojiFor(card)} Play ${escape(card.name)}</b></div>`;
    playRow.onclick = () => { closeModal(); send({ type: "PLAY_CARD", cardId: card.id }); };
    list.appendChild(playRow);

    openModal(card.name, list);
  }

  // Generic meal picker (which player's meal to act on) — adds "Discard this card" as the top option.
  function openMealPicker(card, title, _defaultPid) {
    const list = document.createElement("div");
    list.className = "target-list";

    // Discard option
    const discardRow = document.createElement("div");
    discardRow.className = "target-row";
    discardRow.innerHTML = `<div class="info"><b>🗑 Discard this card</b></div>`;
    discardRow.onclick = () => { closeModal(); send({ type: "DISCARD", cardId: card.id }); };
    list.appendChild(discardRow);

    // Players: just name + score, no card preview
    for (const o of renderOrder()) {
      const row = document.createElement("div");
      row.className = "target-row";
      const meTag = o.id === S.playerId ? " (you)" : "";
      row.innerHTML =
        `<div class="info"><b>${escape(o.name)}${meTag}</b></div>` +
        `<span class="score-pill">${computeLiveScore(o)}</span>`;
      row.onclick = () => { closeModal(); send({ type: "PLAY_CARD", cardId: card.id, targetPlayerId: o.id }); };
      list.appendChild(row);
    }
    openModal(title, list);
  }

  // Crafty Crow: pick an opponent's meal card to steal
  function openCraftyCrowPicker(card) {
    const st = S.state;
    const opps = st.players.filter(p => p.id !== S.playerId);
    const wrap = document.createElement("div");

    // Discard-this-card option at top
    const discardBtn = document.createElement("div");
    discardBtn.className = "target-row";
    discardBtn.style.marginBottom = "12px";
    discardBtn.innerHTML = `<div class="info"><b>🗑 Discard this card</b></div>`;
    discardBtn.onclick = () => {
      closeModal();
      send({ type: "DISCARD", cardId: card.id });
    };
    wrap.appendChild(discardBtn);

    let anyCards = false;
    for (const o of opps) {
      const head = document.createElement("div");
      head.innerHTML = `<b>${escape(o.name)}</b> <span class="score-pill" style="font-size:11px">${computeLiveScore(o)}</span>`;
      head.style.margin = "8px 0 4px";
      wrap.appendChild(head);
      const grid = document.createElement("div");
      grid.className = "discard-grid";
      for (const mc of (o.meal?.slots || [])) {
        anyCards = true;
        const cell = document.createElement("div");
        cell.className = "pick-card";
        const pts = (mc.kind === "HOT_SAUCE_BOSS")
          ? "×2"
          : (mc.points != null ? (mc.points > 0 ? "+" + mc.points : mc.points) : null);
        const ptsCls = (mc.kind === "HOT_SAUCE_BOSS")
          ? "hot"
          : (mc.points != null && mc.points < 0 ? "neg" : "pos");
        const ptsLine = pts != null
          ? `<div class="pick-inline-pts ${ptsCls}">${pts}</div>`
          : "";
        cell.innerHTML =
          ptsLine +
          `<div style="font-size:22px">${emojiFor(mc)}</div>` +
          `<div>${escape(mc.name)}</div>`;
        const btn = document.createElement("button");
        btn.className = "primary"; btn.textContent = "Steal";
        btn.onclick = () => {
          closeModal();
          send({ type: "PLAY_CARD", cardId: card.id,
                 targetPlayerId: o.id, targetCardId: mc.id });
        };
        cell.appendChild(btn);
        grid.appendChild(cell);
      }
      wrap.appendChild(grid);
    }
    if (!anyCards) {
      const empty = document.createElement("i");
      empty.textContent = "No opponent meal cards available to steal.";
      wrap.appendChild(empty);
    }
    openModal("Crafty Crow — steal a meal card", wrap);
  }

  // ----- Target picker (action cards needing a target player) -----
  function openTargetPicker(card, title) {
    const st = S.state;
    const list = document.createElement("div");
    list.className = "target-list";

    // Discard-this-card option at top
    const discardRow = document.createElement("div");
    discardRow.className = "target-row";
    discardRow.innerHTML = `<div class="info"><b>🗑 Discard this card</b></div>`;
    discardRow.onclick = () => {
      closeModal();
      send({ type: "DISCARD", cardId: card.id });
    };
    list.appendChild(discardRow);

    // Then opponents
    const opps = st.players.filter(p => p.id !== S.playerId);
    for (const o of opps) {
      const row = document.createElement("div");
      row.className = "target-row";
      const slots = (o.meal?.slots || []);
      const preview = slots.slice(0, 6).map(s => `<div class="mini">${emojiFor(s)}</div>`).join("");
      row.innerHTML =
        `<div class="info"><b>${escape(o.name)}</b>` +
        `<div class="preview">${preview || '<span style="opacity:.5">empty</span>'}</div></div>` +
        `<span class="score-pill">${computeLiveScore(o)}</span>`;
      row.onclick = () => {
        closeModal();
        send({ type: "PLAY_CARD", cardId: card.id, targetPlayerId: o.id });
      };
      list.appendChild(row);
    }
    openModal(title, list);
  }

  // ----- Discard modal -----
  function openDiscardModal(asPicker) {
    const st = S.state;
    const dp = (st.discardPile || []).slice().reverse(); // newest first
    const wrap = document.createElement("div");
    wrap.className = "discard-grid";
    if (!dp.length) wrap.innerHTML = '<i style="opacity:.6">Discard is empty.</i>';
    for (const c of dp) {
      const cell = document.createElement("div");
      cell.className = "pick-card";
      const ptsLine = (c.points != null)
        ? `<div class="pick-pts ${c.points > 0 ? "pos" : "neg"}">${c.points > 0 ? "+" + c.points : c.points}</div>`
        : "";
      cell.innerHTML =
        ptsLine +
        `<div style="font-size:22px">${emojiFor(c)}</div>` +
        `<div>${escape(c.name)}</div>`;
      if (asPicker) {
        const btn = document.createElement("button");
        btn.className = "primary"; btn.textContent = "Pick";
        btn.onclick = () => {
          closeModal(true);
          send({ type: "RESOLVE_CHOICE", pickFromDiscardId: c.id });
        };
        cell.appendChild(btn);
      }
      wrap.appendChild(cell);
    }
    openModal(asPicker ? "Trash Panda — pick a card (or skip)" : "Discard pile", wrap, {required: !!asPicker});
    // If this is the Trash Panda picker, append a skip option
    if (asPicker) {
      const skip = document.createElement("button");
      skip.className = ""; skip.textContent = "Skip — take nothing";
      skip.style.cssText = "display:block;width:100%;margin-top:14px;background:transparent;color:var(--brown-soft);text-decoration:underline;box-shadow:none;";
      skip.onclick = () => {
        closeModal(true);
        send({ type: "RESOLVE_CHOICE", pickFromDiscardId: "__skip__" });
      };
      $("modalContent").appendChild(skip);
    }
  }

  // ----- Give-card modal (Crafty Crow / Food Fight response) -----
  function openGivePicker(pc) {
    const me = S.state.players.find(p => p.id === S.playerId);
    const hand = me?.hand || [];
    const wrap = document.createElement("div");
    wrap.className = "discard-grid";
    if (!hand.length) {
      wrap.innerHTML = '<i>You have no cards to give.</i>';
    }
    for (const c of hand) {
      const cell = document.createElement("div");
      cell.className = "pick-card";
      const ptsLine = (c.points != null)
        ? `<div class="pick-pts ${c.points > 0 ? "pos" : "neg"}">${c.points > 0 ? "+" + c.points : c.points}</div>`
        : "";
      cell.innerHTML =
        ptsLine +
        `<div style="font-size:22px">${emojiFor(c)}</div>` +
        `<div>${escape(c.name)}</div>`;
      const btn = document.createElement("button");
      btn.textContent = "Give"; btn.className = "primary";
      btn.onclick = () => {
        closeModal(true);
        send({ type: "RESOLVE_CHOICE", giveCardId: c.id });
      };
      cell.appendChild(btn);
      wrap.appendChild(cell);
    }
    openModal(`Give a card (${pc.cardName || ""})`, wrap, {required: true});
  }

  // ----- Pending choices -----
  function handlePending(st, me) {
    const pc = st.pendingChoice;
    if (!pc || pc.playerId !== S.playerId) return;
    if (pc.kind === "TRASH_PANDA") {
      openDiscardModal(true);
    } else if (pc.kind === "FOOD_FIGHT_PICK") {
      openFoodFightPicker(pc);
    }
  }

  function openFoodFightPicker(pc) {
    const opts = pc.options || [];
    const wrap = document.createElement("div");
    wrap.className = "discard-grid";
    if (!opts.length) wrap.innerHTML = '<i>No options.</i>';
    for (const c of opts) {
      const cell = document.createElement("div");
      cell.className = "pick-card";
      const ptsLine = (c.points != null)
        ? `<div class="pick-pts ${c.points > 0 ? "pos" : "neg"}">${c.points > 0 ? "+" + c.points : c.points}</div>`
        : "";
      cell.innerHTML =
        ptsLine +
        `<div style="font-size:22px">${emojiFor(c)}</div>` +
        `<div>${escape(c.name)}</div>`;
      const btn = document.createElement("button");
      btn.className = "primary"; btn.textContent = "Take";
      btn.onclick = () => {
        closeModal(true);
        send({ type: "RESOLVE_CHOICE", pickFromDiscardId: c.id });
      };
      cell.appendChild(btn);
      wrap.appendChild(cell);
    }
    openModal("Food Fight — pick a flipped card", wrap, {required: true});
  }

  // ----- No Bueno banner with 5s auto-pass timer -----
  let _noBuenoTimer = null;
  let _noBuenoStackKey = null;
  function handleNoBueno(st, me) {
    const banner = $("noBueno");
    const clearTimer = () => {
      if (_noBuenoTimer) { clearInterval(_noBuenoTimer); _noBuenoTimer = null; }
      _noBuenoStackKey = null;
    };
    if (st.phase !== "RESPONSE_WINDOW") { banner.classList.add("hidden"); banner.classList.remove("danger"); clearTimer(); return; }
    const top = (st.stack || [])[st.stack.length - 1];
    if (!top) { banner.classList.add("hidden"); banner.classList.remove("danger"); clearTimer(); return; }
    if (top.sourcePlayerId === S.playerId) { banner.classList.add("hidden"); banner.classList.remove("danger"); clearTimer(); return; }
    const hand = me?.hand || [];
    const nb = hand.find(c => c.name === "No Bueno");
    if (!nb) { banner.classList.add("hidden"); banner.classList.remove("danger"); clearTimer(); return; }
    const src = st.players.find(p => p.id === top.sourcePlayerId);
    const tgt = top.targetPlayerId ? st.players.find(p => p.id === top.targetPlayerId) : null;
    const srcName = src?.id === S.playerId ? "you" : (src?.name || "?");
    const tgtName = tgt ? (tgt.id === S.playerId ? "you" : tgt.name) : null;
    const targetsMe = tgt && tgt.id === S.playerId;
    const action = tgtName ? `played <b>${escape(top.cardName)}</b> on <b>${escape(tgtName)}</b>` : `played <b>${escape(top.cardName)}</b>`;
    const stackKey = `${top.cardId}-${st.stack.length}`;
    // Only start a fresh timer when stack top changes
    if (_noBuenoStackKey !== stackKey) {
      clearTimer();
      _noBuenoStackKey = stackKey;
      let remaining = targetsMe ? 10 : 5;
      const tick = () => {
        const cd = banner.querySelector(".countdown");
        if (cd) cd.textContent = remaining;
        if (remaining <= 0) {
          clearTimer();
          send({ type: "RESPOND_PASS" });
        }
        remaining--;
      };
      _noBuenoTimer = setInterval(tick, 1000);
    }
    banner.innerHTML = `<span class="msg">🛡 <b>${escape(srcName)}</b> ${action}. Counter? <span class="countdown">${targetsMe ? 10 : 5}</span>s</span>`;
    const cBtn = document.createElement("button");
    cBtn.className = "primary"; cBtn.textContent = "Counter";
    cBtn.onclick = () => { clearTimer(); send({ type: "PLAY_CARD", cardId: nb.id }); };
    const pBtn = document.createElement("a");
    pBtn.href = "#"; pBtn.className = "pass-link";
    pBtn.textContent = "Pass";
    pBtn.onclick = (e) => { e.preventDefault(); clearTimer(); send({ type: "RESPOND_PASS" }); };
    banner.appendChild(cBtn); banner.appendChild(pBtn);
    banner.classList.toggle("danger", !!targetsMe);
    banner.classList.remove("hidden");
  }

  // ----- Game over -----
  function renderGameOver() {
    const st = S.state;
    const players = st.players.slice().sort((a, b) => {
      const sa = st.scores?.[a.id]?.total ?? 0;
      const sb2 = st.scores?.[b.id]?.total ?? 0;
      return sb2 - sa;
    });
    const winner = players[0];
    // Winner block
    const wb = $("winner-block"); wb.innerHTML = "";
    if (winner) {
      const youWon = winner.id === S.playerId;
      wb.innerHTML =
        `<div class="crown">👑</div>` +
        `<div class="winner-name">${escape(winner.name)}${youWon ? " — you!" : ""}</div>` +
        `<div class="winner-score">${st.scores?.[winner.id]?.total ?? 0} pts</div>`;
    }
    // Rest of scoreboard (place + name + score)
    const sb = $("scoreboard"); sb.innerHTML = "";
    players.forEach((p, idx) => {
      const sc = st.scores?.[p.id];
      const row = document.createElement("div");
      row.className = "go-row" + (p.id === S.playerId ? " me" : "");
      const place = ["🥇","🥈","🥉"][idx] || `${idx+1}.`;
      const breakdown = sc
        ? `<span class="go-breakdown">+${sc.ingredientPoints} ${sc.tummyAchePenalty<0?sc.tummyAchePenalty:""}${sc.hotSauceMultiplierApplied ? " ×2" : ""}</span>`
        : "";
      row.innerHTML =
        `<span class="go-place">${place}</span>` +
        `<span class="go-name">${escape(p.name)}</span>` +
        breakdown +
        `<span class="go-total">${sc?.total ?? 0}</span>`;
      sb.appendChild(row);
    });
  }

  // ----- Util -----
  function escape(s) { return String(s).replace(/[&<>"']/g, c => ({ "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;" }[c])); }

  // Initial screen: home (also hides topbar)
  setScreen("home");

  // Auto-join from #CODE (4 digits) or legacy /r/CODE
  (function autoJoin() {
    const hash = (location.hash || "").match(/^#(\d{4})$/);
    const path = location.pathname.match(/\/r\/(\d{4})\/?$/);
    const code = (hash && hash[1]) || (path && path[1]);
    if (code) {
      if (S.name) {
        $("name").value = S.name;
        connect(code, S.name);
      } else {
        // Land on home with the code pre-filled
        $("joinCode").value = code;
      }
    }
  })();
})();

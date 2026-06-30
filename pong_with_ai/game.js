const canvas = document.getElementById("game");
const ctx = canvas.getContext("2d");

const playerScoreEl = document.getElementById("playerScore");
const aiScoreEl = document.getElementById("aiScore");
const roundText = document.getElementById("roundText");
const hintText = document.getElementById("hintText");
const difficultyEl = document.getElementById("difficulty");
const ollamaModeEl = document.getElementById("ollamaMode");

const W = canvas.width;
const H = canvas.height;
const paddle = { w: 16, h: 104, speed: 8.2 };

const state = {
  running: false,
  paused: false,
  playerScore: 0,
  aiScore: 0,
  keys: new Set(),
  player: { x: 34, y: H / 2 - paddle.h / 2 },
  ai: { x: W - 50, y: H / 2 - paddle.h / 2 },
  ball: { x: W / 2, y: H / 2, vx: 6.4, vy: 3.1, r: 10 },
  particles: [],
  lastTime: performance.now(),
  model: {
    enabled: false,
    available: false,
    pending: false,
    lastAsk: 0,
    command: "stay",
    modelName: "qwen3:30b",
  },
};

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function resetBall(direction = Math.random() > 0.5 ? 1 : -1) {
  state.ball.x = W / 2;
  state.ball.y = H / 2;
  state.ball.vx = 6.2 * direction;
  state.ball.vy = (Math.random() * 4 - 2) || 2.4;
}

function setStatus(text, hint = "W/S oder Maus bewegen. Leertaste startet.") {
  roundText.textContent = text;
  hintText.textContent = hint;
}

function burst(x, y, color) {
  for (let i = 0; i < 18; i++) {
    state.particles.push({
      x,
      y,
      vx: Math.cos(i * 0.7) * (1.2 + Math.random() * 3),
      vy: Math.sin(i * 0.7) * (1.2 + Math.random() * 3),
      life: 26 + Math.random() * 16,
      color,
    });
  }
}

function movePlayer() {
  if (state.keys.has("w") || state.keys.has("arrowup")) {
    state.player.y -= paddle.speed;
  }
  if (state.keys.has("s") || state.keys.has("arrowdown")) {
    state.player.y += paddle.speed;
  }
  state.player.y = clamp(state.player.y, 0, H - paddle.h);
}

function moveScriptAi() {
  const strength = Number(difficultyEl.value);
  const target = state.ball.y - paddle.h / 2;
  const predictionBias = state.ball.vx > 0 ? state.ball.vy * 10 : 0;
  state.ai.y += (target + predictionBias - state.ai.y) * strength * 0.09;
  state.ai.y = clamp(state.ai.y, 0, H - paddle.h);
}

function applyModelCommand() {
  const strength = Number(difficultyEl.value);
  const speed = paddle.speed * (0.35 + strength);
  if (state.model.command === "up") {
    state.ai.y -= speed;
  } else if (state.model.command === "down") {
    state.ai.y += speed;
  }
  state.ai.y = clamp(state.ai.y, 0, H - paddle.h);
}

async function askModelForMove(now) {
  if (!state.model.enabled || state.model.pending || now - state.model.lastAsk < 450) {
    return;
  }
  state.model.pending = true;
  state.model.lastAsk = now;

  const payload = {
    ball: {
      x: Math.round(state.ball.x),
      y: Math.round(state.ball.y),
      vx: Number(state.ball.vx.toFixed(2)),
      vy: Number(state.ball.vy.toFixed(2)),
    },
    ai: {
      y: Math.round(state.ai.y),
      center: Math.round(state.ai.y + paddle.h / 2),
    },
    player: {
      y: Math.round(state.player.y),
      center: Math.round(state.player.y + paddle.h / 2),
    },
    field: { width: W, height: H, paddleHeight: paddle.h },
    score: { umut: state.playerScore, agent: state.aiScore },
  };

  try {
    const response = await fetch("/ai_move", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    if (["up", "down", "stay"].includes(data.move)) {
      state.model.command = data.move;
      state.model.available = true;
      if (data.model) state.model.modelName = data.model;
      if (data.reason) {
        hintText.textContent = `Ollama rechts: ${data.move} - ${data.reason}`;
      }
    }
  } catch (error) {
    state.model.available = false;
    state.model.enabled = false;
    ollamaModeEl.checked = false;
    setStatus("Browser-KI aktiv", "Ollama-Spieler nicht erreichbar. Starte ueber start_pong.ps1.");
  } finally {
    state.model.pending = false;
  }
}

function moveAi(now) {
  if (state.model.enabled) {
    askModelForMove(now);
    applyModelCommand();
  } else {
    moveScriptAi();
  }
}

function rectHit(ball, rect) {
  return (
    ball.x - ball.r < rect.x + paddle.w &&
    ball.x + ball.r > rect.x &&
    ball.y - ball.r < rect.y + paddle.h &&
    ball.y + ball.r > rect.y
  );
}

function hitPaddle(rect, isPlayer) {
  const ball = state.ball;
  const offset = (ball.y - (rect.y + paddle.h / 2)) / (paddle.h / 2);
  ball.vx = Math.abs(ball.vx) * (isPlayer ? 1 : -1);
  ball.vx *= 1.045;
  ball.vy = offset * 7.4;
  ball.x = isPlayer ? rect.x + paddle.w + ball.r : rect.x - ball.r;
  burst(ball.x, ball.y, isPlayer ? "#37d67a" : "#58a6ff");
}

function scorePoint(playerWon) {
  if (playerWon) {
    state.playerScore += 1;
    setStatus("Punkt fuer Umut", "Weiter so. Der Agent justiert nach.");
    burst(W - 40, state.ball.y, "#37d67a");
  } else {
    state.aiScore += 1;
    setStatus("Punkt fuer Agent", "Konter vorbereiten.");
    burst(40, state.ball.y, "#58a6ff");
  }
  playerScoreEl.textContent = state.playerScore;
  aiScoreEl.textContent = state.aiScore;
  resetBall(playerWon ? -1 : 1);
}

function updateParticles() {
  state.particles = state.particles.filter((p) => p.life > 0);
  for (const p of state.particles) {
    p.x += p.vx;
    p.y += p.vy;
    p.life -= 1;
  }
}

function update(now) {
  if (!state.running || state.paused) return;

  movePlayer();
  moveAi(now);

  const ball = state.ball;
  ball.x += ball.vx;
  ball.y += ball.vy;

  if (ball.y - ball.r <= 0 || ball.y + ball.r >= H) {
    ball.vy *= -1;
    ball.y = clamp(ball.y, ball.r, H - ball.r);
    burst(ball.x, ball.y, "#ffd166");
  }

  if (rectHit(ball, state.player) && ball.vx < 0) {
    hitPaddle(state.player, true);
  }
  if (rectHit(ball, state.ai) && ball.vx > 0) {
    hitPaddle(state.ai, false);
  }

  if (ball.x < -30) scorePoint(false);
  if (ball.x > W + 30) scorePoint(true);

  updateParticles();
}

function drawCourt() {
  ctx.fillStyle = "#080b10";
  ctx.fillRect(0, 0, W, H);

  ctx.strokeStyle = "rgba(255,255,255,0.16)";
  ctx.lineWidth = 2;
  ctx.setLineDash([10, 12]);
  ctx.beginPath();
  ctx.moveTo(W / 2, 24);
  ctx.lineTo(W / 2, H - 24);
  ctx.stroke();
  ctx.setLineDash([]);

  const glow = ctx.createRadialGradient(W / 2, H / 2, 40, W / 2, H / 2, W / 1.5);
  glow.addColorStop(0, "rgba(88,166,255,0.10)");
  glow.addColorStop(1, "rgba(88,166,255,0)");
  ctx.fillStyle = glow;
  ctx.fillRect(0, 0, W, H);
}

function drawPaddle(rect, color, label) {
  ctx.shadowColor = color;
  ctx.shadowBlur = 18;
  ctx.fillStyle = color;
  ctx.fillRect(rect.x, rect.y, paddle.w, paddle.h);
  ctx.shadowBlur = 0;
  ctx.fillStyle = "rgba(255,255,255,0.72)";
  ctx.font = "700 16px Segoe UI";
  ctx.fillText(label, rect.x - (label === "AI" ? 8 : 3), rect.y - 12);
}

function draw() {
  drawCourt();
  drawPaddle(state.player, "#37d67a", "DU");
  drawPaddle(state.ai, "#58a6ff", "AI");

  for (const p of state.particles) {
    ctx.globalAlpha = clamp(p.life / 34, 0, 1);
    ctx.fillStyle = p.color;
    ctx.beginPath();
    ctx.arc(p.x, p.y, 3, 0, Math.PI * 2);
    ctx.fill();
  }
  ctx.globalAlpha = 1;

  ctx.shadowColor = "#ffd166";
  ctx.shadowBlur = 20;
  ctx.fillStyle = "#ffd166";
  ctx.beginPath();
  ctx.arc(state.ball.x, state.ball.y, state.ball.r, 0, Math.PI * 2);
  ctx.fill();
  ctx.shadowBlur = 0;
}

function loop(now) {
  const delta = now - state.lastTime;
  state.lastTime = now;
  if (delta < 80) update(now);
  draw();
  requestAnimationFrame(loop);
}

function startGame() {
  state.running = true;
  state.paused = false;
  const hint = state.model.enabled
    ? "Du links, Ollama-Sprachmodell rechts."
    : "Du gegen die schnelle Browser-KI. Ollama-Modus optional.";
  setStatus("Laeuft", hint);
}

function pauseGame() {
  if (!state.running) return;
  state.paused = !state.paused;
  setStatus(state.paused ? "Pause" : "Laeuft", state.paused ? "Leertaste zum Fortsetzen." : "Du gegen den Agenten.");
}

function resetGame() {
  state.playerScore = 0;
  state.aiScore = 0;
  playerScoreEl.textContent = "0";
  aiScoreEl.textContent = "0";
  state.player.y = H / 2 - paddle.h / 2;
  state.ai.y = H / 2 - paddle.h / 2;
  resetBall();
  setStatus("Bereit", "W/S oder Maus bewegen. Leertaste startet.");
}

document.getElementById("startBtn").addEventListener("click", startGame);
document.getElementById("pauseBtn").addEventListener("click", pauseGame);
document.getElementById("resetBtn").addEventListener("click", resetGame);

ollamaModeEl.addEventListener("change", () => {
  state.model.enabled = ollamaModeEl.checked;
  state.model.command = "stay";
  if (state.model.enabled) {
    setStatus("Ollama-Modus", "Das Sprachmodell entscheidet rechts langsamer, aber echt lokal.");
  } else {
    setStatus("Browser-KI aktiv", "Der rechte Schlaeger nutzt wieder schnelle Spiel-Logik.");
  }
});

window.addEventListener("keydown", (event) => {
  const key = event.key.toLowerCase();
  state.keys.add(key);
  if (key === " ") {
    event.preventDefault();
    state.running ? pauseGame() : startGame();
  }
});

window.addEventListener("keyup", (event) => {
  state.keys.delete(event.key.toLowerCase());
});

canvas.addEventListener("mousemove", (event) => {
  const rect = canvas.getBoundingClientRect();
  const scale = H / rect.height;
  state.player.y = clamp((event.clientY - rect.top) * scale - paddle.h / 2, 0, H - paddle.h);
});

resetGame();
requestAnimationFrame(loop);

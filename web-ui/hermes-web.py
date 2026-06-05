#!/usr/bin/env python3
"""
Hermes Web UI — lightweight aiohttp server with login + chat proxy.
Runs alongside the Hermes Agent gateway.
"""
import asyncio, os, json, hashlib, hmac, time, base64, html
from pathlib import Path

import aiohttp
from aiohttp import web

# ── Configuration ──────────────────────────────────────────────
WEB_PORT      = int(os.getenv("WEB_PORT", "8080"))
HERMES_API    = os.getenv("HERMES_API", "http://127.0.0.1:8642")
WEB_USERNAME  = os.getenv("WEB_USERNAME", "hanna")
WEB_PASSWORD  = os.getenv("WEB_PASSWORD", "hanna123")
SESSION_SECRET= os.getenv("SESSION_SECRET", "hermes-web-secret-change-me")

# ── Session helpers ────────────────────────────────────────────
def make_token(username: str) -> str:
    payload = f"{username}:{int(time.time()) + 86400}:{SESSION_SECRET}"
    return base64.urlsafe_b64encode(
        hashlib.sha256(payload.encode()).hexdigest().encode()
    ).decode()[:32]

def check_token(token: str) -> str | None:
    """Return username if token valid, else None."""
    # simplistic: token is just a hash of username+expiry
    # In production use proper JWT
    if not token or len(token) < 10:
        return None
    for u in [WEB_USERNAME]:
        expected = make_token(u)
        if hmac.compare_digest(token, expected):
            return u
    return None

# ── HTML Template (SPA) ────────────────────────────────────────
HTML = r"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Hanna — Assistente do Condomínio</title>
<style>
  :root {
    --bg: #0f172a; --card: #1e293b; --text: #e2e8f0;
    --muted: #94a3b8; --accent: #3b82f6; --accent-hover: #2563eb;
    --border: #334155; --success: #22c55e; --danger: #ef4444;
  }
  * { margin:0; padding:0; box-sizing:border-box; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: var(--bg); color: var(--text); min-height: 100vh;
  }
  .hidden { display: none !important; }

  /* Login */
  .login-page {
    display: flex; align-items: center; justify-content: center;
    min-height: 100vh; padding: 1rem;
  }
  .login-card {
    background: var(--card); border-radius: 1rem; padding: 2.5rem;
    width: 100%; max-width: 400px; border: 1px solid var(--border);
  }
  .login-card h1 { font-size: 1.5rem; margin-bottom: .25rem; }
  .login-card p { color: var(--muted); margin-bottom: 1.5rem; font-size: .9rem; }
  .login-card label { display: block; margin-bottom: .25rem; font-size: .85rem; color: var(--muted); }
  .login-card input {
    width: 100%; padding: .75rem; border-radius: .5rem; border: 1px solid var(--border);
    background: var(--bg); color: var(--text); margin-bottom: 1rem; font-size: .95rem;
  }
  .login-card input:focus { outline: none; border-color: var(--accent); }
  .login-card button {
    width: 100%; padding: .75rem; border-radius: .5rem; border: none;
    background: var(--accent); color: white; font-size: 1rem; font-weight: 600;
    cursor: pointer; transition: background .2s;
  }
  .login-card button:hover { background: var(--accent-hover); }
  .login-error { color: var(--danger); font-size: .85rem; margin-top: .5rem; }

  /* App layout */
  .app { display: flex; height: 100vh; }
  .sidebar {
    width: 260px; background: var(--card); border-right: 1px solid var(--border);
    display: flex; flex-direction: column; flex-shrink: 0;
  }
  .sidebar-header {
    padding: 1.25rem; border-bottom: 1px solid var(--border);
  }
  .sidebar-header h2 { font-size: 1.1rem; font-weight: 700; }
  .sidebar-header span { font-size: .75rem; color: var(--muted); }
  .sidebar-nav {
    flex: 1; padding: .5rem; overflow-y: auto;
  }
  .sidebar-nav a {
    display: flex; align-items: center; gap: .5rem;
    padding: .65rem .75rem; border-radius: .5rem; color: var(--text);
    text-decoration: none; font-size: .9rem; transition: background .2s; cursor: pointer;
  }
  .sidebar-nav a:hover, .sidebar-nav a.active { background: var(--bg); }
  .sidebar-nav a .icon { font-size: 1.1rem; width: 1.5rem; text-align: center; }
  .sidebar-footer {
    padding: .75rem 1rem; border-top: 1px solid var(--border); font-size: .8rem; color: var(--muted);
  }
  .sidebar-footer button {
    width: 100%; padding: .5rem; border-radius: .5rem; border: 1px solid var(--border);
    background: transparent; color: var(--danger); cursor: pointer; font-size: .85rem;
    margin-top: .5rem;
  }

  /* Main */
  .main { flex: 1; display: flex; flex-direction: column; min-width: 0; }

  /* Chat */
  .chat-container { flex: 1; display: flex; flex-direction: column; }
  .chat-messages { flex: 1; overflow-y: auto; padding: 1.5rem; }
  .message { margin-bottom: 1.25rem; display: flex; gap: .75rem; }
  .message.user { flex-direction: row-reverse; }
  .message .avatar {
    width: 32px; height: 32px; border-radius: 50%; display: flex;
    align-items: center; justify-content: center; font-size: .8rem;
    flex-shrink: 0; font-weight: 700;
  }
  .message.user .avatar { background: var(--accent); color: white; }
  .message.assistant .avatar { background: var(--success); color: white; }
  .message .bubble {
    max-width: 75%; padding: .75rem 1rem; border-radius: 1rem;
    line-height: 1.5; font-size: .9rem; white-space: pre-wrap; word-break: break-word;
  }
  .message.user .bubble {
    background: var(--accent); color: white;
    border-bottom-right-radius: .25rem;
  }
  .message.assistant .bubble {
    background: var(--card); border: 1px solid var(--border);
    border-bottom-left-radius: .25rem;
  }
  .message.assistant .bubble p { margin-bottom: .5rem; }
  .message.assistant .bubble p:last-child { margin-bottom: 0; }
  .message.assistant .bubble ul, .message.assistant .bubble ol { padding-left: 1.25rem; margin-bottom: .5rem; }
  .message.assistant .bubble code {
    background: var(--bg); padding: .15rem .4rem; border-radius: .25rem; font-size: .85em;
  }
  .message.assistant .bubble pre {
    background: var(--bg); padding: .75rem; border-radius: .5rem; overflow-x: auto;
    margin: .5rem 0; border: 1px solid var(--border);
  }
  .typing .bubble::after {
    content: '...'; animation: dots 1.5s steps(4) infinite;
  }
  @keyframes dots { 0%, 20% { content: '.'; } 40% { content: '..'; } 60%, 100% { content: '...'; } }

  /* Input */
  .chat-input-area {
    padding: 1rem 1.5rem; border-top: 1px solid var(--border);
  }
  .chat-input-wrap {
    display: flex; gap: .5rem; background: var(--card);
    border-radius: .75rem; padding: .5rem; border: 1px solid var(--border);
  }
  .chat-input-wrap textarea {
    flex: 1; background: transparent; border: none; color: var(--text);
    padding: .5rem; resize: none; font-size: .9rem; font-family: inherit;
    min-height: 24px; max-height: 120px;
  }
  .chat-input-wrap textarea:focus { outline: none; }
  .chat-input-wrap button {
    width: 40px; height: 40px; border-radius: .5rem; border: none;
    background: var(--accent); color: white; cursor: pointer;
    display: flex; align-items: center; justify-content: center;
    font-size: 1.2rem; flex-shrink: 0; transition: background .2s;
  }
  .chat-input-wrap button:hover { background: var(--accent-hover); }
  .chat-input-wrap button:disabled { opacity: .5; cursor: not-allowed; }

  /* Guide page */
  .guide-page { padding: 2rem; overflow-y: auto; max-width: 800px; }
  .guide-page h1 { font-size: 1.5rem; margin-bottom: 1rem; }
  .guide-page h2 { font-size: 1.2rem; margin: 1.5rem 0 .75rem; color: var(--accent); }
  .guide-page p { margin-bottom: .75rem; line-height: 1.6; }
  .guide-page code {
    background: var(--card); padding: .2rem .4rem; border-radius: .25rem; font-size: .9em;
    border: 1px solid var(--border);
  }
  .guide-page pre {
    background: var(--card); padding: 1rem; border-radius: .5rem; overflow-x: auto;
    margin: .75rem 0; border: 1px solid var(--border); font-size: .85rem;
  }
  .guide-page .step { margin-bottom: .5rem; padding: .75rem; background: var(--card); border-radius: .5rem; border-left: 3px solid var(--accent); }

  /* Responsive */
  @media (max-width: 768px) {
    .sidebar { display: none; }
    .sidebar.open { display: flex; position: fixed; inset: 0; z-index: 10; width: 100%; }
    .message .bubble { max-width: 90%; }
  }
</style>
</head>
<body>

<!-- Login -->
<div id="loginPage" class="login-page">
  <div class="login-card">
    <h1>🏰 Hanna</h1>
    <p>Assistente do Condomínio — Morador Online</p>
    <label for="username">Usuário</label>
    <input type="text" id="username" placeholder="hanna" autocomplete="username" />
    <label for="password">Senha</label>
    <input type="password" id="password" placeholder="••••••" autocomplete="current-password" />
    <button onclick="login()">Entrar</button>
    <div id="loginError" class="login-error hidden"></div>
  </div>
</div>

<!-- App -->
<div id="app" class="app hidden">
  <!-- Sidebar -->
  <div class="sidebar" id="sidebar">
    <div class="sidebar-header">
      <h2>🏰 Hanna</h2>
      <span>• Online</span>
    </div>
    <div class="sidebar-nav">
      <a class="active" onclick="showPage('chat')"><span class="icon">💬</span> Chat</a>
      <a onclick="showPage('guide')"><span class="icon">📖</span> Integrações</a>
      <a onclick="showPage('about')"><span class="icon">ℹ️</span> Sobre</a>
    </div>
    <div class="sidebar-footer">
      <div id="userDisplay">👤 hanna</div>
      <button onclick="logout()">Sair</button>
    </div>
  </div>

  <!-- Main -->
  <div class="main">
    <!-- Chat -->
    <div id="pageChat" class="chat-container">
      <div class="chat-messages" id="chatMessages">
        <div class="message assistant">
          <div class="avatar">H</div>
          <div class="bubble">Olá! Sou a Hanna, assistente do condomínio. Como posso ajudar?</div>
        </div>
      </div>
      <div class="chat-input-area">
        <div class="chat-input-wrap">
          <textarea id="chatInput" placeholder="Digite sua mensagem..." rows="1" onkeydown="if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();sendMsg()}"></textarea>
          <button id="sendBtn" onclick="sendMsg()">➤</button>
        </div>
      </div>
    </div>

    <!-- Guide -->
    <div id="pageGuide" class="guide-page hidden">
      <h1>📖 Integrações</h1>
      <p>Conecte a Hanna aos canais do seu condomínio.</p>

      <h2>🤖 Telegram</h2>
      <div class="step">1. Crie um bot no <a href="https://t.me/BotFather" target="_blank" style="color:var(--accent)">@BotFather</a> e obtenha o token</div>
      <div class="step">2. Configure no Hermes Agent:</div>
      <pre>TELEGRAM_BOT_TOKEN=seu_token_aqui</pre>
      <div class="step">3. Reinicie o gateway e converse com o bot</div>

      <h2>💬 Discord</h2>
      <div class="step">1. Crie um aplicativo em <a href="https://discord.com/developers/applications" target="_blank" style="color:var(--accent)">Discord Developer Portal</a></div>
      <div class="step">2. Gere um token de bot e adicione ao servidor</div>
      <div class="step">3. Configure:</div>
      <pre>DISCORD_BOT_TOKEN=seu_token_aqui</pre>

      <h2>📧 WhatsApp / SMS</h2>
      <div class="step">Consulte a documentação do Hermes Agent para gateways de messaging adicionais.</div>

      <h2>🔗 API OpenAI-compatível</h2>
      <p>Use qualquer cliente OpenAI (Open WebUI, Cursor, etc.) apontando para:</p>
      <pre>Endpoint: https://hermes-agent-hermes.apps.cluster1.sandbox1992.opentlc.com/v1
API Key: seu_token_api_server</pre>
    </div>

    <!-- About -->
    <div id="pageAbout" class="guide-page hidden">
      <h1>ℹ️ Sobre a Hanna</h1>
      <p><strong>Hanna</strong> é a assistente inteligente do <strong>Morador Online</strong>, o sistema de gestão condominial.</p>
      <br/>
      <h2>🔧 Stack</h2>
      <ul>
        <li><strong>Backend:</strong> Hermes Agent + DeepSeek (via API OpenAI-compatível)</li>
        <li><strong>Infra:</strong> OpenShift (Red Hat)</li>
        <li><strong>Modelo:</strong> DeepSeek V4 Flash</li>
      </ul>
      <br/>
      <h2>📋 Funcionalidades</h2>
      <ul>
        <li>💬 Chat interativo com IA</li>
        <li>🔌 Integrações com Telegram, Discord e WhatsApp</li>
        <li>🔐 API OpenAI-compatível para ferramentas externas</li>
      </ul>
    </div>
  </div>
</div>

<script>
const API_BASE = '';
let token = localStorage.getItem('hermes_token');

function showError(msg) {
  const el = document.getElementById('loginError');
  el.textContent = msg; el.classList.remove('hidden');
}

async function login() {
  const user = document.getElementById('username').value.trim();
  const pass = document.getElementById('password').value;
  if (!user || !pass) { showError('Preencha usuário e senha'); return; }
  document.querySelector('.login-card button').disabled = true;
  try {
    const r = await fetch('/api/login', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({username: user, password: pass})
    });
    const data = await r.json();
    if (r.ok) {
      token = data.token;
      localStorage.setItem('hermes_token', token);
      document.getElementById('loginPage').classList.add('hidden');
      document.getElementById('app').classList.remove('hidden');
      document.getElementById('userDisplay').textContent = '👤 ' + user;
    } else {
      showError(data.error || 'Login inválido');
    }
  } catch(e) {
    showError('Erro de conexão: ' + e.message);
  }
  document.querySelector('.login-card button').disabled = false;
}

function logout() {
  token = null; localStorage.removeItem('hermes_token');
  document.getElementById('app').classList.add('hidden');
  document.getElementById('loginPage').classList.remove('hidden');
  document.getElementById('username').value = '';
  document.getElementById('password').value = '';
  document.getElementById('loginError').classList.add('hidden');
}

async function checkAuth() {
  if (!token) return false;
  try {
    const r = await fetch('/api/check', {
      headers: {'Authorization': 'Bearer ' + token}
    });
    return r.ok;
  } catch { return false; }
}

function showPage(name) {
  document.querySelectorAll('.main > div').forEach(d => d.classList.add('hidden'));
  document.getElementById('page' + name.charAt(0).toUpperCase() + name.slice(1)).classList.remove('hidden');
  document.querySelectorAll('.sidebar-nav a').forEach(a => a.classList.remove('active'));
  document.querySelectorAll('.sidebar-nav a').forEach(a => {
    if (a.textContent.trim().toLowerCase().includes(name)) a.classList.add('active');
  });
  if (name === 'chat') {
    document.getElementById('chatInput').focus();
    scrollChat();
  }
}

async function sendMsg() {
  const input = document.getElementById('chatInput');
  const text = input.value.trim();
  if (!text) return;
  input.value = '';
  document.getElementById('sendBtn').disabled = true;

  // Add user message
  addMsg('user', text);
  scrollChat();

  // Typing indicator
  const typingId = addMsg('assistant', '', true);

  try {
    const r = await fetch('/api/chat', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer ' + token
      },
      body: JSON.stringify({message: text})
    });

    if (!r.ok) {
      const err = await r.json().catch(() => ({}));
      removeMsg(typingId);
      addMsg('assistant', '❌ Erro: ' + (err.error || r.statusText));
      scrollChat();
      document.getElementById('sendBtn').disabled = false;
      return;
    }

    const data = await r.json();
    removeMsg(typingId);
    const reply = data.choices?.[0]?.message?.content || '(sem resposta)';
    addMsg('assistant', reply);
  } catch(e) {
    removeMsg(typingId);
    addMsg('assistant', '❌ Erro de conexão: ' + e.message);
  }
  scrollChat();
  document.getElementById('sendBtn').disabled = false;
}

function addMsg(role, text, typing = false) {
  const container = document.getElementById('chatMessages');
  const div = document.createElement('div');
  div.className = 'message ' + role + (typing ? ' typing' : '');
  div.innerHTML = '<div class="avatar">' + (role === 'user' ? 'U' : 'H') + '</div>' +
    '<div class="bubble">' + (typing ? '' : formatText(text)) + '</div>';
  container.appendChild(div);
  return div;
}

function removeMsg(el) {
  if (el && el.parentNode) el.parentNode.removeChild(el);
}

function formatText(text) {
  return text.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
    .replace(/\n/g, '<br>');
}

function scrollChat() {
  const el = document.getElementById('chatMessages');
  setTimeout(() => el.scrollTop = el.scrollHeight, 50);
}

// Auto-login check
(async () => {
  if (token && await checkAuth()) {
    document.getElementById('loginPage').classList.add('hidden');
    document.getElementById('app').classList.remove('hidden');
    document.getElementById('chatInput').focus();
  }
})();
</script>
</body>
</html>
"""

# ── Web App ────────────────────────────────────────────────────
async def handle_index(request):
    return web.Response(text=HTML, content_type="text/html")

async def handle_login(request):
    try:
        body = await request.json()
        u = body.get("username", "").strip()
        p = body.get("password", "").strip()
        if hmac.compare_digest(u, WEB_USERNAME) and hmac.compare_digest(p, WEB_PASSWORD):
            tok = make_token(u)
            return web.json_response({"token": tok, "user": u})
        return web.json_response({"error": "Usuário ou senha inválidos"}, status=401)
    except Exception:
        return web.json_response({"error": "Requisição inválida"}, status=400)

async def handle_check(request):
    auth = request.headers.get("Authorization", "")
    tok = auth.replace("Bearer ", "") if auth.startswith("Bearer ") else ""
    if check_token(tok):
        return web.json_response({"ok": True})
    return web.json_response({"ok": False}, status=401)

async def handle_chat(request):
    auth = request.headers.get("Authorization", "")
    tok = auth.replace("Bearer ", "") if auth.startswith("Bearer ") else ""
    if not check_token(tok):
        return web.json_response({"error": "Não autorizado"}, status=401)
    try:
        body = await request.json()
        msg = body.get("message", "").strip()
        if not msg:
            return web.json_response({"error": "Mensagem vazia"}, status=400)

        # Build chat history from request or use simple conversation
        messages = body.get("messages") or [{"role": "user", "content": msg}]

        # Forward to Hermes Agent API
        async with aiohttp.ClientSession() as session:
            payload = {
                "model": "deepseek-chat",
                "messages": messages
            }
            async with session.post(
                f"{HERMES_API}/v1/chat/completions",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=120)
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return web.json_response(data)
                else:
                    err_text = await resp.text()
                    return web.json_response(
                        {"error": f"Hermes API error: {resp.status} - {err_text}"},
                        status=502
                    )
    except asyncio.TimeoutError:
        return web.json_response({"error": "Timeout ao conectar com Hermes"}, status=504)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

async def handle_guide(request):
    return web.json_response({
        "telegram": "Crie um bot no @BotFather e configure TELEGRAM_BOT_TOKEN",
        "discord": "Crie um app no Discord Developer Portal e configure DISCORD_BOT_TOKEN",
        "api": f"Endpoint: {HERMES_API}/v1\nUse sua API_SERVER_KEY como Bearer token"
    })

# ── Startup ────────────────────────────────────────────────────
async def main():
    app = web.Application()
    app.router.add_get("/", handle_index)
    app.router.add_post("/api/login", handle_login)
    app.router.add_get("/api/check", handle_check)
    app.router.add_post("/api/chat", handle_chat)
    app.router.add_get("/api/guide", handle_guide)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", WEB_PORT)
    await site.start()
    print(f"[Hermes Web] UI rodando em http://0.0.0.0:{WEB_PORT}")
    # Keep running
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())

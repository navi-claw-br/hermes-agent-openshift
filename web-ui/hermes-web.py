#!/usr/bin/env python3
"""
Agente Administrativo — Web UI com autenticação via MCP do condomínio.
Proxy de chat para o Hermes Agent.
"""
import asyncio, os, json, hashlib, hmac, time, base64, hmac
import aiohttp
from aiohttp import web

# ── Configuração ──────────────────────────────────────────────
WEB_PORT      = int(os.getenv("WEB_PORT", "8080"))
HERMES_API    = os.getenv("HERMES_API", "http://127.0.0.1:8642")
CONDOMINIO    = os.getenv("CONDOMINIO", "").strip().rstrip("/")
MCP_ADMIN_URL = os.getenv("MCP_ADMIN_URL", "https://mcp-server-mo-admin.mo.app.br/mcp")
SESSION_SECRET= os.getenv("SESSION_SECRET", "agente-admin-secret")

# ── Session helpers ────────────────────────────────────────────
def make_token(data: dict) -> str:
    """Gera token HMAC com payload JSON."""
    raw = json.dumps(data, sort_keys=True, separators=(",", ":"))
    sig = hmac.new(SESSION_SECRET.encode(), raw.encode(), hashlib.sha256).hexdigest()[:24]
    token = base64.urlsafe_b64encode(f"{raw}|{sig}".encode()).decode()
    return token[:64]

def check_token(token: str) -> dict | None:
    """Retorna payload se token válido, None caso contrário."""
    if not token or len(token) < 10:
        return None
    try:
        decoded = base64.urlsafe_b64decode(token + "==").decode()
        raw, sig = decoded.rsplit("|", 1)
        expected = hmac.new(SESSION_SECRET.encode(), raw.encode(), hashlib.sha256).hexdigest()[:24]
        if hmac.compare_digest(sig, expected):
            return json.loads(raw)
    except Exception:
        pass
    return None

# ── MCP Client ────────────────────────────────────────────────
async def mcp_call(method: str, params: dict = None, token: str = None) -> dict:
    """Chama o MCP server admin via JSON-RPC."""
    headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    payload = {
        "jsonrpc": "2.0",
        "id": int(time.time()),
        "method": method,
        "params": params or {}
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(
            MCP_ADMIN_URL, json=payload, headers=headers,
            timeout=aiohttp.ClientTimeout(total=30)
        ) as resp:
            text = await resp.text()
            # Handle SSE responses (tools/call returns text/event-stream)
            if "event:" in text or "data:" in text:
                import re
                # Extract last data: line
                data_matches = re.findall(r'^data: (.+)$', text, re.MULTILINE)
                if data_matches:
                    return json.loads(data_matches[-1])
            # Fallback: try direct JSON
            try:
                return json.loads(text)
            except (json.JSONDecodeError, ValueError):
                return {"error": f"Resposta inesperada: {text[:200]}"}

# ── HTML Template ──────────────────────────────────────────────
HTML = r"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Agente Administrativo</title>
<style>
  :root{--bg:#0f172a;--card:#1e293b;--text:#e2e8f0;--muted:#94a3b8;--accent:#3b82f6;--accent-hover:#2563eb;--border:#334155;--success:#22c55e;--danger:#ef4444}
  *{margin:0;padding:0;box-sizing:border-box}
  body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:var(--bg);color:var(--text);min-height:100vh}
  .hidden{display:none!important}
  .login-page{display:flex;align-items:center;justify-content:center;min-height:100vh;padding:1rem}
  .login-card{background:var(--card);border-radius:1rem;padding:2.5rem;width:100%;max-width:420px;border:1px solid var(--border)}
  .login-card h1{font-size:1.5rem;margin-bottom:.25rem}
  .login-card .subtitle{color:var(--muted);margin-bottom:1.5rem;font-size:.85rem;line-height:1.4}
  .login-card label{display:block;margin-bottom:.25rem;font-size:.85rem;color:var(--muted)}
  .login-card input{width:100%;padding:.75rem;border-radius:.5rem;border:1px solid var(--border);background:var(--bg);color:var(--text);margin-bottom:.75rem;font-size:.95rem}
  .login-card input:focus{outline:none;border-color:var(--accent)}
  .login-card button{width:100%;padding:.75rem;border-radius:.5rem;border:none;background:var(--accent);color:#fff;font-size:1rem;font-weight:600;cursor:pointer;transition:background .2s}
  .login-card button:hover{background:var(--accent-hover)}
  .login-card button:disabled{opacity:.6;cursor:not-allowed}
  .login-error{color:var(--danger);font-size:.85rem;margin-top:.5rem}
  .login-info{color:var(--muted);font-size:.8rem;margin-top:1rem;text-align:center;border-top:1px solid var(--border);padding-top:1rem}
  .app{display:flex;height:100vh}
  .sidebar{width:260px;background:var(--card);border-right:1px solid var(--border);display:flex;flex-direction:column;flex-shrink:0}
  .sidebar-header{padding:1.25rem;border-bottom:1px solid var(--border)}
  .sidebar-header h2{font-size:1.1rem;font-weight:700}
  .sidebar-header .status{font-size:.75rem;color:var(--muted);display:flex;align-items:center;gap:.35rem}
  .sidebar-header .status .dot{width:6px;height:6px;border-radius:50%;background:var(--success);display:inline-block}
  .sidebar-nav{flex:1;padding:.5rem;overflow-y:auto}
  .sidebar-nav a{display:flex;align-items:center;gap:.5rem;padding:.65rem .75rem;border-radius:.5rem;color:var(--text);text-decoration:none;font-size:.9rem;cursor:pointer;transition:background .2s}
  .sidebar-nav a:hover,.sidebar-nav a.active{background:var(--bg)}
  .sidebar-nav a .icon{font-size:1.1rem;width:1.5rem;text-align:center}
  .sidebar-footer{padding:.75rem 1rem;border-top:1px solid var(--border);font-size:.8rem;color:var(--muted)}
  .sidebar-footer button{width:100%;padding:.5rem;border-radius:.5rem;border:1px solid var(--border);background:transparent;color:var(--danger);cursor:pointer;font-size:.85rem;margin-top:.5rem}
  .main{flex:1;display:flex;flex-direction:column;min-width:0}
  .chat-container{flex:1;display:flex;flex-direction:column}
  .chat-messages{flex:1;overflow-y:auto;padding:1.5rem}
  .message{margin-bottom:1.25rem;display:flex;gap:.75rem}
  .message.user{flex-direction:row-reverse}
  .message .avatar{width:32px;height:32px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:.8rem;flex-shrink:0;font-weight:700}
  .message.user .avatar{background:var(--accent);color:#fff}
  .message.assistant .avatar{background:var(--success);color:#fff}
  .message .bubble{max-width:75%;padding:.75rem 1rem;border-radius:1rem;line-height:1.5;font-size:.9rem;white-space:pre-wrap;word-break:break-word}
  .message.user .bubble{background:var(--accent);color:#fff;border-bottom-right-radius:.25rem}
  .message.assistant .bubble{background:var(--card);border:1px solid var(--border);border-bottom-left-radius:.25rem}
  .chat-input-area{padding:1rem 1.5rem;border-top:1px solid var(--border)}
  .chat-input-wrap{display:flex;gap:.5rem;background:var(--card);border-radius:.75rem;padding:.5rem;border:1px solid var(--border)}
  .chat-input-wrap textarea{flex:1;background:transparent;border:none;color:var(--text);padding:.5rem;resize:none;font-size:.9rem;font-family:inherit;min-height:24px;max-height:120px}
  .chat-input-wrap textarea:focus{outline:none}
  .chat-input-wrap button{width:40px;height:40px;border-radius:.5rem;border:none;background:var(--accent);color:#fff;cursor:pointer;display:flex;align-items:center;justify-content:center;font-size:1.2rem;flex-shrink:0}
  .chat-input-wrap button:disabled{opacity:.5;cursor:not-allowed}
  .guide-page{padding:2rem;overflow-y:auto;max-width:800px}
  .guide-page h1{font-size:1.5rem;margin-bottom:1rem}
  .guide-page h2{font-size:1.2rem;margin:1.5rem 0 .75rem;color:var(--accent)}
  .guide-page p{margin-bottom:.75rem;line-height:1.6}
  .guide-page code{background:var(--card);padding:.2rem .4rem;border-radius:.25rem;font-size:.9em;border:1px solid var(--border)}
  .guide-page pre{background:var(--card);padding:1rem;border-radius:.5rem;overflow-x:auto;margin:.75rem 0;border:1px solid var(--border);font-size:.85rem}
  .guide-page .step{margin-bottom:.5rem;padding:.75rem;background:var(--card);border-radius:.5rem;border-left:3px solid var(--accent)}
  .guide-page .badge{display:inline-block;padding:.15rem .5rem;border-radius:1rem;font-size:.75rem;font-weight:600;margin-left:.5rem}
  .guide-page .badge.ok{background:var(--success);color:#fff}
  .guide-page .badge.wait{background:#a855f7;color:#fff}
  .guide-page .mcp-list{margin:.75rem 0;padding:0;list-style:none}
  .guide-page .mcp-list li{padding:.5rem .75rem;margin-bottom:.25rem;background:var(--card);border-radius:.5rem;font-size:.85rem;display:flex;align-items:center;gap:.5rem}
  .guide-page .mcp-list li::before{content:'🔌';font-size:.85rem}
  @media(max-width:768px){.sidebar{display:none}.sidebar.open{display:flex;position:fixed;inset:0;z-index:10;width:100%}.message .bubble{max-width:90%}}
</style>
</head>
<body>

<!-- Login -->
<div id="loginPage" class="login-page">
  <div class="login-card">
    <h1>🏢 Agente Administrativo</h1>
    <p class="subtitle">Acesso ao sistema de gestão condominial</p>
    <label for="username">Usuário (login do condomínio)</label>
    <input type="text" id="username" placeholder="seu login" autocomplete="username" />
    <label for="password">Senha</label>
    <input type="password" id="password" placeholder="sua senha" autocomplete="current-password" />
    <button id="loginBtn" onclick="login()">Entrar</button>
    <div id="loginError" class="login-error hidden"></div>
    <div id="loginInfo" class="login-info hidden"></div>
  </div>
</div>

<!-- App -->
<div id="app" class="app hidden">
  <div class="sidebar" id="sidebar">
    <div class="sidebar-header">
      <h2>🏢 Agente Administrativo</h2>
      <div class="status"><span class="dot"></span> Online</div>
    </div>
    <div class="sidebar-nav">
      <a class="active" onclick="showPage('chat')"><span class="icon">💬</span> Assistente</a>
      <a onclick="showPage('guide')"><span class="icon">📖</span> Integrações</a>
      <a onclick="showPage('mcp')"><span class="icon">🔌</span> MCP Tools</a>
      <a onclick="showPage('about')"><span class="icon">ℹ️</span> Sobre</a>
    </div>
    <div class="sidebar-footer">
      <div id="userDisplay">👤 </div>
      <div id="condDisplay" style="font-size:.7rem;color:var(--muted);margin-top:.25rem"></div>
      <button onclick="logout()">Sair</button>
    </div>
  </div>

  <div class="main">
    <!-- Chat -->
    <div id="pageChat" class="chat-container">
      <div class="chat-messages" id="chatMessages">
        <div class="message assistant">
          <div class="avatar">A</div>
          <div class="bubble">Olá! Sou o Agente Administrativo. Estou conectado ao sistema de gestão condominial. Como posso ajudar?</div>
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
      <p>Conecte o Agente Administrativo aos canais do condomínio.</p>

      <h2>🤖 Telegram</h2>
      <div class="step">1. Crie um bot no <a href="https://t.me/BotFather" target="_blank" style="color:var(--accent)">@BotFather</a> e obtenha o token</div>
      <div class="step">2. Configure a env var <code>TELEGRAM_BOT_TOKEN</code></div>
      <div class="step">3. Reinicie o deployment</div>

      <h2>💬 Discord</h2>
      <div class="step">1. Crie um app no <a href="https://discord.com/developers/applications" target="_blank" style="color:var(--accent)">Discord Developer Portal</a></div>
      <div class="step">2. Gere um token de bot e adicione ao servidor</div>
      <div class="step">3. Configure a env var <code>DISCORD_BOT_TOKEN</code></div>

      <h2>🔗 API OpenAI-compatível</h2>
      <p>Use qualquer cliente OpenAI apontando para:</p>
      <pre>Endpoint: /v1
API Key: sua API_SERVER_KEY</pre>
    </div>

    <!-- MCP Tools -->
    <div id="pageMcp" class="guide-page hidden">
      <h1>🔌 MCP Tools Disponíveis</h1>
      <p>O agente está conectado ao MCP Server Admin do Morador Online.</p>
      <p>As seguintes ferramentas estão disponíveis para consulta:</p>
      <ul class="mcp-list" id="mcpToolsList">
        <li>Carregando...</li>
      </ul>
      <p style="margin-top:1rem;font-size:.85rem;color:var(--muted)">O agente pode usar essas ferramentas para responder perguntas sobre o condomínio automaticamente.</p>
    </div>

    <!-- About -->
    <div id="pageAbout" class="guide-page hidden">
      <h1>ℹ️ Sobre</h1>
      <p><strong>Agente Administrativo</strong> — assistente inteligente para gestão condominial.</p>
      <h2>🔧 Stack</h2>
      <ul>
        <li><strong>Backend:</strong> Hermes Agent + DeepSeek</li>
        <li><strong>MCP:</strong> Morador Online Admin</li>
        <li><strong>Infra:</strong> OpenShift</li>
      </ul>
      <h2>🔐 Autenticação</h2>
      <p>Login realizado via <strong>MCP autenticar</strong> do sistema de condomínio.</p>
      <p>O token de acesso é armazenado na sessão e usado nas chamadas ao MCP.</p>
    </div>
  </div>
</div>

<script>
const API_BASE='';let token=localStorage.getItem('agente_token');let loginData=null;

async function login(){
  const u=document.getElementById('username').value.trim();
  const p=document.getElementById('password').value;
  const btn=document.getElementById('loginBtn');
  if(!u||!p){
    const el=document.getElementById('loginError');
    el.textContent='Preencha usuário e senha';el.classList.remove('hidden');
    return;
  }
  btn.disabled=true;btn.textContent='Autenticando...';
  document.getElementById('loginError').classList.add('hidden');
  document.getElementById('loginInfo').classList.add('hidden');
  try{
    const r=await fetch('/api/login',{
      method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({username:u,password:p})
    });
    const d=await r.json();
    if(r.ok){
      token=d.token;loginData=d;
      localStorage.setItem('agente_token',token);
      document.getElementById('loginPage').classList.add('hidden');
      document.getElementById('app').classList.remove('hidden');
      document.getElementById('userDisplay').textContent='👤 '+u;
      const cond=document.getElementById('condDisplay');
      if(d.condominio) cond.textContent='🏢 '+d.condominio;
    }else{
      const el=document.getElementById('loginError');
      el.textContent=d.error||'Falha na autenticação';el.classList.remove('hidden');
    }
  }catch(e){
    const el=document.getElementById('loginError');
    el.textContent='Erro de conexão: '+e.message;el.classList.remove('hidden');
  }
  btn.disabled=false;btn.textContent='Entrar';
}

function logout(){
  token=null;loginData=null;
  localStorage.removeItem('agente_token');
  document.getElementById('app').classList.add('hidden');
  document.getElementById('loginPage').classList.remove('hidden');
  document.getElementById('loginError').classList.add('hidden');
  document.getElementById('username').value='';
  document.getElementById('password').value='';
}

async function checkAuth(){
  if(!token)return false;
  try{
    const r=await fetch('/api/check',{headers:{'Authorization':'Bearer '+token}});
    return r.ok;
  }catch{return false}
}

function showPage(n){
  document.querySelectorAll('.main>div').forEach(d=>d.classList.add('hidden'));
  const id='page'+n.charAt(0).toUpperCase()+n.slice(1);
  const el=document.getElementById(id);
  if(el)el.classList.remove('hidden');
  document.querySelectorAll('.sidebar-nav a').forEach(a=>a.classList.remove('active'));
  document.querySelectorAll('.sidebar-nav a').forEach(a=>{
    if(a.textContent.trim().toLowerCase().includes(n))a.classList.add('active');
  });
  if(n==='chat')setTimeout(()=>document.getElementById('chatInput')?.focus(),100);
  if(n==='mcp')loadMcpTools();
}

async function loadMcpTools(){
  const list=document.getElementById('mcpToolsList');
  if(!list)return;
  list.innerHTML='<li>Carregando...</li>';
  try{
    const r=await fetch('/api/mcp/tools',{headers:{'Authorization':'Bearer '+token}});
    if(r.ok){
      const d=await r.json();
      const tools=d.tools||d.result||[];
      if(tools.length){
        list.innerHTML='';
        tools.forEach(t=>{
          const li=document.createElement('li');
          li.textContent=t.name+(t.description?' — '+t.description:'');
          list.appendChild(li);
        });
      }else{
        list.innerHTML='<li>Nenhuma ferramenta disponível</li>';
      }
    }else{
      list.innerHTML='<li>Erro ao carregar ferramentas</li>';
    }
  }catch(e){
    list.innerHTML='<li>Erro: '+e.message+'</li>';
  }
}

async function sendMsg(){
  const inp=document.getElementById('chatInput'),txt=inp.value.trim();
  if(!txt)return;
  inp.value='';
  document.getElementById('sendBtn').disabled=true;
  const c=document.getElementById('chatMessages');
  const um=document.createElement('div');um.className='message user';
  um.innerHTML='<div class="avatar">U</div><div class="bubble">'+txt.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')+'</div>';
  c.appendChild(um);
  const tm=document.createElement('div');tm.className='message assistant typing';
  tm.innerHTML='<div class="avatar">A</div><div class="bubble"></div>';
  c.appendChild(tm);
  c.scrollTop=c.scrollHeight;
  try{
    const r=await fetch('/api/chat',{
      method:'POST',headers:{'Content-Type':'application/json','Authorization':'Bearer '+token},
      body:JSON.stringify({message:txt})
    });
    tm.remove();
    let content='';
    if(r.ok){
      const d=await r.json();
      content=d.choices?.[0]?.message?.content||'(sem resposta)';
    }else{
      const e=await r.json().catch(()=>({}));
      content='❌ '+(e.error||'Erro '+r.status);
    }
    const fm=document.createElement('div');fm.className='message assistant';
    fm.innerHTML='<div class="avatar">A</div><div class="bubble">'+content.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/\n/g,'<br>')+'</div>';
    c.appendChild(fm);
  }catch(e){
    tm.remove();
    const fm=document.createElement('div');fm.className='message assistant';
    fm.innerHTML='<div class="avatar">A</div><div class="bubble">Erro de conexão: '+e.message+'</div>';
    c.appendChild(fm);
  }
  c.scrollTop=c.scrollHeight;
  document.getElementById('sendBtn').disabled=false;
}

(async()=>{
  if(token&&await checkAuth()){
    const d=loginData||JSON.parse(atob(token.split('.')[0]||e��'))||{};
    document.getElementById('loginPage').classList.add('hidden');
    document.getElementById('app').classList.remove('hidden');
    document.getElementById('userDisplay').textContent='👤 '+(d.user||'');
    if(d.condominio) document.getElementById('condDisplay').textContent='🏢 '+d.condominio;
  }
})();
</script>
</body>
</html>
"""

# ── Handlers ───────────────────────────────────────────────────
async def handle_index(request):
    return web.Response(text=HTML, content_type="text/html")

async def handle_login(request):
    """Autentica via MCP autenticar do condomínio."""
    try:
        body = await request.json()
        u = body.get("username", "").strip()
        p = body.get("password", "").strip()
        if not u or not p:
            return web.json_response({"error": "Usuário e senha obrigatórios"}, status=400)

        if not CONDOMINIO:
            return web.json_response(
                {"error": "CONDOMINIO não configurado — defina a URL do condomínio nas variáveis de ambiente"},
                status=500
            )

        # Chama MCP autenticar
        result = await mcp_call("tools/call", {
            "name": "autenticar",
            "arguments": {
                "login": u,
                "senha": p,
                "url": CONDOMINIO
            }
        })

        # Resultado MCP pode vir em result.content ou result
        mcp_result = result.get("result", {}) or result
        content = mcp_result.get("content", [])
        mcp_token = ""

        if content and isinstance(content, list):
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    mcp_token = item.get("text", "")
        elif isinstance(content, str):
            mcp_token = content
        elif isinstance(mcp_result, dict) and mcp_result.get("token"):
            mcp_token = mcp_result["token"]

        if mcp_token:
            session_data = {
                "user": u,
                "condominio": CONDOMINIO,
                "token": mcp_token,
                "iat": int(time.time())
            }
            tok = make_token(session_data)
            return web.json_response({"token": tok, "user": u, "condominio": CONDOMINIO})
        else:
            return web.json_response(
                {"error": "Usuário ou senha inválidos — verifique suas credenciais de administrador"},
                status=401
            )
    except asyncio.TimeoutError:
        return web.json_response({"error": "MCP server não respondeu (timeout)"}, status=504)
    except Exception as e:
        return web.json_response({"error": f"Erro ao autenticar: {str(e)}"}, status=500)

async def handle_check(request):
    auth = request.headers.get("Authorization", "")
    tok = auth.replace("Bearer ", "") if auth.startswith("Bearer ") else ""
    data = check_token(tok)
    if data:
        return web.json_response({"ok": True, "user": data.get("user")})
    return web.json_response({"ok": False}, status=401)

async def handle_mcp_tools(request):
    """Lista ferramentas disponíveis no MCP server admin."""
    auth = request.headers.get("Authorization", "")
    tok = auth.replace("Bearer ", "") if auth.startswith("Bearer ") else ""
    if not check_token(tok):
        return web.json_response({"error": "Não autorizado"}, status=401)

    try:
        result = await mcp_call("tools/list")
        return web.json_response(result)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=502)

async def handle_chat(request):
    """Proxy de chat para o Hermes Agent."""
    auth = request.headers.get("Authorization", "")
    tok = auth.replace("Bearer ", "") if auth.startswith("Bearer ") else ""
    session = check_token(tok)
    if not session:
        return web.json_response({"error": "Não autorizado"}, status=401)

    try:
        body = await request.json()
        msg = body.get("message", "").strip()
        if not msg:
            return web.json_response({"error": "Mensagem vazia"}, status=400)

        msgs = body.get("messages") or [{"role": "user", "content": msg}]

        api_key = os.getenv("API_SERVER_KEY", "")
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{HERMES_API}/v1/chat/completions",
                json={"model": "deepseek-chat", "messages": msgs},
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=120)
            ) as resp:
                if resp.status == 200:
                    return web.json_response(await resp.json())
                err = await resp.text()
                return web.json_response({"error": f"Hermes API error: {resp.status}"}, status=502)
    except asyncio.TimeoutError:
        return web.json_response({"error": "Timeout ao conectar com Hermes"}, status=504)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

# ── Startup ────────────────────────────────────────────────────
async def main():
    app = web.Application()
    app.router.add_get("/", handle_index)
    app.router.add_post("/api/login", handle_login)
    app.router.add_get("/api/check", handle_check)
    app.router.add_get("/api/mcp/tools", handle_mcp_tools)
    app.router.add_post("/api/chat", handle_chat)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", WEB_PORT)
    await site.start()
    print(f"[Web] Agente Administrativo rodando em http://0.0.0.0:{WEB_PORT}")
    print(f"[Web] MCP Admin: {MCP_ADMIN_URL}")
    print(f"[Web] Condomínio: {CONDOMINIO or 'NÃO CONFIGURADO'}")
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())

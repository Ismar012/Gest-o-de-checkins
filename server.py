"""Servidor piloto do painel de check-ins da unidade."""
import hashlib
import hmac
import json
import os
import sqlite3
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from flask import Flask, abort, request, send_from_directory

app = Flask(__name__, static_folder=None)
app.config["MAX_CONTENT_LENGTH"] = 256 * 1024
ROOT = Path(__file__).resolve().parent
ICONS = {"raio": "⚡", "tubarao": "🦈", "bola": "🏐", "onda": "🌊", "sol": "☀️"}
COLORS = {"oceano": "#36b1e8", "sol": "#ffd264", "areia": "#f2bd8c", "verde": "#80ecb1", "violeta": "#cdb4ff"}
LABELS = {
    "waiting": "Aguardando validação",
    "released": "Liberado para a aula",
    "review": "Revisar",
    "rejected": "Não validado",
}


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def instant(value):
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("O horário deve incluir fuso")
    return parsed.astimezone(timezone.utc)


def database():
    db = sqlite3.connect(os.environ.get("PRESIQ_DB", str(ROOT / "checkins.sqlite3")), timeout=10)
    db.execute("""CREATE TABLE IF NOT EXISTS checkins (
        reference TEXT PRIMARY KEY, booking TEXT, state TEXT NOT NULL,
        reason TEXT NOT NULL, timestamp TEXT NOT NULL
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS school (
        singleton INTEGER PRIMARY KEY CHECK(singleton = 1),
        name TEXT NOT NULL, unit TEXT NOT NULL, color TEXT NOT NULL, icon TEXT NOT NULL
    )""")
    db.commit()
    return db


def roster():
    path = os.environ.get("PRESIQ_ROSTER", str(ROOT / "turmas.json"))
    return json.loads(Path(path).read_text(encoding="utf-8"))


def validate_at_totalpass(endpoint):
    opener = build_opener(NoRedirect())
    try:
        with opener.open(Request(endpoint, method="POST"), timeout=5) as result:
            return result.status
    except HTTPError as error:
        return error.code


def endpoint_allowed(endpoint):
    url = urlsplit(endpoint)
    allowed = os.environ.get("TOTALPASS_HOSTS", "gym-service-api.totalpass.com").split(",")
    prefixes = ("/webhook_confirmations/", "/api/v1/webhook_confirmations/")
    return (
        url.scheme == "https" and url.netloc in allowed and not url.query
        and not url.fragment and any(
            url.path.startswith(prefix) and "/" not in url.path[len(prefix):]
            and bool(url.path[len(prefix):]) for prefix in prefixes
        )
    )


def process(payload, confirm, now=None):
    now = now or datetime.now(timezone.utc)
    endpoint = payload["endpoint"]
    if payload["type"] != "CHECK_IN_CREATED" or not endpoint_allowed(endpoint):
        raise ValueError("Evento inválido")
    provider_code = payload["user"]["code"]
    unit = payload["place"]["place"]
    start = instant(payload["check_in"]["started_at"])
    expires = instant(payload["check_in"]["expires_at"])
    if not isinstance(provider_code, str) or not provider_code or expires <= start:
        raise ValueError("Dados inválidos")
    reference = hashlib.sha256(urlsplit(endpoint).path.rsplit("/", 1)[-1].encode()).hexdigest()
    data = roster()
    if unit != data["unidade"]:
        raise ValueError("Unidade inválida")
    matches = [
        booking for booking in data["reservas"]
        if booking["totalpass"] == provider_code
        and instant(booking["inicio_checkin"]) <= start <= instant(booking["fim_checkin"])
        and now <= instant(booking["fim_checkin"])
    ]
    booking = matches[0]["id"] if len(matches) == 1 else None
    db = database()
    try:
        with db:
            db.execute("BEGIN IMMEDIATE")
            found = db.execute("SELECT state FROM checkins WHERE reference=?", (reference,)).fetchone()
            if found:
                return found[0]
            if now >= expires:
                state, reason = "rejected", "Check-in expirado"
            elif not booking:
                state, reason = "review", "Vínculo ou reserva sem correspondência única"
            elif db.execute("SELECT 1 FROM checkins WHERE booking=? AND state IN ('waiting','released')", (booking,)).fetchone():
                state, reason = "review", "Já existe uma validação para esta reserva"
            else:
                state, reason = "waiting", "Confirmação em andamento"
            db.execute("INSERT INTO checkins VALUES (?,?,?,?,?)",
                       (reference, booking, state, reason, now.isoformat()))
        if state == "waiting":
            try:
                status = confirm(endpoint)
                if status == 200:
                    state, reason = "released", "Confirmação oficial recebida"
                elif status == 404:
                    state, reason = "rejected", "Check-in não localizado"
                else:
                    state, reason = "review", f"Confirmação pendente de conferência no parceiro ({status})"
            except OSError:
                state, reason = "review", "Sem resposta do parceiro. Conferir no portal."
            with db:
                db.execute("UPDATE checkins SET state=?, reason=? WHERE reference=?",
                           (state, reason, reference))
        return state
    finally:
        db.close()


def require_secret(env_name, supplied):
    expected = os.environ.get(env_name, "")
    if len(expected) < 24 or not hmac.compare_digest(expected.encode(), supplied.encode()):
        abort(401)


@app.get("/")
def demo():
    return send_from_directory(ROOT, "index.html")


@app.post("/integracoes/totalpass/<secret>")
def totalpass(secret):
    require_secret("PRESIQ_WEBHOOK_SECRET", secret)
    try:
        state = process(request.get_json(), validate_at_totalpass)
    except (KeyError, TypeError, ValueError):
        abort(400)
    return {"status": state}



def panel_auth():
    auth = request.authorization
    require_secret("PRESIQ_PANEL_PASSWORD", (auth.password or "") if auth else "")


def school_profile():
    db = database()
    try:
        profile = db.execute("SELECT name, unit, color, icon FROM school").fetchone()
    finally:
        db.close()
    return profile or ("", "", "oceano", "raio")


def totalpass_post(origin, path, payload, token=None):
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = Request(origin + path, data=json.dumps(payload).encode(), headers=headers, method="POST")
    with build_opener(NoRedirect()).open(req, timeout=8) as result:
        return result.status, result.read(65536)


def connect_totalpass(place_key, partner_key, origin, webhook):
    status, body = totalpass_post(origin, "/partner/auth", {
        "partner_api_key": partner_key, "place_api_key": place_key,
    })
    auth = json.loads(body)
    token = auth.get("token") or auth.get("access_token") or (auth.get("data") or {}).get("token")
    if status not in (200, 201) or not isinstance(token, str) or not token or not token.isascii() or any(c.isspace() for c in token):
        raise ValueError("A autenticação não retornou um token reconhecido")
    status, _ = totalpass_post(origin, "/partner/webhook/create", {
        "webhook_type": "CHECKIN", "webhook_url": webhook,
    }, token)
    return status == 201


def connection_config():
    origin = os.environ.get("TOTALPASS_API_ORIGIN", "").rstrip("/")
    public = os.environ.get("PRESIQ_PUBLIC_URL", "").rstrip("/")
    partner_key = os.environ.get("TOTALPASS_PARTNER_API_KEY", "")
    secret = os.environ.get("PRESIQ_WEBHOOK_SECRET", "")
    urls = [urlsplit(origin), urlsplit(public)]
    if any(u.scheme != "https" or not u.hostname or u.username or u.password or u.path or u.query or u.fragment for u in urls):
        return None
    if not urls[0].hostname.endswith(".totalpass.com") or not partner_key or len(secret) < 24:
        return None
    if not all(c.isascii() and (c.isalnum() or c in "_-") for c in secret):
        return None
    return origin, public, partner_key, secret


@app.route("/conectar-totalpass", methods=["GET", "POST"])
def totalpass_connection():
    panel_auth()
    csrf = hmac.new(os.environ["PRESIQ_PANEL_PASSWORD"].encode(), b"totalpass-connect", hashlib.sha256).hexdigest()
    config = connection_config()
    db = database()
    message = ""
    try:
        db.execute("CREATE TABLE IF NOT EXISTS totalpass_connection (singleton INTEGER PRIMARY KEY)")
        if request.method == "POST":
            if not hmac.compare_digest(csrf, request.form.get("csrf", "")):
                abort(403)
            place_key = request.form.get("place_key", "").strip()
            if not config or not place_key or len(place_key) > 250:
                abort(400)
            origin, public, partner_key, secret = config
            with db:
                db.execute("BEGIN IMMEDIATE")
                if not db.execute("SELECT 1 FROM totalpass_connection").fetchone():
                    try:
                        if connect_totalpass(place_key, partner_key, origin, f"{public}/integracoes/totalpass/{secret}"):
                            db.execute("INSERT INTO totalpass_connection VALUES (1)")
                        else:
                            message = "A TotalPass não confirmou o cadastro do recebimento."
                    except HTTPError as error:
                        message = f"A TotalPass recusou a solicitação (HTTP {error.code}). Confira a chave da unidade e o ambiente."
                    except (OSError, ValueError, AttributeError):
                        message = "Sem confirmação da TotalPass. Confira no portal se o recebimento foi cadastrado antes de tentar novamente."
        connected = bool(db.execute("SELECT 1 FROM totalpass_connection").fetchone())
    finally:
        db.close()
    if connected:
        detail = "<p>Recebimento cadastrado. Faça um check-in de homologação para verificar a entrega e a validação no painel.</p>"
    elif config:
        detail = f"""<p>Use a chave da unidade do ambiente configurado pelo responsável técnico.</p>
        <form method="post"><input type="hidden" name="csrf" value="{csrf}">
        <label for="place_key">Chave da unidade</label>
        <input id="place_key" name="place_key" type="password" autocomplete="off" maxlength="250" required>
        <button>Conectar TotalPass</button></form>"""
    else:
        detail = "<p>Preparação pendente. O responsável técnico precisa configurar a credencial do integrador e o endereço HTTPS do PRESIQ.</p>"
    return f"""<!doctype html><html lang="pt-BR"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Conectar TotalPass · PRESIQ</title>
    <style>body{{background:#101a28;color:#f6f7fb;font:1rem system-ui;max-width:36rem;margin:auto;padding:1.25rem;line-height:1.6}}
    a{{color:#9fdcff}}form{{display:grid;gap:.6rem}}input,button{{box-sizing:border-box;width:100%;min-height:44px;font:inherit;border-radius:.5rem;padding:.5rem}}
    button{{background:#36b1e8;color:#101a28;border:0;font-weight:bold}}</style>
    <main><a href="/configuracao">Voltar à configuração</a><h1>Conectar TotalPass</h1>
    <p role="status">{escape(message)}</p>{detail}</main></html>""", 200, {"Cache-Control": "no-store"}


@app.route("/configuracao", methods=["GET", "POST"])
def setup():
    panel_auth()
    secret = os.environ["PRESIQ_PANEL_PASSWORD"]
    csrf = hmac.new(secret.encode(), b"presiq-school-profile", hashlib.sha256).hexdigest()
    if request.method == "POST":
        if not hmac.compare_digest(csrf, request.form.get("csrf", "")):
            abort(403)
        name = request.form.get("name", "").strip()
        unit = request.form.get("unit", "").strip()
        color = request.form.get("color", "")
        icon = request.form.get("icon", "")
        if not name or not unit or len(name) > 80 or len(unit) > 80 or color not in COLORS or icon not in ICONS:
            abort(400)
        db = database()
        try:
            with db:
                db.execute("INSERT OR REPLACE INTO school VALUES (1,?,?,?,?)", (name, unit, color, icon))
        finally:
            db.close()
        return "", 303, {"Location": "/configuracao?salvo=1"}
    name, unit, color, icon = school_profile()
    color_options = "".join(
        f'<option value="{value}" {"selected" if value == color else ""}>{value.title()}</option>'
        for value in COLORS
    )
    icon_options = "".join(
        f'<option value="{value}" {"selected" if value == icon else ""}>{symbol} {value.title()}</option>'
        for value, symbol in ICONS.items()
    )
    saved = '<p role="status">Identidade da escola salva.</p>' if request.args.get("salvo") else ""
    return f"""<!doctype html><html lang="pt-BR"><meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>PRESIQ · Configuração da escola</title>
    <style>
    :root{{color-scheme:dark;--accent:{COLORS[color]}}}*{{box-sizing:border-box}}
    body{{margin:0;background:#101a28;color:#f6f7fb;font:1rem system-ui;line-height:1.55}}
    main{{width:min(100%,66rem);margin:auto;padding:clamp(1rem,4vw,3rem)}}
    a{{color:#9fdcff;overflow-wrap:anywhere}} h1{{font-size:clamp(1.8rem,5vw,3.2rem);line-height:1.1}}
    .layout{{display:grid;gap:1rem;grid-template-columns:repeat(2,minmax(0,1fr))}}
    section{{background:#1b2b3e;border-radius:1rem;padding:clamp(1rem,3vw,1.5rem);min-width:0}}
    label{{display:block;margin:.8rem 0 .2rem}}input,select,button{{font:inherit;min-height:44px;border-radius:.5rem}}
    input,select{{width:100%;padding:.5rem .6rem;border:1px solid #6f8299;background:#101a28}}
    button{{margin-top:1rem;background:var(--accent);color:#111923;border:0;padding:.6rem 1rem;font-weight:700}}
    output{{display:block;margin-top:1rem;border:2px solid var(--accent);border-radius:.6rem;padding:.8rem;overflow-wrap:anywhere}}
    li{{margin-bottom:.6rem}} :focus-visible{{outline:3px solid white;outline-offset:3px}}
    @media(max-width:680px){{.layout{{grid-template-columns:1fr}}button{{width:100%}}}}
    </style>
    <main><a href="/professor">Abrir painel do professor</a><h1>Configurar escola</h1>{saved}
    <div class="layout"><section><h2>Identidade da escola</h2>
    <form method="post" id="school">
    <input type="hidden" name="csrf" value="{csrf}">
    <label for="name">Nome da escola</label><input id="name" name="name" maxlength="80" value="{escape(name)}" required>
    <label for="unit">Unidade ou bairro</label><input id="unit" name="unit" maxlength="80" value="{escape(unit)}" required>
    <label for="color">Padrão de cores</label><select id="color" name="color">{color_options}</select>
    <label for="icon">Símbolo da escola</label><select id="icon" name="icon">{icon_options}</select>
    <output id="preview" for="name unit color icon">{ICONS[icon]} {escape(name or "Sua escola")}</output>
    <button type="submit">Salvar escola</button></form></section>
    <section><h2>Conectar parceiros</h2><p>Use os portais oficiais com o responsável pela unidade.</p>
    <h3>TotalPass</h3><p><a href="/conectar-totalpass">Conectar TotalPass</a></p><ol>
    <li>Solicite acesso de integrador no <a href="https://developers.totalpass.com/">portal de desenvolvedores</a>.</li>
    <li>No Portal TotalPass da unidade, abra <strong>Integrações</strong> e gere a chave da unidade. Entregue a chave por um canal seguro ao responsável técnico.</li>
    <li>O técnico configura o recebimento dos check-ins e vincula os códigos dos alunos às reservas da turma piloto.</li>
    <li>Peça ao aluno de teste para fazer check-in no app. Confira a liberação no painel e a confirmação no histórico TotalPass.</li>
    </ol><h3>Wellhub</h3><ol>
    <li>No Portal do Parceiro, selecione a unidade em <strong>Integrações</strong> e solicite avaliação do PRESIQ como sistema de gestão.</li>
    <li>Confirme com o Wellhub se a unidade usa controle de acesso, reservas ou ambos.</li>
    <li>Com acesso técnico concedido, implemente e homologue o conector antes de usar com alunos. O conector Wellhub está pendente nesta versão.</li>
    </ol></section></div></main>
    <script>
    const form = document.getElementById('school');
    const colors = {json.dumps(COLORS)};
    function preview() {{
        const fields = new FormData(form);
        const symbol = form.elements.icon.selectedOptions[0].textContent.split(' ')[0];
        const name = fields.get('name').trim() || 'Sua escola';
        const unit = fields.get('unit').trim();
        document.getElementById('preview').textContent = symbol + ' ' + name + (unit ? ' · ' + unit : '');
        document.documentElement.style.setProperty('--accent', colors[fields.get('color')]);
    }}
    form.addEventListener('input', preview);
    preview();
    </script></html>"""


@app.get("/professor")
def teacher():
    panel_auth()
    name, unit, color, icon = school_profile()
    room = roster()
    db = database()
    try:
        records = db.execute("SELECT booking, state, reason FROM checkins ORDER BY timestamp").fetchall()
    finally:
        db.close()
    booking_status = {}
    for booking, state, reason in records:
        if booking and booking_status.get(booking, ("", ""))[0] != "released":
            booking_status[booking] = (state, reason)
    rows = []
    for entry in room["reservas"]:
        state, reason = booking_status.get(entry["id"], ("waiting", "Check-in ainda não recebido"))
        rows.append(f'<li><strong>{escape(entry["aluno"])}</strong> · {escape(entry["turma"])}'
                    f'<p class="{state}">{LABELS[state]} · {escape(reason)}</p></li>')
    pending = sum(booking is None and state == "review" for booking, state, _ in records)
    return f"""<!doctype html><html lang="pt-BR"><meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <meta http-equiv="refresh" content="5"><title>PRESIQ · Professor</title>
    <style>body{{background:#101a28;color:#f6f7fb;font:1rem system-ui;max-width:45rem;margin:auto;padding:1rem}}
    a{{color:#9fdcff}}h1{{border-bottom:3px solid {COLORS[color]};padding-bottom:.6rem;overflow-wrap:anywhere}}
    li{{background:#1b2b3e;padding:1rem;margin:.6rem 0;border-radius:.6rem;overflow-wrap:anywhere}} ul{{padding-left:0;list-style:none}}
    p{{margin:.35rem 0}} .released{{color:#80ecb1}} .review,.rejected{{color:#ffc88e}}</style>
    <main><a href="/configuracao">Configurar escola</a><h1>{ICONS[icon]} {escape(name or "Painel do professor")}</h1>
    <p>{escape(unit or room["nome"])}</p>
    <p>Check-ins sem vínculo para revisar: {pending}</p><ul>{"".join(rows)}</ul></main></html>"""


@app.errorhandler(401)
def unauthorized(_error):
    headers = {"WWW-Authenticate": 'Basic realm="PRESIQ"'} if request.path in ("/professor", "/configuracao", "/conectar-totalpass") else {}
    return "Acesso restrito", 401, headers

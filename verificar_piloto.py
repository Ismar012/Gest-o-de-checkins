"""Exercita o webhook e o painel sem enviar dados a um parceiro real."""
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import server

now = datetime.now(timezone.utc)
secret = "exemplo-local-somente-para-testes"
room = {"nome": "Turma fictícia", "unidade": "teste", "reservas": [{
    "id": "r1", "aluno": "Aluno de teste", "turma": "Iniciante",
    "totalpass": "aluno1", "inicio_checkin": (now - timedelta(minutes=5)).isoformat(),
    "fim_checkin": (now + timedelta(minutes=30)).isoformat(),
}]}


def event(token, user="aluno1", expired=False):
    return {
        "type": "CHECK_IN_CREATED",
        "endpoint": f"https://gym-service-api.totalpass.com/webhook_confirmations/{token}",
        "check_in": {"started_at": (now - timedelta(minutes=4)).isoformat(),
                     "expires_at": (now + timedelta(minutes=-1 if expired else 30)).isoformat()},
        "place": {"place": "teste"}, "user": {"code": user},
    }


with TemporaryDirectory() as tmp, patch.dict(os.environ, {
    "PRESIQ_DB": str(Path(tmp) / "test.sqlite3"),
    "PRESIQ_WEBHOOK_SECRET": secret, "PRESIQ_PANEL_PASSWORD": secret,
}), patch.object(server, "roster", return_value=room), patch.object(
    server, "validate_at_totalpass", side_effect=[422, 200],
) as confirm:
    client = server.app.test_client()
    route = f"/integracoes/totalpass/{secret}"
    auth = ("professor", secret)
    assert client.get("/professor").status_code == 401
    assert client.post("/integracoes/totalpass/incorreto", json=event("invalid")).status_code == 401
    assert "Aguardando validação" in client.get("/professor", auth=auth).text
    assert client.post(route, json=event("unknown", "desconhecido")).json["status"] == "review"
    assert client.post(route, json=event("expired", expired=True)).json["status"] == "rejected"
    assert client.post(route, json=event("manual")).json["status"] == "review"
    assert "Liberado para a aula" not in client.get("/professor", auth=auth).text
    assert client.post(route, json=event("ok")).json["status"] == "released"
    assert client.post(route, json=event("ok")).json["status"] == "released"
    assert client.post(route, json=event("another")).json["status"] == "review"
    assert "Liberado para a aula" in client.get("/professor", auth=auth).text
    assert confirm.call_count == 2
    setup = client.get("/configuracao", auth=auth)
    assert setup.status_code == 200 and "@media(max-width:680px)" in setup.text
    csrf = re.search(r'name="csrf" value="([a-f0-9]+)"', setup.text)[1]
    form = {"csrf": csrf, "name": "Beach Float", "unit": "Imbuí",
            "color": "areia", "icon": "tubarao"}
    assert client.post("/configuracao", auth=auth, data=form).status_code == 303
    panel = client.get("/professor", auth=auth).text
    assert "🦈 Beach Float" in panel and "#f2bd8c" in panel
    assert client.post("/configuracao", auth=auth, data={**form, "csrf": ""}).status_code == 403
    print("Cadastro da escola, proteção do formulário e identidade compartilhada verificados.")
    print("Webhook, autenticação, painel, expiração, divergência, aceite e duplicidade verificados.")

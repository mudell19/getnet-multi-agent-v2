import time

import jwt
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from getnet_multi_agent import cli
from getnet_multi_agent.contracts import Principal
from getnet_multi_agent.core.settings import Settings, get_settings
from getnet_multi_agent.security.auth import (
    AuthError,
    issue_token,
    require_merchant,
    require_operator,
    verify_token,
)
from getnet_multi_agent.security.pseudonym import pseudonym


def test_fr_033_valid_token(settings):
    p = verify_token(settings, issue_token(settings, "cliente001", "merchant"))
    assert p == Principal(sub="cliente001", role="merchant")


def _claims(settings, **over):
    c = {"iss": settings.JWT_ISSUER, "aud": settings.JWT_AUDIENCE, "sub": "x", "role": "merchant",
         "exp": int(time.time()) + 600}
    c.update(over)
    return c


def _enc(settings, claims, key=None):
    return jwt.encode(claims, key or settings.JWT_SECRET.get_secret_value(), algorithm="HS256")


def test_fr_033_invalid_tokens(settings):
    bad = {
        "expired": _enc(settings, _claims(settings, exp=int(time.time()) - 10)),
        "aud": _enc(settings, _claims(settings, aud="other")),
        "iss": _enc(settings, _claims(settings, iss="other")),
        "sig": _enc(settings, _claims(settings), key="another-secret-another-secret-123456"),
        "role": _enc(settings, _claims(settings, role="admin")),
        "garbage": "not-a-token",
    }
    for name, tok in bad.items():
        with pytest.raises(AuthError) as e:
            verify_token(settings, tok)
        assert e.value.status_code == 401, name


def test_empty_secret_refused():
    s = Settings(_env_file=None, JWT_SECRET="")
    with pytest.raises(AuthError):
        issue_token(s, "x", "merchant")
    with pytest.raises(AuthError):
        verify_token(s, "abc")


@pytest.fixture
def client(settings):
    app = FastAPI()

    @app.get("/m")
    def m(p: Principal = Depends(require_merchant)):
        return p.model_dump()

    @app.get("/o")
    def o(p: Principal = Depends(require_operator)):
        return p.model_dump()

    app.dependency_overrides[get_settings] = lambda: settings
    return TestClient(app)


def test_fr_033_dependencies_401(client):
    assert client.get("/m").status_code == 401
    r = client.get("/m", headers={"Authorization": "Bearer nope"})
    assert r.status_code == 401 and r.json()["detail"]["code"] == "unauthorized"


def test_fr_034_role_enforced(client, settings):
    op = {"Authorization": f"Bearer {issue_token(settings, 'op1', 'operator')}"}
    me = {"Authorization": f"Bearer {issue_token(settings, 'cliente001', 'merchant')}"}
    r = client.get("/m", headers=op)
    assert r.status_code == 403 and r.json()["detail"]["code"] == "forbidden"
    assert client.get("/o", headers=me).status_code == 403
    assert client.get("/m", headers=me).json() == {"sub": "cliente001", "role": "merchant"}
    assert client.get("/o", headers=op).status_code == 200


def test_fr_035_cli_token(monkeypatch, tmp_path, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("JWT_SECRET", "cli-secret-cli-secret-cli-secret-0123456789")
    get_settings.cache_clear()
    try:
        assert cli.main(["token", "--sub", "cliente002", "--role", "merchant"]) == 0
        token = capsys.readouterr().out.strip()
        assert "\n" not in token
        assert verify_token(get_settings(), token) == Principal(sub="cliente002", role="merchant")
    finally:
        get_settings.cache_clear()


def test_fr_036_pseudonym(settings):
    a = pseudonym("cliente001", settings)
    assert a == pseudonym("cliente001", settings)
    assert len(a) == 16 and int(a, 16) >= 0 and a != "cliente001"
    other = Settings(_env_file=None, PSEUDONYM_KEY="different-key")
    assert pseudonym("cliente001", other) != a
    assert pseudonym("cliente002", settings) != a

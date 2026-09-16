from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from saga_shared.auth import require_admin_api_key


def test_admin_api_key_is_required():
    app = FastAPI()
    app.state.admin_api_key = "test-secret"

    @app.get("/admin/check", dependencies=[Depends(require_admin_api_key)])
    async def admin_check():
        return {"status": "ok"}

    with TestClient(app) as client:
        missing = client.get("/admin/check")
        wrong = client.get("/admin/check", headers={"X-Admin-API-Key": "wrong"})
        valid = client.get(
            "/admin/check", headers={"X-Admin-API-Key": "test-secret"}
        )

    assert missing.status_code == 401
    assert wrong.status_code == 401
    assert valid.status_code == 200

import secrets

from fastapi import Header, HTTPException, Request, status


async def require_admin_api_key(
    request: Request,
    x_admin_api_key: str | None = Header(default=None),
) -> None:
    expected_key = request.app.state.admin_api_key
    if not x_admin_api_key or not secrets.compare_digest(x_admin_api_key, expected_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid or missing admin API key",
            headers={"WWW-Authenticate": "ApiKey"},
        )

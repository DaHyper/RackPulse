from __future__ import annotations

from typing import Annotated, Callable

from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader

from rackpulse.config import AuthConfig

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def make_auth_dependency(auth: AuthConfig) -> Callable[..., str | None]:
    def optional_api_key(
        api_key: Annotated[str | None, Security(_api_key_header)] = None,
    ) -> str | None:
        if not auth.enabled:
            return None
        if not auth.api_key:
            raise HTTPException(status_code=500, detail="Auth enabled but api_key not configured")
        if api_key != auth.api_key:
            raise HTTPException(status_code=401, detail="Invalid or missing API key")
        return api_key

    return optional_api_key

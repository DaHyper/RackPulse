from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI
from fastapi.responses import JSONResponse

from rackpulse import __version__
from rackpulse.api.auth import make_auth_dependency
from rackpulse.engine.poller import Poller

_poller: Poller | None = None


def get_poller() -> Poller:
    if _poller is None:
        raise RuntimeError("Poller not initialized")
    return _poller


def create_app(config_path: str) -> FastAPI:
    from rackpulse.config import load_config

    global _poller
    config = load_config(config_path)
    require_auth = make_auth_dependency(config.auth)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        global _poller
        _poller = Poller(config_path)
        await _poller.start()
        yield
        await _poller.stop()
        _poller = None

    app = FastAPI(title="RackPulse", version=__version__, lifespan=lifespan)

    @app.get("/api/health")
    async def health() -> JSONResponse:
        return JSONResponse({"ok": True, "version": __version__})

    @app.get("/api/status")
    async def status(
        _key: Annotated[str | None, Depends(require_auth)] = None,
    ) -> JSONResponse:
        poller = get_poller()
        snapshot = poller.get_snapshot()
        return JSONResponse(
            {
                "last_poll": snapshot.last_poll.isoformat() if snapshot.last_poll else None,
                "total_power_watts": snapshot.total_power_watts,
                "racks": [
                    {
                        "name": r.name,
                        "power_watts": r.power_watts,
                        "status": r.status.value,
                        "devices": [
                            {
                                "name": d.name,
                                "type": d.device_type,
                                "status": d.status.value,
                                "power_watts": d.power_watts,
                            }
                            for d in r.devices
                        ],
                    }
                    for r in snapshot.racks
                ],
            }
        )

    @app.post("/api/refresh")
    async def refresh(
        _key: Annotated[str | None, Depends(require_auth)] = None,
    ) -> JSONResponse:
        poller = get_poller()
        snapshot = await poller.poll_once()
        return JSONResponse(
            {
                "last_poll": snapshot.last_poll.isoformat() if snapshot.last_poll else None,
                "total_power_watts": snapshot.total_power_watts,
            }
        )

    return app


def run_server(config_path: str, host: str | None = None, port: int | None = None) -> None:
    from rackpulse.config import load_config
    import uvicorn

    config = load_config(config_path)
    bind_host = host or config.server.host
    bind_port = port or config.server.port
    app = create_app(config_path)

    print(f"RackPulse API on http://{bind_host}:{bind_port}")
    print(f"Config: {config_path}")
    if config.auth.enabled:
        print("Auth: enabled (X-API-Key header required)")
    else:
        print("Auth: disabled")

    uvicorn.run(app, host=bind_host, port=bind_port, log_level="info")

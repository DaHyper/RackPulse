from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI
from fastapi.responses import JSONResponse

from rackpulse import __version__
from rackpulse.api.auth import make_auth_dependency
from rackpulse.api.routes_config import create_config_router, create_test_router
from rackpulse.engine.poller import Poller
from rackpulse.presentation.dashboard import build_dashboard_state

_poller: Poller | None = None


def get_poller() -> Poller:
    if _poller is None:
        raise RuntimeError("Poller not initialized")
    return _poller


def create_app(config_path: str, *, enable_web: bool = False) -> FastAPI:
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
        return JSONResponse(
            {
                "ok": True,
                "version": __version__,
                "auth_required": config.auth.enabled,
            }
        )

    @app.get("/api/status")
    async def status(
        view: str = "default",
        _key: Annotated[str | None, Depends(require_auth)] = None,
    ) -> JSONResponse:
        poller = get_poller()
        snapshot = poller.get_snapshot()
        if view == "dashboard" or enable_web:
            return JSONResponse(
                build_dashboard_state(snapshot, poller.config, poller.storage)
            )
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
        view: str = "default",
        _key: Annotated[str | None, Depends(require_auth)] = None,
    ) -> JSONResponse:
        poller = get_poller()
        snapshot = await poller.poll_once()
        if view == "dashboard" or enable_web:
            return JSONResponse(
                build_dashboard_state(snapshot, poller.config, poller.storage)
            )
        return JSONResponse(
            {
                "last_poll": snapshot.last_poll.isoformat() if snapshot.last_poll else None,
                "total_power_watts": snapshot.total_power_watts,
            }
        )

    @app.get("/api/devices/{device_name}")
    async def device_detail(
        device_name: str,
        _key: Annotated[str | None, Depends(require_auth)] = None,
    ) -> JSONResponse:
        poller = get_poller()
        snapshot = poller.get_snapshot()
        reading = None
        for rack in snapshot.racks:
            for device in rack.devices:
                if device.name == device_name:
                    reading = device
                    break
        if reading is None:
            return JSONResponse({"error": "Device not found"}, status_code=404)

        latest = poller.storage.latest_power_metric(device_name)
        return JSONResponse(
            {
                "device": device_name,
                "type": reading.device_type,
                "host": reading.host,
                "rack": reading.rack,
                "status": reading.status.value,
                "power_watts": reading.power_watts,
                "volts": reading.metrics.volts,
                "amps": reading.metrics.amps,
                "cpu_percent": reading.metrics.cpu_percent,
                "ram_percent": reading.metrics.ram_percent,
                "temperature_c": reading.metrics.temperature_c,
                "last_poll": reading.last_poll.isoformat() if reading.last_poll else None,
                "latest_stored": latest,
            }
        )

    @app.get("/api/devices/{device_name}/power")
    async def device_power_history(
        device_name: str,
        hours: float = 24,
        _key: Annotated[str | None, Depends(require_auth)] = None,
    ) -> JSONResponse:
        poller = get_poller()
        history = poller.storage.device_power_history(device_name, hours=hours)
        return JSONResponse(
            {
                "device": device_name,
                "hours": hours,
                "samples": history,
            }
        )

    if enable_web:
        from fastapi.staticfiles import StaticFiles
        from rackpulse.web.routes import WEB_DIR, create_web_router

        static_dir = WEB_DIR / "static"
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
        app.include_router(create_web_router(__version__))
        app.include_router(create_config_router(config_path, get_poller, require_auth))
        app.include_router(create_test_router(get_poller, require_auth))

        @app.get("/api/meta/device-types")
        async def device_types(
            _key: Annotated[str | None, Depends(require_auth)] = None,
        ) -> JSONResponse:
            from rackpulse.collectors.registry import SUPPORTED_TYPES

            return JSONResponse({"types": SUPPORTED_TYPES})

    return app


def run_server(
    config_path: str,
    host: str | None = None,
    port: int | None = None,
    *,
    enable_web: bool = False,
) -> None:
    from rackpulse.config import load_config
    import uvicorn

    config = load_config(config_path)
    bind_host = host or config.server.host
    bind_port = port or config.server.port
    app = create_app(config_path, enable_web=enable_web)

    mode = "dashboard + API" if enable_web else "API"
    print(f"RackPulse {mode} on http://{bind_host}:{bind_port}")
    print(f"Config: {config_path}")
    if enable_web:
        print(f"Dashboard: http://{bind_host}:{bind_port}/")
        print(f"Configuration: http://{bind_host}:{bind_port}/config")
        if not config.auth.enabled:
            print(
                "WARNING: Auth is disabled. Enable auth.enabled in config before "
                "exposing the dashboard on your network."
            )
    if config.auth.enabled:
        print("Auth: enabled (X-API-Key header required)")
    else:
        print("Auth: disabled")

    uvicorn.run(app, host=bind_host, port=bind_port, log_level="info")

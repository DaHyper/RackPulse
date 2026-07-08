from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

import yaml

from rackpulse.config_io import config_to_dict, config_to_yaml, merge_config_update, save_config


class ConfigUpdate(BaseModel):
    poll_interval_seconds: int | None = None
    storage: dict | None = None
    secrets: dict | None = None
    auth: dict | None = None
    snmp: dict | None = None
    pdu: dict | None = None
    alerts: dict | None = None
    maintenance: dict | None = None
    server: dict | None = None
    racks: list[dict] | None = None
    # Legacy flat keys from older UI payloads
    alert_cooldown_minutes: int | None = None
    smtp: dict | None = None
    webhooks: list[dict] | None = None


def create_config_router(
    config_path: str,
    get_poller: callable,
    require_auth: callable,
) -> APIRouter:
    router = APIRouter()

    @router.get("/api/config")
    async def api_get_config(
        _key: Annotated[str | None, Depends(require_auth)] = None,
    ) -> JSONResponse:
        poller = get_poller()
        data = config_to_dict(poller.config, mask_secrets=True)
        return JSONResponse(data)

    @router.put("/api/config")
    async def api_save_config(
        body: ConfigUpdate,
        _key: Annotated[str | None, Depends(require_auth)] = None,
    ) -> JSONResponse:
        poller = get_poller()
        try:
            update = body.model_dump(exclude_none=True)
            merged = merge_config_update(poller.config, update)
            save_config(config_path, merged)
            poller.reload_config()
            data = config_to_dict(poller.config, mask_secrets=True)
            return JSONResponse({"ok": True, "config": data})
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/api/config/export")
    async def api_export_config(
        _key: Annotated[str | None, Depends(require_auth)] = None,
    ) -> Response:
        poller = get_poller()
        yaml_text = config_to_yaml(poller.config, mask_secrets=True)
        return Response(
            content=yaml_text,
            media_type="application/x-yaml",
            headers={"Content-Disposition": 'attachment; filename="rackpulse-config.yaml"'},
        )

    @router.post("/api/config/import")
    async def api_import_config(
        file: UploadFile = File(...),
        _key: Annotated[str | None, Depends(require_auth)] = None,
    ) -> JSONResponse:
        poller = get_poller()
        try:
            raw = await file.read()
            data = yaml.safe_load(raw.decode("utf-8"))
            if not isinstance(data, dict):
                raise ValueError("Config must be a YAML mapping")
            save_config(config_path, data)
            poller.reload_config()
            result = config_to_dict(poller.config, mask_secrets=True)
            return JSONResponse({"ok": True, "config": result})
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/api/test/smtp")
    async def api_test_smtp(
        _key: Annotated[str | None, Depends(require_auth)] = None,
    ) -> JSONResponse:
        from rackpulse.alerts import AlertNotifier

        poller = get_poller()
        notifier = AlertNotifier(poller.config.alerts.smtp, poller.config.alerts.webhooks)
        if not notifier.email.configured:
            raise HTTPException(status_code=400, detail="SMTP not configured")
        try:
            notifier.send_test_email()
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        return JSONResponse({"ok": True})

    @router.post("/api/test/webhooks")
    async def api_test_webhooks(
        _key: Annotated[str | None, Depends(require_auth)] = None,
    ) -> JSONResponse:
        from rackpulse.alerts import AlertNotifier

        poller = get_poller()
        notifier = AlertNotifier(poller.config.alerts.smtp, poller.config.alerts.webhooks)
        if not notifier.webhooks.configured:
            raise HTTPException(status_code=400, detail="No webhooks configured")
        try:
            notifier.send_test_webhooks()
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        return JSONResponse({"ok": True})

    return router


def create_test_router(get_poller: callable, require_auth: callable) -> APIRouter:
    router = APIRouter()

    @router.post("/api/test/devices/all")
    async def api_test_all_devices(
        _key: Annotated[str | None, Depends(require_auth)] = None,
    ) -> JSONResponse:
        poller = get_poller()
        results = []
        for rack in poller.config.racks:
            for device in rack.devices:
                try:
                    reading = await poller.poll_device_by_name(device.name)
                    ok = reading.status.value in ("ok", "stale")
                    entry = {
                        "rack": rack.name,
                        "name": device.name,
                        "type": device.type,
                        "host": device.host,
                        "ok": ok,
                        "error": reading.error,
                        "status": reading.status.value,
                    }
                    if reading.power_watts is not None:
                        entry["power_watts"] = reading.power_watts
                        entry["power_kw"] = round(reading.power_watts / 1000, 3)
                except Exception as exc:  # noqa: BLE001
                    entry = {
                        "rack": rack.name,
                        "name": device.name,
                        "type": device.type,
                        "host": device.host,
                        "ok": False,
                        "error": str(exc),
                    }
                results.append(entry)
        return JSONResponse({"results": results})

    @router.post("/api/test/device/{device_name}")
    async def api_test_device(
        device_name: str,
        _key: Annotated[str | None, Depends(require_auth)] = None,
    ) -> JSONResponse:
        poller = get_poller()
        try:
            reading = await poller.poll_device_by_name(device_name)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        ok = reading.status.value in ("ok", "stale")
        payload = {
            "ok": ok,
            "status": reading.status.value,
            "error": reading.error,
            "power_watts": reading.power_watts,
        }
        if reading.power_watts is not None:
            payload["power_kw"] = round(reading.power_watts / 1000, 3)
        return JSONResponse(payload)

    return router

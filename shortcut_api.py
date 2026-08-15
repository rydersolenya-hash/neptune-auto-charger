"""供 iPhone 快捷指令调用的 Neptune HTTP API。

接口：
  GET  /health       健康检查
  POST /v1/plan      查询设备、端口和计划时间，不启动充电
  POST /v1/charge    查询后启动充电

所有 /v1 接口都要求 Authorization: Bearer <NEPTUNE_API_TOKEN>。
"""

import asyncio
import os
from typing import Any

from aiohttp import web

from charge_schedule import build_charge_plan, parse_schedule_time
from config import AREA_ID, BASE_URL, SCHEDULE_TIME, validate_config
from main import HEADERS, begin_charge, get_device_info, get_user_info
from ports import get_port_status


API_HOST = os.getenv("NEPTUNE_API_HOST", "127.0.0.1")
API_PORT = int(os.getenv("NEPTUNE_API_PORT", "8080"))
API_TOKEN = os.getenv("NEPTUNE_API_TOKEN", "")


def json_error(message: str, status: int = 400, **extra: Any) -> web.Response:
    body = {"ok": False, "error": message}
    body.update(extra)
    return web.json_response(body, status=status)


def is_authorized(request: web.Request) -> bool:
    if not API_TOKEN:
        return False
    authorization = request.headers.get("Authorization", "")
    api_key = request.headers.get("X-API-Key", "")
    return authorization == f"Bearer {API_TOKEN}" or api_key == API_TOKEN


async def require_json(request: web.Request) -> dict | web.Response:
    if not is_authorized(request):
        return json_error("未授权", status=401)
    try:
        payload = await request.json()
    except Exception:
        return json_error("请求体必须是 JSON")
    if not isinstance(payload, dict):
        return json_error("请求体必须是 JSON 对象")
    return payload


def parse_request(payload: dict) -> tuple[str, str, str, int | None] | web.Response:
    device = str(payload.get("device", "")).strip()
    port = str(payload.get("port", "")).strip()
    schedule_time = str(payload.get("scheduled_time", SCHEDULE_TIME)).strip()

    if not device.isdigit():
        return json_error("device 必须是设备编号")
    try:
        port_number = int(port)
        if port_number < 1:
            raise ValueError
    except (TypeError, ValueError):
        return json_error("port 必须是从 1 开始的物理端口号")

    try:
        schedule_time = parse_schedule_time(schedule_time).strftime("%H:%M")
    except ValueError as exc:
        return json_error(str(exc))

    charge_money = payload.get("charge_money")
    if charge_money is not None:
        try:
            charge_money = int(charge_money)
            if charge_money < 1:
                raise ValueError
        except (TypeError, ValueError):
            return json_error("charge_money 必须是正整数，单位与接口一致")

    return device, str(port_number), schedule_time, charge_money


async def get_live_plan(
    session,
    device: str,
    port: str,
    schedule_time: str,
    charge_money: int | None,
) -> tuple[dict | None, web.Response | None]:
    user_info = await get_user_info(session)
    if not user_info:
        return None, json_error("获取用户信息失败", status=502)

    device_info = await get_device_info(session, device)
    if not device_info:
        return None, json_error("获取设备信息失败", status=502)

    port_status = get_port_status(device_info.get("portstatur", ""), port)
    plan = build_charge_plan(
        device,
        port,
        port_status,
        schedule_time=schedule_time,
        balance=user_info.get("readyaccountmoney", 0),
        charge_money=charge_money,
    )
    plan["ok"] = True
    plan["device_name"] = device_info.get("devdescript")
    plan["work_time"] = device_info.get("workTime")
    return plan, None


async def health(_request: web.Request) -> web.Response:
    return web.json_response({"ok": True, "service": "neptune-shortcut-api"})


async def plan(request: web.Request) -> web.Response:
    payload = await require_json(request)
    if isinstance(payload, web.Response):
        return payload

    parsed = parse_request(payload)
    if isinstance(parsed, web.Response):
        return parsed
    device, port, schedule_time, charge_money = parsed

    timeout = request.app["timeout"]
    async with request.app["session_factory"](timeout=timeout) as session:
        result, error = await get_live_plan(
            session, device, port, schedule_time, charge_money
        )
    return error if error is not None else web.json_response(result)


async def charge(request: web.Request) -> web.Response:
    payload = await require_json(request)
    if isinstance(payload, web.Response):
        return payload

    parsed = parse_request(payload)
    if isinstance(parsed, web.Response):
        return parsed
    device, port, schedule_time, charge_money = parsed

    timeout = request.app["timeout"]
    async with request.app["session_factory"](timeout=timeout) as session:
        plan_result, error = await get_live_plan(
            session, device, port, schedule_time, charge_money
        )
        if error is not None:
            return error
        if not plan_result["ready"]:
            return web.json_response(
                {"ok": False, "error": "端口当前不可用", "plan": plan_result},
                status=409,
            )

        user_info = await get_user_info(session)
        device_info = await get_device_info(session, device)
        result = await begin_charge(
            session,
            device,
            port,
            user_info.get("readyaccountmoney", 0),
            device_info,
            charge_money=charge_money,
        )

    return web.json_response(
        {"ok": bool(result.get("success")), "plan": plan_result, "result": result},
        status=200 if result.get("success") else 502,
    )


async def on_startup(app: web.Application) -> None:
    app["timeout"] = __import__("aiohttp").ClientTimeout(total=30)
    app["session_factory"] = __import__("aiohttp").ClientSession


def create_app() -> web.Application:
    if not API_TOKEN:
        raise RuntimeError("请设置 NEPTUNE_API_TOKEN 后再启动 API 服务")
    config_errors = validate_config()
    if config_errors:
        raise RuntimeError("；".join(config_errors))

    app = web.Application()
    app.router.add_get("/health", health)
    app.router.add_post("/v1/plan", plan)
    app.router.add_post("/v1/charge", charge)
    app.on_startup.append(on_startup)
    return app


if __name__ == "__main__":
    web.run_app(create_app(), host=API_HOST, port=API_PORT)

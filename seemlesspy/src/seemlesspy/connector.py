import asyncio
from collections.abc import Sequence
from dataclasses import asdict
from typing import TYPE_CHECKING, Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from .contract import Contract, ContractResolution
from .holder import (
    Session,
    _descriptor,
    resolve_contract,
    to_jsonable,
)

if TYPE_CHECKING:
    from .base import SeemlessPy


class ConnectionManager:
    def __init__(self) -> None:
        self.active: list[WebSocket] = []
        self.rooms: dict[str, set[WebSocket]] = {}
        self.sessions: dict[WebSocket, Session] = {}
        self.loop: asyncio.AbstractEventLoop | None = None

    async def connect(self, ws: WebSocket) -> Session:
        await ws.accept()
        self.active.append(ws)
        self.loop = asyncio.get_running_loop()
        session = Session()
        self.sessions[ws] = session
        return session

    def disconnect(self, ws: WebSocket) -> None:
        if ws in self.active:
            self.active.remove(ws)

        self.sessions.pop(ws, None)

        for members in self.rooms.values():
            members.discard(ws)

    def join(self, ws: WebSocket, room: str) -> None:
        self.rooms.setdefault(room, set()).add(ws)

    def leave(self, ws: WebSocket, room: str) -> None:
        members = self.rooms.get(room)

        if members is not None:
            members.discard(ws)

    async def broadcast(self, message: dict, room: str) -> None:
        for ws in self.rooms.get(room, set()):
            await ws.send_json(message)

    async def notify(
        self,
        instance: "SeemlessPy",
        members: Sequence[str] | None = None,
    ) -> None:
        for ws, session in self.sessions.items():
            for update in session.take_updates(instance, members):
                await ws.send_json(_update_message(*update))

    def notify_nowait(
        self,
        instance: "SeemlessPy",
        members: Sequence[str] | None = None,
    ) -> None:
        loop = self.loop

        if loop is None:
            return

        coroutine = self.notify(instance, members)

        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            asyncio.run_coroutine_threadsafe(coroutine, loop)
            return

        if running is loop:
            loop.create_task(coroutine)
        else:
            asyncio.run_coroutine_threadsafe(coroutine, loop)


manager = ConnectionManager()


def setup_websocket(app: FastAPI) -> None:
    @app.websocket("/ws")
    async def websocket_endpoint(ws: WebSocket) -> None:
        session = await manager.connect(ws)
        try:
            while True:
                data: dict[str, Any] = await ws.receive_json()
                await _resolve(data, session, ws)

        except WebSocketDisconnect:
            manager.disconnect(ws)


def _parse_contract(data: dict[str, Any]) -> Contract:
    params = [tuple(param) for param in data.get("params", [])]
    return Contract(
        kind=data["kind"],
        cls_name=data["cls_name"],
        instance_id=data.get("instance_id"),
        member=data["member"],
        params=params,
    )


def _describe_call(contract: Contract) -> str:
    if contract.kind == "release":
        return f"{contract.cls_name}.release()"

    call = f"{contract.cls_name}.{contract.member}"

    if contract.kind in {"property", "subscribe", "unsubscribe"}:
        return call

    args = ", ".join(f"{name}={value!r}" for name, value in contract.params)
    return f"{call}({args})"


def _update_message(
    instance_id: str, member: str, value: object
) -> dict[str, Any]:
    return {
        "event": "update",
        "instance_id": instance_id,
        "member": member,
        "value": to_jsonable(value),
    }


async def _resolve(
    data: dict[str, Any], session: Session, ws: WebSocket
) -> None:
    call = ""
    try:
        contract = _parse_contract(data)
        call = _describe_call(contract)
        result = to_jsonable(resolve_contract(contract, session))
    except Exception as error:
        await ws.send_json(
            asdict(ContractResolution(call=call, error=str(error)))
        )
        return

    await ws.send_json(asdict(ContractResolution(call=call, result=result)))

    if contract.kind == "method" and contract.instance_id is not None:
        instance = session.get(contract.cls_name, contract.instance_id)
        changes: Sequence[str] | None = None
        cls = _descriptor.classes.get(contract.cls_name)

        if cls is not None:
            member = cls.members.get(contract.member)

            if member is not None and member.changes:
                changes = member.changes

        for update in session.take_updates(instance, changes):
            await ws.send_json(_update_message(*update))

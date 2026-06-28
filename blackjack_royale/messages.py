"""Small JSON message helpers used by clients and servers."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Message:
    type: str
    sender: str
    payload: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    def to_line(self) -> bytes:
        return (json.dumps(self.__dict__, separators=(",", ":")) + "\n").encode("utf-8")

    @staticmethod
    def from_line(line: bytes) -> "Message":
        raw = json.loads(line.decode("utf-8"))
        return Message(
            type=raw["type"],
            sender=raw["sender"],
            payload=raw.get("payload", {}),
            timestamp=raw.get("timestamp", time.time()),
        )


async def send_message(writer: Any, message: Message) -> None:
    writer.write(message.to_line())
    await writer.drain()


async def read_message(reader: Any) -> Message | None:
    line = await reader.readline()
    return Message.from_line(line) if line else None

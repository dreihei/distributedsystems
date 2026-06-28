"""UDP discovery helpers for finding Blackjack servers in a local network."""

from __future__ import annotations

import json
import socket
import time
from dataclasses import dataclass


DISCOVERY_PORTS = range(9201, 9210)
DISCOVERY_REQUEST = "BLACKJACK_ROYALE_DISCOVER"
DISCOVERY_RESPONSE = "BLACKJACK_ROYALE_SERVER"


@dataclass(frozen=True)
class DiscoveredServer:
    server_id: int
    host: str
    client_port: int
    server_port: int
    discovery_port: int


def local_lan_ip() -> str:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]
    except OSError:
        return socket.gethostbyname(socket.gethostname())
    finally:
        sock.close()


def discover_servers(timeout: float = 1.5) -> list[DiscoveredServer]:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.settimeout(0.2)

    request = json.dumps({"type": DISCOVERY_REQUEST}).encode("utf-8")
    for port in DISCOVERY_PORTS:
        sock.sendto(request, ("255.255.255.255", port))
        sock.sendto(request, ("localhost", port))

    found: dict[tuple[str, int], DiscoveredServer] = {}
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            data, addr = sock.recvfrom(4096)
        except TimeoutError:
            continue
        except OSError:
            continue
        raw = json.loads(data.decode("utf-8"))
        if raw.get("type") != DISCOVERY_RESPONSE:
            continue
        host = raw.get("host") or addr[0]
        server = DiscoveredServer(
            server_id=int(raw["server_id"]),
            host=host,
            client_port=int(raw["client_port"]),
            server_port=int(raw["server_port"]),
            discovery_port=int(raw["discovery_port"]),
        )
        found[(server.host, server.client_port)] = server

    sock.close()
    return sorted(found.values(), key=lambda item: item.server_id, reverse=True)

"""Shared runtime configuration for Blackjack Royale."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RuntimeConfig:
    host: str = "0.0.0.0"
    client_port: int = 9000
    server_port: int = 9100
    discovery_port: int = 9200
    heartbeat_interval: float = 1.0
    heartbeat_timeout: float = 4.0
    client_timeout: float = 8.0
    reconnect_window: float = 45.0
    election_timeout: float = 3.0
    turn_timeout: float = 30.0


DEFAULT_CONFIG = RuntimeConfig()

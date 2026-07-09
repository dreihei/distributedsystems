"""Async server for Blackjack Royale.

One process exposes two TCP ports:
- client_port for players
- server_port for peer servers
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import time
from typing import Awaitable, Callable

from .blackjack import RuleError, Table
from .config import DEFAULT_CONFIG, RuntimeConfig
from .discovery import DISCOVERY_REQUEST, DISCOVERY_RESPONSE, local_lan_ip
from .messages import Message, read_message, send_message
from .state import ClusterState, Peer


Handler = Callable[[Message], Awaitable[dict]]


class DiscoveryProtocol(asyncio.DatagramProtocol):
    def __init__(self, server: "BlackjackServer") -> None:
        self.server = server
        self.transport: asyncio.DatagramTransport | None = None

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        self.transport = transport  # type: ignore[assignment]

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        if self.transport is None:
            return
        try:
            request = json.loads(data.decode("utf-8"))
        except json.JSONDecodeError:
            return
        if request.get("type") != DISCOVERY_REQUEST:
            return
        peer = self.server.state.local_peer()
        response = {
            "type": DISCOVERY_RESPONSE,
            "server_id": peer.server_id,
            "host": peer.host,
            "client_port": peer.client_port,
            "server_port": peer.server_port,
            "discovery_port": self.server.discovery_port,
        }
        self.transport.sendto(json.dumps(response).encode("utf-8"), addr)


class BlackjackServer:
    def __init__(self, server_id: int, host: str, client_port: int, server_port: int, discovery_port: int) -> None:
        advertised_host = local_lan_ip() if host in {"0.0.0.0", ""} else host
        self.config = RuntimeConfig(host=host, client_port=client_port, server_port=server_port)
        self.discovery_port = discovery_port
        self.state = ClusterState(
            server_id, advertised_host, server_port, client_port, turn_timeout=self.config.turn_timeout
        )
        self.election_running = False
        self._tasks: list[asyncio.Task] = []

    async def start(self) -> None:
        client_server = await asyncio.start_server(self.handle_client, self.config.host, self.config.client_port)
        peer_server = await asyncio.start_server(self.handle_peer, self.config.host, self.config.server_port)
        await self.start_udp_discovery()
        self._tasks = [
            asyncio.create_task(self.discovery_loop()),
            asyncio.create_task(self.heartbeat_loop()),
            asyncio.create_task(self.turn_timer_loop()),
        ]
        print(
            f"server {self.state.server_id} running "
            f"client={self.config.client_port} peer={self.config.server_port}",
            flush=True,
        )
        async with client_server, peer_server:
            await asyncio.gather(client_server.serve_forever(), peer_server.serve_forever())

    async def handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        message = await read_message(reader)
        response = await self.route_client_message(message) if message else {"error": "empty request"}
        await send_message(writer, Message("RESPONSE", str(self.state.server_id), response))
        writer.close()
        await writer.wait_closed()

    async def handle_peer(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        message = await read_message(reader)
        response = await self.route_peer_message(message) if message else {"error": "empty request"}
        await send_message(writer, Message("RESPONSE", str(self.state.server_id), response))
        writer.close()
        await writer.wait_closed()

    async def route_client_message(self, message: Message) -> dict:
        handlers: dict[str, Handler] = {
            "LIST_TABLES": self.client_list_tables,
            "JOIN_TABLE": self.client_join_table,
            "ADD_BOT": self.client_add_bot,
            "PLACE_BET": self.client_place_bet,
            "START_ROUND": self.client_start_round,
            "NEW_ROUND": self.client_new_round,
            "HIT": self.client_hit,
            "STAND": self.client_stand,
            "DOUBLE": self.client_double,
            "SPLIT": self.client_split,
            "REFILL_BALANCE": self.client_refill_balance,
        }
        handler = handlers.get(message.type)
        if handler is None:
            return {"error": f"unknown client message {message.type}"}
        try:
            return await handler(message)
        except RuleError as exc:
            response: dict = {"error": str(exc)}
            table = self.find_table(message)
            if table is not None:
                response["table"] = table.snapshot()
            return response

    async def route_peer_message(self, message: Message) -> dict:
        handlers: dict[str, Handler] = {
            "SERVER_ANNOUNCE": self.peer_announce,
            "HEARTBEAT": self.peer_heartbeat,
            "STATE_SYNC": self.peer_state_sync,
            "GET_TABLES": self.peer_get_tables,
            "ELECTION": self.peer_election,
            "COORDINATOR": self.peer_coordinator,
        }
        handler = handlers.get(message.type)
        return await handler(message) if handler else {"error": f"unknown peer message {message.type}"}

    async def client_list_tables(self, message: Message) -> dict:
        return {"tables": [table.snapshot() for table in self.state.tables.values()]}

    def find_table(self, message: Message) -> Table | None:
        return self.state.tables.get(message.payload.get("table_id", "main"))

    def unknown_table_error(self, message: Message) -> dict:
        return {"error": f"unknown table {message.payload.get('table_id', 'main')}; join first"}

    async def client_join_table(self, message: Message) -> dict:
        table = self.find_table(message)
        if table is None:
            # Only the cluster coordinator (highest active id) may create tables.
            # Everyone else forwards the join so no second lineage can appear.
            coordinator_id = self.state.highest_active_server_id()
            if coordinator_id != self.state.server_id:
                peer = self.state.peers.get(coordinator_id)
                response = await self.request(peer.host, peer.client_port, message) if peer else None
                return response or {"error": "coordinator unavailable"}
            table = self.state.ensure_table(message.payload.get("table_id", "main"))
        if not self.is_game_master(table.table_id):
            return await self.forward_to_master(message, table.table_id)
        player = table.join(message.payload.get("player_id"), message.payload.get("name", "Player"))
        await self.sync_table(table.table_id)
        return {"table": table.snapshot(), "player_id": player.player_id}

    async def client_add_bot(self, message: Message) -> dict:
        table = self.find_table(message)
        if table is None:
            return self.unknown_table_error(message)
        if not self.is_game_master(table.table_id):
            return await self.forward_to_master(message, table.table_id)
        bot_name = message.payload.get("name") or "Bot"
        table.add_bot(None, bot_name, int(message.payload.get("amount", 50)))
        await self.sync_table(table.table_id)
        return {"table": table.snapshot()}

    async def client_place_bet(self, message: Message) -> dict:
        table = self.find_table(message)
        if table is None:
            return self.unknown_table_error(message)
        if not self.is_game_master(table.table_id):
            return await self.forward_to_master(message, table.table_id)
        player_id = message.payload.get("player_id")
        if not player_id:
            return {"error": "player_id required", "table": table.snapshot()}
        table.place_bet(player_id, int(message.payload["amount"]))
        await self.sync_table(table.table_id)
        return {"table": table.snapshot()}

    async def client_start_round(self, message: Message) -> dict:
        table = self.find_table(message)
        if table is None:
            return self.unknown_table_error(message)
        if not self.is_game_master(table.table_id):
            return await self.forward_to_master(message, table.table_id)
        table.start_round()
        await self.sync_table(table.table_id)
        return {"table": table.snapshot()}

    async def client_new_round(self, message: Message) -> dict:
        table = self.find_table(message)
        if table is None:
            return self.unknown_table_error(message)
        if not self.is_game_master(table.table_id):
            return await self.forward_to_master(message, table.table_id)
        player_id = message.payload.get("player_id")
        if not player_id:
            return {"error": "player_id required", "table": table.snapshot()}
        table.place_bet(player_id, int(message.payload["amount"]))
        table.start_round()
        await self.sync_table(table.table_id)
        return {"table": table.snapshot()}

    def enforce_turn(self, table: Table, player_id: str) -> dict | None:
        current = table.current_player()
        if current is None or player_id != current.player_id:
            return {"error": "not your turn", "table": table.snapshot()}
        return None

    async def client_hit(self, message: Message) -> dict:
        table = self.find_table(message)
        if table is None:
            return self.unknown_table_error(message)
        if not self.is_game_master(table.table_id):
            return await self.forward_to_master(message, table.table_id)
        player_id = message.payload.get("player_id")
        if not player_id:
            return {"error": "player_id required", "table": table.snapshot()}
        guard = self.enforce_turn(table, player_id)
        if guard is not None:
            return guard
        table.hit(player_id)
        await self.sync_table(table.table_id)
        return {"table": table.snapshot()}

    async def client_stand(self, message: Message) -> dict:
        table = self.find_table(message)
        if table is None:
            return self.unknown_table_error(message)
        if not self.is_game_master(table.table_id):
            return await self.forward_to_master(message, table.table_id)
        player_id = message.payload.get("player_id")
        if not player_id:
            return {"error": "player_id required", "table": table.snapshot()}
        guard = self.enforce_turn(table, player_id)
        if guard is not None:
            return guard
        table.stand(player_id)
        await self.sync_table(table.table_id)
        return {"table": table.snapshot()}

    async def client_double(self, message: Message) -> dict:
        table = self.find_table(message)
        if table is None:
            return self.unknown_table_error(message)
        if not self.is_game_master(table.table_id):
            return await self.forward_to_master(message, table.table_id)
        player_id = message.payload.get("player_id")
        if not player_id:
            return {"error": "player_id required", "table": table.snapshot()}
        guard = self.enforce_turn(table, player_id)
        if guard is not None:
            return guard
        table.double(player_id)
        await self.sync_table(table.table_id)
        return {"table": table.snapshot()}

    async def client_split(self, message: Message) -> dict:
        table = self.find_table(message)
        if table is None:
            return self.unknown_table_error(message)
        if not self.is_game_master(table.table_id):
            return await self.forward_to_master(message, table.table_id)
        player_id = message.payload.get("player_id")
        if not player_id:
            return {"error": "player_id required", "table": table.snapshot()}
        guard = self.enforce_turn(table, player_id)
        if guard is not None:
            return guard
        table.split(player_id)
        await self.sync_table(table.table_id)
        return {"table": table.snapshot()}

    async def client_refill_balance(self, message: Message) -> dict:
        table = self.find_table(message)
        if table is None:
            return self.unknown_table_error(message)
        if not self.is_game_master(table.table_id):
            return await self.forward_to_master(message, table.table_id)
        player_id = message.payload.get("player_id")
        if not player_id:
            return {"error": "player_id required", "table": table.snapshot()}
        table.refill(player_id, int(message.payload.get("amount", 1000)))
        await self.sync_table(table.table_id)
        return {"table": table.snapshot()}

    async def peer_announce(self, message: Message) -> dict:
        self.state.upsert_peer(Peer(**message.payload))
        return {"peer": self.state.local_peer().__dict__, "tables": self.serialized_tables()}

    async def peer_heartbeat(self, message: Message) -> dict:
        self.state.upsert_peer(Peer(**message.payload["peer"]))
        return {
            "peer": self.state.local_peer().__dict__,
            "tables": self.stale_tables_for(message.payload.get("tables", {})),
        }

    def stale_tables_for(self, remote_versions: dict) -> list[dict]:
        """Full snapshots of tables this server masters and the sender lags behind on."""
        stale = []
        for table_id, table in self.state.tables.items():
            if not self.is_game_master(table_id):
                continue
            remote = remote_versions.get(table_id)
            if remote is None or remote.get("lineage") != table.lineage or remote.get("version", 0) < table.state_version:
                stale.append(table.to_dict())
        return stale

    async def peer_state_sync(self, message: Message) -> dict:
        self.state.apply_snapshot(message.payload["table"])
        return {"state_version": message.payload["table"]["state_version"]}

    async def peer_get_tables(self, message: Message) -> dict:
        return {"tables": self.serialized_tables()}

    async def peer_election(self, message: Message) -> dict:
        caller = int(message.sender)
        if self.state.server_id > caller:
            asyncio.create_task(self.run_election())
            return {"status": "OK"}
        return {"status": "IGNORED"}

    async def peer_coordinator(self, message: Message) -> dict:
        new_master = int(message.payload["server_id"])
        now = time.time()
        # Reject a stale coordinator claim if we know of a genuinely alive
        # server with a higher id (it will reclaim via its own election).
        higher_alive = self.state.server_id > new_master or any(
            peer.server_id > new_master and now - peer.last_seen <= self.config.heartbeat_timeout
            for peer in self.state.peers.values()
        )
        if higher_alive:
            return {"status": "REJECTED"}
        for table in self.state.tables.values():
            table.game_master_id = new_master
        self.election_running = False
        return {"status": "COORDINATOR_ACCEPTED"}

    async def discovery_loop(self) -> None:
        while True:
            await self.announce_to_known_ports()
            await asyncio.sleep(2.0)

    async def announce_to_known_ports(self) -> None:
        payload = self.state.local_peer().__dict__
        for port in self.nearby_peer_ports():
            if port != self.config.server_port:
                response = await self.request("127.0.0.1", port, Message("SERVER_ANNOUNCE", str(self.state.server_id), payload))
                self.learn_from_response(response)

    async def start_udp_discovery(self) -> None:
        loop = asyncio.get_running_loop()
        await loop.create_datagram_endpoint(
            lambda: DiscoveryProtocol(self),
            local_addr=("0.0.0.0", self.discovery_port),
            allow_broadcast=True,
        )

    def nearby_peer_ports(self) -> list[int]:
        base = self.config.server_port - (self.config.server_port % 10)
        return list(range(base, base + 10))

    async def heartbeat_loop(self) -> None:
        while True:
            await self.send_heartbeats()
            self.prune_dead_peers()
            await self.detect_failed_master()
            await asyncio.sleep(self.config.heartbeat_interval)

    def table_versions(self) -> dict:
        return {
            table_id: {"lineage": table.lineage, "version": table.state_version}
            for table_id, table in self.state.tables.items()
        }

    async def send_heartbeats(self) -> None:
        payload = {"peer": self.state.local_peer().__dict__, "tables": self.table_versions()}
        peers = list(self.state.peers.values())
        responses = await asyncio.gather(
            *[self.request(peer.host, peer.server_port, Message("HEARTBEAT", str(self.state.server_id), payload)) for peer in peers]
        )
        for peer, response in zip(peers, responses):
            if response:
                peer.touch()
                # The response repairs any table we are behind on (anti-entropy).
                self.learn_from_response(response)

    def prune_dead_peers(self) -> None:
        now = time.time()
        for server_id, peer in list(self.state.peers.items()):
            if now - peer.last_seen > self.config.heartbeat_timeout:
                del self.state.peers[server_id]

    async def detect_failed_master(self) -> None:
        now = time.time()
        for table in self.state.tables.values():
            master = table.game_master_id
            peer = self.state.peers.get(master)
            master_missing = master != self.state.server_id and (peer is None or now - peer.last_seen > self.config.heartbeat_timeout)
            # A higher-id peer that just recovered outranks the current master
            # and must reclaim the role, per the bully algorithm.
            master_outranked = master != self.state.highest_active_server_id()
            if master_missing or master_outranked:
                await self.run_election()

    async def turn_timer_loop(self) -> None:
        while True:
            await self.expire_overdue_turns()
            await asyncio.sleep(1.0)

    async def expire_overdue_turns(self) -> None:
        now = time.time()
        for table_id, table in list(self.state.tables.items()):
            if not self.is_game_master(table_id):
                continue
            if table.phase != "playing" or table.turn_deadline is None or now < table.turn_deadline:
                continue
            current = table.current_player()
            if current is not None:
                table.stand(current.player_id)
                await self.sync_table(table_id)

    async def run_election(self) -> None:
        if self.election_running:
            return
        self.election_running = True
        higher = [peer for peer in self.state.peers.values() if peer.server_id > self.state.server_id]
        responses = await asyncio.gather(
            *[self.request(peer.host, peer.server_port, Message("ELECTION", str(self.state.server_id), {})) for peer in higher]
        )
        got_ok = any(response and response.get("status") == "OK" for response in responses)
        if got_ok:
            await asyncio.sleep(self.config.election_timeout)
        if not got_ok or self.state.server_id == self.state.highest_active_server_id():
            await self.become_coordinator()
        self.election_running = False

    async def become_coordinator(self) -> None:
        # Read repair: adopt the freshest table state from all reachable peers
        # before taking over, so a backup that missed the old master's last
        # sync cannot make us resurrect stale state.
        await self.pull_latest_tables()
        for table in self.state.tables.values():
            table.game_master_id = self.state.server_id
            table.bump()
        message = Message("COORDINATOR", str(self.state.server_id), {"server_id": self.state.server_id})
        await asyncio.gather(*[self.request(peer.host, peer.server_port, message) for peer in self.state.peers.values()])
        for table_id in list(self.state.tables):
            await self.sync_table(table_id)
        print(f"server {self.state.server_id} became game master", flush=True)

    async def pull_latest_tables(self) -> None:
        message = Message("GET_TABLES", str(self.state.server_id), {})
        responses = await asyncio.gather(
            *[self.request(peer.host, peer.server_port, message) for peer in self.state.peers.values()]
        )
        for response in responses:
            for table in (response or {}).get("tables", []):
                self.state.apply_snapshot(table)

    async def sync_table(self, table_id: str) -> None:
        table = self.state.tables[table_id]
        message = Message("STATE_SYNC", str(self.state.server_id), {"table": table.to_dict()})
        await asyncio.gather(*[self.request(peer.host, peer.server_port, message) for peer in self.state.peers.values()])

    async def forward_to_master(self, message: Message, table_id: str) -> dict:
        table = self.state.tables[table_id]
        peer = self.state.peers.get(table.game_master_id)
        if peer is None:
            return {"error": "game master unavailable"}
        return await self.request(peer.host, peer.client_port, message) or {"error": "forward failed"}

    async def request(self, host: str, port: int, message: Message) -> dict | None:
        try:
            reader, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout=1.0)
            await send_message(writer, message)
            response = await asyncio.wait_for(read_message(reader), timeout=1.0)
            writer.close()
            await writer.wait_closed()
            return response.payload if response else None
        except (OSError, TimeoutError, ConnectionError, asyncio.TimeoutError):
            return None

    def learn_from_response(self, response: dict | None) -> None:
        if not response:
            return
        if "peer" in response:
            self.state.upsert_peer(Peer(**response["peer"]))
        for table in response.get("tables", []):
            self.state.apply_snapshot(table)

    def serialized_tables(self) -> list[dict]:
        return [table.to_dict() for table in self.state.tables.values()]

    def is_game_master(self, table_id: str) -> bool:
        return self.state.tables[table_id].game_master_id == self.state.server_id


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a Blackjack Royale server.")
    parser.add_argument("--id", type=int, required=True, help="Unique numeric server id.")
    parser.add_argument("--host", default=DEFAULT_CONFIG.host)
    parser.add_argument("--client-port", type=int, required=True)
    parser.add_argument("--server-port", type=int, required=True)
    parser.add_argument("--discovery-port", type=int)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    discovery_port = args.discovery_port or 9200 + args.id
    server = BlackjackServer(args.id, args.host, args.client_port, args.server_port, discovery_port)
    with contextlib.suppress(KeyboardInterrupt):
        try:
            asyncio.run(server.start())
        except OSError as exc:
            print(
                f"server {args.id} could not start: port already in use or unavailable "
                f"(client={args.client_port}, peer={args.server_port}, discovery={discovery_port}): {exc}",
                flush=True,
            )


if __name__ == "__main__":
    main()

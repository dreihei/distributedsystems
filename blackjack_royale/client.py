"""Command line client for Blackjack Royale."""

from __future__ import annotations

import argparse
import asyncio
import json
from typing import Any

from .config import DEFAULT_CONFIG
from .discovery import discover_servers
from .messages import Message, read_message, send_message


async def send(host: str, port: int, message_type: str, payload: dict[str, Any]) -> dict:
    reader, writer = await asyncio.open_connection(host, port)
    await send_message(writer, Message(message_type, "client", payload))
    response = await read_message(reader)
    writer.close()
    await writer.wait_closed()
    return response.payload if response else {"error": "no response"}


def print_response(response: dict) -> None:
    print(json.dumps(response, indent=2))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Use a Blackjack Royale server.")
    parser.add_argument("--host")
    parser.add_argument("--port", type=int)
    parser.add_argument("--table", default="main")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("discover")
    sub.add_parser("tables")

    join = sub.add_parser("join")
    join.add_argument("--player-id", required=True)
    join.add_argument("--name", required=True)

    bot = sub.add_parser("add-bot")
    bot.add_argument("--bot-id", required=True)
    bot.add_argument("--name", default="Bot")
    bot.add_argument("--amount", type=int, default=50)

    bet = sub.add_parser("bet")
    bet.add_argument("--player-id", required=True)
    bet.add_argument("--amount", type=int, required=True)

    start = sub.add_parser("start")
    start.add_argument("--player-id", default="dealer")

    new_round = sub.add_parser("new-round")
    new_round.add_argument("--player-id", required=True)
    new_round.add_argument("--amount", type=int, required=True)

    hit = sub.add_parser("hit")
    hit.add_argument("--player-id", required=True)

    stand = sub.add_parser("stand")
    stand.add_argument("--player-id", required=True)

    return parser.parse_args()


def to_message(args: argparse.Namespace) -> tuple[str, dict]:
    base = {"table_id": args.table}
    builders = {
        "tables": lambda: ("LIST_TABLES", base),
        "join": lambda: ("JOIN_TABLE", base | {"player_id": args.player_id, "name": args.name}),
        "add-bot": lambda: ("ADD_BOT", base | {"bot_id": args.bot_id, "name": args.name, "amount": args.amount}),
        "bet": lambda: ("PLACE_BET", base | {"player_id": args.player_id, "amount": args.amount}),
        "start": lambda: ("START_ROUND", base | {"player_id": args.player_id}),
        "new-round": lambda: ("NEW_ROUND", base | {"player_id": args.player_id, "amount": args.amount}),
        "hit": lambda: ("HIT", base | {"player_id": args.player_id}),
        "stand": lambda: ("STAND", base | {"player_id": args.player_id}),
    }
    return builders[args.command]()


async def async_main() -> None:
    args = parse_args()
    if args.command == "discover":
        servers = [server.__dict__ for server in discover_servers()]
        print_response({"servers": servers})
        return
    if args.port is None:
        servers = discover_servers()
        if not servers:
            print_response({"error": "no server discovered; pass --host and --port manually"})
            return
        args.host = servers[0].host
        args.port = servers[0].client_port
    if args.host is None:
        args.host = "localhost"
    message_type, payload = to_message(args)
    print_response(await send(args.host, args.port, message_type, payload))


def main() -> None:
    asyncio.run(async_main())


if __name__ == "__main__":
    main()

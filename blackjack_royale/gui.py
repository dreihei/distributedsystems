"""Tkinter control panel for local Blackjack Royale demos."""

from __future__ import annotations

import json
import queue
import subprocess
import sys
import threading
import time
import asyncio
import tkinter as tk
from tkinter import ttk
from typing import Any

from .client import send
from .discovery import discover_servers


SERVER_PRESETS = {
    1: {"client_port": 9001, "server_port": 9101},
    2: {"client_port": 9002, "server_port": 9102},
    3: {"client_port": 9003, "server_port": 9103},
}


class ServerProcess:
    def __init__(self, server_id: int, client_port: int, server_port: int) -> None:
        self.server_id = server_id
        self.client_port = client_port
        self.server_port = server_port
        self.process: subprocess.Popen | None = None

    def start(self) -> None:
        if self.is_running():
            return
        self.process = subprocess.Popen(
            [
                sys.executable,
                "-u",
                "-m",
                "blackjack_royale.server",
                "--id",
                str(self.server_id),
                "--client-port",
                str(self.client_port),
                "--server-port",
                str(self.server_port),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform.startswith("win") else 0,
        )

    def stop(self) -> None:
        if not self.is_running():
            return
        assert self.process is not None
        self.process.terminate()
        try:
            self.process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            self.process.kill()

    def is_running(self) -> bool:
        return self.process is not None and self.process.poll() is None


class BlackjackControlPanel(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Blackjack Royale")
        self.geometry("1120x760")
        self.minsize(980, 680)

        self.servers = {
            server_id: ServerProcess(server_id, preset["client_port"], preset["server_port"])
            for server_id, preset in SERVER_PRESETS.items()
        }
        self.log_queue: queue.Queue[str] = queue.Queue()

        self.selected_port = tk.IntVar(value=9003)
        self.server_host = tk.StringVar(value="localhost")
        self.player_id = tk.StringVar(value="p1")
        self.player_name = tk.StringVar(value="Sergej")
        self.bot_id = tk.StringVar(value="bot1")
        self.bot_name = tk.StringVar(value="DealerBot")
        self.bet_amount = tk.IntVar(value=50)
        self.table_id = tk.StringVar(value="main")
        self.dealer_status = tk.StringVar(value="Dealer: -")
        self.player_status = tk.StringVar(value="You: -")
        self.bot_status = tk.StringVar(value="Bots: -")
        self.round_status = tk.StringVar(value="Round: no table loaded")

        self.build_layout()
        self.after(500, self.refresh_status)
        self.after(200, self.drain_log_queue)

    def build_layout(self) -> None:
        root = ttk.Frame(self, padding=14)
        root.pack(fill="both", expand=True)

        self.build_server_section(root)
        self.build_command_section(root)
        self.build_status_section(root)
        self.build_table_section(root)
        self.build_output_section(root)

    def build_server_section(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="Server")
        frame.pack(fill="x", pady=(0, 10))

        for server_id, server in self.servers.items():
            row = ttk.Frame(frame, padding=6)
            row.pack(fill="x")

            ttk.Label(row, text=f"Server {server_id}", width=10).pack(side="left")
            ttk.Label(row, text=f"Client {server.client_port} / Peer {server.server_port}", width=24).pack(side="left")

            status = ttk.Label(row, text="stopped", width=12)
            status.pack(side="left")
            setattr(self, f"status_{server_id}", status)

            ttk.Button(row, text="Start", command=lambda sid=server_id: self.start_server(sid)).pack(side="left", padx=4)
            ttk.Button(row, text="Stop", command=lambda sid=server_id: self.stop_server(sid)).pack(side="left", padx=4)

        buttons = ttk.Frame(frame, padding=6)
        buttons.pack(fill="x")
        ttk.Button(buttons, text="Start All", command=self.start_all).pack(side="left", padx=4)
        ttk.Button(buttons, text="Stop All", command=self.stop_all).pack(side="left", padx=4)
        ttk.Button(buttons, text="Simulate Game Master Failure", command=lambda: self.stop_server(3)).pack(side="left", padx=4)

    def build_command_section(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="Spiel")
        frame.pack(fill="x", pady=(0, 10))

        form = ttk.Frame(frame, padding=6)
        form.pack(fill="x")

        self.add_entry(form, "Server-Port", self.selected_port, 0)
        self.add_entry(form, "Server-Host", self.server_host, 1)
        self.add_entry(form, "Table", self.table_id, 2)
        self.add_entry(form, "Player ID", self.player_id, 3)
        self.add_entry(form, "Name", self.player_name, 4)
        self.add_entry(form, "Bet", self.bet_amount, 5)
        self.add_entry(form, "Bot ID", self.bot_id, 6)
        self.add_entry(form, "Bot Name", self.bot_name, 7)

        buttons = ttk.Frame(frame, padding=6)
        buttons.pack(fill="x")

        commands = [
            ("Refresh", self.list_tables),
            ("Discover LAN", self.discover_network_servers),
            ("Join Table", self.join_table),
            ("Add Bot", self.add_bot),
            ("Place Bet", self.place_bet),
            ("Start Round", self.start_round),
            ("Hit", self.hit),
            ("Stand", self.stand),
            ("Demo Sequence", self.demo_sequence),
        ]
        for label, command in commands:
            ttk.Button(buttons, text=label, command=command).pack(side="left", padx=4, pady=4)

    def build_output_section(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="Log")
        frame.pack(fill="both")

        self.output = tk.Text(frame, height=7, wrap="word")
        self.output.pack(side="left", fill="both", expand=True)

        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=self.output.yview)
        scrollbar.pack(side="right", fill="y")
        self.output.configure(yscrollcommand=scrollbar.set)

    def build_table_section(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="Blackjack Table")
        frame.pack(fill="both", expand=True, pady=(0, 10))

        self.table_canvas = tk.Canvas(frame, height=360, bg="#146b4a", highlightthickness=0)
        self.table_canvas.pack(fill="both", expand=True)
        self.draw_empty_table()

    def build_status_section(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="Aktueller Stand")
        frame.pack(fill="x", pady=(0, 10))

        labels = [
            (self.round_status, 30),
            (self.dealer_status, 26),
            (self.player_status, 36),
            (self.bot_status, 46),
        ]
        for variable, width in labels:
            ttk.Label(frame, textvariable=variable, width=width).pack(side="left", padx=8, pady=8)

    def add_entry(self, parent: ttk.Frame, label: str, variable: tk.Variable, column: int) -> None:
        cell = ttk.Frame(parent)
        cell.grid(row=0, column=column, padx=5, sticky="ew")
        ttk.Label(cell, text=label).pack(anchor="w")
        ttk.Entry(cell, textvariable=variable, width=16).pack(fill="x")

    def start_server(self, server_id: int) -> None:
        self.servers[server_id].start()
        self.watch_server_output(server_id)
        self.log(f"started server {server_id}")

    def stop_server(self, server_id: int) -> None:
        self.servers[server_id].stop()
        self.log(f"stopped server {server_id}")

    def start_all(self) -> None:
        for server_id in self.servers:
            self.start_server(server_id)
        self.log("all servers requested; wait 3 to 5 seconds, then click Demo Sequence")

    def stop_all(self) -> None:
        for server_id in self.servers:
            self.stop_server(server_id)

    def watch_server_output(self, server_id: int) -> None:
        server = self.servers[server_id]
        if server.process is None or server.process.stdout is None:
            return
        threading.Thread(target=self.read_server_output, args=(server_id, server.process), daemon=True).start()

    def read_server_output(self, server_id: int, process: subprocess.Popen) -> None:
        assert process.stdout is not None
        for line in process.stdout:
            self.log_queue.put(f"[server {server_id}] {line.rstrip()}")

    def list_tables(self) -> None:
        self.run_client_command("LIST_TABLES", {"table_id": self.table_id.get()})

    def discover_network_servers(self) -> None:
        servers = discover_servers()
        self.log_queue.put(json.dumps({"servers": [server.__dict__ for server in servers]}, indent=2))
        if servers:
            self.server_host.set(servers[0].host)
            self.selected_port.set(servers[0].client_port)

    def join_table(self) -> None:
        self.run_client_command("JOIN_TABLE", self.base_player_payload() | {"name": self.player_name.get()})

    def add_bot(self) -> None:
        payload = {
            "table_id": self.table_id.get(),
            "bot_id": self.bot_id.get(),
            "name": self.bot_name.get(),
            "amount": self.bet_amount.get(),
        }
        self.run_client_command("ADD_BOT", payload)

    def place_bet(self) -> None:
        self.run_client_command("PLACE_BET", self.base_player_payload() | {"amount": self.bet_amount.get()})

    def start_round(self) -> None:
        self.run_client_command("START_ROUND", {"table_id": self.table_id.get()})

    def new_round(self) -> None:
        self.run_client_command("NEW_ROUND", self.base_player_payload() | {"amount": self.bet_amount.get()})

    def hit(self) -> None:
        self.run_client_command("HIT", self.base_player_payload())

    def stand(self) -> None:
        self.run_client_command("STAND", self.base_player_payload())

    def demo_sequence(self) -> None:
        steps = [
            ("JOIN_TABLE", self.base_player_payload() | {"name": self.player_name.get()}),
            ("PLACE_BET", self.base_player_payload() | {"amount": self.bet_amount.get()}),
            ("START_ROUND", {"table_id": self.table_id.get()}),
            ("LIST_TABLES", {"table_id": self.table_id.get()}),
        ]
        threading.Thread(target=self.run_demo_steps, args=(steps,), daemon=True).start()

    def run_demo_steps(self, steps: list[tuple[str, dict]]) -> None:
        for message_type, payload in steps:
            self.send_and_log(message_type, payload)
            time.sleep(0.3)

    def run_client_command(self, message_type: str, payload: dict) -> None:
        threading.Thread(target=self.send_and_log, args=(message_type, payload), daemon=True).start()

    def send_and_log(self, message_type: str, payload: dict) -> None:
        ports = self.command_ports()
        try:
            response = asyncio.run(send(self.server_host.get(), ports[0], message_type, payload))
            formatted = json.dumps(response, indent=2)
            self.queue_table_draw(response)
            self.log_queue.put(f"> {message_type} on port {ports[0]}\n{formatted}")
        except OSError as exc:
            self.try_fallback_ports(message_type, payload, ports[1:], exc)

    def command_ports(self) -> list[int]:
        selected = self.selected_port.get()
        running_ports = [
            server.client_port
            for server in sorted(self.servers.values(), key=lambda item: item.server_id, reverse=True)
            if server.is_running()
        ]
        return [selected, *[port for port in running_ports if port != selected]]

    def try_fallback_ports(self, message_type: str, payload: dict, ports: list[int], first_error: OSError) -> None:
        for port in ports:
            try:
                response = asyncio.run(send(self.server_host.get(), port, message_type, payload))
                formatted = json.dumps(response, indent=2)
                self.selected_port.set(port)
                self.queue_table_draw(response)
                self.log_queue.put(f"> {message_type} on fallback port {port}\n{formatted}")
                return
            except OSError:
                continue
        self.log_queue.put(f"> {message_type}\nconnection failed: {first_error}")

    def base_player_payload(self) -> dict:
        return {"table_id": self.table_id.get(), "player_id": self.player_id.get()}

    def refresh_status(self) -> None:
        for server_id, server in self.servers.items():
            status = getattr(self, f"status_{server_id}")
            status.configure(text="running" if server.is_running() else "stopped")
        self.after(500, self.refresh_status)

    def drain_log_queue(self) -> None:
        while not self.log_queue.empty():
            item = self.log_queue.get()
            if isinstance(item, tuple) and item[0] == "DRAW":
                self.draw_table(item[1])
            else:
                self.log(item)
        self.after(200, self.drain_log_queue)

    def log(self, text: str) -> None:
        self.output.insert("end", text + "\n\n")
        self.output.see("end")

    def queue_table_draw(self, response: dict) -> None:
        table = self.extract_table(response)
        if table:
            self.log_queue.put(("DRAW", table))

    def extract_table(self, response: dict) -> dict | None:
        if "table" in response:
            return response["table"]
        tables = response.get("tables", [])
        return tables[0] if tables else None

    def draw_empty_table(self) -> None:
        self.table_canvas.delete("all")
        self.table_canvas.create_text(490, 135, text="No table loaded", fill="white", font=("Segoe UI", 18, "bold"))

    def draw_table(self, table: dict[str, Any]) -> None:
        self.update_status_labels(table)
        canvas = self.table_canvas
        canvas.delete("all")
        width = max(canvas.winfo_width(), 900)
        height = max(canvas.winfo_height(), 360)
        canvas.create_rectangle(0, 0, width, height, fill="#146b4a", outline="")
        canvas.create_oval(26, 36, width - 26, height + 170, outline="#d8b45d", width=4)
        canvas.create_text(20, 16, anchor="nw", text=f"Table {table['table_id']} | Game Master {table['game_master_id']} | {table['phase']}", fill="white", font=("Segoe UI", 13, "bold"))

        dealer_cards = table.get("dealer_hand", [])
        dealer_value = table.get("dealer_value", 0)
        self.current_dealer_action = table.get("dealer_action", "waiting")
        self.draw_hand("Dealer", dealer_cards, dealer_value, width // 2 - 120, 54)

        players = table.get("players", {})
        humans = [(pid, player) for pid, player in players.items() if not player.get("is_bot")]
        bots = [(pid, player) for pid, player in players.items() if player.get("is_bot")]

        x = 46
        y = 188
        for player_id, player in humans:
            label = f"{player['name']} ({player_id})"
            if player_id == self.player_id.get():
                label += " - YOU"
            details = f"value {player['value']} | bet {player['bet']} | balance {player['balance']}"
            self.draw_player(label, details, player.get("hand", []), x, y)
            x += 330
            if x > width - 300:
                x = 40
                y += 120

        bot_x = 46
        bot_y = max(285, y + 108 if humans else 188)
        for player_id, player in bots:
            label = f"{player['name']} ({player_id}) - BOT"
            details = f"value {player['value']} | bet {player['bet']} | balance {player['balance']}"
            self.draw_player(label, details, player.get("hand", []), bot_x, bot_y)
            bot_x += 330
            if bot_x > width - 300:
                bot_x = 40
                bot_y += 120

        if table.get("last_result"):
            self.draw_last_result(table["last_result"], width - 318, 54)

    def update_status_labels(self, table: dict[str, Any]) -> None:
        self.round_status.set(f"Round: {table['phase']} | GM {table['game_master_id']}")
        self.dealer_status.set(
            f"Dealer: {table.get('dealer_value', 0)} ({len(table.get('dealer_hand', []))} cards) | {table.get('dealer_action', 'waiting')}"
        )

        players = table.get("players", {})
        own = players.get(self.player_id.get())
        if own:
            self.player_status.set(
                f"You: {own['value']} | bet {own['bet']} | balance {own['balance']} | cards {len(own.get('hand', []))}"
            )
        else:
            self.player_status.set("You: not joined")

        bot_parts = [
            f"{player['name']} {player['value']}"
            for player in players.values()
            if player.get("is_bot")
        ]
        self.bot_status.set("Bots: " + (", ".join(bot_parts) if bot_parts else "none"))

    def draw_player(self, label: str, details: str, cards: list[str], x: int, y: int) -> None:
        canvas = self.table_canvas
        canvas.create_text(x, y, anchor="nw", text=label, fill="white", font=("Segoe UI", 11, "bold"))
        canvas.create_text(x, y + 20, anchor="nw", text=details, fill="#e7f8ef", font=("Segoe UI", 9))
        self.draw_cards(cards, x, y + 42)

    def draw_hand(self, label: str, cards: list[str], value: int, x: int, y: int) -> None:
        action = ""
        if label == "Dealer":
            action = f" | {getattr(self, 'current_dealer_action', '')}"
        self.table_canvas.create_text(x, y, anchor="nw", text=f"{label} | value {value}{action}", fill="white", font=("Segoe UI", 11, "bold"))
        self.draw_cards(cards, x, y + 24)

    def draw_cards(self, cards: list[str], x: int, y: int) -> None:
        for index, card in enumerate(cards):
            cx = x + index * 56
            color = "#b2182b" if "hearts" in card or "diamonds" in card else "#111111"
            self.table_canvas.create_rectangle(cx, y, cx + 46, y + 66, fill="white", outline="#222222", width=2)
            rank = card.split(" of ")[0]
            suit = card.split(" of ")[1][0].upper() if " of " in card else "?"
            self.table_canvas.create_text(cx + 23, y + 22, text=rank, fill=color, font=("Segoe UI", 13, "bold"))
            self.table_canvas.create_text(cx + 23, y + 46, text=suit, fill=color, font=("Segoe UI", 11))

    def draw_last_result(self, result: dict[str, Any], x: int, y: int) -> None:
        lines = [
            "Last round",
            f"Dealer {result['dealer_value']} {'bust' if result.get('dealer_bust') else ''}".strip(),
        ]
        for player in result.get("players", {}).values():
            lines.append(f"{player['name']}: {player['outcome']} payout {player['payout']}")
        self.table_canvas.create_rectangle(x, y, x + 280, y + 120, fill="#0b3d2c", outline="#d9f2e4")
        for offset, line in enumerate(lines[:5]):
            font = ("Segoe UI", 10, "bold") if offset == 0 else ("Segoe UI", 9)
            self.table_canvas.create_text(x + 10, y + 10 + offset * 22, anchor="nw", text=line, fill="white", font=font)

    def destroy(self) -> None:
        self.stop_all()
        super().destroy()


def main() -> None:
    app = BlackjackControlPanel()
    app.mainloop()


if __name__ == "__main__":
    main()

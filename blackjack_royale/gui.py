"""Tkinter control panel for local Blackjack Royale demos."""

from __future__ import annotations

import json
import queue
import socket
import subprocess
import sys
import threading
import time
import asyncio
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Any

from .client import send
from .discovery import discover_servers


SERVER_PRESETS = {
    1: {"client_port": 9001, "server_port": 9101},
    2: {"client_port": 9002, "server_port": 9102},
    3: {"client_port": 9003, "server_port": 9103},
}
ACTION_REPLAY_DELAY_MS = 1800


class ServerProcess:
    def __init__(self, server_id: int, client_port: int, server_port: int) -> None:
        self.server_id = server_id
        self.client_port = client_port
        self.server_port = server_port
        self.discovery_port = 9200 + server_id
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

    def cleanup_finished_process(self) -> None:
        if self.process is not None and self.process.poll() is not None:
            self.process = None


class BlackjackControlPanel(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Blackjack Royale")
        self.geometry("1280x800")
        self.minsize(600, 500)

        self.servers = {
            server_id: ServerProcess(server_id, preset["client_port"], preset["server_port"])
            for server_id, preset in SERVER_PRESETS.items()
        }
        self.log_queue: queue.Queue[str] = queue.Queue()
        self.action_seen_counts: dict[str, int] = {}
        self.animation_running = False

        self.sidebar_visible = True
        self.sidebar_frame: ttk.Frame | None = None
        self.toggle_strip_frame: ttk.Frame | None = None
        self.toggle_btn: ttk.Button | None = None

        self.selected_port = tk.IntVar(value=9003)
        self.server_host = tk.StringVar(value="localhost")
        self.player_id = tk.StringVar(value="p1")
        self.player_name = tk.StringVar(value="Sergej")
        self.bot_name = tk.StringVar(value="DealerBot")
        self.bet_amount = tk.IntVar(value=50)
        self.table_id = tk.StringVar(value="main")
        self.cluster_status = tk.StringVar(value="Cluster: no table loaded")
        self.dealer_status = tk.StringVar(value="Dealer: -")
        self.player_status = tk.StringVar(value="You: -")
        self.bot_status = tk.StringVar(value="Bots: -")
        self.round_status = tk.StringVar(value="Round: no table loaded")
        self.action_status = tk.StringVar(value="Actions: waiting")
        self.command_buttons: dict[str, ttk.Button] = {}
        self.action_history: tk.Text | None = None
        self.player_id_entry: ttk.Entry | None = None
        self.turn_status = tk.StringVar(value="Turn: -")
        self._turn_deadline: float | None = None
        self._current_player_for_turn: str | None = None

        self.known_tables: dict[str, dict] = {}
        self.tables_panel_visible = True
        self.tables_panel_content: ttk.Frame | None = None
        self.tables_toggle_btn: ttk.Button | None = None

        self.build_layout()
        self.prompt_for_name()
        self.after(500, self.refresh_status)
        self.after(200, self.drain_log_queue)
        self.after(1000, self.tick_turn_countdown)
        self.after(1000, self.poll_current_table)

    def build_layout(self) -> None:
        outer = ttk.Frame(self, padding=0)
        outer.pack(fill="both", expand=True)

        # Left sidebar (fixed 300px wide, scrollable)
        self.sidebar_frame = ttk.Frame(outer, width=300)
        self.sidebar_frame.pack(side="left", fill="y")
        self.sidebar_frame.pack_propagate(False)
        self._build_sidebar_content(self.sidebar_frame)

        # Narrow toggle strip (always visible)
        self.toggle_strip_frame = ttk.Frame(outer, width=22)
        self.toggle_strip_frame.pack(side="left", fill="y")
        self.toggle_strip_frame.pack_propagate(False)
        self.toggle_btn = ttk.Button(self.toggle_strip_frame, text="◄", width=2, command=self.toggle_sidebar)
        self.toggle_btn.pack(fill="y", expand=True)

        # Right area: board + action history + log
        main = ttk.Frame(outer)
        main.pack(side="left", fill="both", expand=True)

        board_frame = ttk.LabelFrame(main, text="Blackjack Table")
        board_frame.pack(fill="both", expand=True)
        self.table_canvas = tk.Canvas(board_frame, bg="#146b4a", highlightthickness=0)
        self.table_canvas.pack(fill="both", expand=True)
        self.draw_empty_table()

        self.build_action_section(main)
        self.build_output_section(main)

    def _build_sidebar_content(self, parent: ttk.Frame) -> None:
        scroll_canvas = tk.Canvas(parent, highlightthickness=0)
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=scroll_canvas.yview)
        scroll_canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        scroll_canvas.pack(side="left", fill="both", expand=True)

        inner = ttk.Frame(scroll_canvas)
        win_id = scroll_canvas.create_window((0, 0), window=inner, anchor="nw")

        inner.bind("<Configure>", lambda e: scroll_canvas.configure(scrollregion=scroll_canvas.bbox("all")))
        scroll_canvas.bind("<Configure>", lambda e: scroll_canvas.itemconfigure(win_id, width=e.width))
        scroll_canvas.bind_all("<MouseWheel>", lambda e: scroll_canvas.yview_scroll(-1 * (e.delta // 120), "units"))

        self.build_server_section(inner)
        self.build_status_section(inner)
        self.build_tables_section(inner)
        self.build_connection_section(inner)
        self.build_player_section(inner)
        self.build_bot_section(inner)
        self.build_gameplay_section(inner)
        self.build_demo_section(inner)

    def toggle_sidebar(self) -> None:
        assert self.sidebar_frame is not None
        assert self.toggle_strip_frame is not None
        assert self.toggle_btn is not None
        if self.sidebar_visible:
            self.sidebar_frame.pack_forget()
            self.toggle_btn.configure(text="►")
            self.sidebar_visible = False
        else:
            self.sidebar_frame.pack(side="left", fill="y", before=self.toggle_strip_frame)
            self.toggle_btn.configure(text="◄")
            self.sidebar_visible = True

    def build_server_section(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="Servers")
        frame.pack(fill="x", pady=(0, 6), padx=4)

        for server_id, server in self.servers.items():
            row = ttk.Frame(frame, padding=(4, 2))
            row.pack(fill="x")

            ttk.Label(row, text=f"S{server_id}", width=3).pack(side="left")
            ttk.Label(row, text=f"{server.client_port}/{server.server_port}", width=10).pack(side="left")

            status = ttk.Label(row, text="stopped", width=10)
            status.pack(side="left")
            setattr(self, f"status_{server_id}", status)

            ttk.Button(row, text="Start", width=5, command=lambda sid=server_id: self.start_server(sid)).pack(side="left", padx=2)
            ttk.Button(row, text="Stop", width=5, command=lambda sid=server_id: self.stop_server(sid)).pack(side="left", padx=2)

        buttons = ttk.Frame(frame, padding=(4, 4))
        buttons.pack(fill="x")
        ttk.Button(buttons, text="Start All", command=self.start_all).pack(side="left", padx=2)
        ttk.Button(buttons, text="Stop All", command=self.stop_all).pack(side="left", padx=2)
        ttk.Button(buttons, text="Fail GM", command=lambda: self.stop_server(3)).pack(side="left", padx=2)

    def build_tables_section(self, parent: ttk.Frame) -> None:
        outer = ttk.Frame(parent)
        outer.pack(fill="x", pady=(0, 6), padx=4)

        header = ttk.Frame(outer)
        header.pack(fill="x")
        ttk.Label(header, text="Tables", font=("Segoe UI", 9, "bold")).pack(side="left", padx=4, pady=4)
        self.tables_toggle_btn = ttk.Button(header, text="▲", width=2, command=self.toggle_tables_panel)
        self.tables_toggle_btn.pack(side="right", padx=4)

        self.tables_panel_content = ttk.Frame(outer)
        self.tables_panel_content.pack(fill="x")
        ttk.Label(self.tables_panel_content, text="No tables — click Refresh", foreground="#888888").pack(
            anchor="w", padx=6, pady=2
        )

    def toggle_tables_panel(self) -> None:
        assert self.tables_panel_content is not None
        assert self.tables_toggle_btn is not None
        if self.tables_panel_visible:
            self.tables_panel_content.pack_forget()
            self.tables_toggle_btn.configure(text="▼")
            self.tables_panel_visible = False
        else:
            self.tables_panel_content.pack(fill="x")
            self.tables_toggle_btn.configure(text="▲")
            self.tables_panel_visible = True

    def update_tables_panel(self, tables: list[dict]) -> None:
        for table in tables:
            self.known_tables[table["table_id"]] = table
        if self.tables_panel_content is None:
            return
        for child in self.tables_panel_content.winfo_children():
            child.destroy()
        if not self.known_tables:
            ttk.Label(self.tables_panel_content, text="No tables", foreground="#888888").pack(
                anchor="w", padx=6, pady=2
            )
            return
        for tid, table in self.known_tables.items():
            phase = table.get("phase", "?")
            n_players = len(table.get("players", {}))
            gm = table.get("game_master_id", "?")
            is_active = tid == self.table_id.get()
            label = f"{'▶ ' if is_active else '  '}{tid}  {phase}  {n_players}p  GM{gm}"
            btn = ttk.Button(
                self.tables_panel_content,
                text=label,
                command=lambda t=table: self.switch_to_table(t),
            )
            btn.pack(fill="x", padx=2, pady=1)

    def switch_to_table(self, table: dict) -> None:
        self.table_id.set(table["table_id"])
        self.draw_table(table)
        self.update_tables_panel([])

    def build_status_section(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="Status")
        frame.pack(fill="x", pady=(0, 6), padx=4)

        labels = [
            self.cluster_status,
            self.round_status,
            self.turn_status,
            self.dealer_status,
            self.player_status,
            self.bot_status,
        ]
        for variable in labels:
            ttk.Label(frame, textvariable=variable, anchor="w", wraplength=270).pack(
                fill="x", padx=6, pady=1
            )

    def build_connection_section(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="Connection")
        frame.pack(fill="x", pady=(0, 6), padx=4)

        self.add_entry(frame, "Server-Port", self.selected_port)
        self.add_entry(frame, "Server-Host", self.server_host)
        self.add_entry(frame, "Table", self.table_id)

        buttons = ttk.Frame(frame, padding=(4, 2))
        buttons.pack(fill="x")
        ttk.Button(buttons, text="Refresh", command=self.list_tables).pack(side="left", padx=2, pady=2)
        ttk.Button(buttons, text="Discover LAN", command=self.discover_network_servers).pack(side="left", padx=2, pady=2)

    def build_player_section(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="Player")
        frame.pack(fill="x", pady=(0, 6), padx=4)

        self.player_id_entry = self.add_entry(frame, "Player ID", self.player_id)
        self.add_entry(frame, "Name", self.player_name)
        self.add_entry(frame, "Bet", self.bet_amount)

        buttons = ttk.Frame(frame, padding=(4, 2))
        buttons.pack(fill="x")
        ttk.Button(buttons, text="Join Table", command=self.join_table).pack(side="left", padx=2, pady=2)
        ttk.Button(buttons, text="Place Bet", command=self.place_bet).pack(side="left", padx=2, pady=2)

    def build_bot_section(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="Bot")
        frame.pack(fill="x", pady=(0, 6), padx=4)

        self.add_entry(frame, "Bot Name", self.bot_name)

        buttons = ttk.Frame(frame, padding=(4, 2))
        buttons.pack(fill="x")
        ttk.Button(buttons, text="Add Bot", command=self.add_bot).pack(side="left", padx=2, pady=2)

    def build_gameplay_section(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="Player Actions")
        frame.pack(fill="x", pady=(0, 6), padx=4)
        buttons = ttk.Frame(frame, padding=(4, 4))
        buttons.pack(fill="x")
        for label, command in [
            ("Start Round", self.start_round),
            ("Hit", self.hit),
            ("Stand", self.stand),
            ("Double", self.double),
            ("Split", self.split),
        ]:
            button = ttk.Button(buttons, text=label, command=command)
            button.pack(side="left", padx=2, pady=2)
            self.command_buttons[label] = button

    def build_demo_section(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="Demo")
        frame.pack(fill="x", pady=(0, 6), padx=4)
        buttons = ttk.Frame(frame, padding=(4, 4))
        buttons.pack(fill="x")
        ttk.Button(buttons, text="Demo Sequence", command=self.demo_sequence).pack(side="left", padx=2, pady=2)

    def build_action_section(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="Visible Actions")
        frame.pack(fill="x", pady=(4, 0))
        ttk.Label(frame, textvariable=self.action_status).pack(anchor="w", padx=8, pady=4)
        history_frame = ttk.Frame(frame, padding=(8, 0, 8, 8))
        history_frame.pack(fill="x")
        self.action_history = tk.Text(history_frame, height=4, wrap="word", state="disabled")
        self.action_history.pack(side="left", fill="x", expand=True)
        scrollbar = ttk.Scrollbar(history_frame, orient="vertical", command=self.action_history.yview)
        scrollbar.pack(side="right", fill="y")
        self.action_history.configure(yscrollcommand=scrollbar.set)

    def build_output_section(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="Log")
        frame.pack(fill="x", pady=(4, 0))

        self.output = tk.Text(frame, height=5, wrap="word")
        self.output.pack(side="left", fill="both", expand=True)

        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=self.output.yview)
        scrollbar.pack(side="right", fill="y")
        self.output.configure(yscrollcommand=scrollbar.set)

    def add_entry(self, parent: ttk.Frame, label: str, variable: tk.Variable) -> ttk.Entry:
        cell = ttk.Frame(parent)
        cell.pack(fill="x", padx=6, pady=2)
        ttk.Label(cell, text=label).pack(anchor="w")
        entry = ttk.Entry(cell, textvariable=variable, width=20)
        entry.pack(fill="x")
        return entry

    def start_server(self, server_id: int) -> None:
        server = self.servers[server_id]
        server.cleanup_finished_process()
        blocked = self.blocked_server_ports(server)
        if blocked:
            self.log(
                f"server {server_id} is already reachable or its port(s) are in use: {', '.join(blocked)}. "
                "Using it as an external server if it responds to game commands."
            )
            return
        server.start()
        self.watch_server_output(server_id)
        self.log(f"started server {server_id}")

    def stop_server(self, server_id: int) -> None:
        server = self.servers[server_id]
        if not server.is_running() and self.server_ports_in_use(server):
            self.log(f"server {server_id} is running outside this GUI; stop that process from its terminal or task manager")
            return
        server.stop()
        self.log(f"stopped server {server_id}")

    def blocked_server_ports(self, server: ServerProcess) -> list[str]:
        blocked = []
        if not self.tcp_port_available(server.client_port):
            blocked.append(f"client {server.client_port}")
        if not self.tcp_port_available(server.server_port):
            blocked.append(f"peer {server.server_port}")
        if not self.udp_port_available(server.discovery_port):
            blocked.append(f"discovery {server.discovery_port}")
        return blocked

    def tcp_port_available(self, port: int) -> bool:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.bind(("", port))
            return True
        except OSError:
            return False
        finally:
            sock.close()

    def udp_port_available(self, port: int) -> bool:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.bind(("", port))
            return True
        except OSError:
            return False
        finally:
            sock.close()

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
        self.auto_join()

    def auto_join(self) -> None:
        self.run_client_command("JOIN_TABLE", {"table_id": self.table_id.get(), "name": self.player_name.get()})

    def prompt_for_name(self) -> None:
        dialog = tk.Toplevel(self)
        dialog.title("Enter your name")
        dialog.transient(self)
        dialog.resizable(False, False)
        dialog.protocol("WM_DELETE_WINDOW", lambda: None)

        ttk.Label(dialog, text="Display name:").pack(padx=16, pady=(16, 4))
        name_var = tk.StringVar(value=self.player_name.get())
        entry = ttk.Entry(dialog, textvariable=name_var, width=28)
        entry.pack(padx=16, pady=4)
        error_label = ttk.Label(dialog, text="", foreground="red")
        error_label.pack(padx=16)

        def submit(event: object = None) -> None:
            name = name_var.get().strip()
            if not name:
                error_label.configure(text="Name cannot be empty")
                return
            self.player_name.set(name)
            dialog.grab_release()
            dialog.destroy()
            self.auto_join()

        entry.bind("<Return>", submit)
        ttk.Button(dialog, text="Join", command=submit).pack(pady=(8, 16))
        dialog.grab_set()
        entry.focus_set()

    def handle_join_response(self, assigned_id: str) -> None:
        self.player_id.set(assigned_id)
        if self.player_id_entry is not None:
            self.player_id_entry.configure(state="readonly")
        self.log(f"Joined as {assigned_id}")

    def tick_turn_countdown(self) -> None:
        if self._turn_deadline is None:
            self.turn_status.set("Turn: -")
        else:
            remaining = max(0, int(self._turn_deadline - time.time()))
            who = self._current_player_for_turn or "?"
            label = "you" if who == self.player_id.get() else who
            self.turn_status.set(f"Turn: {label} - {remaining}s left")
        self.after(1000, self.tick_turn_countdown)

    def poll_current_table(self) -> None:
        if not self.animation_running and self.player_id.get() and self.table_id.get():
            self.run_client_command("LIST_TABLES", {"table_id": self.table_id.get()})
        self.after(1000, self.poll_current_table)

    def add_bot(self) -> None:
        payload = {
            "table_id": self.table_id.get(),
            "name": self.bot_name.get(),
            "amount": self.bet_amount.get(),
        }
        self.run_client_command("ADD_BOT", payload)

    def place_bet(self) -> None:
        amount = self.bet_amount.get()
        player_data = self.known_tables.get(self.table_id.get(), {}).get("players", {}).get(self.player_id.get())
        if player_data and amount > player_data["balance"]:
            messagebox.showwarning("Zu wenig Chips", f"Du hast nur {player_data['balance']} Chips. Einsatz angepasst.")
            return
        self.run_client_command("PLACE_BET", self.base_player_payload() | {"amount": amount})

    def start_round(self) -> None:
        self.run_client_command("START_ROUND", {"table_id": self.table_id.get()})

    def new_round(self) -> None:
        self.run_client_command("NEW_ROUND", self.base_player_payload() | {"amount": self.bet_amount.get()})

    def hit(self) -> None:
        self.run_client_command("HIT", self.base_player_payload())

    def stand(self) -> None:
        self.run_client_command("STAND", self.base_player_payload())

    def double(self) -> None:
        self.run_client_command("DOUBLE", self.base_player_payload())

    def split(self) -> None:
        self.run_client_command("SPLIT", self.base_player_payload())

    def refill_balance(self) -> None:
        self.run_client_command("REFILL_BALANCE", self.base_player_payload())

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
            self.queue_table_draw(response, message_type)
            self.log_queue.put(f"> {message_type} on port {ports[0]}\n{formatted}")
        except OSError as exc:
            self.try_fallback_ports(message_type, payload, ports[1:], exc)

    def command_ports(self) -> list[int]:
        selected = self.selected_port.get()
        running_ports = [
            server.client_port
            for server in sorted(self.servers.values(), key=lambda item: item.server_id, reverse=True)
            if server.is_running() or self.server_ports_in_use(server)
        ]
        return [selected, *[port for port in running_ports if port != selected]]

    def try_fallback_ports(self, message_type: str, payload: dict, ports: list[int], first_error: OSError) -> None:
        for port in ports:
            try:
                response = asyncio.run(send(self.server_host.get(), port, message_type, payload))
                formatted = json.dumps(response, indent=2)
                self.selected_port.set(port)
                self.queue_table_draw(response, message_type)
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
            status.configure(text=self.server_status_text(server))
        self.after(500, self.refresh_status)

    def server_status_text(self, server: ServerProcess) -> str:
        if server.is_running():
            return "running"
        if self.server_ports_in_use(server):
            return "running ext"
        return "stopped"

    def server_ports_in_use(self, server: ServerProcess) -> bool:
        return not self.tcp_port_available(server.client_port) or not self.tcp_port_available(server.server_port)

    def drain_log_queue(self) -> None:
        while not self.log_queue.empty():
            item = self.log_queue.get()
            if isinstance(item, tuple) and item[0] == "DRAW":
                self.draw_table(item[1])
            elif isinstance(item, tuple) and item[0] == "ANIMATE":
                self.play_action_sequence(item[1], item[2])
            elif isinstance(item, tuple) and item[0] == "UPDATE_TABLES":
                self.update_tables_panel(item[1])
            elif isinstance(item, tuple) and item[0] == "JOIN_RESULT":
                self.handle_join_response(item[1])
            else:
                self.log(item)
        self.after(200, self.drain_log_queue)

    def log(self, text: str) -> None:
        self.output.insert("end", text + "\n\n")
        self.output.see("end")

    def queue_table_draw(self, response: dict, message_type: str) -> None:
        if message_type == "JOIN_TABLE" and "player_id" in response:
            self.log_queue.put(("JOIN_RESULT", response["player_id"]))

        all_tables = response.get("tables", [])
        if all_tables:
            self.log_queue.put(("UPDATE_TABLES", all_tables))

        table = self.extract_table(response)
        if table:
            self.log_queue.put(("UPDATE_TABLES", [table]))
            actions = self.new_actions(table)
            animated_messages = {"START_ROUND", "HIT", "STAND", "NEW_ROUND", "DOUBLE", "SPLIT"}
            if actions and message_type in animated_messages:
                self.log_queue.put(("ANIMATE", table, actions))
            else:
                self.log_queue.put(("DRAW", table))

    def new_actions(self, table: dict[str, Any]) -> list[dict[str, Any]]:
        table_id = table.get("table_id", "main")
        action_log = table.get("action_log", [])
        seen = self.action_seen_counts.get(table_id, 0)
        if len(action_log) < seen:
            seen = 0
            self.append_action_history("--- New round ---")
        self.action_seen_counts[table_id] = len(action_log)
        return action_log[seen:]

    def append_action_history(self, message: str) -> None:
        if self.action_history is None:
            return
        self.action_history.configure(state="normal")
        self.action_history.insert("end", message + "\n")
        self.action_history.see("end")
        self.action_history.configure(state="disabled")

    def update_gameplay_buttons(self, table: dict) -> None:
        if self.animation_running:
            return
        phase = table.get("phase")
        current_pid = table.get("current_player_id")
        my_pid = self.player_id.get()
        is_my_turn = phase == "playing" and current_pid == my_pid
        player = table.get("players", {}).get(my_pid, {})
        on_split = player.get("on_split_hand", False)
        hand = player.get("hand", [])
        split_hand = player.get("split_hand", [])
        active_hand = split_hand if on_split else hand
        n_cards = len(active_hand)
        balance = player.get("balance", 0)
        bet = player.get("split_bet", 0) if on_split else player.get("bet", 0)

        can_split = (
            is_my_turn
            and n_cards == 2
            and not split_hand
            and len(hand) == 2
            and len(hand) >= 2
            and hand[0].split(" of ")[0] == hand[1].split(" of ")[0]
            and balance > bet
        )

        states = {
            "Start Round": "normal" if phase in ("waiting", "finished") else "disabled",
            "Hit":         "normal" if is_my_turn else "disabled",
            "Stand":       "normal" if is_my_turn else "disabled",
            "Double":      "normal" if is_my_turn and n_cards == 2 and balance > bet else "disabled",
            "Split":       "normal" if can_split else "disabled",
        }
        for label, btn in self.command_buttons.items():
            btn.configure(state=states.get(label, "normal"))

    def check_empty_balance(self, table: dict) -> None:
        if table.get("phase") != "finished":
            return
        player = table.get("players", {}).get(self.player_id.get())
        if player and player.get("balance", 1) <= 0:
            if messagebox.askyesno("Keine Chips mehr", "Du hast keine Chips mehr!\n1000 Chips auffüllen?"):
                self.refill_balance()

    def set_gameplay_buttons_enabled(self, enabled: bool) -> None:
        state = "normal" if enabled and not self.animation_running else "disabled"
        for button in self.command_buttons.values():
            button.configure(state=state)

    def play_action_sequence(self, table: dict[str, Any], actions: list[dict[str, Any]]) -> None:
        self.animation_running = True
        self.set_gameplay_buttons_enabled(False)
        self.draw_table(table, show_result=False)
        self.play_action_step(table, actions, 0)

    def play_action_step(self, table: dict[str, Any], actions: list[dict[str, Any]], index: int) -> None:
        if index >= len(actions):
            self.animation_running = False
            self.draw_table(table, show_result=True)
            self.action_status.set("Actions: completed")
            self.set_gameplay_buttons_enabled(table.get("phase") != "finished")
            if table.get("phase") == "finished" and table.get("last_result"):
                self.show_next_round_popup()
            return
        action = actions[index]
        message = action.get("message", "updated")
        self.action_status.set("Actions: " + message)
        self.append_action_history(message)
        self.draw_table(self.table_for_action(table, action), show_result=False)
        self.after(ACTION_REPLAY_DELAY_MS, lambda: self.play_action_step(table, actions, index + 1))

    def table_for_action(self, table: dict[str, Any], action: dict[str, Any]) -> dict[str, Any]:
        visible = json.loads(json.dumps(table))
        visible["last_result"] = None
        actor = action.get("actor")
        hand = action.get("hand")
        value = action.get("value")
        on_split = action.get("on_split_hand", False)
        if actor == "dealer" and hand is not None:
            visible["current_player_id"] = "dealer"
            visible["dealer_hand"] = hand
            visible["dealer_value"] = value
            visible["dealer_action"] = action.get("action", "drawing")
        elif actor in {"bot", "player"} and hand is not None:
            visible["current_player_id"] = action.get("player_id")
            player = visible.get("players", {}).get(action.get("player_id"))
            if player:
                if on_split:
                    player["split_hand"] = hand
                    player["split_value"] = value
                    player["split_stood"] = action.get("action") in {"stand", "bust"}
                    player["on_split_hand"] = True
                else:
                    player["hand"] = hand
                    player["value"] = value
                    player["stood"] = action.get("action") in {"stand", "bust"}
        return visible

    def show_next_round_popup(self) -> None:
        if messagebox.askyesno("Round finished", "Round finished. Start Next Round?"):
            self.new_round()
        else:
            self.set_gameplay_buttons_enabled(True)

    def extract_table(self, response: dict) -> dict | None:
        if "table" in response:
            return response["table"]
        tables = response.get("tables", [])
        if not tables:
            return None
        match = next((t for t in tables if t.get("table_id") == self.table_id.get()), None)
        return match or tables[0]

    def draw_empty_table(self) -> None:
        self.table_canvas.delete("all")
        self.table_canvas.create_text(490, 135, text="No table loaded", fill="white", font=("Segoe UI", 18, "bold"))

    def draw_table(self, table: dict[str, Any], show_result: bool = True) -> None:
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
        current_player_id = table.get("current_player_id")
        self.current_dealer_action = table.get("dealer_action", "waiting")
        self.draw_hand("Dealer", dealer_cards, dealer_value, width // 2 - 120, 54, active=current_player_id == "dealer")

        players = table.get("players", {})
        humans = [(pid, player) for pid, player in players.items() if not player.get("is_bot")]
        bots = [(pid, player) for pid, player in players.items() if player.get("is_bot")]

        x = 46
        y = 188
        for player_id, player in humans:
            label = f"{player['name']} ({player_id})"
            if player_id == self.player_id.get():
                label += " - YOU"
            on_split = player.get("on_split_hand", False)
            hand_indicator = " [SPLIT HAND]" if on_split else ""
            details = f"value {player['value']}{hand_indicator} | bet {player['bet']} | balance {player['balance']}"
            self.draw_player(label, details, player.get("hand", []), x, y, active=player_id == current_player_id and not on_split)
            split_hand = player.get("split_hand", [])
            if split_hand:
                split_value = player.get("split_value", 0)
                split_details = f"SPLIT | value {split_value} | bet {player.get('split_bet', 0)}"
                self.draw_player(split_details, "", split_hand, x + 340, y, active=player_id == current_player_id and on_split)
                x += 340
            x += 330
            if x > width - 300:
                x = 40
                y += 120

        bot_x = 46
        bot_y = max(285, y + 108 if humans else 188)
        for player_id, player in bots:
            label = f"{player['name']} {str(player_id).upper()}"
            details = f"value {player['value']} | bet {player['bet']} | balance {player['balance']}"
            self.draw_player(label, details, player.get("hand", []), bot_x, bot_y, active=player_id == current_player_id)
            bot_x += 330
            if bot_x > width - 300:
                bot_x = 40
                bot_y += 120

        if show_result and table.get("last_result"):
            self.draw_last_result(table["last_result"], width - 318, 54)

        self.update_gameplay_buttons(table)
        if show_result:
            self.check_empty_balance(table)

    def update_status_labels(self, table: dict[str, Any]) -> None:
        self.cluster_status.set(
            f"Cluster: host {self.server_host.get()} | port {self.selected_port.get()} | GM {table['game_master_id']} | v{table.get('state_version', 0)}"
        )
        self.round_status.set(f"Round: {table['phase']} | GM {table['game_master_id']}")
        self.dealer_status.set(
            f"Dealer: {table.get('dealer_value', 0)} ({len(table.get('dealer_hand', []))} cards) | {table.get('dealer_action', 'waiting')}"
        )

        players = table.get("players", {})
        own = players.get(self.player_id.get())
        if own:
            self.player_status.set(
                f"You: Value {own['value']} | bet {own['bet']} | balance {own['balance']} | cards {len(own.get('hand', []))}"
            )
        else:
            self.player_status.set("You: not joined")

        bot_parts = [
            f"{player['name']} {player['value']}"
            for player in players.values()
            if player.get("is_bot")
        ]
        self.bot_status.set("Bots: " + (", ".join(bot_parts) if bot_parts else "none"))

        self._turn_deadline = table.get("turn_deadline")
        self._current_player_for_turn = table.get("current_player_id")

    def draw_player(self, label: str, details: str, cards: list[str], x: int, y: int, active: bool = False) -> None:
        canvas = self.table_canvas
        if active:
            canvas.create_rectangle(x - 10, y - 8, x + 300, y + 122, fill="#f4c542", outline="#fff7c7", width=3)
            canvas.create_text(x + 250, y, anchor="nw", text="ACTIVE", fill="#17351f", font=("Segoe UI", 9, "bold"))
        canvas.create_text(x, y, anchor="nw", text=label, fill="#17351f" if active else "white", font=("Segoe UI", 11, "bold"))
        canvas.create_text(x, y + 20, anchor="nw", text=details, fill="#17351f" if active else "#e7f8ef", font=("Segoe UI", 9))
        self.draw_cards(cards, x, y + 42)

    def draw_hand(self, label: str, cards: list[str], value: int, x: int, y: int, active: bool = False) -> None:
        action = ""
        if label == "Dealer":
            action = f" | {getattr(self, 'current_dealer_action', '')}"
        if active:
            self.table_canvas.create_rectangle(x - 10, y - 8, x + 300, y + 104, fill="#f4c542", outline="#fff7c7", width=3)
            self.table_canvas.create_text(x + 246, y, anchor="nw", text="ACTIVE", fill="#17351f", font=("Segoe UI", 9, "bold"))
        self.table_canvas.create_text(
            x,
            y,
            anchor="nw",
            text=f"{label} | value {value}{action}",
            fill="#17351f" if active else "white",
            font=("Segoe UI", 11, "bold"),
        )
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
            outcome = player["outcome"]
            payout_label = f"payout {player['payout']}" if outcome != "push" else "push"
            lines.append(f"{player['name']}: {outcome} {payout_label}")
            split = player.get("split_result")
            if split:
                lines.append(f"  split: {split['outcome']} payout {split['payout']}")
        height = max(120, 30 + len(lines) * 22)
        self.table_canvas.create_rectangle(x, y, x + 280, y + height, fill="#0b3d2c", outline="#d9f2e4")
        for offset, line in enumerate(lines[:8]):
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

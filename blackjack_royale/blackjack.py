"""Pure Blackjack rules without networking."""

from __future__ import annotations

import random
import time
import uuid
from dataclasses import dataclass, field

SUITS = ("hearts", "diamonds", "clubs", "spades")
RANKS = ("A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K")


class RuleError(Exception):
    """A game action violated the Blackjack rules or the current table state."""


@dataclass(frozen=True)
class Card:
    rank: str
    suit: str

    def label(self) -> str:
        return f"{self.rank} of {self.suit}"

    def to_dict(self) -> dict:
        return {"rank": self.rank, "suit": self.suit}

    @staticmethod
    def from_dict(raw: dict) -> "Card":
        return Card(rank=raw["rank"], suit=raw["suit"])


def new_deck() -> list[Card]:
    deck = [Card(rank, suit) for suit in SUITS for rank in RANKS]
    random.shuffle(deck)
    return deck


def hand_value(cards: list[Card]) -> int:
    total = 0
    aces = 0
    for card in cards:
        if card.rank == "A":
            aces += 1
            total += 11
        elif card.rank in {"J", "Q", "K"}:
            total += 10
        else:
            total += int(card.rank)

    while total > 21 and aces:
        total -= 10
        aces -= 1
    return total


def is_blackjack(cards: list[Card]) -> bool:
    return len(cards) == 2 and hand_value(cards) == 21


def is_bust(cards: list[Card]) -> bool:
    return hand_value(cards) > 21


def hand_outcome(
    cards: list[Card], bet: int, dealer_hand: list[Card], *, blackjack_eligible: bool = True
) -> tuple[str, int, int]:
    """Evaluate one hand against the dealer.

    Returns (outcome, payout, balance_delta). ``payout`` is the amount returned
    to the player including the stake (for display); ``balance_delta`` is the
    net change applied at settlement, because bets are only deducted from the
    balance when the round is settled. Split hands are not blackjack-eligible.
    """
    dealer_score = hand_value(dealer_hand)
    dealer_bust = dealer_score > 21
    dealer_blackjack = is_blackjack(dealer_hand)
    score = hand_value(cards)
    blackjack = blackjack_eligible and is_blackjack(cards)
    if score > 21:
        return "lost", 0, -bet
    if blackjack and dealer_blackjack:
        return "push", bet, 0
    if blackjack:
        win = int(bet * 1.5)  # 3:2 payout
        return "blackjack", bet + win, win
    if dealer_bust or score > dealer_score:
        return "won", bet * 2, bet
    if score == dealer_score:
        return "push", bet, 0
    return "lost", 0, -bet


@dataclass
class Player:
    player_id: str
    name: str
    balance: int = 1000
    bet: int = 0
    default_bet: int = 50
    hand: list[Card] = field(default_factory=list)
    connected: bool = True
    stood: bool = False
    is_bot: bool = False
    split_hand: list[Card] = field(default_factory=list)
    split_stood: bool = False
    split_bet: int = 0
    on_split_hand: bool = False

    def to_dict(self) -> dict:
        return {
            "player_id": self.player_id,
            "name": self.name,
            "balance": self.balance,
            "bet": self.bet,
            "default_bet": self.default_bet,
            "hand": [card.to_dict() for card in self.hand],
            "connected": self.connected,
            "stood": self.stood,
            "is_bot": self.is_bot,
            "split_hand": [card.to_dict() for card in self.split_hand],
            "split_stood": self.split_stood,
            "split_bet": self.split_bet,
            "on_split_hand": self.on_split_hand,
        }

    @staticmethod
    def from_dict(raw: dict) -> "Player":
        return Player(
            player_id=raw["player_id"],
            name=raw["name"],
            balance=raw["balance"],
            bet=raw["bet"],
            default_bet=raw.get("default_bet", 50),
            hand=[Card.from_dict(card) for card in raw["hand"]],
            connected=raw["connected"],
            stood=raw["stood"],
            is_bot=raw.get("is_bot", False),
            split_hand=[Card.from_dict(c) for c in raw.get("split_hand", [])],
            split_stood=raw.get("split_stood", False),
            split_bet=raw.get("split_bet", 0),
            on_split_hand=raw.get("on_split_hand", False),
        )


@dataclass
class Table:
    table_id: str
    game_master_id: int
    phase: str = "waiting"
    deck: list[Card] = field(default_factory=new_deck)
    players: dict[str, Player] = field(default_factory=dict)
    dealer_hand: list[Card] = field(default_factory=list)
    current_player_index: int = 0
    state_version: int = 0
    last_result: dict | None = None
    dealer_action: str = "waiting"
    action_log: list[dict] = field(default_factory=list)
    turn_timeout: float = 30.0
    turn_deadline: float | None = None
    # Identifies this table's creation event. Two tables with the same table_id
    # but different lineage are independent forks; state_version comparisons are
    # only meaningful within one lineage.
    lineage: str = field(default_factory=lambda: uuid.uuid4().hex)
    created_at: float = field(default_factory=time.time)

    def require_player(self, player_id: str | None) -> Player:
        if not player_id or player_id not in self.players:
            raise RuleError(f"unknown player {player_id!r}")
        return self.players[player_id]

    def join(self, player_id: str | None = None, name: str = "Player", is_bot: bool = False) -> Player:
        if player_id and player_id in self.players:
            player = self.players[player_id]
            player.connected = True
            return player
        if self.phase == "playing":
            raise RuleError("round in progress; join again after this round")
        player_id = player_id or self.next_player_id()
        player = Player(player_id=player_id, name=name, is_bot=is_bot)
        self.players[player_id] = player
        self.bump()
        return player

    def next_player_id(self) -> str:
        index = 1
        while f"p{index}" in self.players:
            index += 1
        return f"p{index}"

    def place_bet(self, player_id: str, amount: int) -> None:
        player = self.require_player(player_id)
        if self.phase == "playing":
            raise RuleError("cannot change the bet during a round")
        if player.balance <= 0:
            raise RuleError("no chips left; refill the balance first")
        if amount < 1:
            raise RuleError("bet must be at least 1")
        player.bet = min(amount, player.balance)
        player.default_bet = player.bet
        self.bump()

    def next_bot_id(self) -> str:
        index = 1
        while f"bot{index}" in self.players:
            index += 1
        return f"bot{index}"

    def add_bot(self, bot_id: str | None = None, name: str = "Bot", default_bet: int = 50) -> Player:
        bot_id = bot_id or self.next_bot_id()
        if bot_id in self.players and not self.players[bot_id].is_bot:
            bot_id = self.next_bot_id()
        bot = self.join(bot_id, name, is_bot=True)
        bot.default_bet = default_bet
        if bot.bet == 0 and bot.balance > 0:
            self.place_bet(bot.player_id, default_bet)
        return bot

    def can_split(self, player_id: str) -> bool:
        player = self.players.get(player_id)
        if not player or len(player.hand) != 2 or player.split_hand:
            return False
        return player.hand[0].rank == player.hand[1].rank and player.balance > player.bet

    def can_double(self, player_id: str) -> bool:
        player = self.players.get(player_id)
        if not player:
            return False
        active_hand = player.split_hand if player.on_split_hand else player.hand
        bet = player.split_bet if player.on_split_hand else player.bet
        return len(active_hand) == 2 and player.balance > bet

    def refill(self, player_id: str, amount: int = 1000) -> None:
        player = self.require_player(player_id)
        player.balance += amount
        self.bump()

    def start_round(self) -> None:
        if self.phase == "playing":
            raise RuleError("round already running")
        if not self.players:
            raise RuleError("no players at the table")
        self.phase = "playing"
        self.deck = new_deck()
        self.action_log = []
        self.last_result = None
        self.dealer_hand = [self.draw(), self.draw()]
        for player in self.players.values():
            player.hand = [self.draw(), self.draw()]
            player.stood = False
            player.split_hand = []
            player.split_stood = False
            player.split_bet = 0
            player.on_split_hand = False
        self.current_player_index = 0
        self.dealer_action = "waiting for players"
        self.record_action("round", "Round started")
        # Auto-stand human players with 21 (blackjack on deal)
        for player in self.players.values():
            if not player.is_bot and hand_value(player.hand) == 21:
                player.stood = True
                self.record_player_action(player, "blackjack")
        self.play_bots()
        self.advance_turn()
        if self.phase != "playing":
            return
        self.bump()

    def hit(self, player_id: str) -> None:
        player = self.require_player(player_id)
        if self.phase != "playing":
            raise RuleError("round is not active; use NEW_ROUND or place a bet and start again")
        if player.on_split_hand:
            card = self.draw()
            player.split_hand.append(card)
            self.record_player_action(player, "draw", card, use_split=True)
            value = hand_value(player.split_hand)
            if value > 21:
                player.split_stood = True
                player.stood = True
                self.record_player_action(player, "bust", use_split=True)
                self.advance_turn()
            elif value == 21:
                player.split_stood = True
                player.stood = True
                self.record_player_action(player, "stand", use_split=True)
                self.advance_turn()
        else:
            card = self.draw()
            player.hand.append(card)
            self.record_player_action(player, "draw", card)
            value = hand_value(player.hand)
            if value > 21:
                self.record_player_action(player, "bust")
                if player.split_hand and not player.split_stood:
                    # The split hand is still open; busting the main hand
                    # moves play to the split hand instead of ending the turn.
                    player.on_split_hand = True
                else:
                    player.stood = True
                    self.advance_turn()
            elif value == 21:
                if player.split_hand:
                    player.on_split_hand = True
                else:
                    player.stood = True
                    self.record_player_action(player, "stand")
                    self.advance_turn()
        self.play_bots()
        if self.all_players_done() and self.phase == "playing":
            self.finish_dealer()
        self.bump()

    def stand(self, player_id: str) -> None:
        player = self.require_player(player_id)
        if self.phase != "playing":
            raise RuleError("round is not active; use NEW_ROUND or place a bet and start again")
        if player.on_split_hand:
            player.split_stood = True
            player.stood = True
            self.record_player_action(player, "stand", use_split=True)
            self.advance_turn()
        elif player.split_hand:
            # Switch to split hand
            player.on_split_hand = True
            self.record_player_action(player, "stand")
            # Auto-stand on split if 21
            if hand_value(player.split_hand) == 21:
                player.split_stood = True
                player.stood = True
                self.advance_turn()
        else:
            player.stood = True
            self.record_player_action(player, "stand")
            self.advance_turn()
        self.play_bots()
        if self.all_players_done() and self.phase == "playing":
            self.finish_dealer()
        self.bump()

    def double(self, player_id: str) -> None:
        player = self.require_player(player_id)
        if self.phase != "playing":
            raise RuleError("round is not active")
        if not self.can_double(player_id):
            raise RuleError("double is only allowed on the first two cards with enough balance")
        if player.on_split_hand:
            extra = min(player.split_bet, player.balance - player.split_bet)
            player.split_bet += extra
            card = self.draw()
            player.split_hand.append(card)
            self.record_player_action(player, "double", card, use_split=True)
            player.split_stood = True
            player.stood = True
            if is_bust(player.split_hand):
                self.record_player_action(player, "bust", use_split=True)
            else:
                self.record_player_action(player, "stand", use_split=True)
            self.advance_turn()
        else:
            extra = min(player.bet, player.balance - player.bet)
            player.bet += extra
            card = self.draw()
            player.hand.append(card)
            self.record_player_action(player, "double", card)
            if player.split_hand:
                player.on_split_hand = True
                if is_bust(player.hand):
                    self.record_player_action(player, "bust")
                # Auto-stand split if 21
                if hand_value(player.split_hand) == 21:
                    player.split_stood = True
                    player.stood = True
                    self.advance_turn()
            else:
                player.stood = True
                if is_bust(player.hand):
                    self.record_player_action(player, "bust")
                else:
                    self.record_player_action(player, "stand")
                self.advance_turn()
        self.play_bots()
        if self.all_players_done() and self.phase == "playing":
            self.finish_dealer()
        self.bump()

    def split(self, player_id: str) -> None:
        player = self.require_player(player_id)
        if self.phase != "playing":
            raise RuleError("round is not active")
        if not self.can_split(player_id):
            raise RuleError("split requires a pair on the first two cards and enough balance")
        player.split_hand = [player.hand.pop()]
        player.hand.append(self.draw())
        player.split_hand.append(self.draw())
        player.split_bet = player.bet
        player.on_split_hand = False
        self.record_action("player", f"{player.name} splits")
        # Auto-stand if 21 on main hand
        if hand_value(player.hand) == 21:
            if hand_value(player.split_hand) == 21:
                player.split_stood = True
                player.stood = True
                self.advance_turn()
            else:
                player.on_split_hand = True
        self.play_bots()
        if self.all_players_done() and self.phase == "playing":
            self.finish_dealer()
        self.bump()

    def finish_dealer(self) -> None:
        self.dealer_action = "drawing"
        while hand_value(self.dealer_hand) < 17:
            card = self.draw()
            self.dealer_hand.append(card)
            self.record_dealer_action("draw", card)
        self.dealer_action = "stand" if hand_value(self.dealer_hand) <= 21 else "bust"
        self.record_dealer_action(self.dealer_action)
        self.phase = "finished"
        self.last_result = self.build_result()
        self.settle_bets()
        self.bump()

    def build_result(self) -> dict:
        dealer_score = hand_value(self.dealer_hand)
        players = {}
        for player_id, player in self.players.items():
            outcome, payout, _ = hand_outcome(player.hand, player.bet, self.dealer_hand)
            entry: dict = {
                "name": player.name,
                "bet": player.bet,
                "hand": [card.label() for card in player.hand],
                "value": hand_value(player.hand),
                "outcome": outcome,
                "payout": payout,
                "is_bot": player.is_bot,
            }
            if player.split_hand:
                soutcome, spayout, _ = hand_outcome(
                    player.split_hand, player.split_bet, self.dealer_hand, blackjack_eligible=False
                )
                entry["split_result"] = {
                    "hand": [card.label() for card in player.split_hand],
                    "value": hand_value(player.split_hand),
                    "bet": player.split_bet,
                    "outcome": soutcome,
                    "payout": spayout,
                }
            players[player_id] = entry

        return {
            "dealer_hand": [card.label() for card in self.dealer_hand],
            "dealer_value": dealer_score,
            "dealer_action": self.dealer_action,
            "dealer_bust": dealer_score > 21,
            "players": players,
        }

    def advance_turn(self) -> None:
        active = list(self.players.values())
        while self.current_player_index < len(active) and active[self.current_player_index].stood:
            self.current_player_index += 1
        if self.current_player_index >= len(active):
            self.finish_dealer()

    def settle_bets(self) -> None:
        for player in self.players.values():
            _, _, delta = hand_outcome(player.hand, player.bet, self.dealer_hand)
            player.balance += delta
            player.bet = 0
            if player.split_hand:
                _, _, split_delta = hand_outcome(
                    player.split_hand, player.split_bet, self.dealer_hand, blackjack_eligible=False
                )
                player.balance += split_delta
                player.split_bet = 0

    def play_bots(self) -> None:
        if self.phase != "playing":
            return
        for player in self.players.values():
            if not player.is_bot or player.stood:
                continue
            while hand_value(player.hand) < 16:
                card = self.draw()
                player.hand.append(card)
                self.record_player_action(player, "draw", card)
            action = "bust" if is_bust(player.hand) else "stand"
            self.record_player_action(player, action)
            player.stood = True

    def current_player(self) -> Player | None:
        active = list(self.players.values())
        if self.current_player_index >= len(active):
            return None
        return active[self.current_player_index]

    def has_human_players_with_money(self) -> bool:
        return any(not player.is_bot and player.balance > 0 for player in self.players.values())

    def all_players_done(self) -> bool:
        if not self.players:
            return False
        for player in self.players.values():
            if not player.stood:
                return False
            if player.split_hand and not player.split_stood:
                return False
        return True

    def draw(self) -> Card:
        if not self.deck:
            self.deck = new_deck()
        return self.deck.pop()

    def record_player_action(self, player: Player, action: str, card: Card | None = None, use_split: bool = False) -> None:
        actor = "bot" if player.is_bot else "player"
        active_hand = player.split_hand if use_split else player.hand
        value = hand_value(active_hand)
        self.action_log.append(
            {
                "actor": actor,
                "player_id": player.player_id,
                "name": player.name,
                "action": action,
                "card": card.label() if card else None,
                "hand": [item.label() for item in active_hand],
                "value": value,
                "bust": value > 21,
                "on_split_hand": use_split,
                "message": self.action_message(actor, player.name, action, card, value),
            }
        )

    def record_dealer_action(self, action: str, card: Card | None = None) -> None:
        value = hand_value(self.dealer_hand)
        self.action_log.append(
            {
                "actor": "dealer",
                "player_id": "dealer",
                "name": "Dealer",
                "action": action,
                "card": card.label() if card else None,
                "hand": [item.label() for item in self.dealer_hand],
                "value": value,
                "bust": value > 21,
                "message": self.action_message("dealer", "Dealer", action, card, value),
            }
        )

    def record_action(self, actor: str, message: str) -> None:
        self.action_log.append({"actor": actor, "action": "info", "message": message})

    def action_message(self, actor: str, name: str, action: str, card: Card | None, value: int) -> str:
        label = "Dealer" if actor == "dealer" else name
        if action == "draw" and card:
            return f"{label} draws {card.label()} and now has {value}"
        if action == "double" and card:
            return f"{label} doubles and draws {card.label()} ({value})"
        if action == "stand":
            return f"{label} stands on {value}"
        if action == "bust":
            return f"{label} busts with {value}"
        if action == "blackjack":
            return f"{label} has Blackjack!"
        return f"{label}: {action} ({value})"

    def bump(self) -> None:
        self.state_version += 1
        self._refresh_turn_deadline()

    def _refresh_turn_deadline(self) -> None:
        current = self.current_player()
        if self.phase == "playing" and current is not None and not current.is_bot:
            self.turn_deadline = time.time() + self.turn_timeout
        else:
            self.turn_deadline = None

    def snapshot(self) -> dict:
        current = self.current_player()
        return {
            "table_id": self.table_id,
            "game_master_id": self.game_master_id,
            "phase": self.phase,
            "state_version": self.state_version,
            "lineage": self.lineage,
            "current_player_id": current.player_id if current and self.phase == "playing" else None,
            "turn_deadline": self.turn_deadline,
            "turn_remaining": max(0.0, self.turn_deadline - time.time()) if self.turn_deadline else None,
            "turn_timeout": self.turn_timeout,
            "dealer_hand": [card.label() for card in self.dealer_hand],
            "dealer_value": hand_value(self.dealer_hand),
            "dealer_action": self.dealer_action,
            "last_result": self.last_result,
            "action_log": self.action_log,
            "players": {
                pid: {
                    "name": player.name,
                    "balance": player.balance,
                    "bet": player.bet,
                    "default_bet": player.default_bet,
                    "hand": [card.label() for card in player.hand],
                    "value": hand_value(player.hand),
                    "connected": player.connected,
                    "stood": player.stood,
                    "is_bot": player.is_bot,
                    "split_hand": [card.label() for card in player.split_hand],
                    "split_value": hand_value(player.split_hand) if player.split_hand else 0,
                    "split_bet": player.split_bet,
                    "split_stood": player.split_stood,
                    "on_split_hand": player.on_split_hand,
                }
                for pid, player in self.players.items()
            },
        }

    def to_dict(self) -> dict:
        return {
            "table_id": self.table_id,
            "game_master_id": self.game_master_id,
            "phase": self.phase,
            "deck": [card.to_dict() for card in self.deck],
            "players": {pid: player.to_dict() for pid, player in self.players.items()},
            "dealer_hand": [card.to_dict() for card in self.dealer_hand],
            "current_player_index": self.current_player_index,
            "state_version": self.state_version,
            "lineage": self.lineage,
            "created_at": self.created_at,
            "last_result": self.last_result,
            "dealer_action": self.dealer_action,
            "action_log": self.action_log,
            "turn_timeout": self.turn_timeout,
            "turn_deadline": self.turn_deadline,
        }

    @staticmethod
    def from_dict(raw: dict) -> "Table":
        table = Table(table_id=raw["table_id"], game_master_id=raw["game_master_id"])
        table.phase = raw["phase"]
        table.deck = [Card.from_dict(card) for card in raw["deck"]]
        table.players = {pid: Player.from_dict(player) for pid, player in raw["players"].items()}
        table.dealer_hand = [Card.from_dict(card) for card in raw["dealer_hand"]]
        table.current_player_index = raw["current_player_index"]
        table.state_version = raw["state_version"]
        table.lineage = raw.get("lineage", "legacy")
        table.created_at = raw.get("created_at", 0.0)
        table.last_result = raw.get("last_result")
        table.dealer_action = raw.get("dealer_action", "waiting")
        table.action_log = raw.get("action_log", [])
        table.turn_timeout = raw.get("turn_timeout", 30.0)
        table.turn_deadline = raw.get("turn_deadline")
        return table

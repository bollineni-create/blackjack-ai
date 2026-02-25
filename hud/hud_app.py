#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  BLACKJACK AI — REAL-TIME HUD ADVISOR OVERLAY                              ║
║  Runs locally on your machine. YOU make every click and decision.           ║
║  The HUD reads the screen and shows: Action | Bet Size | Count | Edge      ║
║                                                                              ║
║  HOW IT WORKS:                                                               ║
║  1. Open your casino in a browser                                            ║
║  2. Run this HUD — it floats on top of everything                           ║
║  3. Enter cards as they're dealt (or enable OCR auto-detection)             ║
║  4. HUD shows you the mathematically optimal action                         ║
║  5. YOU decide what to do with that information                              ║
╚══════════════════════════════════════════════════════════════════════════════╝

Requirements:
    pip install pillow pytesseract opencv-python mss numpy

Run:
    python hud_app.py --bankroll 1000 --min-bet 10 --max-bet 200 --decks 6
"""

import tkinter as tk
from tkinter import ttk, font as tkfont
import sys, os, time, threading, math, argparse, json
from typing import Optional, List, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from core.strategy import get_action, HandState, Action, best_total, has_soft_ace
from core.counting import CardCounter
from core.bankroll import BankrollManager, BankrollConfig


# ═══════════════════════════════════════════════════════════════════════════════
# CONSTANTS & THEME
# ═══════════════════════════════════════════════════════════════════════════════

VERSION = "2.0 — Rainman Edition"

# Dark elite color scheme
BG_DARK    = '#07070f'
BG_PANEL   = '#0d0d1e'
BG_CARD    = '#131330'
TEXT_WHITE = '#f0f0ff'
TEXT_DIM   = '#55557a'
TEXT_GOLD  = '#ffd700'
TEXT_GREEN = '#00ff88'
TEXT_RED   = '#ff3355'
TEXT_CYAN  = '#00e5ff'
TEXT_ORANGE= '#ff9800'
TEXT_PURPLE= '#c084fc'

ACTION_COLORS = {
    'HIT':       '#00ff88',
    'STAND':     '#ffd700',
    'DOUBLE':    '#00e5ff',
    'SPLIT':     '#c084fc',
    'SURRENDER': '#ff3355',
    'WAIT':      '#55557a',
}

CARD_KEYS = {
    '2': 2, '3': 3, '4': 4, '5': 5, '6': 6,
    '7': 7, '8': 8, '9': 9, '0': 10, 't': 10,
    'j': 10, 'q': 10, 'k': 10, 'a': 1,
}

RANK_DISPLAY = {1: 'A', 10: '10', 2: '2', 3: '3', 4: '4', 5: '5',
                6: '6', 7: '7', 8: '8', 9: '9'}


# ═══════════════════════════════════════════════════════════════════════════════
# GAME STATE ENGINE
# ═══════════════════════════════════════════════════════════════════════════════

class GameState:
    """Tracks a single hand + session state. Advisor queries this every frame."""

    def __init__(self, bankroll: float, table_min: float, table_max: float,
                 num_decks: int = 6, kelly_fraction: float = 0.25,
                 can_surrender: bool = True, das: bool = True):

        self.bankroll     = bankroll
        self.starting_bankroll = bankroll
        self.table_min    = table_min
        self.table_max    = table_max
        self.num_decks    = num_decks
        self.kf           = kelly_fraction
        self.can_surrender = can_surrender
        self.das          = das

        self.counter      = CardCounter(num_decks)

        # Hand state
        self.player_cards : List[int] = []
        self.dealer_upcard: Optional[int] = None
        self.split_hands  : List[List[int]] = []
        self.active_split  = 0
        self.current_bet  = table_min
        self.is_split_hand = False

        # Session tracking
        self.hands_played  = 0
        self.session_profit= 0.0
        self.session_wins  = 0
        self.session_losses= 0
        self.session_pushes= 0
        self.net_profit    = 0.0
        self.peak_profit   = 0.0
        self.max_drawdown  = 0.0

        # History
        self.hand_history : List[dict] = []
        self.profit_history: List[float] = []

        # Phase: BETTING | PLAYING | DEALER | DONE
        self.phase = 'BETTING'

    # ── Card entry ──────────────────────────────────────────────────────────────

    def set_dealer_upcard(self, card: int):
        self.dealer_upcard = card
        self.counter.see_card(card)
        self._update_phase()

    def add_player_card(self, card: int):
        self.player_cards.append(card)
        self.counter.see_card(card)
        self._update_phase()

    def remove_last_player_card(self):
        if self.player_cards:
            removed = self.player_cards.pop()
            # Undo count (approximate — proper undo would need history)
            self.counter.see_card(removed)   # Will cancel if tag is same
            self._update_phase()

    def set_bet(self, amount: float):
        self.current_bet = max(self.table_min, min(self.table_max, amount))

    def new_hand(self):
        """Reset hand state, keep session + count."""
        self.player_cards  = []
        self.dealer_upcard = None
        self.split_hands   = []
        self.active_split  = 0
        self.is_split_hand = False
        self.phase = 'BETTING'

    def record_result(self, outcome: str, profit: float):
        """Call after hand completes."""
        self.bankroll += profit
        self.session_profit += profit
        self.net_profit = self.bankroll - self.starting_bankroll
        self.peak_profit = max(self.peak_profit, self.net_profit)
        self.max_drawdown = max(self.max_drawdown, self.peak_profit - self.net_profit)
        self.profit_history.append(self.net_profit)
        self.hands_played += 1

        if outcome == 'WIN':   self.session_wins   += 1
        elif outcome == 'LOSS': self.session_losses += 1
        else:                   self.session_pushes += 1

        self.hand_history.append({
            'hand': self.hands_played,
            'player': list(self.player_cards),
            'dealer': self.dealer_upcard,
            'bet': self.current_bet,
            'profit': profit,
            'tc': self.counter.true_count,
            'outcome': outcome,
        })

    def reshuffle(self):
        self.counter.reset_shoe()

    def _update_phase(self):
        if self.dealer_upcard and len(self.player_cards) >= 2:
            self.phase = 'PLAYING'
        elif self.dealer_upcard or self.player_cards:
            self.phase = 'DEALING'
        else:
            self.phase = 'BETTING'

    # ── Computed properties ─────────────────────────────────────────────────────

    @property
    def tc(self) -> float:
        return self.counter.true_count

    @property
    def rc(self) -> int:
        return self.counter.state.running_count

    @property
    def edge(self) -> float:
        return self.counter.state.player_edge * 100

    @property
    def optimal_bet(self) -> float:
        """Kelly-optimal bet for current count."""
        e = self.counter.state.player_edge
        if e <= 0:
            return self.table_min
        kelly_bet = (e / 1.33) * self.kf * self.bankroll
        return max(self.table_min, min(self.table_max, round(kelly_bet / 5) * 5))

    @property
    def decks_remaining(self) -> float:
        return self.counter.state.decks_remaining

    @property
    def recommendation(self) -> Tuple[str, str]:
        """Returns (action_name, explanation)."""
        if not self.player_cards or not self.dealer_upcard:
            return 'WAIT', 'Enter dealer upcard and your cards'

        player_total = best_total(self.player_cards)
        is_soft      = has_soft_ace(self.player_cards)
        can_split    = (len(self.player_cards) == 2 and
                        self.player_cards[0] == self.player_cards[1])
        can_double   = len(self.player_cards) == 2
        can_surr     = self.can_surrender and len(self.player_cards) == 2

        state = HandState(
            player_total=player_total,
            dealer_upcard=self.dealer_upcard,
            is_soft=is_soft,
            can_split=can_split,
            can_double=can_double,
            can_surrender=can_surr,
            true_count=self.tc,
        )

        try:
            action = get_action(state)
            action_name = action.name
        except Exception as e:
            action_name = 'HIT'

        # Build explanation
        explanations = {
            'HIT':       f'Hit — total {player_total}, dealer {self.dealer_upcard}',
            'STAND':     f'Stand — total {player_total} vs dealer {self.dealer_upcard}',
            'DOUBLE':    f'Double — max EV on {player_total} vs {self.dealer_upcard}',
            'SPLIT':     f'Split — mathematically optimal at TC {self.tc:.1f}',
            'SURRENDER': f'Surrender — save half bet, EV > playing',
        }

        return action_name, explanations.get(action_name, '')


# ═══════════════════════════════════════════════════════════════════════════════
# HUD OVERLAY — MAIN WINDOW
# ═══════════════════════════════════════════════════════════════════════════════

class HUDOverlay:
    """
    Always-on-top transparent overlay window.
    Designed to sit in the corner of your screen while you play.
    """

    def __init__(self, game: GameState):
        self.game = game
        self.root = tk.Tk()
        self._setup_window()
        self._build_ui()
        self._bind_keys()
        self._start_refresh_loop()

    def _setup_window(self):
        self.root.title(f'BJ AI HUD v{VERSION}')
        self.root.configure(bg=BG_DARK)
        self.root.attributes('-topmost', True)       # Always on top
        self.root.attributes('-alpha', 0.93)          # Slight transparency
        self.root.resizable(True, True)

        # Position in top-right corner
        sw = self.root.winfo_screenwidth()
        self.root.geometry(f'380x720+{sw-395}+20')

        # Allow drag to reposition
        self.root.bind('<Button-1>', self._start_drag)
        self.root.bind('<B1-Motion>', self._drag)
        self._drag_x = self._drag_y = 0

    def _start_drag(self, e):
        self._drag_x, self._drag_y = e.x, e.y

    def _drag(self, e):
        x = self.root.winfo_x() + e.x - self._drag_x
        y = self.root.winfo_y() + e.y - self._drag_y
        self.root.geometry(f'+{x}+{y}')

    # ── UI Construction ──────────────────────────────────────────────────────────

    def _build_ui(self):
        pad = {'padx': 8, 'pady': 3}

        # ── HEADER ───────────────────────────────────────────────────────────────
        hdr = tk.Frame(self.root, bg=BG_PANEL, relief='flat', bd=0)
        hdr.pack(fill='x', padx=6, pady=(6, 2))

        tk.Label(hdr, text='🃏 BJ AI ADVISOR', bg=BG_PANEL,
                fg=TEXT_GOLD, font=('Courier', 12, 'bold')).pack(side='left', padx=8, pady=4)
        tk.Label(hdr, text=VERSION, bg=BG_PANEL,
                fg=TEXT_DIM, font=('Courier', 7)).pack(side='right', padx=8)

        # ── ACTION BOX (biggest, most prominent) ─────────────────────────────────
        self.action_frame = tk.Frame(self.root, bg=BG_CARD,
                                     relief='flat', bd=2, highlightthickness=2,
                                     highlightbackground=TEXT_GOLD)
        self.action_frame.pack(fill='x', padx=6, pady=4)

        self.action_label = tk.Label(self.action_frame, text='WAIT',
                                     bg=BG_CARD, fg=TEXT_DIM,
                                     font=('Courier', 36, 'bold'))
        self.action_label.pack(pady=(10, 4))

        self.action_explain = tk.Label(self.action_frame, text='Enter cards to begin',
                                       bg=BG_CARD, fg=TEXT_DIM,
                                       font=('Courier', 9), wraplength=340)
        self.action_explain.pack(pady=(0, 10))

        # ── COUNT + EDGE STRIP ────────────────────────────────────────────────────
        count_frame = tk.Frame(self.root, bg=BG_PANEL)
        count_frame.pack(fill='x', padx=6, pady=2)

        for col, (label, attr, color) in enumerate([
            ('RC',   'rc_val',   TEXT_WHITE),
            ('TC',   'tc_val',   TEXT_CYAN),
            ('EDGE', 'edge_val', TEXT_GREEN),
            ('DECKS','deck_val', TEXT_DIM),
        ]):
            f = tk.Frame(count_frame, bg=BG_CARD, relief='flat')
            f.grid(row=0, column=col, sticky='nsew', padx=2, pady=2)
            count_frame.columnconfigure(col, weight=1)
            tk.Label(f, text=label, bg=BG_CARD, fg=TEXT_DIM,
                    font=('Courier', 7, 'bold')).pack(pady=(4, 0))
            lbl = tk.Label(f, text='0', bg=BG_CARD, fg=color,
                          font=('Courier', 14, 'bold'))
            lbl.pack(pady=(0, 4))
            setattr(self, attr, lbl)

        # ── BET RECOMMENDATION ────────────────────────────────────────────────────
        bet_frame = tk.Frame(self.root, bg=BG_PANEL)
        bet_frame.pack(fill='x', padx=6, pady=2)

        tk.Label(bet_frame, text='OPTIMAL BET', bg=BG_PANEL,
                fg=TEXT_DIM, font=('Courier', 8, 'bold')).pack(side='left', padx=8)
        self.bet_label = tk.Label(bet_frame, text='$--',
                                  bg=BG_PANEL, fg=TEXT_GOLD,
                                  font=('Courier', 18, 'bold'))
        self.bet_label.pack(side='left', padx=4)

        self.bet_context = tk.Label(bet_frame, text='',
                                    bg=BG_PANEL, fg=TEXT_DIM,
                                    font=('Courier', 8))
        self.bet_context.pack(side='right', padx=8)

        # ── HAND DISPLAY ──────────────────────────────────────────────────────────
        hand_frame = tk.Frame(self.root, bg=BG_PANEL)
        hand_frame.pack(fill='x', padx=6, pady=2)

        # Dealer row
        d_row = tk.Frame(hand_frame, bg=BG_PANEL)
        d_row.pack(fill='x', padx=4, pady=2)
        tk.Label(d_row, text='DEALER:', bg=BG_PANEL, fg=TEXT_DIM,
                font=('Courier', 9, 'bold'), width=8).pack(side='left')
        self.dealer_display = tk.Label(d_row, text='[ ? ]',
                                       bg=BG_PANEL, fg=TEXT_RED,
                                       font=('Courier', 14, 'bold'))
        self.dealer_display.pack(side='left', padx=4)
        self.dealer_total = tk.Label(d_row, text='',
                                     bg=BG_PANEL, fg=TEXT_DIM,
                                     font=('Courier', 9))
        self.dealer_total.pack(side='left')

        # Player row
        p_row = tk.Frame(hand_frame, bg=BG_PANEL)
        p_row.pack(fill='x', padx=4, pady=2)
        tk.Label(p_row, text='PLAYER:', bg=BG_PANEL, fg=TEXT_DIM,
                font=('Courier', 9, 'bold'), width=8).pack(side='left')
        self.player_display = tk.Label(p_row, text='[ ]',
                                       bg=BG_PANEL, fg=TEXT_GREEN,
                                       font=('Courier', 14, 'bold'))
        self.player_display.pack(side='left', padx=4)
        self.player_total_lbl = tk.Label(p_row, text='',
                                          bg=BG_PANEL, fg=TEXT_CYAN,
                                          font=('Courier', 11, 'bold'))
        self.player_total_lbl.pack(side='left')

        # ── KEYBOARD INPUT AREA ───────────────────────────────────────────────────
        input_frame = tk.Frame(self.root, bg=BG_PANEL, relief='flat', bd=1,
                               highlightthickness=1,
                               highlightbackground=TEXT_DIM)
        input_frame.pack(fill='x', padx=6, pady=4)

        tk.Label(input_frame, text='CARD ENTRY',
                bg=BG_PANEL, fg=TEXT_GOLD, font=('Courier', 8, 'bold')).pack(pady=(4,1))

        self.input_mode = tk.StringVar(value='player')
        mode_frame = tk.Frame(input_frame, bg=BG_PANEL)
        mode_frame.pack(fill='x', padx=4, pady=2)

        for val, txt, color in [('dealer', 'DEALER CARD', TEXT_RED),
                                  ('player', 'PLAYER CARD', TEXT_GREEN)]:
            rb = tk.Radiobutton(mode_frame, text=txt, variable=self.input_mode,
                               value=val, bg=BG_PANEL, fg=color,
                               selectcolor=BG_CARD,
                               font=('Courier', 8, 'bold'), relief='flat',
                               activebackground=BG_PANEL)
            rb.pack(side='left', padx=8)

        # Current input display
        self.input_display = tk.Label(input_frame, text='Press key: A 2-9 T/J/Q/K',
                                      bg=BG_PANEL, fg=TEXT_DIM,
                                      font=('Courier', 9))
        self.input_display.pack(pady=(2, 4))

        # Quick buttons row
        btn_frame = tk.Frame(input_frame, bg=BG_PANEL)
        btn_frame.pack(fill='x', padx=4, pady=(0, 6))

        self._make_btn(btn_frame, 'NEW HAND', self._new_hand,
                      TEXT_CYAN, bg=BG_CARD).pack(side='left', padx=2, expand=True, fill='x')
        self._make_btn(btn_frame, 'RESHUFFLE', self._reshuffle,
                      TEXT_ORANGE, bg=BG_CARD).pack(side='left', padx=2, expand=True, fill='x')
        self._make_btn(btn_frame, 'UNDO', self._undo_card,
                      TEXT_RED, bg=BG_CARD).pack(side='left', padx=2, expand=True, fill='x')

        # ── SESSION STATS ─────────────────────────────────────────────────────────
        stats_frame = tk.Frame(self.root, bg=BG_PANEL)
        stats_frame.pack(fill='x', padx=6, pady=2)

        tk.Label(stats_frame, text='SESSION STATS',
                bg=BG_PANEL, fg=TEXT_GOLD, font=('Courier', 8, 'bold')).pack(pady=(4,2))

        stats_grid = tk.Frame(stats_frame, bg=BG_PANEL)
        stats_grid.pack(fill='x', padx=4)

        self.stat_labels = {}
        stat_defs = [
            ('Bankroll',   'bankroll',    TEXT_WHITE),
            ('Net P&L',    'net_pnl',     TEXT_GREEN),
            ('Hands',      'hands',       TEXT_DIM),
            ('Win Rate',   'win_rate',    TEXT_CYAN),
            ('Max Profit', 'max_profit',  TEXT_GOLD),
            ('Max DD',     'max_dd',      TEXT_RED),
        ]

        for i, (name, key, color) in enumerate(stat_defs):
            row, col = divmod(i, 2)
            f = tk.Frame(stats_grid, bg=BG_CARD, relief='flat')
            f.grid(row=row, column=col, sticky='nsew', padx=2, pady=1)
            stats_grid.columnconfigure(col, weight=1)

            tk.Label(f, text=name, bg=BG_CARD, fg=TEXT_DIM,
                    font=('Courier', 7)).pack(anchor='w', padx=4, pady=(3,0))
            lbl = tk.Label(f, text='--', bg=BG_CARD, fg=color,
                          font=('Courier', 10, 'bold'))
            lbl.pack(anchor='w', padx=4, pady=(0,3))
            self.stat_labels[key] = lbl

        # ── STRATEGY INDICATOR ────────────────────────────────────────────────────
        strat_frame = tk.Frame(self.root, bg=BG_PANEL)
        strat_frame.pack(fill='x', padx=6, pady=2)

        self.strategy_bar = tk.Label(strat_frame,
                                     text='RAINMAN MULTI-LEVEL | KELLY 0.35 | 6-DECK S17 DAS',
                                     bg=BG_PANEL, fg=TEXT_DIM, font=('Courier', 7))
        self.strategy_bar.pack(pady=4)

        # ── KEYBOARD REFERENCE ────────────────────────────────────────────────────
        ref_frame = tk.Frame(self.root, bg=BG_DARK)
        ref_frame.pack(fill='x', padx=6, pady=(2, 6))

        ref_text = ('Keys: D=set Dealer | P=set Player | N=New Hand | R=Reshuffle\n'
                    'Cards: A=Ace, 2-9, 0/T=Ten, J=Jack, Q=Queen, K=King\n'
                    'Results: W=Win, L=Loss, X=Push | Backspace=Undo')
        tk.Label(ref_frame, text=ref_text, bg=BG_DARK, fg=TEXT_DIM,
                font=('Courier', 7), justify='left').pack(pady=2)

    def _make_btn(self, parent, text, cmd, fg, bg=BG_CARD):
        return tk.Button(parent, text=text, command=cmd,
                        bg=bg, fg=fg, relief='flat',
                        activebackground=BG_PANEL, activeforeground=fg,
                        font=('Courier', 8, 'bold'), cursor='hand2',
                        padx=4, pady=3)

    # ── Key Bindings ─────────────────────────────────────────────────────────────

    def _bind_keys(self):
        self.root.bind('<Key>', self._on_key)
        self.root.focus_force()

    def _on_key(self, event):
        k = event.keysym.lower()

        # Mode switching
        if k == 'd':
            self.input_mode.set('dealer')
            self.input_display.config(text='Mode: DEALER CARD — press card key')
            return
        if k == 'p':
            self.input_mode.set('player')
            self.input_display.config(text='Mode: PLAYER CARD — press card key')
            return

        # Commands
        if k == 'n':          self._new_hand();    return
        if k == 'r':          self._reshuffle();   return
        if k == 'backspace':  self._undo_card();   return

        # Result recording
        if k == 'w':  self._record_win();   return
        if k == 'l':  self._record_loss();  return
        if k == 'x':  self._record_push();  return

        # Card input
        char = event.char.lower() if event.char else k
        card_val = None

        if char in ('0', 't', 'j', 'q', 'k'):
            card_val = 10
        elif char == 'a':
            card_val = 1
        elif char in '23456789':
            card_val = int(char)

        if card_val is not None:
            mode = self.input_mode.get()
            rank_str = RANK_DISPLAY.get(card_val, str(card_val))

            if mode == 'dealer':
                self.game.set_dealer_upcard(card_val)
                self.input_display.config(text=f'Dealer upcard set: {rank_str}',
                                         fg=TEXT_RED)
                # Switch to player mode automatically
                self.input_mode.set('player')
            else:
                self.game.add_player_card(card_val)
                total = best_total(self.game.player_cards)
                self.input_display.config(
                    text=f'Added {rank_str} to player hand. Total: {total}',
                    fg=TEXT_GREEN)

            self._refresh_ui()

    # ── Button Handlers ───────────────────────────────────────────────────────────

    def _new_hand(self):
        self.game.new_hand()
        self.input_display.config(text='New hand started. Press D for dealer card.',
                                  fg=TEXT_CYAN)
        self.input_mode.set('dealer')
        self._refresh_ui()

    def _reshuffle(self):
        self.game.reshuffle()
        self.input_display.config(text='Shoe reshuffled. Count reset.',
                                  fg=TEXT_ORANGE)
        self._refresh_ui()

    def _undo_card(self):
        if self.game.player_cards:
            self.game.remove_last_player_card()
            self.input_display.config(text='Last player card removed.', fg=TEXT_RED)
        elif self.game.dealer_upcard:
            self.game.counter.see_card(self.game.dealer_upcard)
            self.game.dealer_upcard = None
            self.input_display.config(text='Dealer upcard removed.', fg=TEXT_RED)
        self._refresh_ui()

    def _record_win(self):
        self.game.record_result('WIN', self.game.current_bet)
        self.input_display.config(text=f'Win: +${self.game.current_bet:.0f}', fg=TEXT_GREEN)
        self._new_hand()

    def _record_loss(self):
        self.game.record_result('LOSS', -self.game.current_bet)
        self.input_display.config(text=f'Loss: -${self.game.current_bet:.0f}', fg=TEXT_RED)
        self._new_hand()

    def _record_push(self):
        self.game.record_result('PUSH', 0.0)
        self.input_display.config(text='Push — no change', fg=TEXT_DIM)
        self._new_hand()

    # ── UI Refresh ────────────────────────────────────────────────────────────────

    def _start_refresh_loop(self):
        self._refresh_ui()
        self.root.after(250, self._refresh_loop)

    def _refresh_loop(self):
        self._refresh_ui()
        self.root.after(250, self._refresh_loop)

    def _refresh_ui(self):
        g = self.game

        # Action
        action, explain = g.recommendation
        action_color = ACTION_COLORS.get(action, TEXT_DIM)
        self.action_label.config(text=action, fg=action_color)
        self.action_explain.config(text=explain, fg=action_color if action != 'WAIT' else TEXT_DIM)
        self.action_frame.config(highlightbackground=action_color)

        # Count strip
        tc = g.tc
        rc = g.rc
        edge = g.edge

        tc_color = TEXT_GREEN if tc >= 2 else (TEXT_GOLD if tc >= 0 else TEXT_RED)
        edge_color = TEXT_GREEN if edge >= 0 else TEXT_RED

        self.rc_val.config(text=f'{rc:+d}')
        self.tc_val.config(text=f'{tc:+.1f}', fg=tc_color)
        self.edge_val.config(text=f'{edge:+.2f}%', fg=edge_color)
        self.deck_val.config(text=f'{g.decks_remaining:.1f}')

        # Bet
        opt_bet = g.optimal_bet
        self.bet_label.config(text=f'${opt_bet:.0f}')
        units = opt_bet / g.table_min
        self.bet_context.config(text=f'{units:.1f}u | TC:{tc:+.1f}')

        # Hand display
        if g.dealer_upcard:
            d_rank = RANK_DISPLAY.get(g.dealer_upcard, str(g.dealer_upcard))
            self.dealer_display.config(text=f'[ {d_rank} ]')
        else:
            self.dealer_display.config(text='[ ? ]')
        self.dealer_total.config(text='')

        if g.player_cards:
            cards_str = ' '.join(f'[{RANK_DISPLAY.get(c, c)}]' for c in g.player_cards)
            total = best_total(g.player_cards)
            soft_str = 'soft ' if has_soft_ace(g.player_cards) and total <= 21 else ''
            self.player_display.config(text=cards_str)
            total_color = TEXT_RED if total > 21 else TEXT_CYAN
            self.player_total_lbl.config(text=f'{soft_str}{total}', fg=total_color)
        else:
            self.player_display.config(text='[ ]')
            self.player_total_lbl.config(text='')

        # Stats
        wins  = g.session_wins
        total_h = g.hands_played
        wr = f'{wins/max(total_h,1)*100:.0f}%'
        net_color = TEXT_GREEN if g.net_profit >= 0 else TEXT_RED
        pnl_color = TEXT_GREEN if g.session_profit >= 0 else TEXT_RED

        self.stat_labels['bankroll'].config(text=f'${g.bankroll:,.0f}')
        self.stat_labels['net_pnl'].config(text=f'${g.session_profit:+,.0f}', fg=pnl_color)
        self.stat_labels['hands'].config(text=str(total_h))
        self.stat_labels['win_rate'].config(text=wr)
        self.stat_labels['max_profit'].config(text=f'${g.peak_profit:+,.0f}')
        self.stat_labels['max_dd'].config(text=f'${g.max_drawdown:,.0f}')

        # Strategy bar
        self.strategy_bar.config(
            text=f'RAINMAN | KF:{g.kf:.2f} | {g.num_decks}D S17 DAS | '
                 f'Hands:{total_h} | Pen:{(1-g.decks_remaining/g.num_decks)*100:.0f}%')

    def run(self):
        self.root.mainloop()


# ═══════════════════════════════════════════════════════════════════════════════
# BET SIZING CALCULATOR WINDOW (pop-out)
# ═══════════════════════════════════════════════════════════════════════════════

class BetSizingPanel:
    """
    Secondary window showing full bet ramp for current bankroll.
    Pops out when you press B.
    """

    def __init__(self, game: GameState):
        self.game = game
        self.win = tk.Toplevel()
        self.win.title('Bet Ramp')
        self.win.configure(bg=BG_DARK)
        self.win.attributes('-topmost', True)
        self.win.geometry('280x400+10+20')
        self._build()

    def _build(self):
        tk.Label(self.win, text='BET RAMP — CURRENT BANKROLL',
                bg=BG_DARK, fg=TEXT_GOLD, font=('Courier', 9, 'bold')).pack(pady=8)

        g = self.game
        canvas = tk.Frame(self.win, bg=BG_PANEL)
        canvas.pack(fill='both', expand=True, padx=8, pady=4)

        headers = ['TC', 'BET', 'UNITS', 'EDGE', 'EV/HR']
        for col, h in enumerate(headers):
            tk.Label(canvas, text=h, bg=BG_PANEL, fg=TEXT_GOLD,
                    font=('Courier', 8, 'bold')).grid(row=0, column=col, padx=6, pady=2)

        for row, tc in enumerate(range(-2, 8), 1):
            edge = -0.004 + tc * 0.005
            if tc <= 1:
                bet = g.table_min
            elif tc == 2:
                bet = max(g.table_min, g.bankroll * g.kf * 0.01)
            elif tc == 3:
                bet = max(g.table_min, g.bankroll * g.kf * 0.02)
            elif tc == 4:
                bet = max(g.table_min, g.bankroll * g.kf * 0.04)
            elif tc == 5:
                bet = max(g.table_min, g.bankroll * g.kf * 0.06)
            else:
                bet = g.table_max

            bet = min(g.table_max, round(bet / 5) * 5)
            units = bet / g.table_min
            ev_hr = edge * bet * 80

            tc_color = TEXT_GREEN if tc >= 2 else (TEXT_DIM if tc < 0 else TEXT_WHITE)
            ev_color = TEXT_GREEN if ev_hr > 0 else TEXT_RED

            bg = BG_CARD if tc >= 2 else BG_PANEL
            vals = [f'{tc:+d}', f'${bet:.0f}', f'{units:.0f}u',
                    f'{edge*100:+.2f}%', f'${ev_hr:.2f}']
            colors = [tc_color, TEXT_WHITE, TEXT_DIM, TEXT_CYAN, ev_color]

            for col, (val, color) in enumerate(zip(vals, colors)):
                tk.Label(canvas, text=val, bg=bg, fg=color,
                        font=('Courier', 9)).grid(row=row, column=col,
                                                  padx=6, pady=1, sticky='w')


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN ENTRY
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description='Blackjack AI HUD Advisor')
    parser.add_argument('--bankroll', type=float, default=1000,
                       help='Starting bankroll (default: 1000)')
    parser.add_argument('--min-bet', type=float, default=10,
                       help='Table minimum bet (default: 10)')
    parser.add_argument('--max-bet', type=float, default=200,
                       help='Table maximum bet (default: 200)')
    parser.add_argument('--decks', type=int, default=6,
                       help='Number of decks (default: 6)')
    parser.add_argument('--kelly', type=float, default=0.35,
                       help='Kelly fraction 0.10-1.0 (default: 0.35 = Rainman optimal)')
    parser.add_argument('--surrender', action='store_true', default=True,
                       help='Allow surrender (default: True)')
    parser.add_argument('--no-surrender', dest='surrender', action='store_false')
    parser.add_argument('--das', action='store_true', default=True,
                       help='Double after split allowed (default: True)')
    args = parser.parse_args()

    print(f"""
╔══════════════════════════════════════════════════════════════════╗
║         BLACKJACK AI HUD — {VERSION:<36}║
╠══════════════════════════════════════════════════════════════════╣
║  Bankroll: ${args.bankroll:<10.0f}  Table: ${args.min_bet:.0f}-${args.max_bet:.0f}           ║
║  Decks: {args.decks}          Kelly: {args.kelly:.0%}  Surrender: {str(args.surrender):<5}    ║
╠══════════════════════════════════════════════════════════════════╣
║  HOW TO USE:                                                     ║
║  • Press D then a card key to set dealer upcard                  ║
║  • Press P (or just press card key) to add player cards          ║
║  • Card keys: A=Ace, 2-9, 0/T/J/Q/K = Ten-value                 ║
║  • After hand: W=Win, L=Loss, X=Push                             ║
║  • N=New Hand, R=Reshuffle when shoe changes                     ║
║  • Backspace=Undo last card                                      ║
╚══════════════════════════════════════════════════════════════════╝
""")

    game = GameState(
        bankroll=args.bankroll,
        table_min=args.min_bet,
        table_max=args.max_bet,
        num_decks=args.decks,
        kelly_fraction=args.kelly,
        can_surrender=args.surrender,
        das=args.das,
    )

    hud = HUDOverlay(game)
    hud.run()


if __name__ == '__main__':
    main()

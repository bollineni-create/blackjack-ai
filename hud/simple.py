#!/usr/bin/env python3
"""
BLACKJACK ADVISOR — Simple Edition
4 inputs → 1 big answer
"""

import tkinter as tk
import sys, os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from core.strategy import get_action, HandState, Action, best_total, has_soft_ace

# ── Theme ──────────────────────────────────────────────────────────────────────
BG     = '#0a0a0f'
PANEL  = '#13131e'
FIELD  = '#1c1c2e'
BORDER = '#2a2a45'
WHITE  = '#f0f0ff'
DIM    = '#44445a'
GOLD   = '#ffd700'
GREEN  = '#00ff88'
RED    = '#ff3355'
CYAN   = '#00e5ff'
PURPLE = '#c084fc'
ORANGE = '#ff9800'

CARD_VALS = {
    'A':1, '2':2, '3':3, '4':4, '5':5, '6':6, '7':7, '8':8, '9':9,
    '10':10, 'T':10, 'J':10, 'Q':10, 'K':10,
}

ACTION_STYLE = {
    'HIT':        (GREEN,  '↑',  'HIT'),
    'STAND':      (GOLD,   '—',  'STAND'),
    'DOUBLE':     (CYAN,   '✦',  'DOUBLE DOWN'),
    'SPLIT':      (PURPLE, '⟺', 'SPLIT'),
    'SURRENDER':  (RED,    '✕',  'SURRENDER'),
}

def parse_card(raw: str):
    v = raw.strip().upper()
    return CARD_VALS.get(v)

def get_advice(dealer1_raw, dealer2_raw, player_raw):
    """
    dealer1 = dealer upcard (visible)
    dealer2 = dealer second card (if known)
    player  = player cards, space-separated e.g. "A 7" or "8 8"
    Returns (action_str, sub_text, can_split, is_soft, total)
    """
    d1 = parse_card(dealer1_raw)
    if d1 is None:
        return None, 'Enter a valid dealer card (A 2–9 T/J/Q/K)', False, False, 0

    # Player cards
    player_tokens = player_raw.strip().upper().split()
    player_cards  = [parse_card(t) for t in player_tokens]
    player_cards  = [c for c in player_cards if c is not None]

    if not player_cards:
        return None, 'Enter your card(s)', False, False, 0

    total    = best_total(player_cards)
    soft     = has_soft_ace(player_cards)
    nc       = len(player_cards)
    can_split= nc == 2 and player_cards[0] == player_cards[1]

    state = HandState(
        total       = total,
        is_soft     = soft,
        can_double  = nc == 2,
        can_split   = can_split,
        can_surrender = nc == 2,
    )
    action = get_action(state, d1)

    sub = f'Your total: {"soft " if soft else ""}{total}  |  Dealer: {dealer1_raw.upper()}'
    return action.name, sub, can_split, soft, total


class App:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title('Blackjack Advisor')
        self.root.configure(bg=BG)
        self.root.attributes('-topmost', True)
        self.root.resizable(False, False)

        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        W, H = 480, 620
        self.root.geometry(f'{W}x{H}+{sw//2 - W//2}+{sh//2 - H//2}')

        self._build()
        self._update()

    # ── UI ─────────────────────────────────────────────────────────────────────

    def _build(self):
        root = self.root

        # Title
        tk.Label(root, text='BLACKJACK ADVISOR', bg=BG,
                 fg=GOLD, font=('Courier', 18, 'bold')).pack(pady=(24, 4))
        tk.Label(root, text='enter your situation below', bg=BG,
                 fg=DIM, font=('Courier', 11)).pack(pady=(0, 20))

        # Input fields
        self._vars = {}
        fields = [
            ('DEALER CARD 1',  'dealer1',  'upcard  (A 2–9 T J Q K)'),
            ('DEALER CARD 2',  'dealer2',  'hole card  (optional)'),
            ('YOUR CARDS',     'player',   'e.g.  A 7  or  8 8'),
            ('BALANCE',        'balance',  '$'),
            ('BET',            'bet',      '$'),
        ]
        for label, key, hint in fields:
            self._build_field(root, label, key, hint)

        # Divider
        tk.Frame(root, bg=BORDER, height=1).pack(fill='x', padx=30, pady=16)

        # Action box
        self.action_frame = tk.Frame(root, bg=PANEL,
                                      highlightthickness=3,
                                      highlightbackground=BORDER)
        self.action_frame.pack(fill='x', padx=24, pady=0)

        self.action_icon = tk.Label(self.action_frame, text='?', bg=PANEL,
                                     fg=DIM, font=('Courier', 52, 'bold'))
        self.action_icon.pack(pady=(16, 0))

        self.action_lbl = tk.Label(self.action_frame, text='WAITING',
                                    bg=PANEL, fg=DIM,
                                    font=('Courier', 34, 'bold'))
        self.action_lbl.pack(pady=(0, 6))

        self.action_sub = tk.Label(self.action_frame, text='Fill in the fields above',
                                    bg=PANEL, fg=DIM,
                                    font=('Courier', 11), wraplength=420)
        self.action_sub.pack(pady=(0, 18))

    def _build_field(self, parent, label, key, hint):
        row = tk.Frame(parent, bg=BG)
        row.pack(fill='x', padx=30, pady=5)

        tk.Label(row, text=label, bg=BG, fg=DIM,
                 font=('Courier', 9, 'bold'), width=14, anchor='w').pack(side='left')

        v = tk.StringVar()
        v.trace_add('write', lambda *_: self._update())
        self._vars[key] = v

        e = tk.Entry(row, textvariable=v, bg=FIELD, fg=WHITE,
                     font=('Courier', 16, 'bold'),
                     insertbackground=WHITE, relief='flat',
                     highlightthickness=2, highlightbackground=BORDER,
                     highlightcolor=GOLD, width=10)
        e.pack(side='left', ipady=8, padx=(8, 8))

        tk.Label(row, text=hint, bg=BG, fg=DIM,
                 font=('Courier', 9)).pack(side='left')

    # ── Logic ──────────────────────────────────────────────────────────────────

    def _update(self, *_):
        d1  = self._vars['dealer1'].get()
        d2  = self._vars['dealer2'].get()
        pl  = self._vars['player'].get()
        bal = self._vars['balance'].get()
        bet = self._vars['bet'].get()

        if not d1.strip() or not pl.strip():
            self._show_waiting()
            return

        action, sub, can_split, soft, total = get_advice(d1, d2, pl)

        if action is None:
            self._show_waiting(sub)
            return

        col, icon, text = ACTION_STYLE.get(action, (WHITE, '?', action))

        # Add balance/bet info to sub if present
        extras = []
        try:
            b = float(bal.replace('$','').replace(',','').strip())
            extras.append(f'Balance: ${b:,.0f}')
        except: pass
        try:
            bt = float(bet.replace('$','').replace(',','').strip())
            extras.append(f'Bet: ${bt:,.0f}')
        except: pass

        full_sub = sub
        if extras:
            full_sub += '  |  ' + '  '.join(extras)

        self.action_frame.config(highlightbackground=col)
        self.action_icon.config(text=icon, fg=col)
        self.action_lbl.config(text=text, fg=col)
        self.action_sub.config(text=full_sub, fg=col)

    def _show_waiting(self, msg='Fill in the fields above'):
        self.action_frame.config(highlightbackground=BORDER)
        self.action_icon.config(text='?', fg=DIM)
        self.action_lbl.config(text='WAITING', fg=DIM)
        self.action_sub.config(text=msg, fg=DIM)

    def run(self):
        self.root.mainloop()


if __name__ == '__main__':
    App().run()

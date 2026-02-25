#!/usr/bin/env python3
"""
BLACKJACK ADVISOR — self-contained
dealer 2 cards, player 1 card, balance, bet → instant answer
"""

import tkinter as tk

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

CARD_MAP = {
    'A':1,'2':2,'3':3,'4':4,'5':5,'6':6,'7':7,'8':8,'9':9,
    '10':10,'T':10,'J':10,'Q':10,'K':10,
}

def parse_card(s):
    return CARD_MAP.get(s.strip().upper())

def best_total(cards):
    t = sum(cards)
    if 1 in cards and t + 10 <= 21:
        t += 10
    return t

def is_soft(cards):
    return 1 in cards and sum(cards) + 10 <= 21

def dealer_idx(d):
    return {2:0,3:1,4:2,5:3,6:4,7:5,8:6,9:7,10:8,1:9}[min(d,10)]

HARD = {
    4:'HHHHHHHHHH', 5:'HHHHHHHHHH', 6:'HHHHHHHHHH', 7:'HHHHHHHHHH',
    8:'HHHHHHHHHH', 9:'HDDDDHHHHH', 10:'DDDDDDDDHH', 11:'DDDDDDDDDH',
    12:'HHSSSHHHHH', 13:'SSSSSHHHHH', 14:'SSSSSHHHHH',
    15:'SSSSSHHHRH', 16:'SSSSSHHRRH',
    17:'SSSSSSSSSS', 18:'SSSSSSSSSS', 19:'SSSSSSSSSS',
    20:'SSSSSSSSSS', 21:'SSSSSSSSSS',
}
SOFT = {
    2:'HHHDDHHHHH', 3:'HHHDDHHHHH', 4:'HHDDDHHHHH', 5:'HHDDDHHHHH',
    6:'HDDDDHHHHH', 7:'SDDDDSSHHH', 8:'SSSSSSSSSS', 9:'SSSSSSSSSS',
}
PAIRS = {
    1:'PPPPPPPPPP', 2:'PPPPPPHHHH', 3:'PPPPPPHHHH', 4:'HHHPHHHHHH',
    5:'DDDDDDDDHH', 6:'PPPPPHHHHH', 7:'PPPPPPHHHR', 8:'PPPPPPPPPP',
    9:'PPPPPSPPSS', 10:'SSSSSSSSSS',
}

def get_action(player_cards, dealer_upcard):
    di    = dealer_idx(dealer_upcard)
    soft  = is_soft(player_cards)
    tot   = best_total(player_cards)

    if len(player_cards) == 2 and player_cards[0] == player_cards[1]:
        a = PAIRS.get(player_cards[0], 'HHHHHHHHHH')[di]
        if a == 'P': return 'SPLIT'

    if soft and tot < 21:
        other = max(2, min(9, tot - 11))
        a = SOFT.get(other, 'HHHHHHHHHH')[di]
        if a == 'D': return 'DOUBLE'
        if a == 'S': return 'STAND'
        return 'HIT'

    tot = min(max(tot, 4), 21)
    a = HARD.get(tot, 'HHHHHHHHHH')[di]
    if a == 'D': return 'DOUBLE'
    if a == 'S': return 'STAND'
    if a == 'R': return 'SURRENDER'
    return 'HIT'

STYLES = {
    'HIT':       (GREEN,  '↑',  'HIT'),
    'STAND':     (GOLD,   '—',  'STAND'),
    'DOUBLE':    (CYAN,   '✦',  'DOUBLE DOWN'),
    'SPLIT':     (PURPLE, '⟺', 'SPLIT'),
    'SURRENDER': (RED,    '✕',  'SURRENDER'),
}

class App:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title('Blackjack Advisor')
        self.root.configure(bg=BG)
        self.root.attributes('-topmost', True)
        self.root.resizable(False, False)
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        W, H = 500, 540
        self.root.geometry(f'{W}x{H}+{sw//2-W//2}+{sh//2-H//2}')
        self._vars = {}
        self._build()

    def _build(self):
        r = self.root
        tk.Label(r, text='BLACKJACK ADVISOR', bg=BG,
                 fg=GOLD, font=('Courier', 20, 'bold')).pack(pady=(22,2))
        tk.Label(r, text='answer updates as you type',
                 bg=BG, fg=DIM, font=('Courier', 10)).pack(pady=(0,16))

        for lbl, key, hint in [
            ('DEALER CARD 1', 'd1',      'A  2–9  T  J  Q  K'),
            ('DEALER CARD 2', 'd2',      'A  2–9  T  J  Q  K'),
            ('YOUR CARD',     'player',  'type your card(s)  e.g.  A  or  8 K'),
            ('BALANCE  $',    'balance', ''),
            ('BET  $',        'bet',     ''),
        ]:
            self._row(r, lbl, key, hint)

        tk.Frame(r, bg=BORDER, height=1).pack(fill='x', padx=28, pady=12)

        self.box = tk.Frame(r, bg=PANEL, highlightthickness=3,
                             highlightbackground=BORDER)
        self.box.pack(fill='x', padx=24)

        self.icon_lbl   = tk.Label(self.box, text='?', bg=PANEL, fg=DIM,
                                    font=('Courier', 56, 'bold'))
        self.action_lbl = tk.Label(self.box, text='WAITING', bg=PANEL, fg=DIM,
                                    font=('Courier', 36, 'bold'))
        self.sub_lbl    = tk.Label(self.box, text='Enter the cards above',
                                    bg=PANEL, fg=DIM, font=('Courier', 11),
                                    wraplength=450)
        self.icon_lbl.pack(pady=(14,0))
        self.action_lbl.pack()
        self.sub_lbl.pack(pady=(4,18))

    def _row(self, parent, label, key, hint):
        f = tk.Frame(parent, bg=BG)
        f.pack(fill='x', padx=30, pady=4)
        tk.Label(f, text=label, bg=BG, fg=DIM,
                 font=('Courier', 10, 'bold'), width=14, anchor='w').pack(side='left')
        v = tk.StringVar()
        v.trace_add('write', lambda *_: self._update())
        self._vars[key] = v
        w = 14 if key == 'player' else 8
        tk.Entry(f, textvariable=v, bg=FIELD, fg=WHITE,
                 font=('Courier', 18, 'bold'), insertbackground=WHITE,
                 relief='flat', highlightthickness=2,
                 highlightbackground=BORDER, highlightcolor=GOLD,
                 width=w).pack(side='left', ipady=7, padx=(8,8))
        if hint:
            tk.Label(f, text=hint, bg=BG, fg=DIM, font=('Courier', 9)).pack(side='left')

    def _update(self, *_):
        d1_raw = self._vars['d1'].get()
        d2_raw = self._vars['d2'].get()
        pl_raw = self._vars['player'].get()

        d1 = parse_card(d1_raw)
        d2 = parse_card(d2_raw)

        # Parse all player cards (space separated)
        tokens       = pl_raw.strip().upper().split()
        player_cards = [parse_card(t) for t in tokens if parse_card(t) is not None]

        # Need at least dealer upcard + 1 player card
        if d1 is None or not player_cards:
            self._waiting(); return

        action = get_action(player_cards, d1)
        col, icon, text = STYLES[action]

        tot  = best_total(player_cards)
        soft = is_soft(player_cards)

        d1_str = d1_raw.strip().upper()
        d2_str = (d2_raw.strip().upper() + ' ' + d1_str) if d2 else d1_str
        sub = f'Your total: {"Soft " if soft else ""}{tot}   Dealer: {d2_str}'

        try:
            b = float(self._vars['balance'].get().replace('$','').replace(',',''))
            sub += f'   Balance: ${b:,.0f}'
        except: pass
        try:
            bt = float(self._vars['bet'].get().replace('$','').replace(',',''))
            sub += f'   Bet: ${bt:,.0f}'
        except: pass

        self.box.config(highlightbackground=col)
        self.icon_lbl.config(text=icon, fg=col)
        self.action_lbl.config(text=text, fg=col)
        self.sub_lbl.config(text=sub, fg=col)

    def _waiting(self):
        self.box.config(highlightbackground=BORDER)
        self.icon_lbl.config(text='?', fg=DIM)
        self.action_lbl.config(text='WAITING', fg=DIM)
        self.sub_lbl.config(text='Enter the cards above', fg=DIM)

    def run(self):
        self.root.mainloop()

if __name__ == '__main__':
    App().run()

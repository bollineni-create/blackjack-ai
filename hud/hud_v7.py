#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  BLACKJACK AI — HUD v7.0 — ABSOLUTE CLARITY EDITION                        ║
║                                                                              ║
║  What's new in v7:                                                           ║
║  • Completely redesigned UI — massive fonts, 2-panel layout                 ║
║  • Screen Scan — draw a region on your monitor, auto-detects cards          ║
║  • Live Balance — editable field, updates every hand                        ║
║  • Live Bet — editable with quick +/- buttons                               ║
║  • Card dock — shows detected/entered cards as visual tiles                 ║
║  • All v5 math retained: SCORE, N0, RoR, Float, Heat, Omega II             ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
import sys, os, time, math, json, argparse, threading, re
from typing import Optional, List, Tuple, Dict
from dataclasses import dataclass, field
from collections import deque
from pathlib import Path

# Screen capture / OCR
try:
    from PIL import ImageGrab, Image, ImageFilter, ImageEnhance
    PIL_OK = True
except ImportError:
    PIL_OK = False

try:
    import pytesseract
    OCR_OK = True
except ImportError:
    OCR_OK = False

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.strategy import get_action, HandState, Action, best_total, has_soft_ace
from core.counting import CardCounter, HI_LO_TAGS

# ═══════════════════════════════════════════════════════════════════════════════
# THEME
# ═══════════════════════════════════════════════════════════════════════════════
BG     = '#0a0a0f'
PANEL  = '#12121f'
CARD   = '#1a1a2e'
DARK   = '#08080e'
WHITE  = '#f0f0ff'
DIM    = '#44446a'
SOFT   = '#8888bb'
GOLD   = '#ffd700'
GREEN  = '#00ff88'
RED    = '#ff3355'
CYAN   = '#00e5ff'
ORANGE = '#ff9800'
PURPLE = '#c084fc'
AMBER  = '#ffbf00'
TEAL   = '#40e0d0'
STEEL  = '#7799bb'
LIME   = '#aaff00'

ACTION_COLORS = {
    'HIT':        ('#00ff88', '#001a0d'),
    'STAND':      ('#ffd700', '#1a1400'),
    'DOUBLE':     ('#00e5ff', '#001a1f'),
    'SPLIT':      ('#c084fc', '#120020'),
    'SURRENDER':  ('#ff3355', '#200010'),
    'WAIT':       ('#44446a', '#0a0a12'),
    'INSURANCE':  ('#ffbf00', '#1a1200'),
    'SCOUT':      ('#7799bb', '#0a1020'),
}

ACTION_TEXT = {
    'HIT': 'HIT', 'STAND': 'STAND', 'DOUBLE': 'DOUBLE',
    'SPLIT': 'SPLIT', 'SURRENDER': 'SURR', 'WAIT': 'WAITING',
    'INSURANCE': 'INSURE', 'SCOUT': 'SCOUT',
}

CARD_KEYS = {'a':1,'2':2,'3':3,'4':4,'5':5,'6':6,'7':7,'8':8,'9':9,
             '0':10,'t':10,'j':10,'q':10,'k':10}
CARD_DISP = {1:'A',2:'2',3:'3',4:'4',5:'5',6:'6',7:'7',8:'8',9:'9',10:'10'}

OMEGA2 = {1:0, 2:1, 3:1, 4:2, 5:2, 6:2, 7:1, 8:0, 9:-1, 10:-2}

DEVIATIONS = [
    (16,10,False,'HIT','STAND',        0, True),
    (15,10,False,'HIT','SURRENDER',    0, True),
    (10,10,False,'HIT','DOUBLE',       4, True),
    (10, 9,False,'HIT','DOUBLE',       1, True),
    (12, 3,False,'HIT','STAND',        2, True),
    (12, 2,False,'HIT','STAND',        3, True),
    (11,10,False,'HIT','DOUBLE',       1, True),
    (12, 4,False,'STAND','HIT',       -1, False),
    (12, 5,False,'STAND','HIT',       -2, False),
    (12, 6,False,'STAND','HIT',       -1, False),
    (13, 2,False,'STAND','HIT',       -1, False),
    (13, 3,False,'STAND','HIT',       -2, False),
    (9,  2,False,'HIT','DOUBLE',       1, True),
    (9,  7,False,'HIT','DOUBLE',       3, True),
    (16, 9,False,'HIT','STAND',        5, True),
    (20, 5,False,'STAND','SPLIT',      5, True),
    (20, 6,False,'STAND','SPLIT',      4, True),
    (14,10,False,'HIT','SURRENDER',    3, True),
    (15, 9,False,'HIT','SURRENDER',    2, True),
    (15, 1,False,'HIT','SURRENDER',    1, True),
]

SAVE_DIR  = Path.home() / '.blackjack_ai'
SAVE_FILE = SAVE_DIR / 'session_history.json'


# ═══════════════════════════════════════════════════════════════════════════════
# MATH ENGINE
# ═══════════════════════════════════════════════════════════════════════════════

def lookup_deviation(ptotal, dealer, tc, soft=False):
    for p,d,s,basic,dev,thr,above in DEVIATIONS:
        if p!=ptotal or d!=dealer or s!=soft: continue
        if above and tc>=thr: return dev
        if not above and tc<thr: return dev
    return None

def float_factor(pen):
    pts = [(0.40,0.85),(0.50,1.00),(0.60,1.06),(0.70,1.10),
           (0.75,1.12),(0.80,1.15),(0.85,1.18),(0.90,1.25),(0.95,1.30)]
    if pen <= pts[0][0]: return pts[0][1]
    if pen >= pts[-1][0]: return pts[-1][1]
    for i in range(len(pts)-1):
        lo,lv = pts[i]; hi,hv = pts[i+1]
        if lo <= pen <= hi:
            return lv + (hv-lv)*(pen-lo)/(hi-lo)
    return 1.0

def calc_ror(bankroll, unit_bet, edge, variance=1.33):
    if edge <= 0 or unit_bet <= 0: return 1.0
    units = bankroll / unit_bet
    return min(1.0, math.exp(-2 * edge * units / variance))

def variance_for_decks(d):
    return {1:1.20,2:1.25,4:1.30,6:1.33,8:1.35}.get(d, 1.33)

def kelly_bet(bankroll, edge, variance, fraction=0.35, min_bet=10, max_bet=500):
    if edge <= 0: return min_bet
    full_kelly = (edge / variance) * bankroll
    bet = full_kelly * fraction
    return max(min_bet, min(max_bet, round(bet / 5) * 5))


# ═══════════════════════════════════════════════════════════════════════════════
# SCREEN SCANNER
# ═══════════════════════════════════════════════════════════════════════════════

class ScreenScanner:
    """Captures a screen region and OCRs card values from it."""

    def __init__(self):
        self.region   = None   # (x1,y1,x2,y2)
        self.active   = False
        self.callback = None   # fn(cards: list[int])
        self._thread  = None
        self._stop    = False

    def set_region(self, x1, y1, x2, y2):
        self.region = (x1, y1, x2, y2)

    def start(self, callback, interval=2.0):
        if not PIL_OK or not OCR_OK: return False
        self.callback = callback
        self._stop    = False
        self._thread  = threading.Thread(target=self._loop,
                                         args=(interval,), daemon=True)
        self._thread.start()
        self.active = True
        return True

    def stop(self):
        self._stop  = True
        self.active = False

    def _loop(self, interval):
        while not self._stop:
            if self.region:
                cards = self._scan_once()
                if cards and self.callback:
                    self.callback(cards)
            time.sleep(interval)

    def _scan_once(self):
        try:
            x1,y1,x2,y2 = self.region
            img = ImageGrab.grab(bbox=(x1,y1,x2,y2))
            # Enhance for OCR
            img = img.convert('L')
            img = ImageEnhance.Contrast(img).enhance(3.0)
            img = img.resize((img.width*2, img.height*2), Image.LANCZOS)
            raw = pytesseract.image_to_string(img,
                config='--psm 7 -c tessedit_char_whitelist=A234567890JQK')
            return self._parse_cards(raw)
        except Exception:
            return []

    @staticmethod
    def _parse_cards(text):
        text = text.upper().strip()
        cards = []
        tokens = re.findall(r'10|[A23456789JQK]', text)
        for t in tokens:
            if t == 'A':      cards.append(1)
            elif t == '10':   cards.append(10)
            elif t in 'JQK':  cards.append(10)
            elif t.isdigit(): cards.append(int(t))
        return cards


# ═══════════════════════════════════════════════════════════════════════════════
# REGION SELECTOR — transparent overlay for drawing scan region
# ═══════════════════════════════════════════════════════════════════════════════

class RegionSelector:
    """Full-screen transparent overlay; user drags to select scan region."""

    def __init__(self, root, callback):
        self.callback = callback
        self.top = tk.Toplevel(root)
        self.top.attributes('-fullscreen', True)
        self.top.attributes('-alpha', 0.3)
        self.top.configure(bg='black')
        self.top.attributes('-topmost', True)

        lbl = tk.Label(self.top, text='Drag to select the table area',
                       font=('Helvetica',24,'bold'), fg='white', bg='black')
        lbl.place(relx=0.5, rely=0.05, anchor='center')

        self.canvas = tk.Canvas(self.top, cursor='crosshair',
                                bg='black', highlightthickness=0)
        self.canvas.pack(fill='both', expand=True)

        self.sx = self.sy = 0
        self.rect = None
        self.canvas.bind('<ButtonPress-1>',   self._start)
        self.canvas.bind('<B1-Motion>',        self._drag)
        self.canvas.bind('<ButtonRelease-1>',  self._finish)
        self.top.bind('<Escape>', lambda e: self.top.destroy())

    def _start(self, e):
        self.sx, self.sy = e.x_root, e.y_root
        if self.rect: self.canvas.delete(self.rect)

    def _drag(self, e):
        if self.rect: self.canvas.delete(self.rect)
        self.rect = self.canvas.create_rectangle(
            self.sx, self.sy, e.x_root, e.y_root,
            outline='#00ff88', width=3, fill='')

    def _finish(self, e):
        x1,y1 = min(self.sx,e.x_root), min(self.sy,e.y_root)
        x2,y2 = max(self.sx,e.x_root), max(self.sy,e.y_root)
        self.top.destroy()
        if x2-x1 > 30 and y2-y1 > 20:
            self.callback(x1, y1, x2, y2)


# ═══════════════════════════════════════════════════════════════════════════════
# GAME STATE
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class GameState:
    decks:        int   = 6
    min_bet:      float = 10.0
    max_bet:      float = 500.0
    kelly:        float = 0.35
    bankroll:     float = 1000.0
    start_bank:   float = 1000.0

    rc:           int   = 0
    omega_rc:     int   = 0
    cards_seen:   int   = 0
    dealer:       List  = field(default_factory=list)
    player:       List  = field(default_factory=list)
    split_hand:   List  = field(default_factory=list)
    in_split:     bool  = False
    dealer_mode:  bool  = False
    scout_mode:   bool  = False

    hands:        int   = 0
    wins:         int   = 0
    losses:       int   = 0
    pushes:       int   = 0
    pnl:          float = 0.0
    peak_bank:    float = 1000.0
    max_dd:       float = 0.0
    session_start:float = field(default_factory=time.time)

    last_bet:     float = 0.0
    heat:         float = 0.0
    hand_times:   List  = field(default_factory=list)

    # Undo stack
    undo_stack:   List  = field(default_factory=list)

    def true_count(self):
        decks_rem = max(0.25, (self.decks * 52 - self.cards_seen) / 52)
        return self.rc / decks_rem

    def penetration(self):
        total = self.decks * 52
        return self.cards_seen / total if total > 0 else 0

    def variance(self):
        return variance_for_decks(self.decks)

    def float_tc(self):
        return self.true_count() * float_factor(self.penetration())

    def edge(self):
        return -0.004 + self.float_tc() * 0.005

    def optimal_bet(self):
        return kelly_bet(self.bankroll, max(0, self.edge()),
                         self.variance(), self.kelly, self.min_bet, self.max_bet)

    def ror(self):
        opt = self.optimal_bet()
        return calc_ror(self.bankroll, opt, max(0, self.edge()), self.variance())

    def n0(self):
        e = max(0, self.edge())
        if e <= 0: return float('inf')
        return self.variance() / (e ** 2)

    def elapsed(self):
        return time.time() - self.session_start

    def win_rate(self):
        if self.hands == 0: return 0.0
        return self.wins / self.hands

    def ev_per_hour(self):
        elapsed = self.elapsed()
        if elapsed < 30: return 0.0
        hph = (self.hands / elapsed) * 3600
        return max(0, self.edge()) * self.optimal_bet() * hph

    def push_card(self, val):
        """Add a card and record to undo stack."""
        snap = (self.rc, self.omega_rc, self.cards_seen,
                list(self.dealer), list(self.player), list(self.split_hand))
        self.undo_stack.append(snap)
        if len(self.undo_stack) > 30:
            self.undo_stack.pop(0)
        # Hi-Lo count
        if val in (2,3,4,5,6):   self.rc += 1
        elif val in (10,1):       self.rc -= 1
        # Omega II
        self.omega_rc += OMEGA2.get(val, 0)
        self.cards_seen += 1

    def undo(self):
        if not self.undo_stack: return
        (self.rc, self.omega_rc, self.cards_seen,
         self.dealer, self.player, self.split_hand) = self.undo_stack.pop()
        self.dealer = list(self.dealer)
        self.player = list(self.player)
        self.split_hand = list(self.split_hand)


# ═══════════════════════════════════════════════════════════════════════════════
# CARD TILE WIDGET
# ═══════════════════════════════════════════════════════════════════════════════

def make_card_tile(parent, value, suit='', size='normal'):
    """Draw a playing card as a canvas widget."""
    W,H = (54,76) if size=='normal' else (40,56)
    c = tk.Canvas(parent, width=W, height=H, bg=CARD, highlightthickness=1,
                  highlightbackground=DIM)
    label = CARD_DISP.get(value, str(value))
    # Card background
    c.create_rectangle(2,2,W-2,H-2, fill='#1e1e35', outline=DIM, width=1)
    # Value text
    red_cards = {'♥','♦'}
    col = RED if suit in red_cards else WHITE
    fs  = 22 if size=='normal' else 16
    c.create_text(W//2, H//2, text=label, font=('Helvetica',fs,'bold'),
                  fill=col, anchor='center')
    if suit:
        c.create_text(W//2, H-10, text=suit, font=('Helvetica',9), fill=col)
    return c


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN HUD
# ═══════════════════════════════════════════════════════════════════════════════

class HUDv7:

    def __init__(self, state: GameState):
        self.g = state
        self.scanner  = ScreenScanner()
        self._scan_pending: List[int] = []
        self._last_scan_cards: List[int] = []

        self.root = tk.Tk()
        self.root.title('Blackjack AI  v7.0  —  Absolute Clarity')
        self.root.configure(bg=BG)
        self.root.resizable(True, True)

        # Tkinter variables
        self.balance_var = tk.StringVar(value=f'{self.g.bankroll:.0f}')
        self.bet_var     = tk.StringVar(value=f'{self.g.optimal_bet():.0f}')
        self.scan_status = tk.StringVar(value='⊙  Screen Scan OFF')

        self._build_ui()
        self._bind_keys()
        self._tick()

    # ─── BUILD UI ──────────────────────────────────────────────────────────────

    def _build_ui(self):
        # ── Top bar: Balance + Bet ──────────────────────────────────────────
        top = tk.Frame(self.root, bg=DARK, pady=8)
        top.pack(fill='x', padx=0, pady=0)
        self._build_topbar(top)

        # ── Main body: left + right panels ─────────────────────────────────
        body = tk.Frame(self.root, bg=BG)
        body.pack(fill='both', expand=True, padx=12, pady=(0,8))

        left  = tk.Frame(body, bg=BG, width=480)
        left.pack(side='left', fill='both', expand=True)
        left.pack_propagate(False)

        sep = tk.Frame(body, bg=DIM, width=2)
        sep.pack(side='left', fill='y', padx=8)

        right = tk.Frame(body, bg=BG, width=360)
        right.pack(side='left', fill='both')

        self._build_left(left)
        self._build_right(right)

        # ── Bottom bar: keyboard controls ───────────────────────────────────
        self._build_bottom()

    def _build_topbar(self, parent):
        # Balance
        lbl_bal = tk.Label(parent, text='💰 BALANCE', font=('Helvetica',11,'bold'),
                           fg=SOFT, bg=DARK)
        lbl_bal.pack(side='left', padx=(16,4))
        self.bal_entry = tk.Entry(parent, textvariable=self.balance_var,
                                  font=('Helvetica',22,'bold'), fg=GOLD, bg=PANEL,
                                  insertbackground=GOLD, relief='flat',
                                  justify='center', width=8)
        self.bal_entry.pack(side='left', padx=(0,20), ipady=4)
        self.bal_entry.bind('<Return>', self._on_balance_change)
        self.bal_entry.bind('<FocusOut>', self._on_balance_change)

        # Bet
        lbl_bet = tk.Label(parent, text='BET', font=('Helvetica',11,'bold'),
                           fg=SOFT, bg=DARK)
        lbl_bet.pack(side='left', padx=(0,4))
        btn_minus = tk.Button(parent, text='−', font=('Helvetica',18,'bold'),
                              fg=RED, bg=PANEL, relief='flat', bd=0,
                              command=self._bet_down, cursor='hand2',
                              activebackground=CARD, activeforeground=RED)
        btn_minus.pack(side='left')
        self.bet_entry = tk.Entry(parent, textvariable=self.bet_var,
                                  font=('Helvetica',22,'bold'), fg=CYAN, bg=PANEL,
                                  insertbackground=CYAN, relief='flat',
                                  justify='center', width=6)
        self.bet_entry.pack(side='left', ipady=4)
        self.bet_entry.bind('<Return>', self._on_bet_change)
        btn_plus = tk.Button(parent, text='+', font=('Helvetica',18,'bold'),
                             fg=GREEN, bg=PANEL, relief='flat', bd=0,
                             command=self._bet_up, cursor='hand2',
                             activebackground=CARD, activeforeground=GREEN)
        btn_plus.pack(side='left', padx=(0,20))

        # Session P&L in top bar
        self.topbar_pnl = tk.Label(parent, text='P&L  $0',
                                   font=('Helvetica',16,'bold'), fg=SOFT, bg=DARK)
        self.topbar_pnl.pack(side='left', padx=16)

        # Scan button (right side)
        tk.Button(parent, text='📷  SCAN SCREEN',
                  font=('Helvetica',12,'bold'), fg=TEAL, bg=PANEL,
                  relief='flat', bd=0, padx=14, pady=4, cursor='hand2',
                  command=self._start_scan,
                  activebackground=CARD, activeforeground=TEAL
                  ).pack(side='right', padx=(0,16))
        self.scan_lbl = tk.Label(parent, textvariable=self.scan_status,
                                 font=('Helvetica',10), fg=STEEL, bg=DARK)
        self.scan_lbl.pack(side='right', padx=4)

    def _build_left(self, parent):
        # ── Action box ─────────────────────────────────────────────────────
        self.action_frame = tk.Frame(parent, bg=ACTION_COLORS['WAIT'][1],
                                     bd=0, relief='flat')
        self.action_frame.pack(fill='x', pady=(10,6))
        self.action_lbl = tk.Label(self.action_frame, text='WAITING',
                                   font=('Helvetica',72,'bold'),
                                   fg=ACTION_COLORS['WAIT'][0],
                                   bg=ACTION_COLORS['WAIT'][1],
                                   pady=24)
        self.action_lbl.pack(fill='x')
        self.deviation_lbl = tk.Label(self.action_frame, text='',
                                      font=('Helvetica',14,'bold'),
                                      fg=AMBER, bg=ACTION_COLORS['WAIT'][1],
                                      pady=4)
        self.deviation_lbl.pack(fill='x')

        # ── Dealer row ──────────────────────────────────────────────────────
        dealer_row = tk.Frame(parent, bg=BG)
        dealer_row.pack(fill='x', pady=(6,2), padx=4)
        tk.Label(dealer_row, text='DEALER', font=('Helvetica',11,'bold'),
                 fg=SOFT, bg=BG, width=8, anchor='w').pack(side='left')
        self.dealer_cards_frame = tk.Frame(dealer_row, bg=BG)
        self.dealer_cards_frame.pack(side='left', padx=6)
        self.dealer_total_lbl = tk.Label(dealer_row, text='',
                                         font=('Helvetica',20,'bold'),
                                         fg=GOLD, bg=BG)
        self.dealer_total_lbl.pack(side='left', padx=12)

        # ── Player row ──────────────────────────────────────────────────────
        player_row = tk.Frame(parent, bg=BG)
        player_row.pack(fill='x', pady=(2,2), padx=4)
        tk.Label(player_row, text='YOU', font=('Helvetica',11,'bold'),
                 fg=SOFT, bg=BG, width=8, anchor='w').pack(side='left')
        self.player_cards_frame = tk.Frame(player_row, bg=BG)
        self.player_cards_frame.pack(side='left', padx=6)
        self.player_total_lbl = tk.Label(player_row, text='',
                                         font=('Helvetica',20,'bold'),
                                         fg=CYAN, bg=BG)
        self.player_total_lbl.pack(side='left', padx=12)

        # ── Card input row (scan preview + manual indicator) ────────────────
        scan_row = tk.Frame(parent, bg=PANEL, pady=4)
        scan_row.pack(fill='x', padx=4, pady=(4,6))
        tk.Label(scan_row, text='Cards detected:', font=('Helvetica',10),
                 fg=SOFT, bg=PANEL).pack(side='left', padx=8)
        self.detected_lbl = tk.Label(scan_row, text='—',
                                     font=('Helvetica',13,'bold'),
                                     fg=TEAL, bg=PANEL)
        self.detected_lbl.pack(side='left', padx=8)
        tk.Button(scan_row, text='Accept Detected',
                  font=('Helvetica',11), fg=GREEN, bg=CARD,
                  relief='flat', bd=0, padx=10, pady=2, cursor='hand2',
                  command=self._accept_detected,
                  activebackground=PANEL, activeforeground=GREEN
                  ).pack(side='right', padx=8)

        # ── Mode indicator ──────────────────────────────────────────────────
        mode_row = tk.Frame(parent, bg=BG)
        mode_row.pack(fill='x', padx=4)
        self.mode_lbl = tk.Label(mode_row, text='● PLAYER CARDS',
                                 font=('Helvetica',12,'bold'), fg=GREEN, bg=BG)
        self.mode_lbl.pack(side='left')
        self.wong_lbl = tk.Label(mode_row, text='',
                                 font=('Helvetica',12,'bold'), fg=AMBER, bg=BG)
        self.wong_lbl.pack(side='right', padx=8)

        # ── Outcome buttons ─────────────────────────────────────────────────
        outcome_row = tk.Frame(parent, bg=BG)
        outcome_row.pack(fill='x', padx=4, pady=(8,4))
        outcomes = [
            ('WIN',       GREEN,  self._win),
            ('LOSS',      RED,    self._loss),
            ('PUSH',      AMBER,  self._push),
            ('BJ',        GOLD,   self._blackjack),
            ('SURR',      ORANGE, self._surrender_outcome),
        ]
        for label, color, cmd in outcomes:
            tk.Button(outcome_row, text=label,
                      font=('Helvetica',14,'bold'), fg=color, bg=CARD,
                      relief='flat', bd=0, padx=12, pady=8, cursor='hand2',
                      command=cmd, width=5,
                      activebackground=PANEL, activeforeground=color
                      ).pack(side='left', padx=3)

        # ── Command buttons row ─────────────────────────────────────────────
        cmd_row = tk.Frame(parent, bg=BG)
        cmd_row.pack(fill='x', padx=4, pady=4)
        cmds = [
            ('NEW HAND',  SOFT,   self._new_hand),
            ('RESHUFFLE', PURPLE, self._reshuffle),
            ('NEW TABLE', TEAL,   self._new_table),
            ('UNDO',      STEEL,  self._undo),
        ]
        for label, color, cmd in cmds:
            tk.Button(cmd_row, text=label,
                      font=('Helvetica',11,'bold'), fg=color, bg=CARD,
                      relief='flat', bd=0, padx=10, pady=6, cursor='hand2',
                      command=cmd,
                      activebackground=PANEL, activeforeground=color
                      ).pack(side='left', padx=3, fill='x', expand=True)

    def _build_right(self, parent):
        def section(title):
            f = tk.Frame(parent, bg=PANEL, pady=6, padx=10)
            f.pack(fill='x', pady=(0,6))
            tk.Label(f, text=title, font=('Helvetica',9,'bold'),
                     fg=DIM, bg=PANEL).pack(anchor='w')
            return f

        # ── Count ───────────────────────────────────────────────────────────
        cf = section('COUNT')
        row1 = tk.Frame(cf, bg=PANEL); row1.pack(fill='x', pady=2)
        self.tc_lbl   = self._big_lbl(row1, 'TC  0.0', CYAN, 32)
        self.edge_lbl = self._big_lbl(row1, 'EDGE  −0.4%', SOFT, 20)
        row2 = tk.Frame(cf, bg=PANEL); row2.pack(fill='x', pady=2)
        self.rc_lbl   = self._stat_lbl(row2, 'RC  0')
        self.ftc_lbl  = self._stat_lbl(row2, 'FTC  0.0')
        self.pen_lbl  = self._stat_lbl(row2, 'PEN  0%')
        self.omega_lbl= self._stat_lbl(row2, 'ΩII  0')

        # ── Bet recommendation ──────────────────────────────────────────────
        bf = section('BET RAMP')
        self.bet_rec_lbl = tk.Label(bf, text='Optimal Bet  $—',
                                    font=('Helvetica',24,'bold'), fg=GOLD, bg=PANEL)
        self.bet_rec_lbl.pack(anchor='w')
        self.kelly_detail = tk.Label(bf, text='', font=('Helvetica',11),
                                     fg=SOFT, bg=PANEL)
        self.kelly_detail.pack(anchor='w')

        # ── Risk ────────────────────────────────────────────────────────────
        rf = section('RISK')
        rrow = tk.Frame(rf, bg=PANEL); rrow.pack(fill='x')
        self.ror_lbl  = self._big_lbl(rrow, 'RoR  —%',  RED,   20)
        self.n0_lbl   = self._big_lbl(rrow, 'N0  —',    STEEL, 14)
        # RoR color bar
        self.ror_bar_frame = tk.Frame(rf, bg=PANEL, height=12)
        self.ror_bar_frame.pack(fill='x', pady=(4,0))
        self.ror_bar = tk.Canvas(self.ror_bar_frame, height=12, bg=DIM,
                                 highlightthickness=0)
        self.ror_bar.pack(fill='x')

        # ── Session Stats ────────────────────────────────────────────────────
        sf = section('SESSION')
        grid = tk.Frame(sf, bg=PANEL); grid.pack(fill='x')
        self.stat_labels = {}
        stats = [
            ('HANDS','0'), ('WIN%','0%'), ('P&L','$0'),
            ('PEAK','$0'), ('MAX DD','$0'), ('EV/HR','$0'),
            ('TIME','0:00'), ('ROI','0%'),
        ]
        for i,(k,v) in enumerate(stats):
            r,c = divmod(i,2)
            cell = tk.Frame(grid, bg=CARD, padx=8, pady=4)
            cell.grid(row=r, column=c, padx=3, pady=2, sticky='ew')
            grid.columnconfigure(c, weight=1)
            tk.Label(cell, text=k, font=('Helvetica',9),
                     fg=DIM, bg=CARD).pack(anchor='w')
            lbl = tk.Label(cell, text=v, font=('Helvetica',15,'bold'),
                           fg=WHITE, bg=CARD)
            lbl.pack(anchor='w')
            self.stat_labels[k] = lbl

        # ── Heat ─────────────────────────────────────────────────────────────
        hf = section('CASINO HEAT')
        self.heat_bar_c = tk.Canvas(hf, height=18, bg=DIM,
                                    highlightthickness=0)
        self.heat_bar_c.pack(fill='x', pady=(2,4))
        hr = tk.Frame(hf, bg=PANEL); hr.pack(fill='x')
        self.heat_lbl = tk.Label(hr, text='COLD', font=('Helvetica',14,'bold'),
                                 fg=GREEN, bg=PANEL)
        self.heat_lbl.pack(side='left')
        self.heat_tip = tk.Label(hr, text='', font=('Helvetica',10),
                                 fg=AMBER, bg=PANEL, wraplength=260, justify='left')
        self.heat_tip.pack(side='left', padx=8)

        # ── Alerts ───────────────────────────────────────────────────────────
        self.alert_lbl = tk.Label(parent, text='', font=('Helvetica',11),
                                  fg=AMBER, bg=BG, wraplength=340, justify='left')
        self.alert_lbl.pack(fill='x', padx=4, pady=4)

    def _big_lbl(self, parent, text, color, size):
        lbl = tk.Label(parent, text=text, font=('Helvetica',size,'bold'),
                       fg=color, bg=parent['bg'])
        lbl.pack(side='left', padx=(0,16))
        return lbl

    def _stat_lbl(self, parent, text):
        lbl = tk.Label(parent, text=text, font=('Helvetica',13,'bold'),
                       fg=SOFT, bg=PANEL, padx=8)
        lbl.pack(side='left')
        return lbl

    def _build_bottom(self):
        bar = tk.Frame(self.root, bg=DARK, pady=5)
        bar.pack(fill='x')
        hint = ('Keys: A 2-9 0/T/J/Q/K = card  |  D = dealer mode  |  '
                'W/L/P/J/S = outcome  |  N = new hand  |  R = reshuffle  |  '
                '⌫ = undo')
        tk.Label(bar, text=hint, font=('Helvetica',10), fg=DIM, bg=DARK
                 ).pack(side='left', padx=12)

    # ─── CARD TILES ────────────────────────────────────────────────────────────

    def _refresh_card_tiles(self):
        for w in self.dealer_cards_frame.winfo_children(): w.destroy()
        for w in self.player_cards_frame.winfo_children(): w.destroy()

        for v in self.g.dealer:
            t = make_card_tile(self.dealer_cards_frame, v)
            t.pack(side='left', padx=2)
        for v in self.g.player:
            t = make_card_tile(self.player_cards_frame, v)
            t.pack(side='left', padx=2)

        # Totals
        if self.g.dealer:
            dtot = best_total(self.g.dealer)
            self.dealer_total_lbl.config(text=f'[{dtot}]')
        else:
            self.dealer_total_lbl.config(text='')

        if self.g.player:
            ptot = best_total(self.g.player)
            soft = has_soft_ace(self.g.player)
            stxt = 'soft ' if soft else ''
            self.player_total_lbl.config(text=f'[{stxt}{ptot}]')
        else:
            self.player_total_lbl.config(text='')

    # ─── ANALYTICS REFRESH ─────────────────────────────────────────────────────

    def _refresh(self):
        g = self.g
        tc   = g.true_count()
        ftc  = g.float_tc()
        edge = g.edge()
        pen  = g.penetration()
        opt  = g.optimal_bet()
        ror  = g.ror()
        n0   = g.n0()
        var  = g.variance()

        # ── Count strip ────────────────────────────────────────────────────
        tc_col  = GREEN if tc > 0 else (RED if tc < -1 else SOFT)
        self.tc_lbl.config(text=f'TC  {tc:+.1f}', fg=tc_col)

        edge_pct = edge * 100
        e_col    = GREEN if edge > 0 else RED
        self.edge_lbl.config(text=f'EDGE  {edge_pct:+.2f}%', fg=e_col)

        self.rc_lbl.config(text=f'RC  {g.rc:+d}')
        self.ftc_lbl.config(text=f'FTC  {ftc:+.1f}')
        self.pen_lbl.config(text=f'PEN  {pen*100:.0f}%')

        # Omega II
        dr = max(0.25, (g.decks*52 - g.cards_seen)/52)
        omega_tc = g.omega_rc / dr
        diverge  = abs(omega_tc/1.6 - tc)
        o_col    = (RED if diverge > 2.5 else AMBER if diverge > 1.5 else DIM)
        self.omega_lbl.config(text=f'ΩII  {omega_tc:+.1f}', fg=o_col)

        # ── Bet ramp ────────────────────────────────────────────────────────
        self.bet_rec_lbl.config(text=f'Optimal Bet  ${opt:.0f}')
        kelly_edge = max(0, edge)
        if kelly_edge > 0:
            fk = (kelly_edge / var)
            kd = f'Full Kelly: ${fk*g.bankroll:.0f}  ({g.kelly*100:.0f}% frac)'
        else:
            kd = 'No edge — flat min bet'
        self.kelly_detail.config(text=kd)

        # Wong
        if g.scout_mode:
            self.wong_lbl.config(text='◎ SCOUTING', fg=STEEL)
        elif tc >= 2:
            self.wong_lbl.config(text='▲ WONG IN', fg=GREEN)
        elif tc <= -1:
            self.wong_lbl.config(text='▼ WONG OUT', fg=RED)
        else:
            self.wong_lbl.config(text='')

        # ── Risk ─────────────────────────────────────────────────────────────
        ror_pct  = ror * 100
        ror_col  = GREEN if ror_pct < 5 else AMBER if ror_pct < 15 else ORANGE if ror_pct < 30 else RED
        self.ror_lbl.config(text=f'RoR  {ror_pct:.1f}%', fg=ror_col)
        n0_disp  = f'{n0/1000:.1f}k' if n0 < float('inf') else '∞'
        self.n0_lbl.config(text=f'N0  {n0_disp}')
        # RoR bar
        self._draw_bar(self.ror_bar, ror_pct/100, ror_col)

        # ── Session stats ─────────────────────────────────────────────────
        elapsed = g.elapsed()
        mins, secs = divmod(int(elapsed), 60)
        hrs,  mins = divmod(mins, 60)
        t_str = f'{hrs}:{mins:02d}:{secs:02d}' if hrs else f'{mins}:{secs:02d}'
        pnl_col  = GREEN if g.pnl >= 0 else RED
        roi      = (g.pnl / g.start_bank * 100) if g.start_bank > 0 else 0
        ev_hr    = g.ev_per_hour()

        self.stat_labels['HANDS'].config(text=str(g.hands))
        self.stat_labels['WIN%'].config(text=f'{g.win_rate()*100:.1f}%')
        self.stat_labels['P&L'].config(text=f'${g.pnl:+,.0f}', fg=pnl_col)
        self.stat_labels['PEAK'].config(text=f'${g.peak_bank:,.0f}')
        self.stat_labels['MAX DD'].config(text=f'-${g.max_dd:,.0f}', fg=RED if g.max_dd > 0 else SOFT)
        self.stat_labels['EV/HR'].config(text=f'${ev_hr:,.0f}')
        self.stat_labels['TIME'].config(text=t_str)
        self.stat_labels['ROI'].config(text=f'{roi:+.1f}%', fg=pnl_col)

        # Top bar P&L
        self.topbar_pnl.config(text=f'P&L  ${g.pnl:+,.0f}', fg=pnl_col)

        # ── Heat ─────────────────────────────────────────────────────────────
        h = g.heat
        if h < 20:    hc,ht = GREEN,  'COLD'
        elif h < 40:  hc,ht = TEAL,   'WARM'
        elif h < 60:  hc,ht = AMBER,  'HOT'
        elif h < 80:  hc,ht = ORANGE, 'DANGER'
        else:         hc,ht = RED,    'LEAVE NOW'
        self._draw_bar(self.heat_bar_c, h/100, hc)
        self.heat_lbl.config(text=ht, fg=hc)
        if h >= 50:
            tips = [
                'Tip the dealer visibly',
                'Flat-bet 2–3 hands',
                'Make a cover play — hit 12v2',
                'Take a 10min break',
                'Move to new table',
            ]
            import random as _r
            self.heat_tip.config(text=f'→ {_r.choice(tips)}')
        else:
            self.heat_tip.config(text='')

        # ── Mode indicator ──────────────────────────────────────────────────
        if g.dealer_mode:
            self.mode_lbl.config(text='● DEALER CARDS', fg=AMBER)
        elif g.scout_mode:
            self.mode_lbl.config(text='◎ SCOUTING', fg=STEEL)
        else:
            self.mode_lbl.config(text='● PLAYER CARDS', fg=GREEN)

        # ── Balance sync ───────────────────────────────────────────────────
        self.balance_var.set(f'{g.bankroll:.0f}')

    def _draw_bar(self, canvas, fraction, color):
        canvas.delete('all')
        canvas.update_idletasks()
        w = canvas.winfo_width()
        if w < 2: return
        h = int(canvas['height'])
        fill_w = int(w * max(0, min(1, fraction)))
        canvas.create_rectangle(0,0,fill_w,h, fill=color, outline='')
        canvas.create_rectangle(fill_w,0,w,h, fill=DIM, outline='')

    def _compute_action(self):
        g = self.g
        if not g.player or not g.dealer:
            self._set_action('WAIT')
            return

        tc    = g.true_count()
        ptot  = best_total(g.player)
        dtot  = g.dealer[0] if g.dealer else 10
        soft  = has_soft_ace(g.player)
        nc    = len(g.player)

        # Deviation check first
        dev_action = lookup_deviation(ptot, dtot, tc, soft)

        state  = HandState(player_cards=g.player, dealer_upcard=dtot,
                           can_split=(nc==2 and len(g.player)>=2 and g.player[0]==g.player[1]),
                           can_double=(nc==2), can_surrender=(nc==2))
        result = get_action(state)
        basic  = result[0].value if isinstance(result, tuple) else result.value
        # Map Action enum values to string keys
        val_map = {'S':'STAND','H':'HIT','D':'DOUBLE','P':'SPLIT','R':'SURRENDER'}
        basic = val_map.get(basic, basic)

        if dev_action and dev_action != basic:
            dev_str = f'DEVIATION at TC{tc:+.0f}'
            self._set_action(dev_action, dev_str)
            g.heat = min(100, g.heat + 1.5)
        else:
            self._set_action(basic)

    def _set_action(self, action, dev_hint=''):
        col_fg, col_bg = ACTION_COLORS.get(action, (WHITE, BG))
        text = ACTION_TEXT.get(action, action)
        self.action_frame.config(bg=col_bg)
        self.action_lbl.config(text=text, fg=col_fg, bg=col_bg)
        self.deviation_lbl.config(text=dev_hint, bg=col_bg)

    # ─── CARD INPUT ────────────────────────────────────────────────────────────

    def _input_card(self, val):
        g = self.g
        g.push_card(val)
        if g.dealer_mode:
            g.dealer.append(val)
        else:
            g.player.append(val)
        self._refresh_card_tiles()
        self._compute_action()
        self._refresh()

    # ─── OUTCOMES ─────────────────────────────────────────────────────────────

    def _settle(self, multiplier, label):
        g = self.g
        try:
            bet = float(self.bet_var.get().replace('$','').replace(',',''))
        except ValueError:
            bet = g.optimal_bet()

        profit = bet * multiplier
        g.bankroll += profit
        g.pnl      += profit
        g.hands    += 1
        if multiplier > 0:   g.wins   += 1
        elif multiplier < 0: g.losses += 1
        else:                g.pushes += 1
        g.peak_bank = max(g.peak_bank, g.bankroll)
        dd = g.peak_bank - g.bankroll
        g.max_dd = max(g.max_dd, dd)
        g.last_bet = bet

        # Heat — big wins
        if profit > bet * 1.5:
            g.heat = min(100, g.heat + 4)
        # Heat — long session
        if g.elapsed() > 3600:
            g.heat = min(100, g.heat + 0.1)

        g.hand_times.append(time.time())
        self._refresh()
        self._save_snap()

    def _win(self):        self._settle(1.0,  'WIN');  self._new_hand_auto()
    def _loss(self):       self._settle(-1.0, 'LOSS'); self._new_hand_auto()
    def _push(self):       self._settle(0.0,  'PUSH'); self._new_hand_auto()
    def _blackjack(self):  self._settle(1.5,  'BJ');   self._new_hand_auto()
    def _surrender_outcome(self): self._settle(-0.5, 'SURR'); self._new_hand_auto()

    def _new_hand_auto(self):
        """Clear cards for next hand but keep count."""
        g = self.g
        g.dealer     = []
        g.player     = []
        g.split_hand = []
        g.in_split   = False
        g.dealer_mode = False
        self._refresh_card_tiles()
        self._set_action('WAIT')
        # Suggest Kelly bet
        self.bet_var.set(f'{g.optimal_bet():.0f}')
        self._refresh()

    def _new_hand(self):   self._new_hand_auto()
    def _reshuffle(self):
        g = self.g
        g.rc = 0; g.omega_rc = 0; g.cards_seen = 0
        g.dealer = []; g.player = []; g.split_hand = []
        g.dealer_mode = False
        self.alert_lbl.config(text='♻ Reshuffled — count reset')
        self._refresh_card_tiles()
        self._set_action('WAIT')
        self._refresh()

    def _new_table(self):
        self.g.heat = max(0, self.g.heat - 20)
        self.g.dealer_mode = False
        self.alert_lbl.config(text='↷ New table — heat −20')
        self._refresh()

    def _undo(self):
        self.g.undo()
        self._refresh_card_tiles()
        self._compute_action()
        self._refresh()

    # ─── BALANCE / BET ────────────────────────────────────────────────────────

    def _on_balance_change(self, event=None):
        try:
            v = float(self.balance_var.get().replace('$','').replace(',',''))
            self.g.bankroll = v
            self._refresh()
        except ValueError:
            self.balance_var.set(f'{self.g.bankroll:.0f}')

    def _on_bet_change(self, event=None):
        try:
            float(self.bet_var.get().replace('$','').replace(',',''))
        except ValueError:
            self.bet_var.set(f'{self.g.optimal_bet():.0f}')

    def _bet_down(self):
        try:
            v = float(self.bet_var.get())
            step = 25 if v > 100 else 5
            self.bet_var.set(f'{max(self.g.min_bet, v-step):.0f}')
        except ValueError:
            pass

    def _bet_up(self):
        try:
            v = float(self.bet_var.get())
            step = 25 if v >= 100 else 5
            self.bet_var.set(f'{min(self.g.max_bet, v+step):.0f}')
        except ValueError:
            pass

    # ─── SCREEN SCAN ─────────────────────────────────────────────────────────

    def _start_scan(self):
        if not PIL_OK or not OCR_OK:
            self.alert_lbl.config(
                text='⚠ Scan needs Pillow + pytesseract. pip install pillow pytesseract')
            return
        if self.scanner.active:
            self.scanner.stop()
            self.scan_status.set('⊙  Screen Scan OFF')
            return
        # Open region selector
        self.root.withdraw()
        self.root.after(200, self._open_region_selector)

    def _open_region_selector(self):
        RegionSelector(self.root, self._on_region_selected)

    def _on_region_selected(self, x1, y1, x2, y2):
        self.root.deiconify()
        self.scanner.set_region(x1, y1, x2, y2)
        ok = self.scanner.start(self._on_cards_detected, interval=2.0)
        if ok:
            self.scan_status.set(
                f'◉  Scanning  ({x2-x1}×{y2-y1}px)')
            self.alert_lbl.config(text=f'📷 Scanning region ({x1},{y1})→({x2},{y2})')
        else:
            self.root.deiconify()

    def _on_cards_detected(self, cards):
        """Called from scanner thread — schedule UI update on main thread."""
        self.root.after(0, self._apply_detected, cards)

    def _apply_detected(self, cards):
        if cards == self._last_scan_cards:
            return   # No change
        self._last_scan_cards = cards
        self._scan_pending = cards
        disp = '  '.join(CARD_DISP.get(c,'?') for c in cards)
        self.detected_lbl.config(text=disp or '—')

    def _accept_detected(self):
        """User approves detected cards — push them all."""
        for v in self._scan_pending:
            self._input_card(v)
        self._scan_pending = []
        self.detected_lbl.config(text='—')

    # ─── KEYBOARD ────────────────────────────────────────────────────────────

    def _bind_keys(self):
        self.root.bind('<Key>', self._on_key)
        self.root.focus_set()

    def _on_key(self, event):
        # Don't capture when typing in entry fields
        if isinstance(event.widget, tk.Entry):
            return
        k = event.keysym.lower()

        if k == 'backspace':
            self._undo(); return
        if k == 'd':
            self.g.dealer_mode = not self.g.dealer_mode
            self._refresh(); return
        if k == 'n': self._new_hand(); return
        if k == 'r': self._reshuffle(); return
        if k == 'w': self._win(); return
        if k == 'l': self._loss(); return
        if k == 'p': self._push(); return
        if k == 'j': self._blackjack(); return
        if k == 's': self._surrender_outcome(); return

        # Card input
        char = event.char.lower()
        if char in CARD_KEYS:
            self._input_card(CARD_KEYS[char])

    # ─── PERSISTENCE ─────────────────────────────────────────────────────────

    def _save_snap(self):
        SAVE_DIR.mkdir(parents=True, exist_ok=True)
        try:
            history = []
            if SAVE_FILE.exists():
                history = json.loads(SAVE_FILE.read_text())
            history.append({
                'time':   time.strftime('%Y-%m-%d %H:%M'),
                'hands':  self.g.hands,
                'pnl':    round(self.g.pnl, 2),
                'bank':   round(self.g.bankroll, 2),
                'roi':    round(self.g.pnl/self.g.start_bank*100, 2),
                'max_dd': round(self.g.max_dd, 2),
            })
            SAVE_FILE.write_text(json.dumps(history[-500:], indent=2))
        except Exception:
            pass

    # ─── TICK ────────────────────────────────────────────────────────────────

    def _tick(self):
        self._refresh()
        self.root.after(1000, self._tick)

    # ─── RUN ─────────────────────────────────────────────────────────────────

    def run(self):
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        w, h = 900, 760
        x = (sw - w) // 2
        y = (sh - h) // 2
        self.root.geometry(f'{w}x{h}+{x}+{y}')
        self.root.mainloop()


# ═══════════════════════════════════════════════════════════════════════════════
# SETUP DIALOG
# ═══════════════════════════════════════════════════════════════════════════════

class SetupDialog:

    def __init__(self, root):
        self.result = None
        d = tk.Toplevel(root)
        d.title('Session Setup')
        d.configure(bg=BG)
        d.resizable(False, False)
        d.grab_set()

        def lbl(text, row):
            tk.Label(d, text=text, font=('Helvetica',12), fg=SOFT, bg=BG,
                     anchor='w').grid(row=row, column=0, padx=20, pady=6, sticky='w')

        def ent(var, row):
            e = tk.Entry(d, textvariable=var, font=('Helvetica',14,'bold'),
                         fg=WHITE, bg=PANEL, insertbackground=WHITE,
                         relief='flat', justify='center', width=12)
            e.grid(row=row, column=1, padx=20, pady=6, ipady=4)
            return e

        fields = [
            ('Bankroll ($)',    '10000'),
            ('Min Bet ($)',     '25'),
            ('Max Bet ($)',     '500'),
            ('Kelly Fraction', '0.35'),
            ('Decks',          '6'),
        ]
        self.vars = [tk.StringVar(value=v) for _,v in fields]
        for i,(label,_) in enumerate(fields):
            lbl(label, i)
            ent(self.vars[i], i)

        tk.Button(d, text='START SESSION',
                  font=('Helvetica',14,'bold'), fg=BG, bg=GREEN,
                  relief='flat', padx=20, pady=8, cursor='hand2',
                  command=lambda: self._done(d)
                  ).grid(row=len(fields), column=0, columnspan=2, pady=20)
        root.wait_window(d)

    def _done(self, d):
        try:
            self.result = [float(v.get()) for v in self.vars]
            d.destroy()
        except ValueError:
            pass


# ═══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description='Blackjack AI HUD v7')
    parser.add_argument('--bankroll',  type=float, default=None)
    parser.add_argument('--min-bet',   type=float, default=None)
    parser.add_argument('--max-bet',   type=float, default=None)
    parser.add_argument('--kelly',     type=float, default=None)
    parser.add_argument('--decks',     type=int,   default=None)
    parser.add_argument('--no-setup',  action='store_true')
    args = parser.parse_args()

    root = tk.Tk()
    root.withdraw()

    g = GameState()

    if not args.no_setup and not any([args.bankroll, args.min_bet]):
        dlg = SetupDialog(root)
        if dlg.result:
            g.bankroll, g.min_bet, g.max_bet, g.kelly, d = dlg.result
            g.start_bank = g.bankroll
            g.decks = int(d)

    # CLI args override dialog
    if args.bankroll: g.bankroll = args.bankroll; g.start_bank = args.bankroll
    if args.min_bet:  g.min_bet  = args.min_bet
    if args.max_bet:  g.max_bet  = args.max_bet
    if args.kelly:    g.kelly    = args.kelly
    if args.decks:    g.decks    = args.decks

    root.destroy()
    HUDv7(g).run()


if __name__ == '__main__':
    main()

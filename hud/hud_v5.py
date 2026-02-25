#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  BLACKJACK AI — HUD v5.0 — ABSOLUTE EDGE EDITION                           ║
║                                                                              ║
║  What's new in v5:                                                           ║
║  • SCORE calculator — Schlesinger's metric, best table comparison tool      ║
║  • N0 (neutral point) — hands to overcome variance, live displayed          ║
║  • Risk of Ruin live tracker — real-time ROR% with survival curve           ║
║  • Composition-dependent strategy — 3-card 16s, multi-card soft plays       ║
║  • Casino heat meter — behavioral fingerprinting to track exposure level    ║
║  • Camouflage advisor — periodic cover play suggestions                     ║
║  • Multi-session persistence — JSON log, lifetime stats, bankroll history   ║
║  • Floating advantage engine — depth-adjusted edge (deep shoe bonus)        ║
║  • Table scout mode — back-count entries with Wong in/out signal             ║
║  • Omega II cross-validation — Level 2 count sanity check                   ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import sys, os, time, math, json, csv, random, argparse
from typing import Optional, List, Tuple, Dict, Any
from dataclasses import dataclass, field, asdict
from collections import deque, Counter
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.strategy import get_action, HandState, Action, best_total, has_soft_ace
from core.counting import CardCounter, HI_LO_TAGS

# ═══════════════════════════════════════════════════════════════════════════════
# CONSTANTS & THEME
# ═══════════════════════════════════════════════════════════════════════════════

V        = "5.0 — Absolute Edge"
SAVE_DIR = Path.home() / '.blackjack_ai'
SAVE_FILE = SAVE_DIR / 'session_history.json'

BG      = '#03030d'
PANEL   = '#0a0a1a'
CARD    = '#0f0f26'
BORDER  = '#181838'
WHITE   = '#eeeeff'
DIM     = '#3a3a60'
BRIGHT  = '#9090cc'
GOLD    = '#ffd700'
GREEN   = '#00ff88'
RED     = '#ff3355'
CYAN    = '#00e5ff'
ORANGE  = '#ff9800'
PURPLE  = '#c084fc'
TEAL    = '#40e0d0'
LIME    = '#aaff00'
PINK    = '#ff69b4'
AMBER   = '#ffbf00'
STEEL   = '#7799bb'
ROSE    = '#ff80ab'
SMOKE   = '#555588'

AC = {'HIT':GREEN,'STAND':GOLD,'DOUBLE':CYAN,'SPLIT':PURPLE,
      'SURRENDER':RED,'WAIT':DIM,'INSURANCE':AMBER,'SCOUT':STEEL}
AG = {'HIT':'↑  HIT','STAND':'―  STAND','DOUBLE':'✦  DOUBLE',
      'SPLIT':'⟺  SPLIT','SURRENDER':'✕  SURRENDER',
      'WAIT':'◦  WAITING','INSURANCE':'☂  INSURANCE','SCOUT':'◎  SCOUTING'}

RD = {1:'A',2:'2',3:'3',4:'4',5:'5',6:'6',7:'7',8:'8',9:'9',10:'10'}
CK = {'a':1,'2':2,'3':3,'4':4,'5':5,'6':6,'7':7,'8':8,'9':9,
      '0':10,'t':10,'j':10,'q':10,'k':10}

# Omega II tags (Level 2 count for cross-validation)
OMEGA2_TAGS = {1:0, 2:1, 3:1, 4:2, 5:2, 6:2, 7:1, 8:0, 9:-1, 10:-2}


# ═══════════════════════════════════════════════════════════════════════════════
# ILLUSTRIOUS 18 + FAB 4 — Complete deviation set
# ═══════════════════════════════════════════════════════════════════════════════

DEVIATIONS = [
    (16,10,False,'HIT','STAND',        0, True,  'Stand 16 vs 10'),
    (15,10,False,'HIT','SURRENDER',    0, True,  'Surrender 15 vs 10'),
    (10,10,False,'HIT','DOUBLE',       4, True,  'Double 10 vs 10'),
    (10, 9,False,'HIT','DOUBLE',       1, True,  'Double 10 vs 9'),
    (12, 3,False,'HIT','STAND',        2, True,  'Stand 12 vs 3'),
    (12, 2,False,'HIT','STAND',        3, True,  'Stand 12 vs 2'),
    (11,10,False,'HIT','DOUBLE',       1, True,  'Double 11 vs 10'),
    (12, 4,False,'STAND','HIT',       -1, False, 'Hit 12 vs 4'),
    (12, 5,False,'STAND','HIT',       -2, False, 'Hit 12 vs 5'),
    (12, 6,False,'STAND','HIT',       -1, False, 'Hit 12 vs 6'),
    (13, 2,False,'STAND','HIT',       -1, False, 'Hit 13 vs 2'),
    (13, 3,False,'STAND','HIT',       -2, False, 'Hit 13 vs 3'),
    (9,  2,False,'HIT','DOUBLE',       1, True,  'Double 9 vs 2'),
    (9,  7,False,'HIT','DOUBLE',       3, True,  'Double 9 vs 7'),
    (16, 9,False,'HIT','STAND',        5, True,  'Stand 16 vs 9'),
    (20, 5,False,'STAND','SPLIT',      5, True,  'Split 20s vs 5'),
    (20, 6,False,'STAND','SPLIT',      4, True,  'Split 20s vs 6'),
    (14,10,False,'HIT','SURRENDER',    3, True,  'Surrender 14 vs 10 [Fab4]'),
    (15, 9,False,'HIT','SURRENDER',    2, True,  'Surrender 15 vs 9 [Fab4]'),
    (15, 1,False,'HIT','SURRENDER',    1, True,  'Surrender 15 vs A [Fab4]'),
]

# Composition-dependent exceptions (3+ card hands)
# These override basic strategy based on exact card composition
COMP_DEP_EXCEPTIONS = {
    # (total, dealer, n_cards, is_soft): action
    (16, 10, 3, False): 'STAND',   # 3-card 16 vs 10: stand (less tens in deck effect)
    (16, 10, 4, False): 'STAND',
    (12,  4, 3, False): 'STAND',   # 3-card 12 vs 4: stand (basic=stand, but 2-card hits)
    (15, 10, 3, False): 'SURRENDER',
    # Soft edge cases with 3+ cards
    (18,  2, 3, True):  'STAND',   # Don't double soft 18 vs 2 with 3 cards
    (18,  3, 3, True):  'STAND',
}

def lookup_deviation(ptotal, dealer, tc, is_soft=False):
    for p,d,s,basic,dev,thr,above,desc in DEVIATIONS:
        if p!=ptotal or d!=dealer or s!=is_soft: continue
        if above and tc>=thr: return dev
        if not above and tc<thr: return dev
    return None

def lookup_comp_dep(ptotal, dealer, n_cards, is_soft=False):
    """Composition-dependent override for 3+ card hands."""
    key = (ptotal, dealer, n_cards, is_soft)
    if key in COMP_DEP_EXCEPTIONS:
        return COMP_DEP_EXCEPTIONS[key]
    # Try with n_cards=3 as fallback for 4+ card hands
    key3 = (ptotal, dealer, 3, is_soft)
    return COMP_DEP_EXCEPTIONS.get(key3)

def closest_deviation(ptotal, dealer, tc, is_soft=False):
    best, best_dist = None, float('inf')
    for p,d,s,basic,dev,thr,above,desc in DEVIATIONS:
        if p!=ptotal or d!=dealer or s!=is_soft: continue
        dist = abs(tc-thr)
        if dist < best_dist:
            best_dist = dist
            delta = thr-tc if above else tc-thr
            direction = '≥' if above else '<'
            best = f'{desc} @ TC{thr:+d} [Δ{delta:+.1f}]'
    return best


# ═══════════════════════════════════════════════════════════════════════════════
# SCORE + N0 CALCULATOR  (Schlesinger's System)
# ═══════════════════════════════════════════════════════════════════════════════

class SCORECalculator:
    """
    SCORE = System for Comparing Options in Real Environments
    Source: Don Schlesinger, Blackjack Attack (3rd ed.)

    SCORE = (mu^2 / sigma^2) * (1 + ruin_adjustment)
    where mu = EV/hand, sigma^2 = variance/hand

    N0 = sigma^2 / mu^2 = hands needed for edge to equal 1 std dev of results
    This is the number of hands before you can be 'statistically confident'.

    Higher SCORE = better table opportunity.
    Typical SCORE for 6-deck: 40–70
    Excellent: >70
    World-class: >100 (usually single deck or great pen)
    """

    VARIANCE_TABLE = {
        1: 1.20,   # Single deck
        2: 1.25,   # Double deck
        4: 1.30,   # 4-deck
        6: 1.33,   # 6-deck (standard)
        8: 1.35,   # 8-deck
    }

    def __init__(self, decks: int = 6, penetration: float = 0.75,
                 spread: float = 12.0, kelly_fraction: float = 0.35):
        self.decks       = decks
        self.penetration = penetration
        self.spread      = spread
        self.kf          = kelly_fraction
        self.variance    = self.VARIANCE_TABLE.get(decks, 1.33)

    def ev_per_hand(self, true_count_avg: float = 1.0,
                    bet_avg: float = 50.0) -> float:
        """Expected value per hand at average bet and count."""
        edge = -0.004 + true_count_avg * 0.005
        return max(0, edge) * bet_avg

    def score(self, ev_per_hand: float, bet_avg: float) -> float:
        """
        SCORE = (EV/hand)^2 / (variance/hand) * 10000
        Normalized to bankroll fraction.
        """
        if bet_avg <= 0: return 0.0
        ev_frac    = ev_per_hand / bet_avg
        var_frac   = self.variance
        raw_score  = (ev_frac ** 2 / var_frac) * 10000
        # Penetration multiplier (deeper = more opportunities)
        pen_mult   = 1 + (self.penetration - 0.70) * 2
        return raw_score * max(0.5, pen_mult)

    def n0(self, ev_per_hand: float, bet_size: float) -> float:
        """
        N0 = hands to overcome standard deviation.
        N0 = variance / (ev/bet)^2
        Lower is better — fewer hands needed to prove edge.
        """
        if ev_per_hand <= 0 or bet_size <= 0: return float('inf')
        ev_frac = ev_per_hand / bet_size
        return self.variance / (ev_frac ** 2)

    def ror(self, bankroll: float, unit_bet: float, edge_pct: float) -> float:
        """
        Risk of Ruin (exact formula).
        RoR = e^(-2 * edge * bankroll_in_units / variance)
        """
        if edge_pct <= 0: return 1.0
        units = bankroll / unit_bet
        return min(1.0, math.exp(-2 * edge_pct * units / self.variance))

    def hours_to_double(self, ev_per_hour: float, bankroll: float) -> float:
        """Expected hours to double bankroll at current EV/hr."""
        if ev_per_hour <= 0: return float('inf')
        return bankroll / ev_per_hour

    def rating(self, s: float) -> str:
        if s >= 100: return '★★★ WORLD CLASS'
        if s >= 70:  return '★★  EXCELLENT'
        if s >= 45:  return '★   GOOD'
        if s >= 25:  return '◇   MARGINAL'
        return '✗   POOR'


# ═══════════════════════════════════════════════════════════════════════════════
# FLOATING ADVANTAGE ENGINE
# ═══════════════════════════════════════════════════════════════════════════════

class FloatingAdvantage:
    """
    The Floating Advantage is the phenomenon where the same TC gives more edge
    deeper in the shoe. This is because TC is measured per deck, but the actual
    composition effect is amplified in smaller remaining decks.

    Empirical correction factors (from Snyder/Griffin research):
    At 50% pen:  TC adjustment × 1.0 (baseline)
    At 75% pen:  TC adjustment × 1.12 (+12%)
    At 85% pen:  TC adjustment × 1.18 (+18%)
    At 90% pen:  TC adjustment × 1.25 (+25%)

    This means a TC+4 at 90% penetration is worth the same as TC+5 at 75%.
    """

    PEN_FACTORS = {
        0.40: 0.85,
        0.50: 1.00,
        0.60: 1.06,
        0.70: 1.10,
        0.75: 1.12,
        0.80: 1.15,
        0.85: 1.18,
        0.90: 1.25,
        0.95: 1.30,
    }

    def adjustment_factor(self, penetration: float) -> float:
        """Interpolate factor for current penetration."""
        pens = sorted(self.PEN_FACTORS.keys())
        if penetration <= pens[0]:
            return self.PEN_FACTORS[pens[0]]
        if penetration >= pens[-1]:
            return self.PEN_FACTORS[pens[-1]]
        for i in range(len(pens)-1):
            lo, hi = pens[i], pens[i+1]
            if lo <= penetration <= hi:
                t = (penetration - lo) / (hi - lo)
                return self.PEN_FACTORS[lo] + t*(self.PEN_FACTORS[hi]-self.PEN_FACTORS[lo])
        return 1.0

    def adjusted_tc(self, tc: float, penetration: float) -> float:
        """Effective TC accounting for floating advantage."""
        return tc * self.adjustment_factor(penetration)

    def adjusted_edge(self, tc: float, penetration: float) -> float:
        """Player edge adjusted for floating advantage."""
        eff_tc = self.adjusted_tc(tc, penetration)
        return -0.004 + eff_tc * 0.005

    def bonus_display(self, penetration: float) -> str:
        f = self.adjustment_factor(penetration)
        if f >= 1.20:  return f'Float ×{f:.2f} ★'
        if f >= 1.10:  return f'Float ×{f:.2f}'
        if f >= 1.00:  return ''
        return f'Float ×{f:.2f} ▼'


# ═══════════════════════════════════════════════════════════════════════════════
# CASINO HEAT METER
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class HeatEvent:
    timestamp: float
    description: str
    heat_delta: float

class CasinoHeatMeter:
    """
    Tracks behavioral signals that may trigger casino attention.
    Each factor raises or lowers heat level (0–100).

    Sources of heat:
    - Large bet spreads in short sessions
    - Rapid bet increases after shuffles
    - Correct deviation plays (especially insurance refusals, big doubles)
    - Long sessions at same table
    - Big win sessions
    - Mid-shoe bet jumps

    Camouflage suggestions are generated when heat rises above thresholds.
    """

    def __init__(self):
        self.heat_level  = 0.0    # 0–100
        self.events: List[HeatEvent] = []
        self.hands_at_table  = 0
        self.last_bet        = 0.0
        self.session_start   = time.time()
        self.max_bet_seen    = 0.0
        self.min_bet_seen    = float('inf')
        self.big_wins        = 0
        self.deviations_made = 0
        self.camouflage_due  = False

    def record_bet(self, bet: float, prev_bet: float, tc: float):
        self.hands_at_table += 1
        self.max_bet_seen    = max(self.max_bet_seen, bet)
        self.min_bet_seen    = min(self.min_bet_seen, bet)

        # Bet spread
        if prev_bet > 0:
            ratio = bet / prev_bet
            if ratio >= 4 and tc < 1:
                self._add_heat(8, 'Large bet jump without count justification')
            elif ratio >= 8:
                self._add_heat(5, f'Big bet spread {ratio:.0f}×')
            elif ratio <= 0.25 and tc > 2:
                self._add_heat(4, 'Bet reduction at high count (suspicious)')

        # Bet spread over session
        if self.min_bet_seen > 0 and self.max_bet_seen > 0:
            spread = self.max_bet_seen / self.min_bet_seen
            if spread >= 16:
                self._add_heat(0.5, f'Spread at {spread:.0f}× this session')

    def record_deviation(self, desc: str):
        self.deviations_made += 1
        if self.deviations_made > 6:
            self._add_heat(3, f'Multiple deviations made: {desc}')
        else:
            self._add_heat(1.5, f'Deviation: {desc}')

    def record_win(self, profit: float, bet: float):
        if profit > bet * 2:
            self.big_wins += 1
            if self.big_wins >= 3:
                self._add_heat(4, f'Multiple big wins — ${profit:.0f}')

    def record_time(self):
        elapsed_min = (time.time() - self.session_start) / 60
        if elapsed_min > 60:
            self._add_heat(0.1, 'Long session (>1hr)')
        if elapsed_min > 120:
            self._add_heat(0.2, 'Very long session (>2hr)')

    def new_table(self):
        self.heat_level    = max(0, self.heat_level - 20)
        self.hands_at_table = 0
        self.last_bet       = 0.0
        self.max_bet_seen   = 0.0
        self.min_bet_seen   = float('inf')

    def _add_heat(self, amount: float, desc: str):
        self.heat_level = min(100, self.heat_level + amount)
        self.events.append(HeatEvent(time.time(), desc, amount))
        if self.heat_level >= 50 and not self.camouflage_due:
            self.camouflage_due = True

    def camouflage_suggestion(self) -> Optional[str]:
        """Returns a camouflage suggestion if heat is building."""
        if not self.camouflage_due:
            return None
        self.camouflage_due = False
        suggestions = [
            'Consider a small "mistake" — call for a hit on a 12 vs 2',
            'Tip the dealer — visible tipping signals recreational player',
            'Take a break for 10–15 mins before returning to same table',
            'Flat-bet 2–3 hands regardless of count',
            'Ask the dealer a basic question — show unfamiliarity',
            'Consider moving to a new table or pit',
            'Buy in for different amount (round vs non-round sum)',
            'Refuse insurance obviously at low count — normal behavior',
        ]
        return random.choice(suggestions)

    @property
    def heat_color(self) -> str:
        if self.heat_level < 25:  return GREEN
        if self.heat_level < 50:  return AMBER
        if self.heat_level < 75:  return ORANGE
        return RED

    @property
    def heat_label(self) -> str:
        if self.heat_level < 20:  return 'COLD ✓'
        if self.heat_level < 40:  return 'WARM'
        if self.heat_level < 60:  return 'HOT ⚠'
        if self.heat_level < 80:  return 'DANGER !'
        return 'LEAVE NOW ✕'


# ═══════════════════════════════════════════════════════════════════════════════
# OMEGA II CROSS-VALIDATOR
# ═══════════════════════════════════════════════════════════════════════════════

class OmegaIICounter:
    """
    Omega II is a Level-2, balanced count.
    More accurate than Hi-Lo but harder to maintain.
    We use it as a cross-validation check: if Hi-Lo and Omega II diverge
    significantly, a counting error may have occurred.
    
    Tags: 2=+1  3=+1  4=+2  5=+2  6=+2  7=+1  8=0  9=-1  10=-2  A=0
    """

    def __init__(self, total_decks: int = 6):
        self.total_decks   = total_decks
        self.running_count = 0
        self.cards_seen    = 0

    def see_card(self, card: int):
        self.running_count += OMEGA2_TAGS.get(min(card, 10), 0)
        self.cards_seen += 1

    def reset(self):
        self.running_count = 0
        self.cards_seen    = 0

    @property
    def true_count(self) -> float:
        cards_rem = max(1, self.total_decks * 52 - self.cards_seen)
        decks_rem = cards_rem / 52
        if decks_rem <= 0: return self.running_count
        return self.running_count / decks_rem

    def divergence_from_hilo(self, hilo_tc: float) -> float:
        """How much Omega II TC differs from Hi-Lo TC."""
        # Normalize: Omega II ~1.6× Hi-Lo in units, so scale it
        return abs(self.true_count / 1.6 - hilo_tc)

    def error_flag(self, hilo_tc: float) -> Optional[str]:
        """Return warning if counts diverge significantly."""
        div = self.divergence_from_hilo(hilo_tc)
        if div > 2.5:
            return f'⚠ COUNT ERROR? Hi-Lo TC={hilo_tc:+.1f} vs ΩII TC={self.true_count:+.1f} (Δ{div:.1f})'
        if div > 1.5:
            return f'◈ Verify count: Hi-Lo={hilo_tc:+.1f} / ΩII={self.true_count:+.1f}'
        return None


# ═══════════════════════════════════════════════════════════════════════════════
# MULTI-SESSION PERSISTENCE
# ═══════════════════════════════════════════════════════════════════════════════

class SessionPersistence:
    """Save and load session history to JSON."""

    def __init__(self):
        SAVE_DIR.mkdir(exist_ok=True)
        self.history: List[dict] = []
        self._load()

    def _load(self):
        if SAVE_FILE.exists():
            try:
                with open(SAVE_FILE) as f:
                    self.history = json.load(f)
            except:
                self.history = []

    def save_session(self, session_data: dict):
        self.history.append(session_data)
        try:
            with open(SAVE_FILE, 'w') as f:
                json.dump(self.history, f, indent=2)
        except:
            pass

    @property
    def lifetime_hands(self) -> int:
        return sum(s.get('hands', 0) for s in self.history)

    @property
    def lifetime_profit(self) -> float:
        return sum(s.get('net_profit', 0) for s in self.history)

    @property
    def lifetime_roi(self) -> float:
        wagered = sum(s.get('wagered', 0) for s in self.history)
        if wagered == 0: return 0.0
        return self.lifetime_profit / wagered * 100

    @property
    def session_count(self) -> int:
        return len(self.history)

    @property
    def best_session(self) -> float:
        if not self.history: return 0.0
        return max(s.get('net_profit', 0) for s in self.history)

    @property
    def worst_session(self) -> float:
        if not self.history: return 0.0
        return min(s.get('net_profit', 0) for s in self.history)

    @property
    def avg_profit_per_session(self) -> float:
        if not self.history: return 0.0
        return self.lifetime_profit / len(self.history)


# ═══════════════════════════════════════════════════════════════════════════════
# ACE SIDE COUNT
# ═══════════════════════════════════════════════════════════════════════════════

class AceSideCount:
    def __init__(self, total_decks=6):
        self.total_decks = total_decks
        self.aces_seen   = 0
        self.cards_seen  = 0

    def see_card(self, c: int):
        self.cards_seen += 1
        if c == 1: self.aces_seen += 1

    def reset(self):
        self.aces_seen = 0
        self.cards_seen = 0

    @property
    def aces_remaining(self) -> float:
        return max(0, 4 * self.total_decks - self.aces_seen)

    @property
    def expected_aces_remaining(self) -> float:
        cards_rem = max(1, self.total_decks * 52 - self.cards_seen)
        return cards_rem * (4 * self.total_decks) / (52 * self.total_decks)

    @property
    def ace_surplus(self) -> float:
        return self.aces_remaining - self.expected_aces_remaining

    @property
    def edge_adjustment(self) -> float:
        cards_rem = max(1, self.total_decks * 52 - self.cards_seen)
        decks_rem = cards_rem / 52
        if decks_rem < 0.1: return 0.0
        return (self.aces_remaining / decks_rem - 4.0) * 0.0059

    @property
    def status_str(self) -> str:
        s = self.ace_surplus
        if s > 1.5:  return f'+{s:.1f}★'
        if s > 0.5:  return f'+{s:.1f}'
        if s < -1.5: return f'{s:.1f}▼'
        if s < -0.5: return f'{s:.1f}'
        return f'{s:+.1f}'


# ═══════════════════════════════════════════════════════════════════════════════
# RAINMAN BET RAMP v5
# ═══════════════════════════════════════════════════════════════════════════════

class RainmanBetRamp:
    RAMP = {-6:1,-5:1,-4:1,-3:1,-2:1,-1:1,0:1,1:1,2:2,3:4,4:8,5:12,6:16}

    def __init__(self, min_bet, max_bet, bankroll, kf=0.35):
        self.min_bet = min_bet
        self.max_bet = max_bet
        self.bankroll = bankroll
        self.kf = kf

    def unit(self) -> float:
        return max(self.min_bet, self.bankroll * self.kf * 0.0068)

    def get_bet(self, tc: float, ace_adj: float = 0.0, float_adj: float = 0.0) -> float:
        eff_tc = tc + ace_adj * 2 + float_adj
        key    = max(-6, min(6, int(eff_tc)))
        bet    = self.unit() * self.RAMP.get(key, 1)
        return max(self.min_bet, min(self.max_bet, round(bet / 5) * 5))

    def full_table(self, ace_adj=0.0, float_adj=0.0) -> List[dict]:
        rows = []
        for tc in range(-2, 7):
            eff = tc + ace_adj*2 + float_adj
            key = max(-6, min(6, int(eff)))
            bet = max(self.min_bet, min(self.max_bet,
                  round(self.unit() * self.RAMP.get(key,1) / 5)*5))
            edge = -0.004 + tc * 0.005 + ace_adj
            rows.append({'tc':tc,'bet':bet,'units':bet/max(1,self.min_bet),
                         'edge_pct':edge*100,'ev_hr':edge*bet*80})
        return rows

    def update(self, bankroll): self.bankroll = bankroll


# ═══════════════════════════════════════════════════════════════════════════════
# GAME STATE v5
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class Alert:
    level: str
    message: str
    ts: float = field(default_factory=time.time)

    @property
    def age(self): return time.time() - self.ts


class GameState:

    def __init__(self, bankroll, table_min, table_max,
                 num_decks=6, kf=0.35, can_surrender=True,
                 das=True, stop_loss_pct=0.20, win_goal_pct=0.50,
                 wong_mode=False, scout_mode=False):

        self.bankroll          = bankroll
        self.starting_bankroll = bankroll
        self.table_min         = table_min
        self.table_max         = table_max
        self.num_decks         = num_decks
        self.kf                = kf
        self.can_surrender     = can_surrender
        self.das               = das
        self.stop_loss_pct     = stop_loss_pct
        self.win_goal_pct      = win_goal_pct
        self.wong_mode         = wong_mode
        self.scout_mode        = scout_mode  # Back-counting mode

        # Engines
        self.counter     = CardCounter(num_decks)
        self.ace_count   = AceSideCount(num_decks)
        self.omega2      = OmegaIICounter(num_decks)
        self.bet_ramp    = RainmanBetRamp(table_min, table_max, bankroll, kf)
        self.float_eng   = FloatingAdvantage()
        self.score_calc  = SCORECalculator(num_decks)
        self.heat        = CasinoHeatMeter()
        self.persistence = SessionPersistence()

        # Hand state
        self.player_cards:  List[int] = []
        self.dealer_upcard: Optional[int] = None
        self.phase = 'SCOUTING' if scout_mode else 'BETTING'

        # Split tracker
        self.split_hands:  List[List[int]] = []
        self.split_active  = False
        self.split_idx     = 0

        # Session stats
        self.hands_played    = 0
        self.session_wins    = 0
        self.session_losses  = 0
        self.session_pushes  = 0
        self.net_profit      = 0.0
        self.peak_profit     = 0.0
        self.max_drawdown    = 0.0
        self.total_wagered   = 0.0
        self.current_bet     = table_min
        self.last_bet        = table_min

        self.profit_history:  deque = deque(maxlen=600)
        self.profit_history.append(0.0)
        self.tc_history:      deque = deque(maxlen=500)
        self.hand_times:      deque = deque(maxlen=30)
        self.hand_log: List[dict]   = []
        self.alerts:          deque = deque(maxlen=8)
        self.session_start    = time.time()
        self.last_hand_time   = time.time()

    # ── Card input ─────────────────────────────────────────────────────────────

    def see_card(self, card: int):
        self.counter.see_card(card)
        self.ace_count.see_card(card)
        self.omega2.see_card(card)

    def set_dealer(self, card: int):
        self.dealer_upcard = card
        self.see_card(card)
        if card == 1 and len(self.player_cards) >= 2:
            self.phase = 'INSURANCE'
        elif len(self.player_cards) >= 2:
            self.phase = 'PLAYING'
        else:
            self.phase = 'DEALING'

    def add_player_card(self, card: int):
        if self.split_active:
            if self.split_idx < len(self.split_hands):
                self.split_hands[self.split_idx].append(card)
        else:
            self.player_cards.append(card)
        self.see_card(card)
        if self.dealer_upcard and not self.split_active:
            if len(self.player_cards) >= 2:
                self.phase = 'PLAYING'
            else:
                self.phase = 'DEALING'

    def undo_last(self):
        if self.split_active and self.split_idx < len(self.split_hands):
            hand = self.split_hands[self.split_idx]
            if hand:
                c = hand.pop()
                self._undo_card(c)
        elif self.player_cards:
            c = self.player_cards.pop()
            self._undo_card(c)

    def _undo_card(self, c: int):
        tag = HI_LO_TAGS.get(min(c,10), 0)
        self.counter.state.running_count -= tag
        self.counter.state.cards_seen    -= 1
        self.counter.state.decks_remaining = self.counter.state.decks_remaining_from_cards(
            self.counter.state.cards_seen, self.num_decks)
        omega_tag = OMEGA2_TAGS.get(min(c,10), 0)
        self.omega2.running_count -= omega_tag
        self.omega2.cards_seen    -= 1
        if c == 1: self.ace_count.aces_seen -= 1
        self.ace_count.cards_seen -= 1

    def initiate_split(self):
        if len(self.player_cards) == 2:
            c = self.player_cards[0]
            self.split_hands  = [[c], [c]]
            self.split_active = True
            self.split_idx    = 0
            self.player_cards = []

    def next_split(self):
        self.split_idx += 1

    def new_hand(self):
        self.player_cards  = []
        self.dealer_upcard = None
        self.split_hands   = []
        self.split_active  = False
        self.split_idx     = 0
        self.phase = 'SCOUTING' if (self.scout_mode and self.tc < 2) else 'BETTING'
        self.bet_ramp.update(self.bankroll)
        self.heat.record_time()

        # Check Omega II for errors
        err = self.omega2.error_flag(self.tc)
        if err:
            self._alert('warn', err)

    def reshuffle(self):
        self.counter.reset_shoe()
        self.ace_count.reset()
        self.omega2.reset()
        self.tc_history.clear()
        self._alert('info', '🔀 Reshuffled — all counts reset')

    def dismiss_insurance(self): self.phase = 'PLAYING'

    def enter_table(self):
        """Exit scout mode when TC reaches entry threshold."""
        self.scout_mode = False
        self.phase      = 'BETTING'
        self._alert('signal', f'✅ ENTERING TABLE — TC {self.tc:+.1f} ≥ +2')

    def record_result(self, outcome: str, profit: float):
        elapsed = time.time() - self.last_hand_time
        self.hand_times.append(max(1, elapsed))
        self.last_hand_time = time.time()

        prev_bet = self.current_bet
        self.bankroll      += profit
        self.net_profit     = self.bankroll - self.starting_bankroll
        self.peak_profit    = max(self.peak_profit, self.net_profit)
        dd = self.peak_profit - self.net_profit
        self.max_drawdown   = max(self.max_drawdown, dd)
        self.total_wagered += self.current_bet
        self.hands_played  += 1
        self.tc_history.append(round(self.tc, 2))

        lbl = outcome.upper()
        if lbl in ('WIN', 'BLACKJACK'): self.session_wins   += 1
        elif lbl == 'LOSS':              self.session_losses += 1
        else:                            self.session_pushes += 1

        self.hand_log.append({
            'hand': self.hands_played,
            'player': list(self.player_cards or []),
            'dealer': self.dealer_upcard,
            'bet': self.current_bet, 'profit': round(profit, 2),
            'tc': round(self.tc, 2), 'rc': self.rc,
            'float_tc': round(self.float_tc, 2),
            'ace_surplus': round(self.ace_count.ace_surplus, 2),
            'edge_pct': round(self.precise_edge * 100, 4),
            'outcome': lbl, 'bankroll': round(self.bankroll, 2),
        })

        # Heat tracking
        self.heat.record_bet(self.current_bet, prev_bet, self.tc)
        if profit > 0:
            self.heat.record_win(profit, self.current_bet)

        # Session alerts
        sl = self.starting_bankroll * self.stop_loss_pct
        wg = self.starting_bankroll * self.win_goal_pct
        if self.net_profit <= -sl:
            self._alert('danger', f'🛑 STOP LOSS HIT — ${abs(self.net_profit):.0f} down')
        elif self.net_profit >= wg:
            self._alert('signal', f'🏆 WIN GOAL HIT — +${self.net_profit:.0f}')

        camo = self.heat.camouflage_suggestion()
        if camo:
            self._alert('warn', f'🎭 CAMO: {camo}')

    def _alert(self, level, msg):
        if self.alerts and self.alerts[0].message == msg and self.alerts[0].age < 8:
            return
        self.alerts.appendleft(Alert(level, msg))

    def save_session(self):
        data = {
            'date':       time.strftime('%Y-%m-%d %H:%M'),
            'hands':      self.hands_played,
            'net_profit': round(self.net_profit, 2),
            'wagered':    round(self.total_wagered, 2),
            'roi':        round(self.roi, 4),
            'bankroll':   round(self.bankroll, 2),
            'max_dd':     round(self.max_drawdown, 2),
            'win_rate':   round(self.win_rate, 2),
            'decks':      self.num_decks,
            'duration_min': round((time.time()-self.session_start)/60, 1),
        }
        self.persistence.save_session(data)
        return data

    # ── Properties ─────────────────────────────────────────────────────────────

    @property
    def tc(self) -> float:
        return self.counter.true_count

    @property
    def rc(self) -> int:
        return self.counter.state.running_count

    @property
    def decks_remaining(self) -> float:
        return self.counter.state.decks_remaining

    @property
    def penetration(self) -> float:
        return min(1.0, self.counter.state.cards_seen / (self.num_decks * 52))

    @property
    def float_tc(self) -> float:
        return self.float_eng.adjusted_tc(self.tc, self.penetration)

    @property
    def hi_lo_edge(self) -> float:
        return self.counter.state.player_edge

    @property
    def float_edge(self) -> float:
        return self.float_eng.adjusted_edge(self.tc, self.penetration)

    @property
    def precise_edge(self) -> float:
        return self.float_edge + self.ace_count.edge_adjustment

    @property
    def optimal_bet(self) -> float:
        float_adj = (self.float_tc - self.tc) / 2
        return self.bet_ramp.get_bet(
            self.tc, self.ace_count.edge_adjustment * 2, float_adj)

    @property
    def wong_signal(self) -> str:
        tc = self.tc
        if tc >= 2:   return 'IN'
        if tc < 0:    return 'OUT'
        return 'WAIT'

    @property
    def insurance_decision(self) -> Tuple[bool, str]:
        tc = self.tc
        if tc >= 3:
            return True,  f'✅ TAKE — TC {tc:+.1f} ≥ +3'
        return False, f'✗ SKIP — TC {tc:+.1f} < +3'

    @property
    def recommendation(self) -> Tuple[str, str, Optional[str]]:
        if self.phase == 'SCOUTING':
            return 'SCOUT', f'Back-counting | TC {self.tc:+.1f} | Entry at TC≥+2', None

        if self.phase == 'INSURANCE':
            take, msg = self.insurance_decision
            return ('INSURANCE' if take else 'HIT'), msg, None

        cards = self.player_cards
        if self.split_active and self.split_idx < len(self.split_hands):
            cards = self.split_hands[self.split_idx]

        if not cards or not self.dealer_upcard:
            return 'WAIT', 'Enter dealer upcard + your cards', None

        total    = best_total(cards)
        is_soft  = has_soft_ace(cards)
        n_cards  = len(cards)
        can_spl  = (n_cards == 2 and cards[0] == cards[1] and not self.split_active)
        can_dbl  = n_cards == 2
        can_surr = self.can_surrender and n_cards == 2 and not self.split_active

        # 1) Composition-dependent override (3+ cards)
        comp_dev = None
        if n_cards >= 3:
            comp_dev = lookup_comp_dep(total, self.dealer_upcard, n_cards, is_soft)

        # 2) Illustrious 18
        i18 = lookup_deviation(total, self.dealer_upcard, self.tc, is_soft)

        # 3) Basic strategy
        state = HandState(
            player_cards=cards, dealer_upcard=self.dealer_upcard,
            can_double=can_dbl, can_split=can_spl, can_surrender=can_surr)
        try:
            basic = get_action(state)[0].name
        except:
            basic = 'HIT'

        final    = comp_dev or (i18 if (i18 and i18 != basic) else basic)
        is_dev   = (comp_dev is not None) or (i18 is not None and i18 != basic)
        soft_str = 'soft ' if is_soft else ''
        comp_str = ' [comp-dep]' if comp_dev else ''
        dev_str  = f'⚡ DEV{comp_str}' if is_dev else 'BS'

        # Heat: record if deviation made
        if is_dev and self.phase == 'PLAYING':
            desc = f'{soft_str}{total} vs {RD.get(self.dealer_upcard,"?")} → {final}'
            self.heat.record_deviation(desc)

        explain = (f'{dev_str} | {soft_str}{total} vs {RD.get(self.dealer_upcard,"?")} '
                  f'| TC{self.tc:+.1f} | Float TC{self.float_tc:+.1f}')
        hint = closest_deviation(total, self.dealer_upcard, self.tc, is_soft)
        return final, explain, hint

    @property
    def ror(self) -> float:
        return self.score_calc.ror(self.bankroll, self.optimal_bet, self.precise_edge)

    @property
    def score(self) -> float:
        evph = self.ev_per_hand
        return self.score_calc.score(evph, self.optimal_bet)

    @property
    def n0(self) -> float:
        evph = self.ev_per_hand
        return self.score_calc.n0(evph, self.optimal_bet)

    @property
    def ev_per_hand(self) -> float:
        return max(0, self.precise_edge) * self.optimal_bet

    @property
    def ev_per_hour(self) -> float:
        return self.ev_per_hand * self.hands_per_hour

    @property
    def hands_per_hour(self) -> float:
        if len(self.hand_times) < 2: return 80.0
        avg = sum(self.hand_times) / len(self.hand_times)
        return min(200, 3600 / max(avg, 5))

    @property
    def hours_to_double(self) -> float:
        evhr = self.ev_per_hour
        return self.bankroll / evhr if evhr > 0 else float('inf')

    @property
    def session_elapsed(self) -> str:
        s = int(time.time() - self.session_start)
        return f'{s//3600:02d}:{(s%3600)//60:02d}:{s%60:02d}'

    @property
    def win_rate(self) -> float:
        t = self.session_wins + self.session_losses + self.session_pushes
        return self.session_wins / max(1, t) * 100

    @property
    def roi(self) -> float:
        return self.net_profit / max(1, self.total_wagered) * 100

    @property
    def sigma_per_hand(self) -> float:
        avg_bet = self.total_wagered / max(1, self.hands_played)
        return avg_bet * 1.15

    @property
    def tc_distribution(self) -> Dict[int, int]:
        return dict(Counter(int(t) for t in self.tc_history))


# ═══════════════════════════════════════════════════════════════════════════════
# WIDGETS
# ═══════════════════════════════════════════════════════════════════════════════

def _lbl(parent, text, fg=WHITE, bg=PANEL, font=('Courier',9), **kw):
    return tk.Label(parent, text=text, fg=fg, bg=bg, font=font, **kw)


class ProfitChart:
    def __init__(self, parent, w=390, h=85):
        self.cv = tk.Canvas(parent, width=w, height=h,
                           bg=CARD, highlightthickness=0)
        self.cv.pack(fill='x', padx=6, pady=1)
        self.w, self.h = w, h

    def update(self, data):
        c = self.cv; c.delete('all')
        data = list(data)
        if len(data) < 2:
            c.create_text(self.w//2, self.h//2, text='No P&L data', fill=DIM, font=('Courier',7))
            return
        mn, mx = min(data), max(data)
        span = max(1, mx - mn)
        if span < 100: mn -= 50; mx += 50; span = mx - mn
        p = 8; pw, ph = self.w-p*2, self.h-p*2

        def pt(i, v):
            return (p + i/(len(data)-1)*pw, p + (1-(v-mn)/span)*ph)

        zy = max(p, min(p+ph, p + (1-(0-mn)/span)*ph))
        c.create_line(p, zy, self.w-p, zy, fill=DIM, dash=(3,5))

        for i in range(len(data)-1):
            x1,y1 = pt(i, data[i]); x2,y2 = pt(i+1, data[i+1])
            c.create_line(x1,y1,x2,y2, fill=(GREEN if data[i+1]>=0 else RED),
                         width=1.5)

        lx, ly = pt(len(data)-1, data[-1])
        col = GREEN if data[-1]>=0 else RED
        c.create_oval(lx-3,ly-3,lx+3,ly+3, fill=col, outline='')
        c.create_text(lx-4, ly-8, text=f'${data[-1]:+,.0f}',
                     fill=col, font=('Courier',7,'bold'), anchor='e')
        c.create_text(p+1, p+ph, text=f'${mn:+,.0f}', fill=DIM,
                     font=('Courier',6), anchor='sw')
        c.create_text(p+1, p, text=f'${mx:+,.0f}', fill=DIM,
                     font=('Courier',6), anchor='nw')


class TCHeatBar:
    def __init__(self, parent, w=390, h=26):
        self.cv = tk.Canvas(parent, width=w, height=h,
                           bg=PANEL, highlightthickness=0)
        self.cv.pack(fill='x', padx=6, pady=1)
        self.w, self.h = w, h

    def update(self, tc, float_tc, ace_sur):
        c = self.cv; c.delete('all')
        norm = max(0.0, min(1.0, (tc + 6) / 12))
        fw   = int(self.w * norm)
        col  = ('#113377' if tc < 0 else '#223344' if tc < 2 else
                ORANGE    if tc < 4 else '#ff5500'  if tc < 6 else GOLD)
        c.create_rectangle(0, 0, self.w, self.h, fill=CARD, outline='')
        if fw > 0:
            c.create_rectangle(0, 0, fw, self.h, fill=col, outline='')

        # Float TC marker
        fn = max(0.0, min(1.0, (float_tc + 6) / 12))
        fx = int(self.w * fn)
        c.create_line(fx, 0, fx, self.h, fill=WHITE, width=1, dash=(2,2))

        cx = self.w // 2
        c.create_line(cx, 0, cx, self.h, fill=DIM, dash=(2,4))
        ace_s = f'  Ace:{ace_sur:+.1f}' if abs(ace_sur) > 0.3 else ''
        label = (f'Hi-Lo TC {tc:+.1f} | Float {float_tc:+.1f}{ace_s}  '
                f'{"❄ COLD" if tc<0 else "◦ NEUTRAL" if tc<2 else "↑ HOT" if tc<4 else "★ MAX"}')
        c.create_text(self.w//2, self.h//2+1, text=label,
                     fill=WHITE, font=('Courier',8,'bold'))


class RoRGauge:
    """Semicircular RoR display."""
    def __init__(self, parent, w=200, h=90):
        self.cv = tk.Canvas(parent, width=w, height=h,
                           bg=CARD, highlightthickness=0)
        self.cv.pack(side='left', padx=4, pady=2)
        self.w, self.h = w, h

    def update(self, ror_pct: float, n0: float, score: float, rating: str):
        c = self.cv; c.delete('all')
        cx, cy, r = self.w//2, int(self.h*0.85), int(self.h*0.70)
        ror_norm = min(1.0, ror_pct / 100)
        col = (GREEN if ror_pct < 5 else AMBER if ror_pct < 15 else
               ORANGE if ror_pct < 30 else RED)

        # Background arc
        c.create_arc(cx-r, cy-r, cx+r, cy+r, start=0, extent=180,
                    style='arc', outline=DIM, width=10)
        # Filled arc
        sweep = 180 * (1 - ror_norm)
        c.create_arc(cx-r, cy-r, cx+r, cy+r, start=0, extent=int(sweep),
                    style='arc', outline=col, width=10)

        c.create_text(cx, cy-r//2, text=f'{ror_pct:.1f}%',
                     fill=col, font=('Courier', 14, 'bold'))
        c.create_text(cx, cy-r//2+18, text='RoR', fill=DIM, font=('Courier',7))
        c.create_text(cx, cy-5, text=f'N₀: {n0:,.0f}h | SCORE: {score:.0f}',
                     fill=BRIGHT, font=('Courier',7))
        c.create_text(cx, cy+10, text=rating, fill=GOLD, font=('Courier',7,'bold'))


class SCOREPanel:
    """Detailed SCORE / N0 / RoR analytics panel."""
    def __init__(self, game: 'GameState'):
        self.game = game
        win = tk.Toplevel()
        win.title('SCORE & Risk Analytics')
        win.configure(bg=BG)
        win.attributes('-topmost', True)
        win.geometry('440x560+60+60')
        self._build(win)

    def _build(self, win):
        g = self.game
        sc = g.score_calc

        tk.Label(win, text='SCORE — TABLE ANALYTICS', bg=BG,
                fg=GOLD, font=('Courier',11,'bold')).pack(pady=(12,4))
        tk.Frame(win, bg=GOLD, height=1).pack(fill='x', padx=20)

        metrics = [
            ('SCORE',          f'{g.score:.1f}',              sc.rating(g.score)),
            ('N0 (neutral pt).',f'{g.n0:,.0f} hands',         '↓ lower = better'),
            ('Risk of Ruin',    f'{g.ror*100:.2f}%',           '< 5% is safe'),
            ('EV / hand',       f'${g.ev_per_hand:+.3f}',      ''),
            ('EV / hour',       f'${g.ev_per_hour:+.2f}',      f'@ {g.hands_per_hour:.0f} h/hr'),
            ('Hrs to double',   (f'{g.hours_to_double:.1f} hr'
                                 if g.hours_to_double < 1e9 else '∞'),   ''),
            ('Float TC',        f'{g.float_tc:+.2f}',          f'(raw {g.tc:+.2f})'),
            ('Float edge',      f'{g.float_edge*100:+.3f}%',   f'Hi-Lo: {g.hi_lo_edge*100:+.3f}%'),
            ('Precise edge',    f'{g.precise_edge*100:+.3f}%', 'w/ Ace + Float'),
            ('Ace surplus',     f'{g.ace_count.ace_surplus:+.2f}', g.ace_count.status_str),
            ('ΩII TC',          f'{g.omega2.true_count:+.1f}', 'cross-check'),
            ('Penetration',     f'{g.penetration*100:.0f}%',   g.float_eng.bonus_display(g.penetration)),
        ]

        f = tk.Frame(win, bg=PANEL, padx=10, pady=8)
        f.pack(fill='both', expand=True, padx=16, pady=8)

        for i, (name, val, note) in enumerate(metrics):
            row = tk.Frame(f, bg=PANEL)
            row.pack(fill='x', pady=2)
            tk.Label(row, text=name, bg=PANEL, fg=DIM,
                    font=('Courier',9), width=18, anchor='w').pack(side='left')
            val_col = (GREEN if '+' in val and val[0]!='-' else
                       RED if val.startswith('-') else CYAN)
            tk.Label(row, text=val, bg=PANEL, fg=val_col,
                    font=('Courier',9,'bold'), width=14).pack(side='left')
            tk.Label(row, text=note, bg=PANEL, fg=SMOKE,
                    font=('Courier',7)).pack(side='left')

        # Lifetime stats
        p = g.persistence
        tk.Frame(win, bg=BORDER, height=1).pack(fill='x', padx=16)
        lf = tk.Frame(win, bg=PANEL, padx=10, pady=6)
        lf.pack(fill='x', padx=16, pady=4)
        tk.Label(lf, text='LIFETIME', bg=PANEL, fg=GOLD,
                font=('Courier',8,'bold')).pack(anchor='w')
        lifetime = [
            f'Sessions: {p.session_count}  |  Hands: {p.lifetime_hands:,}',
            f'P&L: ${p.lifetime_profit:+,.2f}  |  ROI: {p.lifetime_roi:+.3f}%',
            f'Best: ${p.best_session:+,.0f}  |  Worst: ${p.worst_session:+,.0f}',
        ]
        for line in lifetime:
            tk.Label(lf, text=line, bg=PANEL, fg=BRIGHT,
                    font=('Courier',8)).pack(anchor='w')


class HeatPanel:
    """Casino heat tracker detail view."""
    def __init__(self, game: 'GameState'):
        win = tk.Toplevel()
        win.title('Casino Heat Monitor')
        win.configure(bg=BG)
        win.attributes('-topmost', True)
        win.geometry('380x480+80+80')
        self._build(win, game)

    def _build(self, win, game):
        h = game.heat
        tk.Label(win, text='CASINO HEAT MONITOR', bg=BG,
                fg=GOLD, font=('Courier',11,'bold')).pack(pady=(12,4))

        # Heat bar
        cv = tk.Canvas(win, width=340, height=30, bg=CARD, highlightthickness=0)
        cv.pack(padx=20, pady=6)
        fw = int(340 * h.heat_level / 100)
        col = h.heat_color
        cv.create_rectangle(0,0,340,30, fill=CARD, outline='')
        if fw > 0:
            cv.create_rectangle(0,0,fw,30, fill=col, outline='')
        cv.create_text(170,15, text=f'{h.heat_level:.0f}% — {h.heat_label}',
                      fill=WHITE, font=('Courier',10,'bold'))

        # Spread info
        spread = (h.max_bet_seen / h.min_bet_seen
                  if h.min_bet_seen < float('inf') and h.min_bet_seen > 0 else 0)
        stats = [
            f'Hands at table: {h.hands_at_table}',
            f'Bet spread: {spread:.0f}× (${h.min_bet_seen:.0f}–${h.max_bet_seen:.0f})',
            f'Deviations made: {h.deviations_made}',
            f'Big wins: {h.big_wins}',
            f'Session time: {int((time.time()-h.session_start)/60)} min',
        ]
        sf = tk.Frame(win, bg=PANEL, padx=10, pady=8)
        sf.pack(fill='x', padx=20, pady=4)
        for s in stats:
            tk.Label(sf, text=s, bg=PANEL, fg=WHITE,
                    font=('Courier',9)).pack(anchor='w', pady=1)

        # Camo suggestions
        tk.Label(win, text='CAMOUFLAGE TECHNIQUES', bg=BG,
                fg=AMBER, font=('Courier',8,'bold')).pack(anchor='w', padx=20, pady=(8,2))
        tips = [
            '• Vary bet from count by ±1 unit occasionally',
            '• Ask basic strategy questions to dealer',
            '• Take insurance at TC<3 once per session',
            '• Show "excitement" on big bets, not methodology',
            '• Tip dealer proportional to bet size',
            '• Stand up / walk around between shoes',
            '• Drink water (not alcohol), look casual',
            '• Play rated card for comps (offset surveillance)',
        ]
        for tip in tips:
            tk.Label(win, text=tip, bg=BG, fg=DIM,
                    font=('Courier',7)).pack(anchor='w', padx=24)

        # New table button
        tk.Button(win, text='MOVED TO NEW TABLE (+20 cool-down)',
                 command=lambda: (game.heat.new_table(),
                                  game._alert('info', '🆕 New table — heat reduced'),
                                  win.destroy()),
                 bg=CARD, fg=GREEN, font=('Courier',8,'bold'),
                 relief='flat', padx=8, pady=6, cursor='hand2'
                 ).pack(pady=12)


class VarianceCone:
    def __init__(self, parent, w=390, h=75):
        self.cv = tk.Canvas(parent, width=w, height=h,
                           bg=CARD, highlightthickness=0)
        self.cv.pack(fill='x', padx=6, pady=1)
        self.w, self.h = w, h

    def update(self, bankroll, ev_ph, sigma_ph, n=100):
        c = self.cv; c.delete('all')
        if sigma_ph < 1:
            c.create_text(self.w//2, self.h//2,
                         text='Variance cone — record hands to calibrate',
                         fill=DIM, font=('Courier',7))
            return
        steps = 40; px_l = 28; py = 6; pw = self.w-px_l*2; ph = self.h-py*2
        evs   = [bankroll + ev_ph*t for t in range(steps+1)]
        s1h   = [evs[t] + sigma_ph*math.sqrt(t) for t in range(steps+1)]
        s1l   = [evs[t] - sigma_ph*math.sqrt(t) for t in range(steps+1)]
        s2h   = [evs[t] + 2*sigma_ph*math.sqrt(t) for t in range(steps+1)]
        s2l   = [evs[t] - 2*sigma_ph*math.sqrt(t) for t in range(steps+1)]
        mn, mx = min(s2l), max(s2h); span = max(1, mx-mn)
        def pt(t, v):
            return (px_l + t/steps*pw, py + (1-(v-mn)/span)*ph)
        for lh, ll, fill in [(s2h,s2l,'#ff330412'),(s1h,s1l,'#00ff4420')]:
            pts = [px_l, py+ph]
            for t in range(steps+1): pts += list(pt(t, lh[t]))
            for t in reversed(range(steps+1)): pts += list(pt(t, ll[t]))
            c.create_polygon(pts, fill=fill, outline='')
        ev_pts = []
        for t in range(steps+1): ev_pts += list(pt(t, evs[t]))
        c.create_line(ev_pts, fill=GREEN, width=1.5)
        lx, ly = pt(steps, evs[-1])
        c.create_text(lx+2, ly, text=f'EV {evs[-1]-bankroll:+,.0f}',
                     fill=GREEN, font=('Courier',6), anchor='w')
        lx1,ly1 = pt(steps,s1h[-1])
        c.create_text(lx1+2,ly1, text=f'+1σ {s1h[-1]-bankroll:+,.0f}',
                     fill=TEAL, font=('Courier',6), anchor='w')
        c.create_text(px_l, 3,
                     text=f'NEXT {n}h | EV/h: {ev_ph:+.2f}',
                     fill=DIM, font=('Courier',6), anchor='nw')


class ShoeTCHist:
    def __init__(self, parent, w=390, h=58):
        self.cv = tk.Canvas(parent, width=w, height=h,
                           bg=CARD, highlightthickness=0)
        self.cv.pack(fill='x', padx=6, pady=1)
        self.w, self.h = w, h

    def update(self, dist, total):
        c = self.cv; c.delete('all')
        if total == 0:
            c.create_text(self.w//2, self.h//2,
                         text='TC histogram', fill=DIM, font=('Courier',7)); return
        tcr = range(-4, 7); n = len(tcr)
        bw = (self.w-16)/n; mx = max((dist.get(t,0) for t in tcr),default=1)
        if mx == 0: return
        p = 8
        for i, tc in enumerate(tcr):
            cnt = dist.get(tc, 0)
            bh  = max(2, cnt/mx*(self.h-18))
            bx  = p + i*bw
            col = (RED if tc<0 else DIM if tc<2 else ORANGE if tc<4 else
                   GREEN if tc<6 else GOLD)
            c.create_rectangle(bx+1, self.h-10-bh, bx+bw-2, self.h-10,
                              fill=col, outline='')
            c.create_text(bx+bw/2, self.h-4, text=f'{tc:+d}',
                         fill=DIM, font=('Courier',6))
        c.create_text(p, 3, text='TC DIST (shoe)', fill=DIM,
                     font=('Courier',6), anchor='nw')


# ═══════════════════════════════════════════════════════════════════════════════
# BET RAMP PANEL
# ═══════════════════════════════════════════════════════════════════════════════

class BetRampPanel:
    def __init__(self, game: 'GameState'):
        win = tk.Toplevel()
        win.title('Bet Ramp — Rainman v5')
        win.configure(bg=BG)
        win.attributes('-topmost', True)
        win.geometry('420x500+15+30')
        g = game; ramp = g.bet_ramp
        float_adj = (g.float_tc - g.tc) / 2

        tk.Label(win, text='RAINMAN BET RAMP v5', bg=BG,
                fg=GOLD, font=('Courier',10,'bold')).pack(pady=(10,2))
        tk.Label(win,
                text=f'BR:${g.bankroll:,.0f} | Unit:${ramp.unit():.0f} | Kelly:{g.kf:.0%}'
                     f' | Float:×{g.float_eng.adjustment_factor(g.penetration):.2f}'
                     f' | Ace:{g.ace_count.status_str}',
                bg=BG, fg=DIM, font=('Courier',7)).pack()

        f = tk.Frame(win, bg=PANEL, padx=8, pady=6)
        f.pack(fill='both', expand=True, padx=10, pady=6)
        hdrs = ['TC','FTC','BET','MULT','EDGE%','EV/HR','']
        widths=[4,  5,   7,   5,   7,    8,    15]
        for col,(h,w) in enumerate(zip(hdrs,widths)):
            tk.Label(f, text=h, bg=PANEL, fg=GOLD,
                    font=('Courier',8,'bold'), width=w
                    ).grid(row=0,column=col,padx=2,pady=2)

        rows = ramp.full_table(g.ace_count.edge_adjustment, float_adj)
        cur  = int(g.tc)
        for ri, r in enumerate(rows, 1):
            tc  = r['tc']
            ftc = tc * g.float_eng.adjustment_factor(g.penetration)
            hot = tc == cur
            bg  = '#0a1a0a' if hot else PANEL
            note= ('← NOW' if hot else 'WONG IN' if tc==2 else
                   'WONG OUT' if tc==0 else 'INS' if tc==3 else '')
            fgc = GREEN if r['edge_pct']>0 else RED
            row_vals = [
                (f'{tc:+d}',     (CYAN if hot else BRIGHT)),
                (f'{ftc:+.1f}',  TEAL),
                (f'${r["bet"]:.0f}', WHITE),
                (f'{r["mult"]}x', DIM),
                (f'{r["edge_pct"]:+.2f}%', fgc),
                (f'${r["ev_hr"]:+.0f}', fgc),
                (note, AMBER if 'NOW' in note else STEEL),
            ]
            for col,((val,col_),w) in enumerate(zip(row_vals,widths)):
                tk.Label(f, text=val, bg=bg, fg=col_,
                        font=('Courier',9,'bold' if hot else 'normal'), width=w
                        ).grid(row=ri,column=col,padx=2,pady=1)

        tk.Label(win,
                text='FTC = Floating TC (penetration-adjusted) | Wong in ≥+2 | Insurance TC≥+3',
                bg=BG, fg=DIM, font=('Courier',7)).pack(pady=6)


# ═══════════════════════════════════════════════════════════════════════════════
# SETTINGS PANEL
# ═══════════════════════════════════════════════════════════════════════════════

class SettingsPanel:
    def __init__(self, game, on_apply):
        self.game = game; self.on_apply = on_apply
        win = tk.Toplevel(); win.title('Settings')
        win.configure(bg=BG); win.attributes('-topmost', True)
        win.geometry('300x460+60+60')
        self.win = win; self._build()

    def _build(self):
        tk.Label(self.win, text='SETTINGS', bg=BG,
                fg=GOLD, font=('Courier',11,'bold')).pack(pady=(12,4))
        g = self.game
        self.vars = {}
        for label, key, val in [
            ('Kelly Fraction',  'kf',        str(g.kf)),
            ('Stop Loss %',     'sl',         str(int(g.stop_loss_pct*100))),
            ('Win Goal %',      'wg',         str(int(g.win_goal_pct*100))),
            ('Table Max ($)',   'max_bet',    str(g.table_max)),
            ('Table Min ($)',   'min_bet',    str(g.table_min)),
        ]:
            row = tk.Frame(self.win, bg=BG)
            row.pack(fill='x', padx=20, pady=4)
            tk.Label(row, text=label, bg=BG, fg=WHITE,
                    font=('Courier',9), width=16, anchor='w').pack(side='left')
            var = tk.StringVar(value=val)
            tk.Entry(row, textvariable=var, bg=CARD, fg=GOLD,
                    font=('Courier',10,'bold'), insertbackground=WHITE,
                    relief='flat', width=8,
                    highlightthickness=1, highlightbackground=BORDER,
                    highlightcolor=CYAN).pack(side='right')
            self.vars[key] = var

        self.surr_var  = tk.BooleanVar(value=g.can_surrender)
        self.scout_var = tk.BooleanVar(value=g.scout_mode)
        for txt, var in [('Surrender allowed', self.surr_var),
                         ('Scout mode (back-count)', self.scout_var)]:
            tk.Checkbutton(self.win, text=txt, variable=var,
                          bg=BG, fg=WHITE, selectcolor=CARD,
                          activebackground=BG, font=('Courier',9)).pack(anchor='w', padx=20, pady=2)

        tk.Button(self.win, text='APPLY', command=self._apply,
                 bg=GOLD, fg=BG, font=('Courier',10,'bold'),
                 relief='flat', padx=16, pady=8, cursor='hand2').pack(pady=16)

    def _apply(self):
        try:
            g = self.game
            g.kf             = float(self.vars['kf'].get())
            g.stop_loss_pct  = float(self.vars['sl'].get()) / 100
            g.win_goal_pct   = float(self.vars['wg'].get()) / 100
            g.table_max      = float(self.vars['max_bet'].get())
            g.table_min      = float(self.vars['min_bet'].get())
            g.can_surrender  = self.surr_var.get()
            g.scout_mode     = self.scout_var.get()
            g.bet_ramp.kf    = g.kf
            g.bet_ramp.max_bet = g.table_max
            g.bet_ramp.min_bet = g.table_min
            self.on_apply()
            self.win.destroy()
        except ValueError as e:
            messagebox.showerror('Invalid', str(e))


# ═══════════════════════════════════════════════════════════════════════════════
# SETUP DIALOG
# ═══════════════════════════════════════════════════════════════════════════════

class SetupDialog:
    def __init__(self):
        self.result = None
        root = tk.Tk(); root.title(f'BJ AI {V} — Setup')
        root.configure(bg=BG); root.resizable(False, False)
        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        root.geometry(f'460x680+{(sw-460)//2}+{(sh-680)//2}')
        self._root = root; self._build(); root.mainloop()

    def _build(self):
        r = self._root
        tk.Frame(r, bg=GOLD, height=3).pack(fill='x')
        hdr = tk.Frame(r, bg=PANEL, pady=14)
        hdr.pack(fill='x')
        tk.Label(hdr, text=f'🃏 BLACKJACK AI ADVISOR v5', bg=PANEL,
                fg=GOLD, font=('Courier',14,'bold')).pack()
        tk.Label(hdr, text='Absolute Edge Edition — SCORE · RoR · Floating Advantage',
                bg=PANEL, fg=DIM, font=('Courier',8)).pack(pady=(2,0))
        tk.Frame(r, bg=GOLD, height=1).pack(fill='x')

        f = tk.Frame(r, bg=BG, padx=28, pady=16)
        f.pack(fill='both', expand=True)
        self.fv = {}
        for label, key, default in [
            ('Bankroll ($)',       'bankroll', '1000'),
            ('Table Minimum ($)',  'min_bet',  '10'),
            ('Table Maximum ($)',  'max_bet',  '300'),
            ('Kelly Fraction',     'kf',       '0.35'),
            ('Stop Loss %',        'sl',       '20'),
            ('Win Goal %',         'wg',       '50'),
        ]:
            row = tk.Frame(f, bg=BG); row.pack(fill='x', pady=5)
            tk.Label(row, text=label, bg=BG, fg=WHITE,
                    font=('Courier',10), width=20, anchor='w').pack(side='left')
            var = tk.StringVar(value=default)
            tk.Entry(row, textvariable=var, bg=CARD, fg=GOLD,
                    font=('Courier',11,'bold'), insertbackground=WHITE,
                    relief='flat', width=10,
                    highlightthickness=1, highlightbackground=BORDER,
                    highlightcolor=CYAN).pack(side='right')
            self.fv[key] = var

        self.surr_v  = tk.BooleanVar(value=True)
        self.das_v   = tk.BooleanVar(value=True)
        self.scout_v = tk.BooleanVar(value=False)
        for txt, var in [('Surrender allowed',      self.surr_v),
                         ('Double After Split',      self.das_v),
                         ('Scout mode (back-count)', self.scout_v)]:
            tk.Checkbutton(f, text=txt, variable=var, bg=BG, fg=WHITE,
                          selectcolor=CARD, activebackground=BG,
                          font=('Courier',9)).pack(anchor='w', pady=2)

        self.deck_var = tk.IntVar(value=6)
        dr = tk.Frame(f, bg=BG); dr.pack(fill='x', pady=6)
        tk.Label(dr, text='Decks:', bg=BG, fg=WHITE,
                font=('Courier',9)).pack(side='left')
        for d in [1,2,4,6,8]:
            tk.Radiobutton(dr, text=str(d), variable=self.deck_var, value=d,
                          bg=BG, fg=CYAN, selectcolor=CARD,
                          activebackground=BG, font=('Courier',9)
                          ).pack(side='left', padx=5)

        # Persistence summary
        p = SessionPersistence()
        if p.session_count > 0:
            info = tk.Frame(f, bg=PANEL, padx=10, pady=8)
            info.pack(fill='x', pady=6)
            tk.Label(info, text=f'📊 LIFETIME  |  {p.session_count} sessions  |  '
                               f'{p.lifetime_hands:,} hands',
                    bg=PANEL, fg=GOLD, font=('Courier',8,'bold')).pack()
            tk.Label(info, text=f'P&L: ${p.lifetime_profit:+,.2f}  '
                               f'ROI: {p.lifetime_roi:+.3f}%  '
                               f'Avg/session: ${p.avg_profit_per_session:+,.2f}',
                    bg=PANEL, fg=BRIGHT, font=('Courier',8)).pack()

        tk.Button(r, text='▶  LAUNCH HUD v5',
                 bg=GOLD, fg=BG, font=('Courier',12,'bold'),
                 relief='flat', padx=20, pady=14,
                 activebackground=GREEN, cursor='hand2',
                 command=self._launch).pack(fill='x', padx=24, pady=(0,20))

    def _launch(self):
        try:
            self.result = {
                'bankroll': float(self.fv['bankroll'].get()),
                'min_bet':  float(self.fv['min_bet'].get()),
                'max_bet':  float(self.fv['max_bet'].get()),
                'kf':       float(self.fv['kf'].get()),
                'sl':       float(self.fv['sl'].get())/100,
                'wg':       float(self.fv['wg'].get())/100,
                'decks':    self.deck_var.get(),
                'surrender':self.surr_v.get(),
                'das':      self.das_v.get(),
                'scout_mode':self.scout_v.get(),
            }
            self._root.destroy()
        except ValueError as e:
            messagebox.showerror('Invalid Input', str(e))


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN HUD v5
# ═══════════════════════════════════════════════════════════════════════════════

class HUDv5:

    def __init__(self, game: GameState):
        self.game = game
        self.root = tk.Tk()
        self._setup_window()
        self._build_ui()
        self._bind_keys()
        self._refresh()

    def _setup_window(self):
        self.root.title(f'BJ AI HUD {V}')
        self.root.configure(bg=BG)
        self.root.attributes('-topmost', True)
        self.root.attributes('-alpha', 0.96)
        self.root.resizable(True, True)
        sw = self.root.winfo_screenwidth()
        self.root.geometry(f'406x1060+{sw-422}+0')
        self.root.bind('<Button-1>', lambda e: (setattr(self,'_dx',e.x), setattr(self,'_dy',e.y)))
        self.root.bind('<B1-Motion>', self._drag)
        self._dx = self._dy = 0

    def _drag(self, e):
        x = self.root.winfo_x() + e.x - self._dx
        y = self.root.winfo_y() + e.y - self._dy
        self.root.geometry(f'+{x}+{y}')

    def _build_ui(self):
        self._build_header()
        self.tc_bar = TCHeatBar(self.root)
        self._build_action_box()
        self._build_count_strip()
        self._build_bet_row()
        self._build_hand_display()
        self._build_controls()
        self._build_outcomes()
        tk.Frame(self.root, bg=BG, height=2).pack(fill='x')
        self._build_ror_row()
        self._build_profit_chart()
        self._build_stats_grid()
        self._build_ev_strip()
        self._build_tc_histogram()
        self._build_variance_cone()
        self._build_heat_row()
        self._build_alert_strip()
        self._build_status_bar()

    def _build_header(self):
        f = tk.Frame(self.root, bg=PANEL); f.pack(fill='x', padx=6, pady=(5,2))
        tk.Frame(f, bg=GOLD, width=4).pack(side='left', fill='y')
        tk.Label(f, text=' 🃏 BJ AI — ABSOLUTE EDGE', bg=PANEL,
                fg=GOLD, font=('Courier',10,'bold')).pack(side='left', padx=6, pady=4)
        self.timer_lbl = tk.Label(f, text='00:00:00', bg=PANEL,
                                  fg=DIM, font=('Courier',8))
        self.timer_lbl.pack(side='right', padx=8)
        tk.Label(f, text=V, bg=PANEL, fg=DIM, font=('Courier',6)).pack(side='right', padx=4)

    def _build_action_box(self):
        self.af = tk.Frame(self.root, bg=CARD, highlightthickness=2,
                          highlightbackground=GOLD)
        self.af.pack(fill='x', padx=6, pady=3)
        self.action_lbl = tk.Label(self.af, text='◦  WAITING', bg=CARD,
                                   fg=DIM, font=('Courier',28,'bold'))
        self.action_lbl.pack(pady=(8,2))
        self.action_sub = tk.Label(self.af, text='Enter dealer upcard + your cards',
                                   bg=CARD, fg=DIM, font=('Courier',9), wraplength=380)
        self.action_sub.pack()
        self.dev_hint   = tk.Label(self.af, text='', bg=CARD,
                                   fg=TEAL, font=('Courier',8), wraplength=380)
        self.dev_hint.pack(pady=(2,4))
        # Insurance banner
        self.ins_frame  = tk.Frame(self.af, bg='#1a0800')
        self.ins_banner = tk.Label(self.ins_frame, text='', bg='#1a0800',
                                   fg=AMBER, font=('Courier',10,'bold'))
        self.ins_banner.pack(pady=4)
        # Scout mode banner
        self.scout_frame  = tk.Frame(self.af, bg='#001a2a')
        self.scout_banner = tk.Label(self.scout_frame, text='', bg='#001a2a',
                                     fg=STEEL, font=('Courier',9,'bold'))
        self.scout_banner.pack(pady=4)

    def _build_count_strip(self):
        f = tk.Frame(self.root, bg=PANEL); f.pack(fill='x', padx=6, pady=2)
        self._cnt = {}
        cols = [
            ('RC',   'rc',   WHITE),  ('TC',   'tc',   CYAN),
            ('FTC',  'ftc',  TEAL),   ('EDGE', 'edge', GREEN),
            ('ACE±', 'ace',  AMBER),  ('ΩII',  'om2',  STEEL),
            ('PEN',  'pen',  ORANGE), ('DECKS','dk',   DIM),
        ]
        for i,(lbl,key,col) in enumerate(cols):
            cell = tk.Frame(f, bg=CARD)
            cell.grid(row=0, column=i, sticky='nsew', padx=1, pady=2)
            f.columnconfigure(i, weight=1)
            tk.Label(cell, text=lbl, bg=CARD, fg=DIM,
                    font=('Courier',5,'bold')).pack(pady=(2,0))
            v = tk.Label(cell, text='—', bg=CARD, fg=col,
                        font=('Courier',10,'bold'))
            v.pack(pady=(0,2))
            self._cnt[key] = v

    def _build_bet_row(self):
        f = tk.Frame(self.root, bg=PANEL); f.pack(fill='x', padx=6, pady=2)
        tf = tk.Frame(f, bg=PANEL); tf.pack(side='left', fill='both', expand=True)
        tk.Label(tf, text='OPTIMAL BET', bg=PANEL, fg=DIM,
                font=('Courier',6,'bold')).pack(side='left', padx=8)
        self.bet_lbl   = tk.Label(tf, text='$—', bg=PANEL, fg=GOLD,
                                   font=('Courier',22,'bold'))
        self.bet_lbl.pack(side='left', padx=2)
        self.bet_sub   = tk.Label(tf, text='', bg=PANEL, fg=DIM,
                                   font=('Courier',7))
        self.bet_sub.pack(side='left', padx=4)

        # Wong
        wf = tk.Frame(f, bg=CARD, padx=5, pady=3); wf.pack(side='right', padx=4)
        tk.Label(wf, text='WONG', bg=CARD, fg=DIM, font=('Courier',5,'bold')).pack()
        self.wong_lbl = tk.Label(wf, text='—', bg=CARD, fg=DIM,
                                  font=('Courier',11,'bold'))
        self.wong_lbl.pack()

    def _build_hand_display(self):
        f = tk.Frame(self.root, bg=PANEL); f.pack(fill='x', padx=6, pady=2)
        for label, attr_d, attr_t, fg_c in [
            ('DEALER', 'dealer_disp', None, RED),
            ('PLAYER', 'player_disp', 'player_tot', GREEN),
        ]:
            row = tk.Frame(f, bg=PANEL); row.pack(fill='x', padx=4, pady=1)
            tk.Label(row, text=label, bg=PANEL, fg=DIM,
                    font=('Courier',8,'bold'), width=7).pack(side='left')
            lbl = tk.Label(row, text='[ ? ]', bg=PANEL, fg=fg_c,
                          font=('Courier',11,'bold'))
            lbl.pack(side='left', padx=4)
            setattr(self, attr_d, lbl)
            if attr_t:
                tl = tk.Label(row, text='', bg=PANEL, fg=CYAN,
                             font=('Courier',10,'bold'))
                tl.pack(side='left', padx=2)
                setattr(self, attr_t, tl)

    def _build_controls(self):
        f = tk.Frame(self.root, bg=PANEL, highlightthickness=1,
                    highlightbackground=BORDER)
        f.pack(fill='x', padx=6, pady=2)
        tk.Label(f, text='INPUT', bg=PANEL, fg=GOLD,
                font=('Courier',7,'bold')).pack(pady=(4,1))
        self.input_mode = tk.StringVar(value='player')
        mf = tk.Frame(f, bg=PANEL); mf.pack()
        for val, txt, col in [('dealer','DEALER↓',RED),('player','PLAYER↑',GREEN)]:
            tk.Radiobutton(mf, text=txt, variable=self.input_mode, value=val,
                          bg=PANEL, fg=col, selectcolor=CARD,
                          activebackground=PANEL, font=('Courier',9,'bold')
                          ).pack(side='left', padx=10)
        self.entry_lbl = tk.Label(f, text='Keys: A  2–9  0/T/J/Q/K | D=dealer mode',
                                  bg=PANEL, fg=DIM, font=('Courier',8))
        self.entry_lbl.pack(pady=(2,2))
        bf = tk.Frame(f, bg=PANEL); bf.pack(fill='x', padx=4, pady=(0,4))
        btns = [
            ('NEW[N]',    self._new_hand,    CYAN),
            ('SHUFFLE[R]',self._reshuffle,   ORANGE),
            ('UNDO[⌫]',   self._undo,        RED),
            ('SPLIT[V]',  self._split,       PURPLE),
            ('NEXT[X]',   self._next_split,  STEEL),
            ('RAMP[B]',   self._ramp,        GOLD),
            ('SCORE[C]',  self._show_score,  LIME),
            ('HEAT[H]',   self._show_heat,   ROSE),
            ('SET[?]',    self._settings,    BRIGHT),
        ]
        for txt, cmd, col in btns:
            tk.Button(bf, text=txt, command=cmd, bg=CARD, fg=col,
                     font=('Courier',6,'bold'), relief='flat',
                     padx=1, pady=3, cursor='hand2',
                     activebackground=BORDER
                     ).pack(side='left', expand=True, fill='x', padx=1)

    def _build_outcomes(self):
        f = tk.Frame(self.root, bg=PANEL); f.pack(fill='x', padx=6, pady=2)
        tk.Label(f, text='RESULT:', bg=PANEL, fg=DIM,
                font=('Courier',7,'bold')).pack(side='left', padx=4)
        for txt, pm, col in [
            ('WIN[W]',  1.0,  GREEN), ('LOSS[L]', -1.0, RED),
            ('PUSH[P]', 0.0,  DIM),   ('BJ[J]',   1.5,  GOLD),
            ('SURR[S]', -0.5, ORANGE),('INS[I]',  'ins',AMBER),
        ]:
            tk.Button(f, text=txt, command=lambda p=pm: self._outcome(p),
                     bg=CARD, fg=col, font=('Courier',6,'bold'),
                     relief='flat', padx=1, pady=3, cursor='hand2'
                     ).pack(side='left', expand=True, fill='x', padx=1)

    def _build_ror_row(self):
        f = tk.Frame(self.root, bg=BG); f.pack(fill='x', padx=6, pady=2)
        self.ror_gauge = RoRGauge(f)
        rf = tk.Frame(f, bg=CARD); rf.pack(side='left', fill='both', expand=True, padx=4)
        self.ror_detail = tk.Label(rf, text='', bg=CARD, fg=BRIGHT,
                                    font=('Courier',7), wraplength=180, justify='left')
        self.ror_detail.pack(padx=6, pady=4)

    def _build_profit_chart(self):
        tk.Label(self.root, text='SESSION P&L', bg=BG,
                fg=DIM, font=('Courier',5,'bold')).pack(anchor='w', padx=14)
        self.chart = ProfitChart(self.root)

    def _build_stats_grid(self):
        outer = tk.Frame(self.root, bg=PANEL)
        outer.pack(fill='x', padx=6, pady=2)
        tk.Label(outer, text='SESSION', bg=PANEL, fg=GOLD,
                font=('Courier',6,'bold')).pack(pady=(3,1))
        grid = tk.Frame(outer, bg=PANEL); grid.pack(fill='x', padx=3, pady=(0,4))
        self.stat = {}
        defs = [
            ('Bankroll','br',WHITE), ('Net P&L','pnl',GREEN),
            ('Hands','h',DIM),       ('Win%','wr',CYAN),
            ('Peak','pk',GOLD),      ('Max DD','dd',RED),
            ('ROI','roi',TEAL),      ('Time','tm',DIM),
        ]
        for i,(name,key,col) in enumerate(defs):
            r, c = divmod(i, 4)
            cell = tk.Frame(grid, bg=CARD)
            cell.grid(row=r, column=c, sticky='nsew', padx=2, pady=1)
            grid.columnconfigure(c, weight=1)
            tk.Label(cell, text=name, bg=CARD, fg=DIM,
                    font=('Courier',5)).pack(anchor='w', padx=2, pady=(1,0))
            lbl = tk.Label(cell, text='—', bg=CARD, fg=col,
                          font=('Courier',8,'bold'))
            lbl.pack(anchor='w', padx=2, pady=(0,1))
            self.stat[key] = lbl

    def _build_ev_strip(self):
        f = tk.Frame(self.root, bg=PANEL); f.pack(fill='x', padx=6, pady=1)
        self.ev_strip = tk.Label(f, text='', bg=PANEL, fg=TEAL, font=('Courier',7))
        self.ev_strip.pack(padx=6, pady=3)

    def _build_tc_histogram(self):
        tk.Label(self.root, text='TC HISTOGRAM', bg=BG,
                fg=DIM, font=('Courier',5,'bold')).pack(anchor='w', padx=14)
        self.shoe_hist = ShoeTCHist(self.root)

    def _build_variance_cone(self):
        tk.Label(self.root, text='VARIANCE CONE (next 100h)', bg=BG,
                fg=DIM, font=('Courier',5,'bold')).pack(anchor='w', padx=14)
        self.var_cone = VarianceCone(self.root)

    def _build_heat_row(self):
        f = tk.Frame(self.root, bg=PANEL); f.pack(fill='x', padx=6, pady=2)
        tk.Label(f, text='HEAT', bg=PANEL, fg=DIM,
                font=('Courier',6,'bold')).pack(side='left', padx=6)
        self.heat_bar_cv = tk.Canvas(f, width=240, height=16,
                                      bg=CARD, highlightthickness=0)
        self.heat_bar_cv.pack(side='left', padx=4)
        self.heat_lbl = tk.Label(f, text='COLD ✓', bg=PANEL,
                                  fg=GREEN, font=('Courier',7,'bold'))
        self.heat_lbl.pack(side='left', padx=4)
        tk.Button(f, text='DETAILS', command=self._show_heat,
                 bg=CARD, fg=DIM, font=('Courier',6),
                 relief='flat', cursor='hand2').pack(side='right', padx=6)

    def _build_alert_strip(self):
        self.alert_lbl = tk.Label(self.root, text='', bg=BG,
                                   fg=ORANGE, font=('Courier',8,'bold'), wraplength=390)
        self.alert_lbl.pack(fill='x', padx=10, pady=2)

    def _build_status_bar(self):
        f = tk.Frame(self.root, bg=PANEL); f.pack(fill='x', side='bottom')
        self.status_lbl = tk.Label(f, text='', bg=PANEL, fg=DIM, font=('Courier',6))
        self.status_lbl.pack(side='left', padx=8, pady=2)
        tk.Button(f, text='SAVE+EXPORT', command=self._save_export,
                 bg=PANEL, fg=DIM, font=('Courier',6),
                 relief='flat', cursor='hand2').pack(side='right', padx=4, pady=2)

    # ── Key Bindings ───────────────────────────────────────────────────────────

    def _bind_keys(self):
        self.root.bind('<Key>', self._key)
        self.root.focus_set()

    def _key(self, e):
        key = e.char.lower() if e.char else ''
        ks  = e.keysym.lower()

        # Scout mode: any card input just counts
        if key in CK:
            card = CK[key]
            g = self.game
            if g.scout_mode and g.phase == 'SCOUTING':
                g.see_card(card)
                self.entry_lbl.config(
                    text=f'Scout: {RD.get(card,card)} | TC {g.tc:+.1f}', fg=STEEL)
                if g.tc >= 2:
                    if messagebox.askyesno('Enter Table?',
                        f'TC {g.tc:+.1f} ≥ +2 — Enter table now?'):
                        g.enter_table()
            elif self.input_mode.get() == 'dealer':
                g.set_dealer(card)
                self.input_mode.set('player')
            else:
                g.add_player_card(card)
            self.entry_lbl.config(
                text=f'Added: {RD.get(card,card)} | RC:{g.rc:+d} TC:{g.tc:+.1f}', fg=WHITE)
            return

        dispatch = {'n':self._new_hand,'r':self._reshuffle,'b':self._ramp,
                    'v':self._split,'x':self._next_split,'c':self._show_score,
                    'h':self._show_heat,'?':self._settings}
        if key in dispatch: dispatch[key](); return
        if ks in ('backspace','delete'): self._undo(); return
        if key == 'd': self.input_mode.set('dealer')
        elif key in ('p','='): self._outcome(0.0)
        elif key == 'w': self._outcome(1.0)
        elif key == 'l': self._outcome(-1.0)
        elif key == 'j': self._outcome(1.5)
        elif key == 's': self._outcome(-0.5)
        elif key == 'i': self._outcome('ins')

    def _new_hand(self):
        self.game.new_hand()
        self.entry_lbl.config(text='New hand — D then dealer card', fg=GOLD)

    def _reshuffle(self): self.game.reshuffle()
    def _undo(self): self.game.undo_last()
    def _ramp(self): BetRampPanel(self.game)
    def _show_score(self): SCOREPanel(self.game)
    def _show_heat(self): HeatPanel(self.game)
    def _settings(self): SettingsPanel(self.game, on_apply=lambda: None)

    def _split(self):
        self.game.initiate_split()
        self.entry_lbl.config(text='Split — enter first hand cards', fg=PURPLE)

    def _next_split(self):
        self.game.next_split()
        self.entry_lbl.config(
            text=f'Split hand #{self.game.split_idx+1}', fg=PURPLE)

    def _outcome(self, pm):
        g = self.game
        bet = g.optimal_bet
        g.current_bet = bet

        if pm == 'ins':
            take, msg = g.insurance_decision
            profit = bet * 0.5 if take else 0.0
            g.record_result('INSURANCE', profit)
            self.entry_lbl.config(text=msg, fg=AMBER)
            g.dismiss_insurance()
            return

        labels = {1.0:'WIN',-1.0:'LOSS',0.0:'PUSH',1.5:'BLACKJACK',-0.5:'SURRENDER'}
        outcome = labels.get(pm, 'WIN')
        profit  = bet * pm
        g.record_result(outcome, profit)
        col = GREEN if profit > 0 else (DIM if profit == 0 else RED)
        self.entry_lbl.config(
            text=f'{outcome} ${profit:+.0f} | BR: ${g.bankroll:,.0f}', fg=col)
        g.new_hand()

    def _save_export(self):
        g = self.game
        g.save_session()
        if not g.hand_log:
            messagebox.showinfo('Saved', 'Session saved. No hands to export.')
            return
        path = filedialog.asksaveasfilename(
            defaultextension='.csv',
            filetypes=[('CSV','*.csv'),('JSON','*.json')],
            title='Export Hand Log')
        if path:
            if path.endswith('.json'):
                with open(path,'w') as f: json.dump(g.hand_log, f, indent=2)
            else:
                with open(path,'w',newline='') as f:
                    w = csv.DictWriter(f, fieldnames=g.hand_log[0].keys())
                    w.writeheader(); w.writerows(g.hand_log)
            messagebox.showinfo('Exported', f'Hand log saved: {path}')

    # ── Refresh ────────────────────────────────────────────────────────────────

    def _refresh(self):
        g = self.game

        # Action
        action, explain, hint = g.recommendation
        col = AC.get(action, DIM)
        self.action_lbl.config(text=AG.get(action, action), fg=col)
        self.af.config(highlightbackground=col)
        self.action_sub.config(text=explain,
                               fg=(col if action not in ('WAIT','SCOUT') else DIM))
        self.dev_hint.config(text=hint or '')

        # Insurance banner
        if g.phase == 'INSURANCE':
            take, msg = g.insurance_decision
            bg_ = '#2a1500' if take else '#1a0000'
            self.ins_frame.pack(fill='x', padx=6, pady=2)
            self.ins_banner.config(text=f'⚡ DEALER ACE  |  {msg}',
                                   bg=bg_, fg=(AMBER if take else RED))
            self.ins_frame.config(bg=bg_)
        else:
            self.ins_frame.pack_forget()

        # Scout mode banner
        if g.scout_mode and g.phase == 'SCOUTING':
            self.scout_frame.pack(fill='x', padx=6, pady=2)
            self.scout_banner.config(
                text=f'◎ SCOUT MODE | TC {g.tc:+.1f} | Entry at TC≥+2 | Press D/cards to count')
        else:
            self.scout_frame.pack_forget()

        # TC bar
        self.tc_bar.update(g.tc, g.float_tc, g.ace_count.ace_surplus)

        # Count strip
        tc_c  = GREEN if g.tc >= 2 else (RED if g.tc < 0 else WHITE)
        ftc_c = (GREEN if g.float_tc >= 2 else (RED if g.float_tc < 0 else TEAL))
        pen_c = GREEN if g.penetration >= 0.75 else (ORANGE if g.penetration >= 0.55 else RED)
        adj   = g.ace_count.edge_adjustment * 100
        adj_c = GREEN if adj > 0.05 else (RED if adj < -0.05 else DIM)
        edge_c= GREEN if g.precise_edge > 0 else RED
        self._cnt['rc'].config(text=f'{g.rc:+d}')
        self._cnt['tc'].config(text=f'{g.tc:+.1f}', fg=tc_c)
        self._cnt['ftc'].config(text=f'{g.float_tc:+.1f}', fg=ftc_c)
        self._cnt['edge'].config(text=f'{g.precise_edge*100:+.2f}%', fg=edge_c)
        self._cnt['ace'].config(text=g.ace_count.status_str, fg=adj_c)
        self._cnt['om2'].config(
            text=f'{g.omega2.true_count:+.1f}',
            fg=(RED if g.omega2.error_flag(g.tc) else STEEL))
        self._cnt['pen'].config(text=f'{g.penetration*100:.0f}%', fg=pen_c)
        self._cnt['dk'].config(text=f'{g.decks_remaining:.1f}')

        # Bet + Wong
        bet = g.optimal_bet
        self.bet_lbl.config(text=f'${bet:.0f}')
        float_bonus = g.float_eng.bonus_display(g.penetration)
        self.bet_sub.config(text=f'{bet/g.table_min:.0f}u  TC{g.tc:+.0f}  {float_bonus}')
        ws = g.wong_signal
        self.wong_lbl.config(
            text=ws, fg=(GREEN if ws=='IN' else (RED if ws=='OUT' else DIM)))

        # Hand
        if g.dealer_upcard:
            self.dealer_disp.config(text=f'[ {RD.get(g.dealer_upcard,"?")} ]')
        else:
            self.dealer_disp.config(text='[ ? ]')

        cards = g.player_cards
        if g.split_active and g.split_idx < len(g.split_hands):
            cards = g.split_hands[g.split_idx]
        if cards:
            cs = ' '.join(f'[{RD.get(c,c)}]' for c in cards)
            tot = best_total(cards)
            sf  = 'soft ' if has_soft_ace(cards) else ''
            self.player_disp.config(text=cs)
            self.player_tot.config(
                text=f'{sf}{tot}', fg=(RED if tot>21 else CYAN))
        else:
            self.player_disp.config(text='[ ]')
            self.player_tot.config(text='')

        # RoR gauge
        ror_pct = g.ror * 100
        score   = g.score
        n0      = min(g.n0, 999999)
        rating  = g.score_calc.rating(score)
        self.ror_gauge.update(ror_pct, n0, score, rating)
        self.ror_detail.config(
            text=(f'Edge: {g.precise_edge*100:+.3f}%\n'
                  f'EV/h: ${g.ev_per_hand:+.3f}\n'
                  f'hrs×2: {g.hours_to_double:.0f}h\n'
                  f'Float: ×{g.float_eng.adjustment_factor(g.penetration):.2f}'))

        # Stats
        pnl_c = GREEN if g.net_profit >= 0 else RED
        self.stat['br'].config(text=f'${g.bankroll:,.0f}')
        self.stat['pnl'].config(text=f'${g.net_profit:+,.0f}', fg=pnl_c)
        self.stat['h'].config(text=str(g.hands_played))
        self.stat['wr'].config(text=f'{g.win_rate:.0f}%')
        self.stat['pk'].config(text=f'${g.peak_profit:+,.0f}')
        self.stat['dd'].config(text=f'${g.max_drawdown:,.0f}')
        self.stat['roi'].config(text=f'{g.roi:+.3f}%',
                               fg=(GREEN if g.roi > 0 else RED))
        self.stat['tm'].config(text=g.session_elapsed)
        self.timer_lbl.config(text=g.session_elapsed)

        # EV strip
        evhr = g.ev_per_hour
        self.ev_strip.config(
            text=(f'EV/hr: ${evhr:+.2f}  |  {g.hands_per_hour:.0f} h/hr  '
                  f'|  Precise edge: {g.precise_edge*100:+.4f}%  '
                  f'|  Float ×{g.float_eng.adjustment_factor(g.penetration):.2f}'),
            fg=(GREEN if evhr > 0 else (RED if evhr < 0 else DIM)))

        # Charts
        self.chart.update(list(g.profit_history))
        self.shoe_hist.update(g.tc_distribution, len(g.tc_history))
        ep_h = g.precise_edge * g.optimal_bet
        self.var_cone.update(g.bankroll, ep_h, g.sigma_per_hand, 100)

        # Heat bar
        cv = self.heat_bar_cv; cv.delete('all')
        fw = int(240 * g.heat.heat_level / 100)
        cv.create_rectangle(0,0,240,16, fill=CARD, outline='')
        if fw > 0: cv.create_rectangle(0,0,fw,16, fill=g.heat.heat_color, outline='')
        cv.create_text(120,8, text=f'{g.heat.heat_level:.0f}%',
                      fill=WHITE, font=('Courier',7,'bold'))
        self.heat_lbl.config(text=g.heat.heat_label, fg=g.heat.heat_color)

        # Alerts
        active = [a for a in g.alerts if a.age < 12]
        if active:
            a   = active[0]
            col = (RED if a.level=='danger' else ORANGE if a.level=='warn' else
                   LIME if a.level=='signal' else CYAN)
            self.alert_lbl.config(text=a.message, fg=col)
        else:
            self.alert_lbl.config(text='')

        # Status
        err = g.omega2.error_flag(g.tc)
        self.status_lbl.config(
            text=(f'{"⚠ "+err[:30] if err else ""}'
                  f'  RAINMAN·{g.num_decks}D·KF:{g.kf:.2f}'
                  f'  Hands:{g.hands_played}'
                  f'  Float:{g.float_eng.bonus_display(g.penetration)}'))

        self.root.after(120, self._refresh)

    def run(self):
        print(f"""
╔═══════════════════════════════════════════════════════════════════════╗
║  BJ AI HUD {V:<52}║
╠═══════════════════════════════════════════════════════════════════════╣
║  D=dealer mode  |  A/2-9/0/T/J/Q/K=card  |  ⌫=undo                 ║
║  W=Win  L=Loss  P=Push  J=BJ  S=Surrender  I=Insurance               ║
║  N=New  R=Reshuffle  B=Ramp  V=Split  X=Next  C=SCORE  H=Heat  ?=Set║
║  Saved to: ~/.blackjack_ai/session_history.json                      ║
╚═══════════════════════════════════════════════════════════════════════╝
""")
        self.root.mainloop()


# ═══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description=f'BJ AI HUD {V}')
    parser.add_argument('--bankroll',  type=float, default=None)
    parser.add_argument('--min-bet',   type=float, default=None)
    parser.add_argument('--max-bet',   type=float, default=None)
    parser.add_argument('--kelly',     type=float, default=None)
    parser.add_argument('--decks',     type=int,   default=None)
    parser.add_argument('--scout',     action='store_true')
    parser.add_argument('--no-setup',  action='store_true')
    args = parser.parse_args()

    if args.no_setup or (args.bankroll and args.min_bet):
        cfg = {
            'bankroll': args.bankroll or 1000,
            'min_bet':  args.min_bet  or 10,
            'max_bet':  args.max_bet  or 300,
            'kf':       args.kelly    or 0.35,
            'decks':    args.decks    or 6,
            'surrender': True, 'das': True,
            'sl': 0.20, 'wg': 0.50,
            'scout_mode': args.scout,
        }
    else:
        dlg = SetupDialog()
        if dlg.result is None:
            return
        cfg = dlg.result

    game = GameState(
        bankroll=cfg['bankroll'],
        table_min=cfg['min_bet'],
        table_max=cfg['max_bet'],
        num_decks=cfg['decks'],
        kf=cfg['kf'],
        can_surrender=cfg['surrender'],
        das=cfg['das'],
        stop_loss_pct=cfg['sl'],
        win_goal_pct=cfg['wg'],
        wong_mode=False,
        scout_mode=cfg.get('scout_mode', False),
    )

    HUDv5(game).run()


if __name__ == '__main__':
    main()

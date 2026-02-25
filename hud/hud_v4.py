#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  BLACKJACK AI — HUD v4.0 — CLINICAL EDITION                                 ║
║                                                                              ║
║  What's new in v4:                                                           ║
║  • Ace side count — separate tracking for ace-poor/ace-rich shoes           ║
║  • Insurance alert panel — auto-activates when dealer shows Ace             ║
║  • Multi-hand split tracker — track up to 4 split hands independently       ║
║  • EV/hour calculator — live expected profit rate at current pace           ║
║  • Wong in/out signal — back-counting entry/exit threshold indicator        ║
║  • Shoe heatmap — color-coded count history for current shoe                ║
║  • Variance cone — projected ±1σ bankroll range after N hands               ║
║  • In-app settings panel — change all parameters without restarting         ║
║  • True count histogram — visualize TC distribution of current shoe         ║
║  • Card removal effects table — which unseen cards are most valuable        ║
║  • Precise edge model — ace side count adjustment to Hi-Lo                  ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import sys, os, time, math, argparse, json, csv
from typing import Optional, List, Tuple, Dict
from dataclasses import dataclass, field
from collections import deque, Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from core.strategy import get_action, HandState, Action, best_total, has_soft_ace
from core.counting import CardCounter, HI_LO_TAGS

# ═══════════════════════════════════════════════════════════════════════════════
# THEME
# ═══════════════════════════════════════════════════════════════════════════════

V = "4.0 — Clinical Edition"

BG     = '#03030d'
PANEL  = '#0a0a1a'
CARD   = '#0f0f26'
BORDER = '#181838'
WHITE  = '#eeeeff'
DIM    = '#3a3a60'
BRIGHT = '#9090cc'
GOLD   = '#ffd700'
GREEN  = '#00ff88'
RED    = '#ff3355'
CYAN   = '#00e5ff'
ORANGE = '#ff9800'
PURPLE = '#c084fc'
TEAL   = '#40e0d0'
LIME   = '#aaff00'
PINK   = '#ff69b4'
AMBER  = '#ffbf00'
STEEL  = '#7799bb'

AC = {
    'HIT':       GREEN,
    'STAND':     GOLD,
    'DOUBLE':    CYAN,
    'SPLIT':     PURPLE,
    'SURRENDER': RED,
    'WAIT':      DIM,
    'INSURANCE': AMBER,
}

AG = {
    'HIT':       '↑  HIT',
    'STAND':     '―  STAND',
    'DOUBLE':    '✦  DOUBLE',
    'SPLIT':     '⟺  SPLIT',
    'SURRENDER': '✕  SURRENDER',
    'WAIT':      '◦  WAITING',
    'INSURANCE': '☂  TAKE INSURANCE',
}

RD = {1:'A',2:'2',3:'3',4:'4',5:'5',6:'6',7:'7',8:'8',9:'9',10:'10'}
CK = {'a':1,'2':2,'3':3,'4':4,'5':5,'6':6,'7':7,'8':8,'9':9,
      '0':10,'t':10,'j':10,'q':10,'k':10}


# ═══════════════════════════════════════════════════════════════════════════════
# ILLUSTRIOUS 18 + FAB 4 — Complete table
# ═══════════════════════════════════════════════════════════════════════════════

DEVIATIONS = [
    # (p_total, dealer, is_soft, basic_action, dev_action, tc_threshold, >=threshold?, desc)
    (16, 10, False, 'HIT',    'STAND',       0,  True,  'Stand 16 vs 10 at TC≥0'),
    (15, 10, False, 'HIT',    'SURRENDER',   0,  True,  'Surrender 15 vs 10 at TC≥0'),
    (10, 10, False, 'HIT',    'DOUBLE',      4,  True,  'Double 10 vs 10 at TC≥4'),
    (10,  9, False, 'HIT',    'DOUBLE',      1,  True,  'Double 10 vs 9 at TC≥1'),
    (12,  3, False, 'HIT',    'STAND',       2,  True,  'Stand 12 vs 3 at TC≥2'),
    (12,  2, False, 'HIT',    'STAND',       3,  True,  'Stand 12 vs 2 at TC≥3'),
    (11, 10, False, 'HIT',    'DOUBLE',      1,  True,  'Double 11 vs 10 at TC≥1'),
    (12,  4, False, 'STAND',  'HIT',        -1, False,  'Hit 12 vs 4 at TC<-1'),
    (12,  5, False, 'STAND',  'HIT',        -2, False,  'Hit 12 vs 5 at TC<-2'),
    (12,  6, False, 'STAND',  'HIT',        -1, False,  'Hit 12 vs 6 at TC<-1'),
    (13,  2, False, 'STAND',  'HIT',        -1, False,  'Hit 13 vs 2 at TC<-1'),
    (13,  3, False, 'STAND',  'HIT',        -2, False,  'Hit 13 vs 3 at TC<-2'),
    (9,   2, False, 'HIT',    'DOUBLE',      1,  True,  'Double 9 vs 2 at TC≥1'),
    (9,   7, False, 'HIT',    'DOUBLE',      3,  True,  'Double 9 vs 7 at TC≥3'),
    (16,  9, False, 'HIT',    'STAND',       5,  True,  'Stand 16 vs 9 at TC≥5'),
    (13,  4, False, 'STAND',  'HIT',        -1, False,  'Hit 13 vs 4 at TC<-1'),
    (20,  5, False, 'STAND',  'SPLIT',       5,  True,  'Split 20s vs 5 at TC≥5'),
    (20,  6, False, 'STAND',  'SPLIT',       4,  True,  'Split 20s vs 6 at TC≥4'),
    # Fab 4 surrenders
    (14, 10, False, 'HIT',    'SURRENDER',   3,  True,  'Surrender 14 vs 10 at TC≥3'),
    (15,  9, False, 'HIT',    'SURRENDER',   2,  True,  'Surrender 15 vs 9 at TC≥2'),
    (15,  1, False, 'HIT',    'SURRENDER',   1,  True,  'Surrender 15 vs A at TC≥1'),
]

def lookup_deviation(ptotal, dealer, tc, is_soft=False):
    """Return deviated action or None."""
    for p, d, s, basic, dev, thr, above, desc in DEVIATIONS:
        if p != ptotal or d != dealer or s != is_soft:
            continue
        if above and tc >= thr:
            return dev
        if not above and tc < thr:
            return dev
    return None

def closest_deviation(ptotal, dealer, tc, is_soft=False):
    """Return description of the deviation closest to triggering."""
    best, best_dist = None, float('inf')
    for p, d, s, basic, dev, thr, above, desc in DEVIATIONS:
        if p != ptotal or d != dealer or s != is_soft:
            continue
        dist = abs(tc - thr)
        if dist < best_dist:
            best_dist = dist
            direction = '≥' if above else '<'
            delta = thr - tc if above else tc - thr
            best = f'{desc} [Δ{delta:+.1f} TC]'
    return best


# ═══════════════════════════════════════════════════════════════════════════════
# ACE SIDE COUNT — Precision edge model
# ═══════════════════════════════════════════════════════════════════════════════

class AceSideCount:
    """
    Track aces separately.
    Hi-Lo tags ace as -1 but aces are worth MORE for betting.
    Side count correction: each excess ace above expected is worth +0.4% edge.
    """

    def __init__(self, total_decks: int = 6):
        self.total_decks = total_decks
        self.aces_seen    = 0
        self.cards_seen   = 0

    def see_card(self, card: int):
        self.cards_seen += 1
        if card == 1:
            self.aces_seen += 1

    def reset(self):
        self.aces_seen  = 0
        self.cards_seen = 0

    @property
    def expected_aces(self) -> float:
        """Expected aces seen based on cards_seen."""
        return self.cards_seen * (4 * self.total_decks) / (52 * self.total_decks)

    @property
    def ace_deviation(self) -> float:
        """Aces seen minus expected. Positive = ace-rich shoe (good for player)."""
        return self.aces_seen - self.expected_aces

    @property
    def aces_remaining(self) -> float:
        """Estimated aces left in shoe."""
        total_aces = 4 * self.total_decks
        return max(0, total_aces - self.aces_seen)

    @property
    def expected_aces_remaining(self) -> float:
        """Expected aces remaining based on cards left."""
        cards_remaining = max(1, self.total_decks * 52 - self.cards_seen)
        return cards_remaining * (4 * self.total_decks) / (52 * self.total_decks)

    @property
    def ace_surplus(self) -> float:
        """Actual aces remaining minus expected. Positive = more aces left than expected."""
        return self.aces_remaining - self.expected_aces_remaining

    @property
    def edge_adjustment(self) -> float:
        """
        Edge adjustment from ace side count.
        Each surplus ace per deck remaining ≈ +0.59% to edge.
        """
        if self.cards_seen == 0:
            return 0.0
        cards_remaining = max(1, self.total_decks * 52 - self.cards_seen)
        decks_remaining = cards_remaining / 52
        if decks_remaining < 0.1:
            return 0.0
        # Aces per deck remaining vs expected
        actual_ace_density = self.aces_remaining / decks_remaining
        expected_ace_density = 4.0   # 4 aces per deck
        ace_rich = actual_ace_density - expected_ace_density
        return ace_rich * 0.0059   # ~0.59% per excess ace per deck

    @property
    def status_str(self) -> str:
        s = self.ace_surplus
        if s > 1.5:   return f'+{s:.1f} ACE RICH ★'
        if s > 0.5:   return f'+{s:.1f} ace surplus'
        if s < -1.5:  return f'{s:.1f} ACE POOR ▼'
        if s < -0.5:  return f'{s:.1f} ace deficit'
        return f'{s:+.1f} neutral'

    @property
    def insurance_ev(self) -> float:
        """
        EV of insurance based on actual ten-density.
        Insurance wins if dealer has ten in hole.
        Break-even: 1 ten per 2 non-tens remaining.
        """
        cards_remaining = max(1, self.total_decks * 52 - self.cards_seen)
        # Estimate tens remaining from Hi-Lo (approximate)
        return 0.0  # Placeholder — main insurance signal comes from TC≥3


# ═══════════════════════════════════════════════════════════════════════════════
# RAINMAN BET RAMP — v4 with ace adjustment
# ═══════════════════════════════════════════════════════════════════════════════

class RainmanBetRamp:
    RAMP_MULT = {-6:1,-5:1,-4:1,-3:1,-2:1,-1:1, 0:1, 1:1,
                  2:2, 3:4, 4:8, 5:12, 6:16}

    def __init__(self, min_bet: float, max_bet: float,
                 bankroll: float, kelly_fraction: float = 0.35):
        self.min_bet  = min_bet
        self.max_bet  = max_bet
        self.bankroll = bankroll
        self.kf       = kelly_fraction

    def base_unit(self) -> float:
        return max(self.min_bet, self.bankroll * self.kf * 0.0068)

    def get_bet(self, tc: float, ace_adjustment: float = 0.0) -> float:
        tc_adj = tc + ace_adjustment * 2   # Ace surplus shifts effective TC
        tc_key = max(-6, min(6, int(tc_adj)))
        mult = self.RAMP_MULT.get(tc_key, 1)
        bet  = self.base_unit() * mult
        return max(self.min_bet, min(self.max_bet, round(bet / 5) * 5))

    def full_table(self, ace_adj: float = 0.0) -> List[dict]:
        rows = []
        for tc in range(-2, 7):
            mult = self.RAMP_MULT.get(tc, 1)
            bet  = max(self.min_bet, min(self.max_bet,
                       round(self.base_unit() * mult / 5) * 5))
            edge = -0.004 + tc * 0.005 + ace_adj
            ev_hr = edge * bet * 80
            rows.append({'tc':tc,'bet':bet,'units':bet/self.min_bet,
                         'edge_pct':edge*100,'ev_hr':ev_hr,'mult':mult})
        return rows

    def update(self, bankroll: float):
        self.bankroll = bankroll

    @property
    def wong_in_threshold(self) -> int:
        """TC to enter table (back-counting entry point)."""
        return 2

    @property
    def wong_out_threshold(self) -> int:
        """TC to exit table (back-counting exit point)."""
        return 0


# ═══════════════════════════════════════════════════════════════════════════════
# SPLIT HAND TRACKER
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class SplitHand:
    cards:  List[int] = field(default_factory=list)
    bet:    float = 0.0
    done:   bool  = False
    result: Optional[float] = None

    @property
    def total(self) -> int:
        return best_total(self.cards)

    @property
    def is_soft(self) -> bool:
        return has_soft_ace(self.cards)


class SplitTracker:
    """Manage up to 4 split hands."""

    def __init__(self):
        self.hands: List[SplitHand] = []
        self.active_idx = 0

    def start_split(self, card: int, bet: float):
        """Initialize from a pair being split."""
        self.hands = [SplitHand(cards=[card], bet=bet),
                      SplitHand(cards=[card], bet=bet)]
        self.active_idx = 0

    def add_split(self, bet: float):
        """Add a 3rd or 4th hand from re-split."""
        if len(self.hands) < 4:
            card = self.hands[self.active_idx].cards[0]
            self.hands.append(SplitHand(cards=[card], bet=bet))

    def active_hand(self) -> Optional[SplitHand]:
        if self.active_idx < len(self.hands):
            return self.hands[self.active_idx]
        return None

    def next_hand(self):
        self.active_idx += 1

    def clear(self):
        self.hands = []
        self.active_idx = 0

    @property
    def total_bet(self) -> float:
        return sum(h.bet for h in self.hands)

    @property
    def is_active(self) -> bool:
        return len(self.hands) > 0


# ═══════════════════════════════════════════════════════════════════════════════
# GAME STATE v4
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class Alert:
    level:   str  # 'info' | 'warn' | 'danger' | 'signal'
    message: str
    timestamp: float = field(default_factory=time.time)

    @property
    def age(self) -> float:
        return time.time() - self.timestamp


class GameState:

    def __init__(self, bankroll: float, table_min: float, table_max: float,
                 num_decks: int = 6, kelly_fraction: float = 0.35,
                 can_surrender: bool = True, das: bool = True,
                 stop_loss_pct: float = 0.20, win_goal_pct: float = 0.50,
                 wong_mode: bool = False):

        self.bankroll          = bankroll
        self.starting_bankroll = bankroll
        self.table_min         = table_min
        self.table_max         = table_max
        self.num_decks         = num_decks
        self.kf                = kelly_fraction
        self.can_surrender     = can_surrender
        self.das               = das
        self.stop_loss_pct     = stop_loss_pct
        self.win_goal_pct      = win_goal_pct
        self.wong_mode         = wong_mode

        self.counter    = CardCounter(num_decks)
        self.ace_count  = AceSideCount(num_decks)
        self.bet_ramp   = RainmanBetRamp(table_min, table_max, bankroll, kelly_fraction)
        self.splitter   = SplitTracker()

        # Hand
        self.player_cards:  List[int] = []
        self.dealer_upcard: Optional[int] = None
        self.phase = 'BETTING'   # BETTING|DEALING|PLAYING|INSURANCE|DONE

        # Session
        self.hands_played    = 0
        self.session_wins    = 0
        self.session_losses  = 0
        self.session_pushes  = 0
        self.net_profit      = 0.0
        self.peak_profit     = 0.0
        self.max_drawdown    = 0.0
        self.total_wagered   = 0.0
        self.current_bet     = table_min

        self.profit_history:   deque = deque(maxlen=600)
        self.profit_history.append(0.0)
        self.tc_history:       deque = deque(maxlen=400)   # TC at each hand
        self.hands_per_hour_history: deque = deque(maxlen=60)

        self.hand_log: List[dict] = []
        self.alerts:   deque = deque(maxlen=8)

        self.session_start   = time.time()
        self.last_hand_time  = time.time()
        self.hand_times:     deque = deque(maxlen=20)

    # ── Card entry ─────────────────────────────────────────────────────────────

    def see_card(self, card: int):
        """Register any card seen at the table (counts but doesn't add to hand)."""
        self.counter.see_card(card)
        self.ace_count.see_card(card)

    def set_dealer_upcard(self, card: int):
        self.dealer_upcard = card
        self.see_card(card)
        # Auto-trigger insurance phase if Ace
        if card == 1 and len(self.player_cards) >= 2:
            self.phase = 'INSURANCE'
        else:
            self._update_phase()

    def add_player_card(self, card: int):
        if self.splitter.is_active:
            hand = self.splitter.active_hand()
            if hand:
                hand.cards.append(card)
        else:
            self.player_cards.append(card)
        self.see_card(card)
        self._update_phase()

    def undo_last_card(self):
        if self.splitter.is_active:
            hand = self.splitter.active_hand()
            if hand and hand.cards:
                c = hand.cards.pop()
                self._reverse_card(c)
        elif self.player_cards:
            c = self.player_cards.pop()
            self._reverse_card(c)
        self._update_phase()

    def _reverse_card(self, c: int):
        tag = HI_LO_TAGS.get(min(c, 10), 0)
        self.counter.state.running_count -= tag
        self.counter.state.cards_seen    -= 1
        self.counter.state.decks_remaining = self.counter.state.decks_remaining_from_cards(
            self.counter.state.cards_seen, self.num_decks)
        if c == 1:
            self.ace_count.aces_seen -= 1
        self.ace_count.cards_seen -= 1

    def initiate_split(self):
        """Called when player chooses to split."""
        if len(self.player_cards) == 2 and self.player_cards[0] == self.player_cards[1]:
            self.splitter.start_split(self.player_cards[0], self.current_bet)
            self.player_cards = []

    def next_split_hand(self):
        self.splitter.next_hand()

    def new_hand(self):
        self.player_cards  = []
        self.dealer_upcard = None
        self.phase         = 'BETTING'
        self.splitter.clear()
        self.bet_ramp.update(self.bankroll)

    def reshuffle(self):
        self.counter.reset_shoe()
        self.ace_count.reset()
        self.tc_history.clear()
        self._push_alert('info', '🔀 Reshuffled — count reset to zero')

    def record_result(self, outcome: str, profit: float):
        elapsed = time.time() - self.last_hand_time
        self.hand_times.append(elapsed)
        self.last_hand_time = time.time()

        self.bankroll      += profit
        self.net_profit     = self.bankroll - self.starting_bankroll
        self.peak_profit    = max(self.peak_profit, self.net_profit)
        dd = self.peak_profit - self.net_profit
        self.max_drawdown   = max(self.max_drawdown, dd)
        self.total_wagered += self.current_bet
        self.hands_played  += 1
        self.tc_history.append(round(self.tc, 2))
        self.profit_history.append(self.net_profit)

        lbl = outcome.upper()
        if lbl in ('WIN', 'BLACKJACK'): self.session_wins   += 1
        elif lbl == 'LOSS':              self.session_losses += 1
        else:                            self.session_pushes += 1

        self.hand_log.append({
            'hand':    self.hands_played,
            'player':  list(self.player_cards),
            'dealer':  self.dealer_upcard,
            'bet':     self.current_bet,
            'profit':  round(profit, 2),
            'tc':      round(self.tc, 2),
            'rc':      self.rc,
            'ace_surplus': round(self.ace_count.ace_surplus, 2),
            'edge_pct':    round(self.precise_edge * 100, 4),
            'outcome': lbl,
            'bankroll':round(self.bankroll, 2),
        })

        # Alerts
        session_profit = self.bankroll - self.starting_bankroll
        sl = self.starting_bankroll * self.stop_loss_pct
        wg = self.starting_bankroll * self.win_goal_pct
        if session_profit <= -sl:
            self._push_alert('danger', f'🛑 STOP LOSS: -${abs(session_profit):.0f} — LEAVE TABLE NOW')
        elif session_profit >= wg:
            self._push_alert('warn', f'🏆 WIN GOAL +${session_profit:.0f} — Consider coloring up')

        if self.penetration >= 0.87:
            self._push_alert('signal', '⚡ PEAK PENETRATION 87%+ — Maximum edge zone')

    def _push_alert(self, level: str, msg: str):
        # Don't duplicate same message
        if self.alerts and self.alerts[0].message == msg and self.alerts[0].age < 10:
            return
        self.alerts.appendleft(Alert(level, msg))

    def _update_phase(self):
        if self.dealer_upcard == 1 and len(self.player_cards) >= 2 and self.phase != 'INSURANCE':
            self.phase = 'INSURANCE'
        elif self.dealer_upcard and len(self.player_cards) >= 2:
            self.phase = 'PLAYING'
        elif self.dealer_upcard or self.player_cards:
            self.phase = 'DEALING'
        else:
            self.phase = 'BETTING'

    def dismiss_insurance(self):
        self.phase = 'PLAYING'

    # ── Computed ───────────────────────────────────────────────────────────────

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
    def precise_edge(self) -> float:
        """Hi-Lo edge + ace side count correction."""
        return self.counter.state.player_edge + self.ace_count.edge_adjustment

    @property
    def decks_remaining(self) -> float:
        return self.counter.state.decks_remaining

    @property
    def penetration(self) -> float:
        return min(1.0, self.counter.state.cards_seen / (self.num_decks * 52))

    @property
    def optimal_bet(self) -> float:
        return self.bet_ramp.get_bet(self.tc, self.ace_count.edge_adjustment * 2)

    @property
    def insurance_decision(self) -> Tuple[bool, str]:
        tc = self.tc
        if tc >= 3:
            return True, f'✅ TAKE INSURANCE — TC {tc:+.1f} ≥ 3 (profitable)'
        else:
            return False, f'✗ SKIP INSURANCE — TC {tc:+.1f} < 3 (negative EV)'

    @property
    def wong_signal(self) -> str:
        tc = self.tc
        if tc >= self.bet_ramp.wong_in_threshold:
            return 'IN'
        elif tc < self.bet_ramp.wong_out_threshold:
            return 'OUT'
        return 'HOLD'

    @property
    def recommendation(self) -> Tuple[str, str, Optional[str]]:
        # Insurance phase override
        if self.phase == 'INSURANCE':
            take, msg = self.insurance_decision
            return 'INSURANCE' if take else 'HIT', msg, None

        # Active split hand
        cards = self.player_cards
        if self.splitter.is_active:
            hand = self.splitter.active_hand()
            if hand:
                cards = hand.cards

        if not cards or not self.dealer_upcard:
            return 'WAIT', 'Enter dealer upcard and your cards', None

        total    = best_total(cards)
        is_soft  = has_soft_ace(cards)
        can_split= (len(cards) == 2 and cards[0] == cards[1])
        can_dbl  = len(cards) == 2
        can_surr = self.can_surrender and len(cards) == 2 and not self.splitter.is_active

        # Illustrious 18 check
        dev = lookup_deviation(total, self.dealer_upcard, self.tc, is_soft)

        state = HandState(
            player_total=total, dealer_upcard=self.dealer_upcard,
            is_soft=is_soft, can_split=can_split, can_double=can_dbl,
            can_surrender=can_surr, true_count=self.tc,
        )
        try:
            basic = get_action(state).name
        except:
            basic = 'HIT'

        final      = dev if (dev and dev != basic) else basic
        is_dev     = (dev is not None and dev != basic)
        soft_str   = 'soft ' if is_soft else ''

        if is_dev:
            explain = f'⚡ DEV | {soft_str}{total} vs {RD.get(self.dealer_upcard,"?")} | TC{self.tc:+.1f} | basic={basic}'
        else:
            explain = f'{soft_str}{total} vs {RD.get(self.dealer_upcard,"?")} | TC{self.tc:+.1f}'

        hint = closest_deviation(total, self.dealer_upcard, self.tc, is_soft)
        return final, explain, hint

    @property
    def ev_per_hour(self) -> float:
        """Expected value per hour at current edge and pace."""
        if len(self.hand_times) < 2:
            return 0.0
        avg_secs = sum(self.hand_times) / len(self.hand_times)
        hands_per_hr = 3600 / max(avg_secs, 5)
        return self.precise_edge * self.optimal_bet * hands_per_hr

    @property
    def hands_per_hour(self) -> float:
        if len(self.hand_times) < 2:
            return 0.0
        avg = sum(self.hand_times) / len(self.hand_times)
        return min(200, 3600 / max(avg, 5))

    @property
    def session_elapsed(self) -> str:
        s = int(time.time() - self.session_start)
        return f'{s//3600:02d}:{(s%3600)//60:02d}:{s%60:02d}'

    @property
    def win_rate(self) -> float:
        total = self.session_wins + self.session_losses + self.session_pushes
        return self.session_wins / max(1, total) * 100

    @property
    def roi(self) -> float:
        return self.net_profit / max(1, self.total_wagered) * 100

    @property
    def variance_1sigma(self) -> float:
        """Bankroll standard deviation after next 100 hands."""
        avg_bet = self.total_wagered / max(1, self.hands_played)
        sigma_per_hand = avg_bet * 1.15   # BJ variance ≈ 1.33, σ ≈ 1.15×bet
        return sigma_per_hand * math.sqrt(100)

    @property
    def tc_distribution(self) -> Dict[int, int]:
        """Histogram of TC values seen this shoe."""
        hist = Counter()
        for tc in self.tc_history:
            hist[int(tc)] += 1
        return dict(hist)


# ═══════════════════════════════════════════════════════════════════════════════
# WIDGETS
# ═══════════════════════════════════════════════════════════════════════════════

class ProfitChart:
    def __init__(self, parent, width=375, height=85):
        self.canvas = tk.Canvas(parent, width=width, height=height,
                               bg=CARD, highlightthickness=0)
        self.canvas.pack(fill='x', padx=6, pady=1)
        self.w, self.h = width, height

    def update(self, history):
        c = self.canvas
        c.delete('all')
        data = list(history)
        if len(data) < 2:
            c.create_text(self.w//2, self.h//2, text='No data',
                         fill=DIM, font=('Courier', 8))
            return
        mn, mx = min(data), max(data)
        span = max(1, mx - mn)
        if span < 100:
            mn -= 50; mx += 50; span = mx - mn
        pad = 8
        pw, ph = self.w - pad*2, self.h - pad*2

        def px(i, v):
            return (pad + (i/(len(data)-1))*pw,
                    pad + (1-(v-mn)/span)*ph)

        # Zero line
        zy = pad + (1-(0-mn)/span)*ph
        zy = max(pad, min(pad+ph, zy))
        c.create_line(pad, zy, self.w-pad, zy, fill=DIM, dash=(3,5))

        # Gradient fill
        for i in range(len(data)-1):
            x1,y1 = px(i,   data[i])
            x2,y2 = px(i+1, data[i+1])
            col = GREEN if data[i+1] >= 0 else RED
            c.create_line(x1,y1,x2,y2, fill=col, width=1.5, smooth=True)

        # Area below line to zero
        pts = [pad, zy]
        for i, v in enumerate(data):
            pts += list(px(i, v))
        pts += [self.w-pad, zy]
        c.create_polygon(pts, fill='#00ff2208', outline='')

        # Current dot
        lx, ly = px(len(data)-1, data[-1])
        col = GREEN if data[-1] >= 0 else RED
        c.create_oval(lx-3,ly-3,lx+3,ly+3, fill=col, outline='')
        c.create_text(lx-6, ly-8, text=f'${data[-1]:+,.0f}',
                     fill=col, font=('Courier', 7, 'bold'), anchor='e')
        c.create_text(pad+1, pad+ph, text=f'${mn:+,.0f}',
                     fill=DIM, font=('Courier', 6), anchor='sw')
        c.create_text(pad+1, pad, text=f'${mx:+,.0f}',
                     fill=DIM, font=('Courier', 6), anchor='nw')


class TCHeatMeter:
    def __init__(self, parent, width=375, height=24):
        self.canvas = tk.Canvas(parent, width=width, height=height,
                               bg=PANEL, highlightthickness=0)
        self.canvas.pack(fill='x', padx=6, pady=1)
        self.w, self.h = width, height

    def update(self, tc, ace_surplus=0.0):
        c = self.canvas
        c.delete('all')
        norm = max(0.0, min(1.0, (tc + 6) / 12))
        fw   = int(self.w * norm)

        color = ('#113377' if tc < 0 else
                 '#223344' if tc < 2 else
                 ORANGE    if tc < 4 else
                 '#ff5500' if tc < 6 else GOLD)

        c.create_rectangle(0, 0, self.w, self.h, fill=CARD, outline='')
        if fw > 0:
            c.create_rectangle(0, 0, fw, self.h, fill=color, outline='')
        cx = self.w // 2
        c.create_line(cx, 0, cx, self.h, fill=DIM, dash=(2,4))

        ace_str = f'  ACE:{ace_surplus:+.1f}' if abs(ace_surplus) > 0.3 else ''
        label = (f'TC {tc:+.1f} — {"COLD" if tc<0 else "NEUTRAL" if tc<2 else "HOT ↑" if tc<4 else "MAX EDGE ★"}{ace_str}')
        c.create_text(self.w//2, self.h//2+1, text=label,
                     fill=WHITE, font=('Courier', 8, 'bold'))


class ShoeTCHistogram:
    """Mini bar chart of TC distribution for current shoe."""
    def __init__(self, parent, width=375, height=60):
        self.canvas = tk.Canvas(parent, width=width, height=height,
                               bg=CARD, highlightthickness=0)
        self.canvas.pack(fill='x', padx=6, pady=1)
        self.w, self.h = width, height

    def update(self, tc_dist: dict, total: int):
        c = self.canvas
        c.delete('all')
        if total == 0:
            c.create_text(self.w//2, self.h//2, text='TC histogram — play hands',
                         fill=DIM, font=('Courier', 7))
            return

        tc_range = range(-4, 7)
        n = len(tc_range)
        bar_w = (self.w - 16) / n
        max_cnt = max((tc_dist.get(t, 0) for t in tc_range), default=1)
        if max_cnt == 0:
            return

        pad = 8
        for i, tc in enumerate(tc_range):
            cnt  = tc_dist.get(tc, 0)
            frac = cnt / max_cnt
            bx   = pad + i * bar_w
            bh   = max(2, frac * (self.h - 20))
            col  = (RED if tc < 0 else DIM if tc < 2 else
                   ORANGE if tc < 4 else GREEN if tc < 6 else GOLD)
            c.create_rectangle(bx+1, self.h-10-bh, bx+bar_w-2, self.h-10,
                              fill=col, outline='')
            c.create_text(bx + bar_w/2, self.h-5,
                         text=f'{tc:+d}', fill=DIM, font=('Courier', 6))

        c.create_text(pad, 4, text='TC DISTRIBUTION (this shoe)',
                     fill=DIM, font=('Courier', 6), anchor='nw')


class VarianceCone:
    """Projected bankroll ±1σ and ±2σ after N hands."""
    def __init__(self, parent, width=375, height=70):
        self.canvas = tk.Canvas(parent, width=width, height=height,
                               bg=CARD, highlightthickness=0)
        self.canvas.pack(fill='x', padx=6, pady=1)
        self.w, self.h = width, height

    def update(self, bankroll: float, ev_per_hand: float,
               sigma_per_hand: float, n_hands: int = 100):
        c = self.canvas
        c.delete('all')
        if sigma_per_hand < 1:
            c.create_text(self.w//2, self.h//2,
                         text='Variance cone — record outcomes to calibrate',
                         fill=DIM, font=('Courier', 7))
            return

        steps   = 50
        n_pts   = n_hands
        pad_x, pad_y = 30, 8
        pw = self.w - pad_x * 2
        ph = self.h - pad_y * 2

        # Build projections
        evs = [bankroll + ev_per_hand * t for t in range(steps+1)]
        s1_hi = [evs[t] + sigma_per_hand * math.sqrt(t) for t in range(steps+1)]
        s1_lo = [evs[t] - sigma_per_hand * math.sqrt(t) for t in range(steps+1)]
        s2_hi = [evs[t] + 2*sigma_per_hand * math.sqrt(t) for t in range(steps+1)]
        s2_lo = [evs[t] - 2*sigma_per_hand * math.sqrt(t) for t in range(steps+1)]

        all_vals = s2_hi + s2_lo
        mn, mx = min(all_vals), max(all_vals)
        span = max(1, mx - mn)

        def px(t, v):
            x = pad_x + (t / steps) * pw
            y = pad_y + (1 - (v - mn) / span) * ph
            return x, y

        # ±2σ fill
        pts2 = [pad_x, pad_y + ph]
        for t in range(steps+1):
            pts2 += list(px(t, s2_hi[t]))
        for t in reversed(range(steps+1)):
            pts2 += list(px(t, s2_lo[t]))
        c.create_polygon(pts2, fill='#ff330415', outline='')

        # ±1σ fill
        pts1 = [pad_x, pad_y + ph]
        for t in range(steps+1):
            pts1 += list(px(t, s1_hi[t]))
        for t in reversed(range(steps+1)):
            pts1 += list(px(t, s1_lo[t]))
        c.create_polygon(pts1, fill='#00ff4420', outline='')

        # EV line
        pts_ev = []
        for t in range(steps+1):
            pts_ev += list(px(t, evs[t]))
        c.create_line(pts_ev, fill=GREEN, width=1.5, smooth=True)

        # Labels at end
        lx, ly = px(steps, evs[-1])
        c.create_text(lx+2, ly, text=f'EV ${evs[-1]-bankroll:+,.0f}',
                     fill=GREEN, font=('Courier', 6), anchor='w')
        lx1, ly1 = px(steps, s1_hi[-1])
        c.create_text(lx1+2, ly1, text=f'+1σ ${s1_hi[-1]-bankroll:+,.0f}',
                     fill=TEAL, font=('Courier', 6), anchor='w')
        lx2, ly2 = px(steps, s1_lo[-1])
        c.create_text(lx2+2, ly2, text=f'-1σ ${s1_lo[-1]-bankroll:+,.0f}',
                     fill=ORANGE, font=('Courier', 6), anchor='w')

        c.create_text(pad_x, 3,
                     text=f'NEXT {n_pts} HANDS: EV {ev_per_hand:+.2f}/hand',
                     fill=DIM, font=('Courier', 6), anchor='nw')
        c.create_text(pad_x, self.h-5, text='0', fill=DIM, font=('Courier', 6), anchor='sw')
        c.create_text(self.w-5, self.h-5, text=f'{n_pts}',
                     fill=DIM, font=('Courier', 6), anchor='se')


# ═══════════════════════════════════════════════════════════════════════════════
# SETTINGS PANEL (in-app)
# ═══════════════════════════════════════════════════════════════════════════════

class SettingsPanel:
    def __init__(self, game: GameState, on_apply):
        self.game = game
        self.on_apply = on_apply
        self.win = tk.Toplevel()
        self.win.title('Settings')
        self.win.configure(bg=BG)
        self.win.attributes('-topmost', True)
        self.win.geometry('320x480+60+60')
        self._build()

    def _build(self):
        tk.Label(self.win, text='SESSION SETTINGS', bg=BG,
                fg=GOLD, font=('Courier', 11, 'bold')).pack(pady=(12, 4))

        self.vars = {}
        defs = [
            ('Kelly Fraction',    'kelly',     str(self.game.kf)),
            ('Stop Loss %',       'stop_loss', str(int(self.game.stop_loss_pct*100))),
            ('Win Goal %',        'win_goal',  str(int(self.game.win_goal_pct*100))),
            ('Table Max ($)',     'max_bet',   str(self.game.table_max)),
            ('Table Min ($)',     'min_bet',   str(self.game.table_min)),
        ]
        for label, key, val in defs:
            row = tk.Frame(self.win, bg=BG)
            row.pack(fill='x', padx=20, pady=4)
            tk.Label(row, text=label, bg=BG, fg=WHITE,
                    font=('Courier', 9), width=18, anchor='w').pack(side='left')
            var = tk.StringVar(value=val)
            tk.Entry(row, textvariable=var, bg=CARD, fg=GOLD,
                    font=('Courier', 10, 'bold'), insertbackground=WHITE,
                    relief='flat', bd=0, width=8,
                    highlightthickness=1, highlightbackground=BORDER,
                    highlightcolor=CYAN).pack(side='right')
            self.vars[key] = var

        self.wong_var = tk.BooleanVar(value=self.game.wong_mode)
        tk.Checkbutton(self.win, text='Wong back-counting mode',
                      variable=self.wong_var, bg=BG, fg=WHITE,
                      selectcolor=CARD, activebackground=BG,
                      font=('Courier', 9)).pack(pady=6)

        self.surr_var = tk.BooleanVar(value=self.game.can_surrender)
        tk.Checkbutton(self.win, text='Surrender allowed',
                      variable=self.surr_var, bg=BG, fg=WHITE,
                      selectcolor=CARD, activebackground=BG,
                      font=('Courier', 9)).pack(pady=2)

        tk.Button(self.win, text='APPLY', command=self._apply,
                 bg=GOLD, fg=BG, font=('Courier', 10, 'bold'),
                 relief='flat', padx=16, pady=8, cursor='hand2').pack(pady=16)

    def _apply(self):
        try:
            self.game.kf             = float(self.vars['kelly'].get())
            self.game.stop_loss_pct  = float(self.vars['stop_loss'].get()) / 100
            self.game.win_goal_pct   = float(self.vars['win_goal'].get()) / 100
            self.game.table_max      = float(self.vars['max_bet'].get())
            self.game.table_min      = float(self.vars['min_bet'].get())
            self.game.wong_mode      = self.wong_var.get()
            self.game.can_surrender  = self.surr_var.get()
            self.game.bet_ramp.kf    = self.game.kf
            self.game.bet_ramp.max_bet = self.game.table_max
            self.game.bet_ramp.min_bet = self.game.table_min
            self.on_apply()
            self.win.destroy()
        except ValueError as e:
            messagebox.showerror('Invalid', str(e))


# ═══════════════════════════════════════════════════════════════════════════════
# BET RAMP PANEL
# ═══════════════════════════════════════════════════════════════════════════════

class BetRampPanel:
    def __init__(self, game: GameState):
        self.game = game
        self.win  = tk.Toplevel()
        self.win.title('Bet Ramp — Rainman v4')
        self.win.configure(bg=BG)
        self.win.attributes('-topmost', True)
        self.win.geometry('360x460+15+30')
        self._build()

    def _build(self):
        g = self.game
        tk.Label(self.win, text='RAINMAN BET RAMP', bg=BG,
                fg=GOLD, font=('Courier', 10, 'bold')).pack(pady=(10, 2))
        tk.Label(self.win,
                text=f'BR: ${g.bankroll:,.0f}  |  Unit: ${g.bet_ramp.base_unit():.0f}'
                     f'  |  Kelly {g.kf:.0%}  |  Ace: {g.ace_count.status_str}',
                bg=BG, fg=DIM, font=('Courier', 7)).pack(pady=(0,6))

        frame = tk.Frame(self.win, bg=PANEL, padx=8, pady=6)
        frame.pack(fill='both', expand=True, padx=10)

        headers = ['TC', 'BET', 'MULT', 'EDGE%', 'EV/HR', 'NOTE']
        widths   = [4,    7,     5,      7,       8,       14   ]
        for col, (h, w) in enumerate(zip(headers, widths)):
            tk.Label(frame, text=h, bg=PANEL, fg=GOLD,
                    font=('Courier', 8, 'bold'), width=w
                    ).grid(row=0, column=col, padx=2, pady=2)

        ramp  = g.bet_ramp.full_table(g.ace_count.edge_adjustment)
        cur_tc = int(g.tc)

        for ri, r in enumerate(ramp, 1):
            tc  = r['tc']
            hot = tc == cur_tc
            bg  = '#0a1a0a' if hot and r['edge_pct'] > 0 else PANEL
            fg_tc = GREEN if r['edge_pct'] > 0 else (DIM if r['edge_pct'] < -0.3 else WHITE)
            note = ('← YOU ARE HERE' if hot else
                   'WONG IN' if tc == 2 else
                   'WONG OUT' if tc == 0 else '')

            vals = [
                (f'{tc:+d}',              fg_tc),
                (f'${r["bet"]:.0f}',      WHITE),
                (f'{r["mult"]}x',         DIM),
                (f'{r["edge_pct"]:+.2f}', GREEN if r["edge_pct"]>0 else RED),
                (f'${r["ev_hr"]:+.2f}',   GREEN if r["ev_hr"]>0 else RED),
                (note,                     CYAN if 'HERE' in note else TEAL),
            ]
            for col, ((val, color), w) in enumerate(zip(vals, widths)):
                tk.Label(frame, text=val, bg=bg, fg=color,
                        font=('Courier', 9, 'bold' if hot else 'normal'), width=w
                        ).grid(row=ri, column=col, padx=2, pady=1)

        tk.Label(self.win,
                text=f'Wong in: TC≥+2 | Wong out: TC<0 | Insurance: TC≥+3',
                bg=BG, fg=DIM, font=('Courier', 7)).pack(pady=8)


# ═══════════════════════════════════════════════════════════════════════════════
# SETUP DIALOG
# ═══════════════════════════════════════════════════════════════════════════════

class SetupDialog:
    def __init__(self):
        self.result = None
        self.root   = tk.Tk()
        self.root.title('BJ AI v4 — Setup')
        self.root.configure(bg=BG)
        self.root.resizable(False, False)
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        self.root.geometry(f'440x640+{(sw-440)//2}+{(sh-640)//2}')
        self._build()
        self.root.mainloop()

    def _build(self):
        tk.Frame(self.root, bg=GOLD, height=3).pack(fill='x')
        hdr = tk.Frame(self.root, bg=PANEL, pady=14)
        hdr.pack(fill='x')
        tk.Label(hdr, text='🃏 BLACKJACK AI ADVISOR v4', bg=PANEL,
                fg=GOLD, font=('Courier', 14, 'bold')).pack()
        tk.Label(hdr, text='Clinical Edition — Ace-adjusted precision counting',
                bg=PANEL, fg=DIM, font=('Courier', 8)).pack(pady=(2,0))
        tk.Frame(self.root, bg=GOLD, height=1).pack(fill='x')

        form = tk.Frame(self.root, bg=BG, padx=28, pady=18)
        form.pack(fill='both', expand=True)

        self.fv = {}
        for label, key, default in [
            ('Bankroll ($)',        'bankroll',  '1000'),
            ('Table Minimum ($)',   'min_bet',   '10'),
            ('Table Maximum ($)',   'max_bet',   '300'),
            ('Kelly Fraction',      'kelly',     '0.35'),
            ('Stop Loss %',         'stop_loss', '20'),
            ('Win Goal %',          'win_goal',  '50'),
        ]:
            row = tk.Frame(form, bg=BG)
            row.pack(fill='x', pady=5)
            tk.Label(row, text=label, bg=BG, fg=WHITE,
                    font=('Courier', 10), width=20, anchor='w').pack(side='left')
            var = tk.StringVar(value=default)
            tk.Entry(row, textvariable=var, bg=CARD, fg=GOLD,
                    font=('Courier', 11, 'bold'), insertbackground=WHITE,
                    relief='flat', width=10,
                    highlightthickness=1, highlightbackground=BORDER,
                    highlightcolor=CYAN).pack(side='right')
            self.fv[key] = var

        self.surr_var  = tk.BooleanVar(value=True)
        self.das_var   = tk.BooleanVar(value=True)
        self.wong_var  = tk.BooleanVar(value=False)
        for text, var in [('Surrender allowed', self.surr_var),
                          ('Double After Split', self.das_var),
                          ('Wong back-counting mode', self.wong_var)]:
            tk.Checkbutton(form, text=text, variable=var,
                          bg=BG, fg=WHITE, selectcolor=CARD,
                          activebackground=BG, font=('Courier', 9)
                          ).pack(anchor='w', pady=2)

        self.deck_var = tk.IntVar(value=6)
        dr = tk.Frame(form, bg=BG)
        dr.pack(fill='x', pady=6)
        tk.Label(dr, text='Decks:', bg=BG, fg=WHITE,
                font=('Courier', 9)).pack(side='left')
        for d in [1, 2, 4, 6, 8]:
            tk.Radiobutton(dr, text=str(d), variable=self.deck_var, value=d,
                          bg=BG, fg=CYAN, selectcolor=CARD,
                          activebackground=BG,
                          font=('Courier', 9)).pack(side='left', padx=5)

        # Info strip
        info = tk.Frame(form, bg=PANEL, padx=10, pady=8)
        info.pack(fill='x', pady=10)
        tk.Label(info, text='v4 adds: Ace side count • Insurance detector',
                bg=PANEL, fg=GREEN, font=('Courier', 8)).pack()
        tk.Label(info, text='Split tracker • EV/hr • Variance cone • Wong signals',
                bg=PANEL, fg=DIM, font=('Courier', 8)).pack()

        tk.Button(self.root, text='▶  LAUNCH HUD v4',
                 bg=GOLD, fg=BG, font=('Courier', 12, 'bold'),
                 relief='flat', padx=20, pady=14,
                 activebackground=GREEN, cursor='hand2',
                 command=self._launch).pack(fill='x', padx=24, pady=(0,20))

    def _launch(self):
        try:
            self.result = {
                'bankroll':  float(self.fv['bankroll'].get()),
                'min_bet':   float(self.fv['min_bet'].get()),
                'max_bet':   float(self.fv['max_bet'].get()),
                'kelly':     float(self.fv['kelly'].get()),
                'stop_loss': float(self.fv['stop_loss'].get()) / 100,
                'win_goal':  float(self.fv['win_goal'].get()) / 100,
                'decks':     self.deck_var.get(),
                'surrender': self.surr_var.get(),
                'das':       self.das_var.get(),
                'wong_mode': self.wong_var.get(),
            }
            self.root.destroy()
        except ValueError as e:
            messagebox.showerror('Invalid Input', str(e))


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN HUD v4
# ═══════════════════════════════════════════════════════════════════════════════

class HUDv4:

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
        self.root.geometry(f'400x980+{sw-416}+0')
        self.root.bind('<Button-1>', lambda e: (setattr(self,'_dx',e.x), setattr(self,'_dy',e.y)))
        self.root.bind('<B1-Motion>', self._drag)
        self._dx = self._dy = 0

    def _drag(self, e):
        x = self.root.winfo_x() + e.x - self._dx
        y = self.root.winfo_y() + e.y - self._dy
        self.root.geometry(f'+{x}+{y}')

    def _build_ui(self):
        self._build_header()
        self.tc_heat = TCHeatMeter(self.root)
        self._build_action_box()
        self._build_count_strip()
        self._build_bet_and_wong()
        self._build_hand_display()
        self._build_card_entry()
        self._build_outcomes()
        tk.Frame(self.root, bg=BG, height=2).pack(fill='x')
        self._build_profit_chart()
        self._build_stats_grid()
        self._build_ev_strip()
        self._build_shoe_histogram()
        self._build_variance_cone()
        self._build_alert_strip()
        self._build_status_bar()

    def _build_header(self):
        f = tk.Frame(self.root, bg=PANEL)
        f.pack(fill='x', padx=6, pady=(5,2))
        tk.Frame(f, bg=GOLD, width=4).pack(side='left', fill='y')
        tk.Label(f, text=' 🃏 BJ AI CLINICAL ADVISOR', bg=PANEL,
                fg=GOLD, font=('Courier', 10, 'bold')).pack(side='left', padx=6, pady=4)
        self.timer_lbl = tk.Label(f, text='00:00:00', bg=PANEL,
                                  fg=DIM, font=('Courier', 8))
        self.timer_lbl.pack(side='right', padx=8)
        tk.Label(f, text=V, bg=PANEL, fg=DIM,
                font=('Courier', 6)).pack(side='right', padx=4)

    def _build_action_box(self):
        self.action_frame = tk.Frame(self.root, bg=CARD, bd=0,
                                     highlightthickness=2,
                                     highlightbackground=GOLD)
        self.action_frame.pack(fill='x', padx=6, pady=3)

        self.action_lbl = tk.Label(self.action_frame, text='◦  WAITING',
                                   bg=CARD, fg=DIM, font=('Courier', 30, 'bold'))
        self.action_lbl.pack(pady=(10, 2))

        self.action_sub = tk.Label(self.action_frame, text='Enter dealer upcard + your cards',
                                   bg=CARD, fg=DIM, font=('Courier', 9), wraplength=370)
        self.action_sub.pack()

        self.dev_hint = tk.Label(self.action_frame, text='',
                                 bg=CARD, fg=TEAL, font=('Courier', 8), wraplength=370)
        self.dev_hint.pack(pady=(2, 6))

        # Insurance banner (hidden by default)
        self.ins_frame = tk.Frame(self.action_frame, bg='#2a1500')
        self.ins_banner = tk.Label(self.ins_frame, text='', bg='#2a1500',
                                   fg=AMBER, font=('Courier', 11, 'bold'))
        self.ins_banner.pack(pady=6)

    def _build_count_strip(self):
        f = tk.Frame(self.root, bg=PANEL)
        f.pack(fill='x', padx=6, pady=2)
        self._cnt = {}
        cols = [
            ('RC',    'rc',    WHITE),
            ('TC',    'tc',    CYAN),
            ('EDGE',  'edge',  GREEN),
            ('ADJ',   'adj',   TEAL),
            ('DECKS', 'decks', DIM),
            ('PEN',   'pen',   ORANGE),
        ]
        for i, (lbl, key, color) in enumerate(cols):
            cell = tk.Frame(f, bg=CARD)
            cell.grid(row=0, column=i, sticky='nsew', padx=2, pady=2)
            f.columnconfigure(i, weight=1)
            tk.Label(cell, text=lbl, bg=CARD, fg=DIM,
                    font=('Courier', 6, 'bold')).pack(pady=(3,0))
            v = tk.Label(cell, text='—', bg=CARD, fg=color,
                        font=('Courier', 12, 'bold'))
            v.pack(pady=(0,3))
            self._cnt[key] = v

    def _build_bet_and_wong(self):
        f = tk.Frame(self.root, bg=PANEL)
        f.pack(fill='x', padx=6, pady=2)

        # Bet recommendation
        bf = tk.Frame(f, bg=PANEL)
        bf.pack(side='left', fill='both', expand=True)
        tk.Label(bf, text='OPTIMAL BET', bg=PANEL, fg=DIM,
                font=('Courier', 7, 'bold')).pack(side='left', padx=8)
        self.bet_lbl = tk.Label(bf, text='$—', bg=PANEL,
                                fg=GOLD, font=('Courier', 22, 'bold'))
        self.bet_lbl.pack(side='left', padx=2)
        self.bet_units_lbl = tk.Label(bf, text='', bg=PANEL,
                                      fg=DIM, font=('Courier', 8))
        self.bet_units_lbl.pack(side='left', padx=4)

        # Wong signal
        wf = tk.Frame(f, bg=CARD, padx=6, pady=4)
        wf.pack(side='right', padx=6)
        tk.Label(wf, text='WONG', bg=CARD, fg=DIM,
                font=('Courier', 6, 'bold')).pack()
        self.wong_lbl = tk.Label(wf, text='—', bg=CARD,
                                 fg=DIM, font=('Courier', 12, 'bold'))
        self.wong_lbl.pack()

        # Ace count display
        af = tk.Frame(f, bg=CARD, padx=6, pady=4)
        af.pack(side='right', padx=4)
        tk.Label(af, text='ACE±', bg=CARD, fg=DIM,
                font=('Courier', 6, 'bold')).pack()
        self.ace_lbl = tk.Label(af, text='—', bg=CARD,
                                fg=TEAL, font=('Courier', 12, 'bold'))
        self.ace_lbl.pack()

    def _build_hand_display(self):
        f = tk.Frame(self.root, bg=PANEL)
        f.pack(fill='x', padx=6, pady=2)

        for row_txt, attr_d, attr_p, attr_t in [
            ('DEALER', 'dealer_display', None, None),
            ('PLAYER', 'player_display', 'player_total_lbl', None),
        ]:
            row = tk.Frame(f, bg=PANEL)
            row.pack(fill='x', padx=4, pady=2)
            tk.Label(row, text=row_txt, bg=PANEL, fg=DIM,
                    font=('Courier', 8, 'bold'), width=7).pack(side='left')
            lbl = tk.Label(row, text='[ ? ]', bg=PANEL,
                          fg=RED if row_txt=='DEALER' else GREEN,
                          font=('Courier', 12, 'bold'))
            lbl.pack(side='left', padx=4)
            setattr(self, attr_d, lbl)
            if attr_p:
                tl = tk.Label(row, text='', bg=PANEL, fg=CYAN,
                             font=('Courier', 10, 'bold'))
                tl.pack(side='left', padx=2)
                setattr(self, attr_p, tl)

        # Split hand display
        self.split_frame = tk.Frame(f, bg=PANEL)
        # populated dynamically

    def _build_card_entry(self):
        f = tk.Frame(self.root, bg=PANEL, highlightthickness=1,
                    highlightbackground=BORDER)
        f.pack(fill='x', padx=6, pady=3)
        tk.Label(f, text='CARD ENTRY', bg=PANEL, fg=GOLD,
                font=('Courier', 8, 'bold')).pack(pady=(5,2))

        self.input_mode = tk.StringVar(value='player')
        mf = tk.Frame(f, bg=PANEL)
        mf.pack()
        for val, txt, col in [('dealer','DEALER ↓', RED), ('player','PLAYER ↑', GREEN)]:
            tk.Radiobutton(mf, text=txt, variable=self.input_mode, value=val,
                          bg=PANEL, fg=col, selectcolor=CARD,
                          activebackground=PANEL, font=('Courier', 9, 'bold')
                          ).pack(side='left', padx=12)

        self.entry_lbl = tk.Label(f, text='Keys: A  2–9  0/T/J/Q/K',
                                  bg=PANEL, fg=DIM, font=('Courier', 9))
        self.entry_lbl.pack(pady=(3,2))

        bf = tk.Frame(f, bg=PANEL)
        bf.pack(fill='x', padx=6, pady=(2,6))
        for text, cmd, color in [
            ('NEW [N]',  self._new_hand,  CYAN),
            ('SHUFFLE[R]',self._reshuffle,ORANGE),
            ('UNDO [⌫]', self._undo,      RED),
            ('SPLIT [V]', self._split,    PURPLE),
            ('NEXT [X]',  self._next_split,STEEL),
            ('RAMP [B]',  self._ramp,     GOLD),
            ('SETTINGS[?]',self._settings,BRIGHT),
        ]:
            tk.Button(bf, text=text, command=cmd, bg=CARD, fg=color,
                     font=('Courier', 6, 'bold'), relief='flat',
                     padx=2, pady=4, cursor='hand2',
                     activebackground=BORDER
                     ).pack(side='left', expand=True, fill='x', padx=1)

    def _build_outcomes(self):
        f = tk.Frame(self.root, bg=PANEL)
        f.pack(fill='x', padx=6, pady=2)
        tk.Label(f, text='RESULT:', bg=PANEL, fg=DIM,
                font=('Courier', 7, 'bold')).pack(side='left', padx=6)
        outcomes = [
            ('WIN [W]',   1.0,  GREEN),
            ('LOSS [L]', -1.0,  RED),
            ('PUSH [P]',  0.0,  DIM),
            ('BJ [J]',    1.5,  GOLD),
            ('SURR [S]', -0.5,  ORANGE),
            ('INS [I]',   'ins',AMBER),
        ]
        for text, pm, col in outcomes:
            tk.Button(f, text=text,
                     command=lambda p=pm: self._outcome(p),
                     bg=CARD, fg=col, font=('Courier', 6, 'bold'),
                     relief='flat', padx=2, pady=3, cursor='hand2'
                     ).pack(side='left', expand=True, fill='x', padx=1)

    def _build_profit_chart(self):
        tk.Label(self.root, text='SESSION P&L', bg=BG,
                fg=DIM, font=('Courier', 6, 'bold')).pack(anchor='w', padx=14)
        self.chart = ProfitChart(self.root)

    def _build_stats_grid(self):
        outer = tk.Frame(self.root, bg=PANEL)
        outer.pack(fill='x', padx=6, pady=2)
        tk.Label(outer, text='SESSION', bg=PANEL, fg=GOLD,
                font=('Courier', 7, 'bold')).pack(pady=(4,1))
        grid = tk.Frame(outer, bg=PANEL)
        grid.pack(fill='x', padx=4, pady=(0,4))
        self.stat = {}
        defs = [
            ('Bankroll', 'br', WHITE), ('Net P&L', 'pnl', GREEN),
            ('Hands',    'h',  DIM),   ('Win%',   'wr',  CYAN),
            ('Peak',    'pk',  GOLD),  ('Max DD', 'dd',  RED),
            ('ROI',     'roi', TEAL),  ('Time',   'tm',  DIM),
        ]
        for i, (name, key, col) in enumerate(defs):
            r, c = divmod(i, 4)
            cell = tk.Frame(grid, bg=CARD)
            cell.grid(row=r, column=c, sticky='nsew', padx=2, pady=1)
            grid.columnconfigure(c, weight=1)
            tk.Label(cell, text=name, bg=CARD, fg=DIM,
                    font=('Courier', 6)).pack(anchor='w', padx=3, pady=(2,0))
            lbl = tk.Label(cell, text='—', bg=CARD, fg=col,
                          font=('Courier', 9, 'bold'))
            lbl.pack(anchor='w', padx=3, pady=(0,2))
            self.stat[key] = lbl

    def _build_ev_strip(self):
        f = tk.Frame(self.root, bg=PANEL)
        f.pack(fill='x', padx=6, pady=1)
        self.ev_strip = tk.Label(f, text='', bg=PANEL, fg=TEAL,
                                 font=('Courier', 8))
        self.ev_strip.pack(padx=8, pady=3)

    def _build_shoe_histogram(self):
        tk.Label(self.root, text='TC HISTOGRAM (current shoe)',
                bg=BG, fg=DIM, font=('Courier', 6, 'bold')).pack(anchor='w', padx=14)
        self.shoe_hist = ShoeTCHistogram(self.root)

    def _build_variance_cone(self):
        tk.Label(self.root, text='VARIANCE CONE (next 100 hands)',
                bg=BG, fg=DIM, font=('Courier', 6, 'bold')).pack(anchor='w', padx=14)
        self.var_cone = VarianceCone(self.root)

    def _build_alert_strip(self):
        self.alert_lbl = tk.Label(self.root, text='', bg=BG,
                                  fg=ORANGE, font=('Courier', 8, 'bold'),
                                  wraplength=380)
        self.alert_lbl.pack(fill='x', padx=12, pady=2)

    def _build_status_bar(self):
        f = tk.Frame(self.root, bg=PANEL)
        f.pack(fill='x', side='bottom')
        self.status_lbl = tk.Label(f, text='', bg=PANEL,
                                   fg=DIM, font=('Courier', 6))
        self.status_lbl.pack(side='left', padx=8, pady=3)
        tk.Button(f, text='EXPORT', command=self._export,
                 bg=PANEL, fg=DIM, font=('Courier', 6),
                 relief='flat', cursor='hand2').pack(side='right', padx=6, pady=2)

    # ── Key Bindings ───────────────────────────────────────────────────────────

    def _bind_keys(self):
        self.root.bind('<Key>', self._key)
        self.root.focus_set()

    def _key(self, e):
        key = e.char.lower() if e.char else ''
        ks  = e.keysym.lower()

        if key in CK:
            card = CK[key]
            if self.input_mode.get() == 'dealer':
                self.game.set_dealer_upcard(card)
                self.input_mode.set('player')
            else:
                self.game.add_player_card(card)
            self.entry_lbl.config(text=f'Added: {RD.get(card,card)}', fg=WHITE)
            return

        dispatch = {
            'n': self._new_hand,    'r': self._reshuffle,
            'b': self._ramp,        'v': self._split,
            'x': self._next_split,  '?': self._settings,
        }
        if key in dispatch:
            dispatch[key]()
            return
        if ks in ('backspace','delete'): self._undo(); return
        if key == 'd': self.input_mode.set('dealer')
        elif key in ('p','='):
            if self.game.phase == 'PLAYING':
                self._outcome(0.0)
            else:
                self.input_mode.set('player')
        elif key == 'w': self._outcome(1.0)
        elif key == 'l': self._outcome(-1.0)
        elif key == 'j': self._outcome(1.5)
        elif key == 's': self._outcome(-0.5)
        elif key == 'i': self._outcome('ins')

    def _new_hand(self):
        self.game.new_hand()
        self.entry_lbl.config(text='New hand — press D then dealer card', fg=GOLD)

    def _reshuffle(self):
        self.game.reshuffle()

    def _undo(self):
        self.game.undo_last_card()
        self.entry_lbl.config(text='Undo', fg=ORANGE)

    def _split(self):
        self.game.initiate_split()
        self.entry_lbl.config(text='Split initiated — enter first hand cards', fg=PURPLE)

    def _next_split(self):
        self.game.next_split_hand()
        idx = self.game.splitter.active_idx
        self.entry_lbl.config(text=f'Split hand #{idx+1}', fg=PURPLE)

    def _ramp(self):
        BetRampPanel(self.game)

    def _settings(self):
        SettingsPanel(self.game, on_apply=lambda: None)

    def _outcome(self, profit_mult):
        g = self.game
        bet = g.optimal_bet
        if profit_mult == 'ins':
            # Insurance side bet: pays 2:1 if dealer BJ (1/3 TC≥3 chance)
            take, msg = g.insurance_decision
            profit = bet * 0.5 if take else 0.0
            g.current_bet = bet
            g.record_result('INSURANCE', profit if take else 0.0)
            self.entry_lbl.config(text=msg, fg=AMBER)
            g.dismiss_insurance()
            return

        labels = {1.0:'WIN',-1.0:'LOSS',0.0:'PUSH',1.5:'BLACKJACK',-0.5:'SURRENDER'}
        outcome = labels.get(profit_mult, 'WIN')
        profit  = bet * profit_mult
        g.current_bet = bet
        g.record_result(outcome, profit)
        col = GREEN if profit > 0 else (DIM if profit == 0 else RED)
        self.entry_lbl.config(
            text=f'{outcome}: ${profit:+.0f} | BR: ${g.bankroll:,.0f}', fg=col)
        g.new_hand()

    def _export(self):
        g = self.game
        if not g.hand_log:
            messagebox.showinfo('No data', 'No hands recorded yet.')
            return
        path = filedialog.asksaveasfilename(
            defaultextension='.csv',
            filetypes=[('CSV','*.csv'),('JSON','*.json')],
            title='Export Hand Log')
        if path:
            if path.endswith('.json'):
                with open(path,'w') as f:
                    json.dump(g.hand_log, f, indent=2)
            else:
                with open(path,'w',newline='') as f:
                    w = csv.DictWriter(f, fieldnames=g.hand_log[0].keys())
                    w.writeheader(); w.writerows(g.hand_log)
            messagebox.showinfo('Exported', f'Saved: {path}')

    # ── Refresh ────────────────────────────────────────────────────────────────

    def _refresh(self):
        g = self.game

        # Action box
        action, explain, hint = g.recommendation
        color = AC.get(action, DIM)
        glyph = AG.get(action, action)
        self.action_lbl.config(text=glyph, fg=color)
        self.action_frame.config(highlightbackground=color)
        self.action_sub.config(text=explain,
                               fg=(color if action not in ('WAIT',) else DIM))
        self.dev_hint.config(text=hint or '')

        # Insurance banner
        if g.phase == 'INSURANCE':
            take, msg = g.insurance_decision
            self.ins_frame.pack(fill='x', padx=6, pady=4)
            self.ins_banner.config(
                text=f'⚡ DEALER ACE  |  {msg}',
                bg='#2a1500' if take else '#1a0000',
                fg=AMBER if take else RED)
            self.ins_frame.config(bg='#2a1500' if take else '#1a0000')
        else:
            self.ins_frame.pack_forget()

        # TC heat
        self.tc_heat.update(g.tc, g.ace_count.ace_surplus)

        # Count strip
        tc_c = GREEN if g.tc >= 2 else (RED if g.tc < 0 else WHITE)
        adj  = g.ace_count.edge_adjustment * 100
        adj_c= GREEN if adj > 0.05 else (RED if adj < -0.05 else DIM)
        pen_c= GREEN if g.penetration >= 0.75 else (ORANGE if g.penetration >= 0.55 else RED)
        edge_c=GREEN if g.edge > 0 else RED

        self._cnt['rc'].config(text=f'{g.rc:+d}')
        self._cnt['tc'].config(text=f'{g.tc:+.1f}', fg=tc_c)
        self._cnt['edge'].config(text=f'{g.edge:+.2f}%', fg=edge_c)
        self._cnt['adj'].config(text=f'{adj:+.2f}%', fg=adj_c)
        self._cnt['decks'].config(text=f'{g.decks_remaining:.1f}')
        self._cnt['pen'].config(text=f'{g.penetration*100:.0f}%', fg=pen_c)

        # Bet + Wong
        bet = g.optimal_bet
        self.bet_lbl.config(text=f'${bet:.0f}')
        self.bet_units_lbl.config(text=f'{bet/g.table_min:.0f}u  TC{g.tc:+.0f}')

        ws = g.wong_signal
        self.wong_lbl.config(
            text=ws,
            fg=(GREEN if ws=='IN' else (RED if ws=='OUT' else DIM)))

        # Ace count
        sur = g.ace_count.ace_surplus
        self.ace_lbl.config(
            text=f'{sur:+.1f}',
            fg=(GREEN if sur > 0.5 else (RED if sur < -0.5 else DIM)))

        # Hand display
        if g.dealer_upcard:
            self.dealer_display.config(text=f'[ {RD.get(g.dealer_upcard,"?")} ]')
        else:
            self.dealer_display.config(text='[ ? ]')

        cards = g.player_cards
        if g.splitter.is_active:
            hand = g.splitter.active_hand()
            if hand:
                cards = hand.cards

        if cards:
            cs = ' '.join(f'[{RD.get(c,c)}]' for c in cards)
            tot = best_total(cards)
            soft= 'soft ' if has_soft_ace(cards) and tot<=21 else ''
            self.player_display.config(text=cs)
            self.player_total_lbl.config(
                text=f'{soft}{tot}',
                fg=(RED if tot>21 else CYAN))
        else:
            self.player_display.config(text='[ ]')
            self.player_total_lbl.config(text='')

        # Stats
        pnl_c = GREEN if g.net_profit >= 0 else RED
        self.stat['br'].config(text=f'${g.bankroll:,.0f}')
        self.stat['pnl'].config(text=f'${g.net_profit:+,.0f}', fg=pnl_c)
        self.stat['h'].config(text=str(g.hands_played))
        self.stat['wr'].config(text=f'{g.win_rate:.0f}%')
        self.stat['pk'].config(text=f'${g.peak_profit:+,.0f}')
        self.stat['dd'].config(text=f'${g.max_drawdown:,.0f}')
        self.stat['roi'].config(text=f'{g.roi:+.3f}%',
                               fg=(GREEN if g.roi>0 else RED))
        self.stat['tm'].config(text=g.session_elapsed)
        self.timer_lbl.config(text=g.session_elapsed)

        # EV/hr strip
        evhr = g.ev_per_hour
        hph  = g.hands_per_hour
        prec_edge = g.precise_edge * 100
        self.ev_strip.config(
            text=f'EV/hr: ${evhr:+.2f}  |  {hph:.0f} hands/hr  |  Precise edge: {prec_edge:+.3f}%',
            fg=(GREEN if evhr>0 else (RED if evhr<0 else DIM)))

        # Profit chart
        self.chart.update(list(g.profit_history))

        # Shoe histogram
        self.shoe_hist.update(g.tc_distribution, len(g.tc_history))

        # Variance cone
        ep_hand = g.precise_edge * g.optimal_bet
        sig_hand = (g.total_wagered / max(1, g.hands_played)) * 1.15
        self.var_cone.update(g.bankroll, ep_hand, sig_hand, 100)

        # Alerts
        active = [a for a in g.alerts if a.age < 10]
        if active:
            a = active[0]
            ac = RED if a.level=='danger' else (ORANGE if a.level=='warn' else
                 LIME if a.level=='signal' else CYAN)
            self.alert_lbl.config(text=a.message, fg=ac)
        else:
            self.alert_lbl.config(text='')

        # Status bar
        pen_warn = ' ⚠️ CHANGE TABLE' if g.penetration < 0.55 and g.hands_played > 20 else ''
        self.status_lbl.config(
            text=f'RAINMAN | KF:{g.kf:.2f} | {g.num_decks}D | '
                 f'Ace:{g.ace_count.status_str} | H:{g.hands_played}{pen_warn}')

        self.root.after(120, self._refresh)

    def run(self):
        print(f"""
╔═══════════════════════════════════════════════════════════════════════╗
║  BLACKJACK AI HUD {V:<46}║
╠═══════════════════════════════════════════════════════════════════════╣
║  Card entry: A 2-9 0/T/J/Q/K  |  D=dealer mode  |  ⌫=undo          ║
║  Outcomes:  W=Win  L=Loss  P=Push  J=Blackjack  S=Surrender  I=Ins  ║
║  Actions:   N=New  R=Reshuffle  B=Bet ramp  V=Split  X=Next split   ║
║             ?=Settings                                                ║
╚═══════════════════════════════════════════════════════════════════════╝
""")
        self.root.mainloop()


# ═══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description=f'BJ AI HUD {V}')
    parser.add_argument('--bankroll', type=float, default=None)
    parser.add_argument('--min-bet',  type=float, default=None)
    parser.add_argument('--max-bet',  type=float, default=None)
    parser.add_argument('--kelly',    type=float, default=None)
    parser.add_argument('--decks',    type=int,   default=None)
    parser.add_argument('--no-setup', action='store_true')
    args = parser.parse_args()

    if args.no_setup or (args.bankroll and args.min_bet):
        cfg = {
            'bankroll':  args.bankroll or 1000,
            'min_bet':   args.min_bet  or 10,
            'max_bet':   args.max_bet  or 300,
            'kelly':     args.kelly    or 0.35,
            'decks':     args.decks    or 6,
            'surrender': True, 'das': True,
            'stop_loss': 0.20, 'win_goal': 0.50,
            'wong_mode': False,
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
        kelly_fraction=cfg['kelly'],
        can_surrender=cfg['surrender'],
        das=cfg['das'],
        stop_loss_pct=cfg['stop_loss'],
        win_goal_pct=cfg['win_goal'],
        wong_mode=cfg.get('wong_mode', False),
    )

    HUDv4(game).run()


if __name__ == '__main__':
    main()

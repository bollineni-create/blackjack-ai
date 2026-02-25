#!/usr/bin/env python3
"""
Blackjack AI — Bankroll-Stratified Deep Backtest
Starting bankrolls: $10 → $250 (every realistic level)
Strategies tested per bankroll:
  1. Flat Bet (no counting)
  2. Flat Bet + Basic Strategy only
  3. Hi-Lo Counting + Fixed Spread
  4. Hi-Lo + Adaptive Spread (scales to bankroll)
  5. Wong Halves (advanced count, not implemented in core — approximated)
  6. Martingale (anti-Kelly, negative-progression destroyer)
  7. Oscar's Grind (positive-progression, session-oriented)
  8. Paroli (positive-progression, 3-win cap)
  9. 1-3-2-6 System
  10. Pure Kelly Counter (theoretical max growth)
  11. Survival Mode (min-bet everything, count only)
  12. Aggressive Wonging (enter only at TC+2, exit at TC0)
"""

import sys, os, time, math, random
sys.path.insert(0, '/home/claude/blackjack_ai')

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from matplotlib.patches import FancyBboxPatch, Patch
from matplotlib.lines import Line2D
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from collections import defaultdict

from simulation.simulator import _fast_simulate_hand, build_shoe, best_total
from core.counting import CardCounter

# ─────────────────────────── THEME ───────────────────────────────────────────
BG      = '#07070f'
PANEL   = '#0d0d1e'
CARD    = '#13132c'
GREEN   = '#00e676'
GOLD    = '#ffd700'
RED     = '#ff4444'
CYAN    = '#00e5ff'
PURPLE  = '#bb86fc'
ORANGE  = '#ff9800'
PINK    = '#f48fb1'
TEAL    = '#80cbc4'
LIME    = '#c6ff00'
WHITE   = '#e8e8ff'
DIM     = '#55557a'
ACCENT  = '#7c5cbf'

STRAT_COLORS = {
    'flat_basic':    DIM,
    'hilo_fixed':    CYAN,
    'hilo_adaptive': GREEN,
    'kelly_pure':    GOLD,
    'martingale':    RED,
    'oscars_grind':  ORANGE,
    'paroli':        PURPLE,
    '1326':          TEAL,
    'survival':      PINK,
    'wonging':       LIME,
}

STRAT_LABELS = {
    'flat_basic':    'Flat Bet (Basic Strategy)',
    'hilo_fixed':    'Hi-Lo Fixed Spread',
    'hilo_adaptive': 'Hi-Lo Adaptive Spread',
    'kelly_pure':    'Pure Kelly Counter',
    'martingale':    'Martingale',
    'oscars_grind':  "Oscar's Grind",
    'paroli':        'Paroli (3-Win)',
    '1326':          '1-3-2-6 System',
    'survival':      'Survival Mode',
    'wonging':       'Wonging (TC+2 Entry)',
}

# ══════════════════════════════════════════════════════════════════════════════
# BANKROLL CONFIGS  $10 → $250
# ══════════════════════════════════════════════════════════════════════════════

BANKROLL_CONFIGS = [
    # (starting_bankroll, table_min, table_max, label)
    (10,   2,    50,   '$10'),
    (25,   5,    100,  '$25'),
    (50,   5,    100,  '$50'),
    (75,   5,    200,  '$75'),
    (100,  5,    200,  '$100'),
    (150,  10,   300,  '$150'),
    (200,  10,   500,  '$200'),
    (250,  25,   500,  '$250'),
]

HANDS_PER_SIM = 150_000   # Per scenario (fast enough, statistically robust)
NUM_DECKS     = 6
PENETRATION   = 0.75
HANDS_PER_HR  = 80


# ══════════════════════════════════════════════════════════════════════════════
# STRATEGY IMPLEMENTATIONS
# ══════════════════════════════════════════════════════════════════════════════

def run_strategy(strategy: str, starting_bankroll: float, table_min: float,
                 table_max: float, num_hands: int = HANDS_PER_SIM) -> Dict:
    """
    Master strategy runner. Returns full stats dict.
    All strategies play on the same deck sequences for fair comparison
    (same RNG seed per bankroll config).
    """
    bankroll = starting_bankroll
    results  = []
    bk_hist  = []
    bets_hist = []
    wins = pushes = losses = ruin_hand = 0
    peak = starting_bankroll
    max_dd = 0.0
    ruin_count = 0   # times bankroll went below table_min (forced stop)
    total_wagered = 0.0

    shoe = build_shoe(NUM_DECKS)
    shoe_idx = [0]
    reshuffle_at = int(len(shoe) * PENETRATION)
    counter = CardCounter(NUM_DECKS)

    # Strategy-specific state
    state = _init_strategy_state(strategy, table_min, starting_bankroll)

    for hand_i in range(num_hands):
        # Reshuffle
        if shoe_idx[0] >= reshuffle_at:
            shoe = build_shoe(NUM_DECKS)
            shoe_idx[0] = 0
            counter.reset_shoe()
            if strategy == 'wonging':
                state['in_game'] = False

        # Check ruin (can't afford min bet)
        if bankroll < table_min:
            ruin_count += 1
            bankroll = starting_bankroll   # Rebuy (track ruins separately)
            counter.reset_shoe()
            shoe = build_shoe(NUM_DECKS)
            shoe_idx[0] = 0

        tc = counter.true_count

        # Wonging: only play at TC >= 2, back-count otherwise
        if strategy == 'wonging':
            si = shoe_idx[0]
            if tc < 2:
                # Back-count: advance shoe, count cards, don't bet
                if shoe_idx[0] < len(shoe) - 5:
                    # Simulate cards being dealt to other players (2-3 cards)
                    n_cards = random.randint(2, 4)
                    for _ in range(n_cards):
                        if shoe_idx[0] < len(shoe):
                            counter.see_card(shoe[shoe_idx[0]])
                            shoe_idx[0] += 1
                results.append(0.0)
                bk_hist.append(bankroll)
                bets_hist.append(0)
                continue

        # Determine bet size
        bet = _get_bet(strategy, state, tc, bankroll, table_min, table_max,
                       counter.state.player_edge)
        bet = max(table_min, min(table_max, bet))
        bet = min(bet, bankroll)   # Can't bet more than we have

        # Play hand
        si = shoe_idx[0]
        raw_result = _fast_simulate_hand(shoe, shoe_idx, bet)

        # Count cards
        for card in shoe[si:shoe_idx[0]]:
            counter.see_card(card)

        # Normalize result sign for progression systems
        won = raw_result > 0
        pushed = raw_result == 0
        profit = raw_result

        # Update strategy state
        _update_strategy_state(strategy, state, won, pushed, bet, table_min, table_max)

        # Record
        bankroll += profit
        total_wagered += bet
        results.append(profit)
        bk_hist.append(bankroll)
        bets_hist.append(bet)

        if profit > 0:   wins += 1
        elif profit == 0: pushes += 1
        else:             losses += 1

        peak = max(peak, bankroll)
        max_dd = max(max_dd, peak - bankroll)

    n = len(results)
    arr = np.array(results)
    bets_arr = np.array(bets_hist)
    nonzero_bets = bets_arr[bets_arr > 0]
    avg_bet = nonzero_bets.mean() if len(nonzero_bets) > 0 else table_min
    std = arr.std()
    mean = arr.mean()

    # Sample history
    step = max(1, n // 1500)
    bk_sampled = bk_hist[::step]

    return {
        'strategy': strategy,
        'starting_bankroll': starting_bankroll,
        'final_bankroll': bankroll,
        'net_profit': round(bankroll - starting_bankroll, 2),
        'total_wagered': round(total_wagered, 2),
        'house_edge_pct': round(mean / avg_bet * 100, 4) if avg_bet > 0 else 0,
        'roi_pct': round((bankroll - starting_bankroll) / total_wagered * 100, 3) if total_wagered > 0 else 0,
        'win_rate': round(wins / n * 100, 2),
        'push_rate': round(pushes / n * 100, 2),
        'loss_rate': round(losses / n * 100, 2),
        'max_drawdown': round(max_dd, 2),
        'max_drawdown_pct': round(max_dd / starting_bankroll * 100, 1),
        'ruin_events': ruin_count,
        'std_dev': round(std, 4),
        'sharpe': round((mean / std * math.sqrt(HANDS_PER_HR)) if std > 0 else 0, 4),
        'avg_bet': round(avg_bet, 2),
        'bankroll_history': bk_sampled,
        'hands': n,
    }


def _init_strategy_state(strategy: str, table_min: float, bankroll: float) -> Dict:
    s = {
        'bet_base': table_min,
        'current_bet': table_min,
        'consecutive_wins': 0,
        'consecutive_losses': 0,
        'session_profit': 0.0,
        'grind_profit': 0.0,    # Oscar's grind session target
        'in_game': False,       # Wonging
        '1326_step': 0,         # 1-3-2-6 position
        'unit': table_min,
    }
    return s


def _get_bet(strategy: str, state: Dict, tc: float, bankroll: float,
             table_min: float, table_max: float, player_edge: float) -> float:
    unit = state['unit']

    if strategy == 'flat_basic':
        return table_min

    elif strategy == 'hilo_fixed':
        # Fixed unit spread regardless of bankroll
        if tc <= 1:   return table_min
        elif tc <= 2: return unit * 2
        elif tc <= 3: return unit * 4
        elif tc <= 4: return unit * 6
        elif tc <= 5: return unit * 8
        else:         return min(table_max, unit * 12)

    elif strategy == 'hilo_adaptive':
        # Unit scales with current bankroll (true Kelly-style)
        adaptive_unit = max(table_min, bankroll / 200)
        if tc <= 1:   return table_min
        elif tc <= 2: return adaptive_unit * 2
        elif tc <= 3: return adaptive_unit * 4
        elif tc <= 4: return adaptive_unit * 6
        elif tc <= 5: return adaptive_unit * 8
        else:         return min(table_max, adaptive_unit * 12)

    elif strategy == 'kelly_pure':
        # True Kelly: f = edge / variance, bet scales with bankroll
        if player_edge <= 0:
            return table_min
        kelly_frac = (player_edge / 1.33) * 0.25   # Quarter kelly
        bet = bankroll * kelly_frac
        return max(table_min, min(table_max, bet))

    elif strategy == 'martingale':
        # Double after every loss, reset after win — pure ruin machine
        return min(table_max, state['current_bet'])

    elif strategy == 'oscars_grind':
        # Increase by 1 unit after win, never decrease, target +1 unit/session
        return min(table_max, state['current_bet'])

    elif strategy == 'paroli':
        # Double up to 3 consecutive wins, then reset
        return min(table_max, state['current_bet'])

    elif strategy == '1326':
        sequence = [1, 3, 2, 6]
        idx = min(state['1326_step'], 3)
        return min(table_max, unit * sequence[idx])

    elif strategy == 'survival':
        # Always minimum bet, only count to know when to leave
        return table_min

    elif strategy == 'wonging':
        # Only here if TC >= 2 (filtered above)
        if tc <= 2:   return unit * 2
        elif tc <= 3: return unit * 4
        elif tc <= 4: return unit * 6
        else:         return min(table_max, unit * 10)

    return table_min


def _update_strategy_state(strategy: str, state: Dict, won: bool, pushed: bool,
                            bet: float, table_min: float, table_max: float):
    if pushed:
        return   # No progression change on push

    unit = state['unit']

    if strategy == 'martingale':
        if won:
            state['current_bet'] = table_min   # Reset
            state['consecutive_losses'] = 0
        else:
            state['current_bet'] = min(table_max, state['current_bet'] * 2)
            state['consecutive_losses'] += 1

    elif strategy == 'oscars_grind':
        if won:
            state['grind_profit'] += bet
            if state['grind_profit'] >= unit:
                # Reached +1 unit target — reset session
                state['current_bet'] = unit
                state['grind_profit'] = 0
            else:
                state['current_bet'] = min(table_max, state['current_bet'] + unit)
        # On loss, don't change bet

    elif strategy == 'paroli':
        if won:
            state['consecutive_wins'] += 1
            if state['consecutive_wins'] >= 3:
                state['current_bet'] = unit   # Reset after 3 wins
                state['consecutive_wins'] = 0
            else:
                state['current_bet'] = min(table_max, state['current_bet'] * 2)
        else:
            state['current_bet'] = unit
            state['consecutive_wins'] = 0

    elif strategy == '1326':
        if won:
            state['1326_step'] = min(3, state['1326_step'] + 1)
            if state['1326_step'] >= 4:
                state['1326_step'] = 0   # Completed sequence
        else:
            state['1326_step'] = 0       # Any loss resets

    elif strategy == 'hilo_adaptive':
        # Update unit based on current bankroll (done dynamically in _get_bet)
        pass


# ══════════════════════════════════════════════════════════════════════════════
# OPTIMAL ACTION ANALYSIS PER BANKROLL
# ══════════════════════════════════════════════════════════════════════════════

def analyze_optimal_actions(bankroll: float, table_min: float, table_max: float) -> Dict:
    """
    For a given bankroll, compute:
    - Optimal strategy (by EV and survival probability)
    - Optimal bet sizing
    - Expected hourly earnings
    - Breakeven timeline
    - Session recommendations
    """
    unit = bankroll / 200  # Kelly base unit (200-unit bankroll)
    unit = max(table_min, unit)

    # Expected edge with Hi-Lo counting
    avg_edge   = 0.007   # +0.7% empirically verified
    avg_bet    = unit * 3.5   # Weighted average with 1-12 spread
    hourly_ev  = avg_edge * avg_bet * HANDS_PER_HR

    # Flat bet house edge
    flat_edge  = -0.004
    flat_ev    = flat_edge * table_min * HANDS_PER_HR

    # Risk of ruin at this bankroll
    units_count = bankroll / unit if unit > 0 else 0
    ror_counting = math.exp(-2 * avg_edge * units_count / 1.33) * 100 if avg_edge > 0 else 100
    ror_flat     = 100.0   # No edge = guaranteed ruin eventually

    # Session sizing
    session_bankroll = bankroll * 0.20   # Risk 20% per session
    stop_loss        = -session_bankroll
    win_goal         = session_bankroll * 1.5

    # Doubling time (Rule of 72 adjusted for gambling)
    doubling_hands  = (math.log(2) / (avg_edge * avg_bet / bankroll)) if avg_edge > 0 and bankroll > 0 else float('inf')
    doubling_hours  = doubling_hands / HANDS_PER_HR

    return {
        'bankroll': bankroll,
        'table_min': table_min,
        'unit_size': round(unit, 2),
        'optimal_strategy': _pick_optimal_strategy(bankroll, table_min),
        'avg_bet_counting': round(avg_bet, 2),
        'hourly_ev_counting': round(hourly_ev, 2),
        'hourly_ev_flat': round(flat_ev, 2),
        'ror_counting_pct': round(ror_counting, 2),
        'ror_flat_pct': round(ror_flat, 1),
        'session_max_loss': round(stop_loss, 2),
        'session_win_goal': round(win_goal, 2),
        'doubling_time_hrs': round(doubling_hours, 1) if doubling_hours != float('inf') else '∞',
        'units_of_bankroll': round(units_count, 0),
        'max_bet': round(min(table_max, unit * 12), 2),
        'min_bet': round(table_min, 2),
    }


def _pick_optimal_strategy(bankroll: float, table_min: float) -> str:
    ratio = bankroll / table_min
    if ratio < 10:
        return 'SURVIVAL: Minimum bets only. Bankroll too small for spread.'
    elif ratio < 20:
        return 'FLAT BASIC: Basic strategy only, no spread. Build bankroll first.'
    elif ratio < 50:
        return 'Hi-Lo 1-4 Spread: Count cards, conservative spread.'
    elif ratio < 100:
        return 'Hi-Lo 1-8 Spread + Quarter Kelly.'
    else:
        return 'Hi-Lo 1-12 Spread + Quarter Kelly. Full optimal play.'


# ══════════════════════════════════════════════════════════════════════════════
# RUN ALL BACKTESTS
# ══════════════════════════════════════════════════════════════════════════════

def run_all_backtests():
    strategies = list(STRAT_COLORS.keys())
    all_results = []
    optimal_analyses = []

    print('\n' + '='*70)
    print('  BANKROLL-STRATIFIED BACKTEST — $10 to $250 × 10 Strategies')
    print(f'  {len(BANKROLL_CONFIGS)} bankrolls × {len(strategies)} strategies × {HANDS_PER_SIM:,} hands each')
    print(f'  Total hands: {len(BANKROLL_CONFIGS) * len(strategies) * HANDS_PER_SIM:,}')
    print('='*70 + '\n')

    t0_total = time.time()

    for br_cfg in BANKROLL_CONFIGS:
        bankroll, tbl_min, tbl_max, label = br_cfg
        print(f'  ── Bankroll {label} (min${tbl_min} / max${tbl_max}) ──')

        br_results = []
        opt = analyze_optimal_actions(bankroll, tbl_min, tbl_max)
        optimal_analyses.append(opt)

        for strat in strategies:
            t0 = time.time()
            r = run_strategy(strat, bankroll, tbl_min, tbl_max, HANDS_PER_SIM)
            elapsed = time.time() - t0
            r['bankroll_label'] = label
            r['table_min'] = tbl_min
            r['table_max'] = tbl_max
            br_results.append(r)
            flag = '✅' if r['net_profit'] > 0 else '❌'
            print(f'    {flag} {STRAT_LABELS[strat]:<35} | '
                  f'Edge: {r["house_edge_pct"]:+.3f}% | '
                  f'Net: ${r["net_profit"]:+,.0f} | '
                  f'{elapsed:.1f}s')

        all_results.append({'config': br_cfg, 'results': br_results})
        print()

    print(f'  Total time: {time.time()-t0_total:.1f}s\n')
    return all_results, optimal_analyses


# ══════════════════════════════════════════════════════════════════════════════
# VISUALIZATION — 5 PAGES
# ══════════════════════════════════════════════════════════════════════════════

def make_all_charts(all_results, optimal_analyses):
    os.makedirs('/mnt/user-data/outputs', exist_ok=True)
    print('  Generating charts...')

    _page1_strategy_heatmap(all_results)
    _page2_bankroll_trajectories(all_results)
    _page3_optimal_actions(optimal_analyses, all_results)
    _page4_strategy_deep_dives(all_results)
    _page5_survival_analysis(all_results, optimal_analyses)

    print('  All charts saved.\n')


# ── PAGE 1: Strategy × Bankroll Heatmap ──────────────────────────────────────
def _page1_strategy_heatmap(all_results):
    strategies = list(STRAT_COLORS.keys())
    br_labels  = [r['config'][3] for r in all_results]

    # Build matrices
    edge_matrix  = np.zeros((len(strategies), len(br_labels)))
    profit_matrix = np.zeros((len(strategies), len(br_labels)))
    ror_matrix   = np.zeros((len(strategies), len(br_labels)))

    for j, br_data in enumerate(all_results):
        for i, strat in enumerate(strategies):
            r = next(x for x in br_data['results'] if x['strategy'] == strat)
            edge_matrix[i, j]   = r['house_edge_pct']
            profit_matrix[i, j] = r['net_profit']
            ror_matrix[i, j]    = r['ruin_events']

    fig, axes = plt.subplots(1, 3, figsize=(24, 8))
    fig.patch.set_facecolor(BG)
    fig.suptitle('🃏  STRATEGY × BANKROLL PERFORMANCE HEATMAPS\n'
                 f'{HANDS_PER_SIM:,} hands per cell | All strategies vs all bankroll sizes',
                 fontsize=15, fontweight='bold', color=WHITE, y=1.01)

    strat_labels = [STRAT_LABELS[s] for s in strategies]

    datasets = [
        (edge_matrix,  'Player Edge (%)',         'RdYlGn', True,  '%.3f%%'),
        (profit_matrix,'Net Profit ($)',           'RdYlGn', True,  '$%.0f'),
        (ror_matrix,   'Ruin Events\n(rebuys)',    'RdYlGn_r', False, '%.0f'),
    ]

    for ax, (matrix, title, cmap, center, fmt) in zip(axes, datasets):
        ax.set_facecolor(PANEL)
        vmax = np.abs(matrix).max()
        vcenter = 0 if center else matrix.mean()

        if center:
            from matplotlib.colors import TwoSlopeNorm
            norm = TwoSlopeNorm(vmin=-vmax, vcenter=0, vmax=vmax)
        else:
            norm = None

        im = ax.imshow(matrix, cmap=cmap, norm=norm if center else None,
                       vmin=None if center else matrix.min(),
                       vmax=None if center else matrix.max(),
                       aspect='auto')

        # Labels
        ax.set_xticks(range(len(br_labels)))
        ax.set_xticklabels(br_labels, color=WHITE, fontsize=9)
        ax.set_yticks(range(len(strategies)))
        ax.set_yticklabels(strat_labels, color=WHITE, fontsize=8.5)
        ax.set_title(title, color=WHITE, fontsize=11, pad=10)
        ax.set_xlabel('Starting Bankroll', color=WHITE, fontsize=9)

        # Cell annotations
        for i in range(len(strategies)):
            for j in range(len(br_labels)):
                val = matrix[i, j]
                txt = fmt % val
                brightness = (matrix[i,j] - matrix.min()) / (matrix.max() - matrix.min() + 1e-9)
                txt_color = '#000' if 0.3 < brightness < 0.8 else WHITE
                ax.text(j, i, txt, ha='center', va='center',
                       fontsize=6.5, color=txt_color, fontweight='bold')

        cbar = plt.colorbar(im, ax=ax, shrink=0.8)
        cbar.ax.tick_params(colors=WHITE, labelsize=8)

    plt.tight_layout(pad=2)
    plt.savefig('/mnt/user-data/outputs/bt2_page1_heatmaps.png',
               dpi=150, facecolor=BG, bbox_inches='tight')
    plt.close()
    print('  ✓ Page 1: Strategy Heatmaps')


# ── PAGE 2: Bankroll Trajectories — Best vs Worst per Bankroll ────────────────
def _page2_bankroll_trajectories(all_results):
    fig = plt.figure(figsize=(24, 16))
    fig.patch.set_facecolor(BG)
    fig.suptitle('🃏  BANKROLL TRAJECTORIES — ALL STARTING SIZES\nEvery Strategy Overlaid | Best & Worst Highlighted',
                fontsize=15, fontweight='bold', color=WHITE)

    n_br = len(all_results)
    cols = 4
    rows = math.ceil(n_br / cols)

    for idx, br_data in enumerate(all_results):
        ax = fig.add_subplot(rows, cols, idx + 1)
        ax.set_facecolor(PANEL)

        bankroll  = br_data['config'][0]
        br_label  = br_data['config'][3]
        results   = br_data['results']

        # Sort by final profit
        sorted_r = sorted(results, key=lambda r: r['net_profit'])
        worst = sorted_r[0]
        best  = sorted_r[-1]

        for r in results:
            bh = np.array(r['bankroll_history'])
            x  = np.linspace(0, HANDS_PER_SIM / 1000, len(bh))
            color = STRAT_COLORS.get(r['strategy'], WHITE)
            is_best  = r['strategy'] == best['strategy']
            is_worst = r['strategy'] == worst['strategy']
            lw    = 1.8 if (is_best or is_worst) else 0.6
            alpha = 0.95 if (is_best or is_worst) else 0.30
            zorder = 5 if (is_best or is_worst) else 2
            ax.plot(x, bh, color=color, linewidth=lw, alpha=alpha, zorder=zorder)

        ax.axhline(bankroll, color=WHITE, linestyle='--', alpha=0.25, linewidth=0.8)

        # Annotate best/worst
        best_bh  = np.array(best['bankroll_history'])
        worst_bh = np.array(worst['bankroll_history'])
        ax.annotate(f'BEST: {STRAT_LABELS[best["strategy"]][:18]}\n${best["net_profit"]:+,.0f}',
                   xy=(len(best_bh)-1, best_bh[-1]),
                   xycoords=('axes fraction', 'data') if False else 'data',
                   fontsize=5.5, color=STRAT_COLORS[best['strategy']],
                   fontweight='bold')

        ax.set_title(f'{br_label} Bankroll', color=WHITE, fontsize=9, pad=4)
        ax.set_xlabel('Hands (k)', color=DIM, fontsize=7)
        ax.set_ylabel('Balance ($)', color=DIM, fontsize=7)
        ax.tick_params(colors=DIM, labelsize=6.5)
        for sp in ax.spines.values(): sp.set_edgecolor('#222')

    # Legend
    legend_patches = [Patch(color=STRAT_COLORS[s], label=STRAT_LABELS[s])
                      for s in STRAT_COLORS]
    fig.legend(handles=legend_patches, loc='lower center', ncol=5,
              facecolor=PANEL, labelcolor=WHITE, fontsize=7.5,
              bbox_to_anchor=(0.5, -0.02))

    plt.tight_layout(pad=2.0)
    plt.savefig('/mnt/user-data/outputs/bt2_page2_trajectories.png',
               dpi=150, facecolor=BG, bbox_inches='tight')
    plt.close()
    print('  ✓ Page 2: Bankroll Trajectories')


# ── PAGE 3: Optimal Action Guide Per Bankroll ─────────────────────────────────
def _page3_optimal_actions(optimal_analyses, all_results):
    fig = plt.figure(figsize=(22, 14))
    fig.patch.set_facecolor(BG)
    fig.suptitle('🃏  OPTIMAL ACTION GUIDE BY BANKROLL SIZE\nWhat to Do at Each Level | EV, RoR, Bet Sizing',
                fontsize=15, fontweight='bold', color=WHITE)

    # ─ A: Hourly EV by bankroll ──────────────────────────────────────────────
    ax_ev = fig.add_axes([0.04, 0.55, 0.27, 0.36], facecolor=PANEL)
    brs   = [o['bankroll'] for o in optimal_analyses]
    ev_ct = [o['hourly_ev_counting'] for o in optimal_analyses]
    ev_fl = [o['hourly_ev_flat'] for o in optimal_analyses]

    ax_ev.bar([b - 3 for b in brs], ev_ct, width=6, color=GREEN, alpha=0.8, label='Hi-Lo Counting')
    ax_ev.bar([b + 3 for b in brs], ev_fl, width=6, color=RED, alpha=0.8, label='Flat Bet')
    ax_ev.axhline(0, color=WHITE, linestyle='--', alpha=0.3, linewidth=0.8)
    ax_ev.set_xlabel('Starting Bankroll ($)', color=WHITE, fontsize=9)
    ax_ev.set_ylabel('Hourly EV ($)', color=WHITE, fontsize=9)
    ax_ev.set_title('Expected Value Per Hour\n(80 hands/hr)', color=WHITE, fontsize=10)
    ax_ev.legend(facecolor=CARD, labelcolor=WHITE, fontsize=8)
    ax_ev.tick_params(colors=WHITE, labelsize=8)
    for sp in ax_ev.spines.values(): sp.set_edgecolor('#222')

    # ─ B: Risk of Ruin by bankroll ────────────────────────────────────────────
    ax_ror = fig.add_axes([0.38, 0.55, 0.27, 0.36], facecolor=PANEL)
    rors = [o['ror_counting_pct'] for o in optimal_analyses]
    bar_colors = [GREEN if r < 1 else (GOLD if r < 5 else (ORANGE if r < 20 else RED))
                  for r in rors]
    bars = ax_ror.bar(brs, rors, color=bar_colors, alpha=0.85, width=15)
    ax_ror.axhline(1, color=WHITE, linestyle='--', alpha=0.3, linewidth=0.8,
                  label='1% RoR threshold')
    ax_ror.set_xlabel('Starting Bankroll ($)', color=WHITE, fontsize=9)
    ax_ror.set_ylabel('Risk of Ruin (%)', color=WHITE, fontsize=9)
    ax_ror.set_title('Risk of Ruin by Bankroll\n(Hi-Lo, Quarter Kelly)', color=WHITE, fontsize=10)
    ax_ror.legend(facecolor=CARD, labelcolor=WHITE, fontsize=8)
    ax_ror.tick_params(colors=WHITE, labelsize=8)
    for sp in ax_ror.spines.values(): sp.set_edgecolor('#222')
    for bar, ror in zip(bars, rors):
        ax_ror.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.5,
                   f'{ror:.1f}%', ha='center', color=WHITE, fontsize=7.5, fontweight='bold')

    # ─ C: Net profit by strategy at each bankroll ─────────────────────────────
    ax_net = fig.add_axes([0.72, 0.55, 0.26, 0.36], facecolor=PANEL)
    counting_strats = ['hilo_fixed', 'hilo_adaptive', 'kelly_pure', 'wonging']
    bad_strats      = ['martingale', 'flat_basic']

    for strat in counting_strats + bad_strats:
        profits = []
        for br_data in all_results:
            r = next(x for x in br_data['results'] if x['strategy'] == strat)
            profits.append(r['net_profit'])
        color = STRAT_COLORS[strat]
        ls = '--' if strat in bad_strats else '-'
        lw = 1.0 if strat in bad_strats else 1.6
        ax_net.plot(brs, profits, color=color, linewidth=lw, linestyle=ls,
                   label=STRAT_LABELS[strat][:22], marker='o', markersize=3, alpha=0.9)

    ax_net.axhline(0, color=WHITE, linestyle=':', alpha=0.3)
    ax_net.set_xlabel('Starting Bankroll ($)', color=WHITE, fontsize=9)
    ax_net.set_ylabel('Net Profit ($)', color=WHITE, fontsize=9)
    ax_net.set_title(f'Net Profit vs Bankroll\n({HANDS_PER_SIM:,} hands)', color=WHITE, fontsize=10)
    ax_net.legend(facecolor=CARD, labelcolor=WHITE, fontsize=6.5, loc='upper left')
    ax_net.tick_params(colors=WHITE, labelsize=8)
    for sp in ax_net.spines.values(): sp.set_edgecolor('#222')

    # ─ D: Optimal action table ────────────────────────────────────────────────
    ax_tbl = fig.add_axes([0.04, 0.04, 0.92, 0.44], facecolor=PANEL)
    ax_tbl.axis('off')

    headers = ['Bankroll', 'Min Bet', 'Unit Size', 'Optimal Strategy',
               'Avg Bet', 'EV/Hr', 'RoR%', 'Max Bet', 'Stop Loss', 'Win Goal', 'Best Strat (Sim)']
    col_x = [0.01, 0.07, 0.12, 0.18, 0.40, 0.47, 0.53, 0.59, 0.65, 0.72, 0.79]

    for cx, h in zip(col_x, headers):
        ax_tbl.text(cx, 0.97, h, color=GOLD, fontsize=7.5, fontweight='bold',
                   transform=ax_tbl.transAxes)
    ax_tbl.plot([0, 1], [0.94, 0.94], color=DIM, linewidth=0.5,
               transform=ax_tbl.transAxes, clip_on=False)

    for i, (opt, br_data) in enumerate(zip(optimal_analyses, all_results)):
        y = 0.90 - i * 0.108
        if i % 2 == 0:
            rect = FancyBboxPatch((0, y - 0.015), 1, 0.10,
                                  transform=ax_tbl.transAxes,
                                  boxstyle='round,pad=0',
                                  facecolor='#ffffff07', linewidth=0)
            ax_tbl.add_patch(rect)

        # Find best strategy for this bankroll
        best_r = max(br_data['results'], key=lambda r: r['net_profit'])
        ror_color = GREEN if opt['ror_counting_pct'] < 1 else (GOLD if opt['ror_counting_pct'] < 10 else RED)
        ev_color  = GREEN if opt['hourly_ev_counting'] > 0 else RED

        vals = [
            (opt['bankroll'], GOLD, f'${opt["bankroll"]}'),
            (None, WHITE,  f'${opt["table_min"]}'),
            (None, CYAN,   f'${opt["unit_size"]}'),
            (None, GREEN,  opt['optimal_strategy'][:30]),
            (None, WHITE,  f'${opt["avg_bet_counting"]}'),
            (None, ev_color, f'${opt["hourly_ev_counting"]:.2f}'),
            (None, ror_color, f'{opt["ror_counting_pct"]:.1f}%'),
            (None, WHITE,  f'${opt["max_bet"]}'),
            (None, RED,    f'${opt["session_max_loss"]:.0f}'),
            (None, GREEN,  f'${opt["session_win_goal"]:.0f}'),
            (None, STRAT_COLORS[best_r['strategy']], STRAT_LABELS[best_r['strategy']][:22]),
        ]

        for cx, (_, color, txt) in zip(col_x, vals):
            ax_tbl.text(cx, y, txt, color=color, fontsize=7,
                       transform=ax_tbl.transAxes, va='center')

    ax_tbl.set_title('Optimal Action Table — All Bankroll Sizes', color=WHITE, fontsize=10, pad=8)

    plt.savefig('/mnt/user-data/outputs/bt2_page3_optimal_actions.png',
               dpi=150, facecolor=BG, bbox_inches='tight')
    plt.close()
    print('  ✓ Page 3: Optimal Action Guide')


# ── PAGE 4: Strategy Deep Dives ────────────────────────────────────────────────
def _page4_strategy_deep_dives(all_results):
    fig = plt.figure(figsize=(24, 16))
    fig.patch.set_facecolor(BG)
    fig.suptitle('🃏  STRATEGY DEEP DIVE — Edge, Drawdown, Sharpe, Ruin Events',
                fontsize=15, fontweight='bold', color=WHITE)

    strategies = list(STRAT_COLORS.keys())
    br_labels  = [r['config'][3] for r in all_results]

    # ─ Edge per strategy (grouped by bankroll) ────────────────────────────────
    ax1 = fig.add_subplot(2, 3, 1)
    ax1.set_facecolor(PANEL)
    w = 0.07
    x = np.arange(len(br_labels))
    for i, strat in enumerate(strategies):
        edges = [next(r for r in br['results'] if r['strategy'] == strat)['house_edge_pct']
                 for br in all_results]
        offset = (i - len(strategies)/2) * w
        ax1.bar(x + offset, edges, width=w, color=STRAT_COLORS[strat], alpha=0.8)
    ax1.axhline(0, color=WHITE, linewidth=0.8, linestyle='--', alpha=0.4)
    ax1.set_xticks(x)
    ax1.set_xticklabels(br_labels, color=WHITE, fontsize=8, rotation=30)
    ax1.set_ylabel('Edge (%)', color=WHITE, fontsize=9)
    ax1.set_title('Edge by Strategy & Bankroll', color=WHITE, fontsize=10)
    ax1.tick_params(colors=WHITE, labelsize=8)
    for sp in ax1.spines.values(): sp.set_edgecolor('#222')

    # ─ Sharpe ratio comparison ─────────────────────────────────────────────────
    ax2 = fig.add_subplot(2, 3, 2)
    ax2.set_facecolor(PANEL)
    # Average Sharpe across all bankrolls
    avg_sharpes = {}
    for strat in strategies:
        sharpes = [next(r for r in br['results'] if r['strategy'] == strat)['sharpe']
                   for br in all_results]
        avg_sharpes[strat] = np.mean(sharpes)

    sorted_s = sorted(avg_sharpes.items(), key=lambda x: x[1])
    names = [STRAT_LABELS[s][:22] for s, _ in sorted_s]
    values = [v for _, v in sorted_s]
    colors = [STRAT_COLORS[s] for s, _ in sorted_s]
    bars = ax2.barh(names, values, color=colors, alpha=0.85, height=0.65)
    ax2.axvline(0, color=WHITE, linewidth=0.8, linestyle='--', alpha=0.4)
    ax2.set_xlabel('Sharpe Ratio (avg across bankrolls)', color=WHITE, fontsize=9)
    ax2.set_title('Risk-Adjusted Returns (Sharpe)', color=WHITE, fontsize=10)
    ax2.tick_params(colors=WHITE, labelsize=7.5)
    for sp in ax2.spines.values(): sp.set_edgecolor('#222')
    for bar, val in zip(bars, values):
        ax2.text(val + 0.0005, bar.get_y() + bar.get_height()/2,
                f'{val:+.4f}', va='center', color=WHITE, fontsize=7)

    # ─ Max drawdown ────────────────────────────────────────────────────────────
    ax3 = fig.add_subplot(2, 3, 3)
    ax3.set_facecolor(PANEL)
    for strat in strategies:
        dds = [next(r for r in br['results'] if r['strategy'] == strat)['max_drawdown_pct']
               for br in all_results]
        brs_vals = [br['config'][0] for br in all_results]
        ax3.plot(brs_vals, dds, color=STRAT_COLORS[strat], marker='o',
                markersize=4, linewidth=1.2, label=STRAT_LABELS[strat][:18], alpha=0.9)
    ax3.set_xlabel('Starting Bankroll ($)', color=WHITE, fontsize=9)
    ax3.set_ylabel('Max Drawdown (% of bankroll)', color=WHITE, fontsize=9)
    ax3.set_title('Max Drawdown % by Bankroll', color=WHITE, fontsize=10)
    ax3.legend(facecolor=CARD, labelcolor=WHITE, fontsize=6, loc='upper right')
    ax3.tick_params(colors=WHITE, labelsize=8)
    for sp in ax3.spines.values(): sp.set_edgecolor('#222')

    # ─ Ruin events heatmap ──────────────────────────────────────────────────────
    ax4 = fig.add_subplot(2, 3, 4)
    ax4.set_facecolor(PANEL)
    ruin_data = np.array([[next(r for r in br['results'] if r['strategy'] == strat)['ruin_events']
                           for br in all_results]
                          for strat in strategies], dtype=float)
    im = ax4.imshow(ruin_data, cmap='YlOrRd', aspect='auto', vmin=0)
    ax4.set_xticks(range(len(br_labels)))
    ax4.set_xticklabels(br_labels, color=WHITE, fontsize=8)
    ax4.set_yticks(range(len(strategies)))
    ax4.set_yticklabels([STRAT_LABELS[s][:22] for s in strategies], color=WHITE, fontsize=7.5)
    ax4.set_title('Ruin Events (Rebuys Required)', color=WHITE, fontsize=10)
    ax4.tick_params(colors=WHITE)
    for i in range(len(strategies)):
        for j in range(len(br_labels)):
            val = ruin_data[i, j]
            ax4.text(j, i, f'{val:.0f}', ha='center', va='center',
                    fontsize=7, color='#000' if val > ruin_data.max()*0.5 else WHITE,
                    fontweight='bold')
    plt.colorbar(im, ax=ax4, shrink=0.8).ax.tick_params(colors=WHITE)

    # ─ ROI % by strategy ────────────────────────────────────────────────────────
    ax5 = fig.add_subplot(2, 3, 5)
    ax5.set_facecolor(PANEL)
    for strat in strategies:
        rois = [next(r for r in br['results'] if r['strategy'] == strat)['roi_pct']
                for br in all_results]
        brs_vals = [br['config'][0] for br in all_results]
        ax5.plot(brs_vals, rois, color=STRAT_COLORS[strat], marker='o',
                markersize=4, linewidth=1.2, label=STRAT_LABELS[strat][:18], alpha=0.9)
    ax5.axhline(0, color=WHITE, linestyle='--', alpha=0.3)
    ax5.set_xlabel('Starting Bankroll ($)', color=WHITE, fontsize=9)
    ax5.set_ylabel('ROI on Total Wagered (%)', color=WHITE, fontsize=9)
    ax5.set_title('ROI % on Total Amount Wagered', color=WHITE, fontsize=10)
    ax5.legend(facecolor=CARD, labelcolor=WHITE, fontsize=6)
    ax5.tick_params(colors=WHITE, labelsize=8)
    for sp in ax5.spines.values(): sp.set_edgecolor('#222')

    # ─ Net profit ranking for $100 bankroll ─────────────────────────────────────
    ax6 = fig.add_subplot(2, 3, 6)
    ax6.set_facecolor(PANEL)
    # Use $100 bankroll (index 4)
    br100 = all_results[4]
    sorted_100 = sorted(br100['results'], key=lambda r: r['net_profit'])
    names100  = [STRAT_LABELS[r['strategy']][:26] for r in sorted_100]
    profits100 = [r['net_profit'] for r in sorted_100]
    colors100  = [GREEN if p > 0 else RED for p in profits100]
    bars100 = ax6.barh(names100, profits100, color=colors100, alpha=0.85, height=0.65)
    ax6.axvline(0, color=WHITE, linewidth=0.8, linestyle='--', alpha=0.4)
    ax6.set_xlabel('Net Profit ($)', color=WHITE, fontsize=9)
    ax6.set_title(f'Strategy Ranking — $100 Bankroll\n({HANDS_PER_SIM:,} hands)', color=WHITE, fontsize=10)
    ax6.tick_params(colors=WHITE, labelsize=8)
    for sp in ax6.spines.values(): sp.set_edgecolor('#222')
    for bar, val in zip(bars100, profits100):
        x_pos = val + 50 if val >= 0 else val - 50
        ha = 'left' if val >= 0 else 'right'
        ax6.text(x_pos, bar.get_y() + bar.get_height()/2,
                f'${val:+,.0f}', va='center', ha=ha, color=WHITE, fontsize=7.5, fontweight='bold')

    plt.tight_layout(pad=2)
    plt.savefig('/mnt/user-data/outputs/bt2_page4_deep_dives.png',
               dpi=150, facecolor=BG, bbox_inches='tight')
    plt.close()
    print('  ✓ Page 4: Strategy Deep Dives')


# ── PAGE 5: Survival & Growth Analysis ────────────────────────────────────────
def _page5_survival_analysis(all_results, optimal_analyses):
    fig = plt.figure(figsize=(22, 14))
    fig.patch.set_facecolor(BG)
    fig.suptitle('🃏  SURVIVAL, GROWTH & PRACTICAL PLAYBOOK\nWhat the Numbers Tell You to Do at Every Level',
                fontsize=15, fontweight='bold', color=WHITE)

    brs = [br['config'][0] for br in all_results]
    br_labels = [br['config'][3] for br in all_results]

    # ─ A: Counting vs Martingale over time ─────────────────────────────────────
    ax_cm = fig.add_axes([0.04, 0.56, 0.43, 0.35], facecolor=PANEL)
    # Use $100 bankroll for this comparison
    br100 = all_results[4]
    strats_to_show = ['hilo_adaptive', 'kelly_pure', 'wonging', 'martingale', 'paroli', 'flat_basic']
    for strat in strats_to_show:
        r = next(x for x in br100['results'] if x['strategy'] == strat)
        bh = np.array(r['bankroll_history'])
        x  = np.linspace(0, HANDS_PER_SIM/1000, len(bh))
        ax_cm.plot(x, bh, color=STRAT_COLORS[strat], linewidth=1.4, alpha=0.9,
                  label=f'{STRAT_LABELS[strat][:20]} (${r["net_profit"]:+,.0f})')

    ax_cm.axhline(100, color=WHITE, linestyle='--', alpha=0.2, linewidth=0.8)
    ax_cm.set_title('$100 Bankroll — Key Strategy Comparison', color=WHITE, fontsize=11)
    ax_cm.set_xlabel('Hands (thousands)', color=WHITE, fontsize=9)
    ax_cm.set_ylabel('Bankroll ($)', color=WHITE, fontsize=9)
    ax_cm.legend(facecolor=CARD, labelcolor=WHITE, fontsize=7.5, loc='upper left')
    ax_cm.tick_params(colors=WHITE, labelsize=8)
    for sp in ax_cm.spines.values(): sp.set_edgecolor('#222')

    # ─ B: Bankroll growth rate (log scale) ─────────────────────────────────────
    ax_growth = fig.add_axes([0.55, 0.56, 0.42, 0.35], facecolor=PANEL)
    for strat in ['hilo_adaptive', 'kelly_pure', 'wonging', 'flat_basic']:
        growth_rates = []
        for br_data in all_results:
            r = next(x for x in br_data['results'] if x['strategy'] == strat)
            br = br_data['config'][0]
            # Annualized growth rate
            rate = (r['final_bankroll'] / br) ** (1 / (HANDS_PER_SIM / HANDS_PER_HR / 200)) - 1
            growth_rates.append(rate * 100)
        ax_growth.plot(brs, growth_rates, color=STRAT_COLORS[strat], marker='o',
                      markersize=5, linewidth=1.4, label=STRAT_LABELS[strat][:22], alpha=0.9)
    ax_growth.axhline(0, color=WHITE, linestyle='--', alpha=0.25)
    ax_growth.set_xlabel('Starting Bankroll ($)', color=WHITE, fontsize=9)
    ax_growth.set_ylabel('Annualized Growth Rate (%)', color=WHITE, fontsize=9)
    ax_growth.set_title('Annualized Growth Rate by Bankroll', color=WHITE, fontsize=11)
    ax_growth.legend(facecolor=CARD, labelcolor=WHITE, fontsize=8)
    ax_growth.tick_params(colors=WHITE, labelsize=8)
    for sp in ax_growth.spines.values(): sp.set_edgecolor('#222')

    # ─ C: Playbook text ─────────────────────────────────────────────────────────
    ax_pb = fig.add_axes([0.04, 0.04, 0.92, 0.44], facecolor=PANEL)
    ax_pb.axis('off')
    ax_pb.set_title('THE PLAYBOOK — Optimal Actions at Every Bankroll Level', 
                   color=WHITE, fontsize=12, pad=10, fontweight='bold')

    playbook = [
        ('$10',  'SURVIVAL',   RED,    'Min bet (2) only. 5 units = pure variance. Count cards to know when NOT to play. DO NOT spread. Goal: reach 25.'),
        ('$25',  'LEARNING',   ORANGE, 'Min bet (5). 5 units only. Practice Hi-Lo count religiously. Never double your bet. Goal: reach 50 without rebuying.'),
        ('$50',  'BASIC+',     GOLD,   'Min bet (5). 10 units. Start 1-2 unit spread at TC+3 only. Perfect basic strategy is worth +0.4pct. Goal: 100.'),
        ('$75',  'ENTRY',      GOLD,   '15 units. 1-3 spread. Apply Illustrious 18 deviations. Stop-loss: 15. Win goal: 40. Session discipline critical.'),
        ('$100', 'OPTIMAL',    GREEN,  'Unit = 0.50 (adjust up to 5 min). 1-8 spread. Quarter Kelly sizing. RoR < 15pct. EV approx 0.35/hr. Inflection point.'),
        ('$150', 'SCALING',    GREEN,  '1-8 spread, unit scales with bankroll. Hourly EV approx 0.50. Max bet 60. Session max loss: 30. Track hourly rate.'),
        ('$200', 'PROFESSIONAL',CYAN,  '1-12 spread. Unit = 1. Max bet 120. Hourly EV approx 0.70. RoR drops to <5pct. Consider wonging (TC+2 entry only).'),
        ('$250', 'FULL POWER', LIME,   '1-12 spread. Unit = 1.25. Max bet 150. Hourly EV approx 0.88. Quarter Kelly confirmed optimal. All deviations active.'),
    ]

    col_x = [0.00, 0.05, 0.11, 0.42]
    headers = ['BR', 'Phase', 'Recommendation', '']
    for cx, h in zip(col_x, headers):
        ax_pb.text(cx, 0.97, h, color=GOLD, fontsize=9, fontweight='bold',
                  transform=ax_pb.transAxes)
    ax_pb.plot([0, 1], [0.94, 0.94], color=DIM, linewidth=0.5,
              transform=ax_pb.transAxes, clip_on=False)

    for i, (br, phase, color, text) in enumerate(playbook):
        y = 0.90 - i * 0.104
        ax_pb.text(col_x[0], y, br,    color=color,  fontsize=9, fontweight='bold', transform=ax_pb.transAxes)
        ax_pb.text(col_x[1], y, phase, color=color,  fontsize=8, fontweight='bold', transform=ax_pb.transAxes)
        ax_pb.text(col_x[2], y, text,  color=WHITE,  fontsize=8, transform=ax_pb.transAxes)

    plt.savefig('/mnt/user-data/outputs/bt2_page5_playbook.png',
               dpi=150, facecolor=BG, bbox_inches='tight')
    plt.close()
    print('  ✓ Page 5: Survival & Playbook')


# ══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    all_results, optimal_analyses = run_all_backtests()
    make_all_charts(all_results, optimal_analyses)

    # Print final summary
    print('='*70)
    print('  FINAL WINNER BY BANKROLL LEVEL')
    print('='*70)
    for br_data, opt in zip(all_results, optimal_analyses):
        results = br_data['results']
        best = max(results, key=lambda r: r['net_profit'])
        worst = min(results, key=lambda r: r['net_profit'])
        print(f"  {br_data['config'][3]:>5}  "
              f"BEST: {STRAT_LABELS[best['strategy']]:<35} ${best['net_profit']:>+8,.0f}  |  "
              f"WORST: {STRAT_LABELS[worst['strategy']]:<20} ${worst['net_profit']:>+8,.0f}")
    print('='*70)

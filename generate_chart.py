#!/usr/bin/env python3
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
import os, sys

sys.path.insert(0, '/home/claude/blackjack_ai')
from simulation.simulator import run_simulation, run_count_simulation

print('Running 500k basic strategy simulation...')
basic = run_simulation(num_hands=500_000, verbose=False)
print('Running 250k card counting simulation...')
count = run_count_simulation(num_hands=250_000, verbose=False)

fig = plt.figure(figsize=(18, 12))
fig.patch.set_facecolor('#0a0a18')
BG = '#0f0f20'
GREEN  = '#00e676'
GOLD   = '#ffd700'
RED    = '#ff5252'
CYAN   = '#00e5ff'
WHITE  = '#e0e0ff'
ACCENT = '#7c5cbf'

fig.text(0.5, 0.97, '🃏  BLACKJACK AI — Monte Carlo Simulation Results', ha='center',
         fontsize=20, fontweight='bold', color=WHITE)
fig.text(0.5, 0.94, 'Perfect Basic Strategy vs Hi-Lo Card Counting | 750,000 Total Hands',
         ha='center', fontsize=12, color='#aaa')

# 1. Basic strategy bankroll
ax1 = fig.add_axes([0.04, 0.57, 0.43, 0.32], facecolor=BG)
bh = np.array(basic.bankroll_history)
x = np.linspace(0, basic.hands/1000, len(bh))
ax1.fill_between(x, bh, 0, where=bh>=0, alpha=0.25, color=GREEN)
ax1.fill_between(x, bh, 0, where=bh<0,  alpha=0.25, color=RED)
ax1.plot(x, bh, color=GREEN, linewidth=0.8)
ax1.axhline(0, color=WHITE, linestyle='--', alpha=0.3, linewidth=0.8)
ax1.set_title('Basic Strategy Bankroll ($1 flat bet)', color=WHITE, fontsize=11, pad=8)
ax1.set_xlabel('Hands (thousands)', color='#aaa', fontsize=9)
ax1.set_ylabel('Net Profit ($)', color='#aaa', fontsize=9)
ax1.tick_params(colors='#aaa', labelsize=8)
for s in ax1.spines.values(): s.set_edgecolor('#333')

# 2. Counting bankroll  
ax2 = fig.add_axes([0.53, 0.57, 0.43, 0.32], facecolor=BG)
ch = np.array(count.bankroll_history)
xc = np.linspace(0, count.hands/1000, len(ch))
ax2.fill_between(xc, ch, 0, where=ch>=0, alpha=0.25, color=GOLD)
ax2.fill_between(xc, ch, 0, where=ch<0,  alpha=0.25, color=RED)
ax2.plot(xc, ch, color=GOLD, linewidth=0.8)
ax2.axhline(0, color=WHITE, linestyle='--', alpha=0.3, linewidth=0.8)
ax2.set_title('Hi-Lo Counting (unit=$10, 1-12 bet spread)', color=WHITE, fontsize=11, pad=8)
ax2.set_xlabel('Hands (thousands)', color='#aaa', fontsize=9)
ax2.set_ylabel('Net Profit ($)', color='#aaa', fontsize=9)
ax2.tick_params(colors='#aaa', labelsize=8)
for s in ax2.spines.values(): s.set_edgecolor('#333')

# 3. Pie chart
ax3 = fig.add_axes([0.04, 0.10, 0.22, 0.38], facecolor=BG)
sizes = [basic.win_rate, basic.push_rate, basic.loss_rate]
labels = ['Win\n{:.1f}%'.format(basic.win_rate),
          'Push\n{:.1f}%'.format(basic.push_rate),
          'Loss\n{:.1f}%'.format(basic.loss_rate)]
ax3.pie(sizes, labels=labels, colors=[GREEN, GOLD, RED], startangle=90,
        textprops={'color': WHITE, 'fontsize': 9})
ax3.set_title('Outcome Distribution', color=WHITE, fontsize=10)

# 4. Histogram
ax4 = fig.add_axes([0.30, 0.10, 0.35, 0.38], facecolor=BG)
sample = np.array(basic.hand_results[::50])
ax4.hist(sample, bins=60, color=CYAN, alpha=0.75, edgecolor='none')
ax4.axvline(sample.mean(), color=RED, linestyle='--', linewidth=1.5,
            label='Mean: {:.3f}'.format(sample.mean()))
ax4.set_title('Hand P&L Distribution', color=WHITE, fontsize=11)
ax4.set_xlabel('Profit/Loss per hand ($)', color='#aaa', fontsize=9)
ax4.set_ylabel('Frequency', color='#aaa', fontsize=9)
ax4.tick_params(colors='#aaa', labelsize=8)
ax4.legend(facecolor=BG, labelcolor=WHITE, fontsize=9)
for s in ax4.spines.values(): s.set_edgecolor('#333')

# 5. Stats panel
ax5 = fig.add_axes([0.69, 0.07, 0.29, 0.44], facecolor=BG)
ax5.axis('off')

rows = [
    ('BASIC STRATEGY', '', True),
    ('House Edge',    '{:+.4f}%'.format(basic.house_edge), False),
    ('Win Rate',      '{:.2f}%'.format(basic.win_rate), False),
    ('Push Rate',     '{:.2f}%'.format(basic.push_rate), False),
    ('Loss Rate',     '{:.2f}%'.format(basic.loss_rate), False),
    ('Std Dev/hand',  '{:.4f}'.format(basic.std_deviation), False),
    ('Max Drawdown',  '${:,.0f}'.format(basic.max_drawdown), False),
    ('', '', False),
    ('HI-LO COUNTING', '', True),
    ('Counter Edge',  '{:+.4f}%'.format(count.house_edge), False),
    ('Net Profit',    '${:+,.0f}'.format(count.net_profit), False),
    ('Win Rate',      '{:.2f}%'.format(count.win_rate), False),
    ('Max Drawdown',  '${:,.0f}'.format(count.max_drawdown), False),
]

for i, item in enumerate(rows):
    label, val, is_header = item
    y = 0.96 - i * 0.070
    if is_header:
        ax5.text(0.05, y, label, color=GOLD, fontsize=9.5, fontweight='bold',
                 transform=ax5.transAxes)
    elif label:
        ax5.text(0.05, y, label, color='#bbb', fontsize=8.5, transform=ax5.transAxes)
        color = GREEN if '+' in val and val != '+0' else (RED if '-' in val else WHITE)
        ax5.text(0.95, y, val, color=color, fontsize=8.5, fontweight='bold',
                 transform=ax5.transAxes, ha='right')

ax5.set_title('Statistical Summary', color=WHITE, fontsize=11, pad=10)
for s in ax5.spines.values(): s.set_edgecolor(ACCENT)

os.makedirs('/mnt/user-data/outputs', exist_ok=True)
plt.savefig('/mnt/user-data/outputs/blackjack_simulation.png',
            dpi=150, facecolor='#0a0a18', bbox_inches='tight')
print('Chart saved successfully.')
print('House edge: {:+.4f}%'.format(basic.house_edge))
print('Counter edge: {:+.4f}%'.format(count.house_edge))
print('Counter net: ${:+,.0f}'.format(count.net_profit))

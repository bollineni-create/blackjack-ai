#!/usr/bin/env python3
"""
Session Logger — Persistent tracking across sessions.
Saves hand history, stats, and bankroll evolution to JSON.
"""

import json, os, time
from datetime import datetime
from pathlib import Path

SESSION_DIR = Path.home() / '.blackjack_ai' / 'sessions'


class SessionLogger:
    def __init__(self, bankroll: float, session_id: str = None):
        SESSION_DIR.mkdir(parents=True, exist_ok=True)
        self.session_id = session_id or datetime.now().strftime('%Y%m%d_%H%M%S')
        self.path       = SESSION_DIR / f'session_{self.session_id}.json'
        self.data       = {
            'session_id':       self.session_id,
            'start_time':       datetime.now().isoformat(),
            'start_bankroll':   bankroll,
            'end_bankroll':     bankroll,
            'hands':            [],
            'profit_curve':     [],
            'final_stats':      {},
        }

    def log_hand(self, hand_data: dict):
        self.data['hands'].append(hand_data)
        self.data['profit_curve'].append({
            'hand':   len(self.data['hands']),
            'bankroll': hand_data.get('bankroll', 0),
            'tc':     hand_data.get('tc', 0),
        })

    def close(self, game_state):
        self.data['end_time']    = datetime.now().isoformat()
        self.data['end_bankroll']= game_state.bankroll
        self.data['final_stats'] = {
            'hands_played':  game_state.hands_played,
            'net_profit':    game_state.net_profit,
            'win_rate':      game_state.session_wins / max(game_state.hands_played, 1),
            'max_profit':    game_state.peak_profit,
            'max_drawdown':  game_state.max_drawdown,
        }
        with open(self.path, 'w') as f:
            json.dump(self.data, f, indent=2)
        print(f'[Logger] Session saved: {self.path}')

    @staticmethod
    def load_all_sessions() -> list:
        sessions = []
        if SESSION_DIR.exists():
            for f in sorted(SESSION_DIR.glob('session_*.json')):
                try:
                    sessions.append(json.loads(f.read_text()))
                except Exception:
                    pass
        return sessions

    @staticmethod
    def lifetime_stats() -> dict:
        sessions = SessionLogger.load_all_sessions()
        if not sessions:
            return {}
        total_hands  = sum(len(s.get('hands', [])) for s in sessions)
        total_profit = sum(s.get('end_bankroll', 0) - s.get('start_bankroll', 0)
                          for s in sessions)
        return {
            'total_sessions': len(sessions),
            'total_hands':    total_hands,
            'total_profit':   round(total_profit, 2),
            'avg_per_session': round(total_profit / max(len(sessions), 1), 2),
            'first_session':  sessions[0].get('start_time', ''),
            'last_session':   sessions[-1].get('start_time', ''),
        }

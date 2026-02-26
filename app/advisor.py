#!/opt/homebrew/bin/python3.11
"""
Blackjack Advisor — Native Mac floating overlay
Reads screen via screencapture, calls Claude Vision, shows action.
"""
import tkinter as tk
from tkinter import font as tkfont
import subprocess, threading, time, json, urllib.request, urllib.error
import base64, os, sys, tempfile

# ── Config ─────────────────────────────────────────────────────────────────
API_KEY_FILE = os.path.expanduser("~/.bj_advisor_key")
SCAN_INTERVAL = 2  # seconds
MODEL = "claude-sonnet-4-20250514"

COLORS = {
    "HIT":       "#00e87a",
    "STAND":     "#f5c842",
    "DOUBLE":    "#00d4ff",
    "SPLIT":     "#b060ff",
    "SURRENDER": "#ff2d55",
    "WAIT":      "#3a3a55",
}
ICONS = {"HIT":"↑","STAND":"—","DOUBLE":"✦","SPLIT":"⟺","SURRENDER":"✕","WAIT":"?"}

# ── Strategy ───────────────────────────────────────────────────────────────
CARD_MAP = {'A':1,'2':2,'3':3,'4':4,'5':5,'6':6,'7':7,'8':8,'9':9,'10':10,'T':10,'J':10,'Q':10,'K':10}

def parse_card(s):
    return CARD_MAP.get((s or '').strip().upper())

def best_total(cards):
    t = sum(cards)
    if 1 in cards and t + 10 <= 21:
        t += 10
    return t

def is_soft(cards):
    return 1 in cards and sum(cards) + 10 <= 21

def dealer_idx(d):
    return {2:0,3:1,4:2,5:3,6:4,7:5,8:6,9:7,10:8,1:9}.get(min(d,10), 0)

HARD = {4:'HHHHHHHHHH',5:'HHHHHHHHHH',6:'HHHHHHHHHH',7:'HHHHHHHHHH',8:'HHHHHHHHHH',
        9:'HDDDDHHHHH',10:'DDDDDDDDHH',11:'DDDDDDDDDH',12:'HHSSSHHHHH',13:'SSSSSHHHHH',
        14:'SSSSSHHHHH',15:'SSSSSHHHRH',16:'SSSSSHHRRH',17:'SSSSSSSSSS',18:'SSSSSSSSSS',
        19:'SSSSSSSSSS',20:'SSSSSSSSSS',21:'SSSSSSSSSS'}
SOFT = {2:'HHHDDHHHHH',3:'HHHDDHHHHH',4:'HHDDDHHHHH',5:'HHDDDHHHHH',
        6:'HDDDDHHHHH',7:'SDDDDSSHHH',8:'SSSSSSSSSS',9:'SSSSSSSSSS'}
PAIRS = {1:'PPPPPPPPPP',2:'PPPPPPHHHH',3:'PPPPPPHHHH',4:'HHHPHHHHHH',
         5:'DDDDDDDDHH',6:'PPPPPHHHHH',7:'PPPPPPHHHR',8:'PPPPPPPPPP',
         9:'PPPPPSPPSS',10:'SSSSSSSSSS'}

def calc_action(p1, p2, d):
    di = dealer_idx(d)
    cards = [p1, p2]
    # Pairs
    if p1 == p2:
        row = PAIRS.get(p1, 'HHHHHHHHHH')
        if row[di] == 'P': return 'SPLIT'
    # Soft
    if is_soft(cards):
        tot = best_total(cards)
        soft_key = max(2, min(9, tot - 11))
        a = SOFT.get(soft_key, 'HHHHHHHHHH')[di]
        if a == 'D': return 'DOUBLE'
        if a == 'S': return 'STAND'
        return 'HIT'
    # Hard
    tot = best_total(cards)
    a = HARD.get(min(max(tot, 4), 21), 'HHHHHHHHHH')[di]
    if a == 'D': return 'DOUBLE'
    if a == 'S': return 'STAND'
    if a == 'R': return 'SURRENDER'
    return 'HIT'

# ── Claude Vision ──────────────────────────────────────────────────────────
def capture_screen():
    tmp = tempfile.mktemp(suffix='.jpg')
    subprocess.run(['screencapture', '-x', '-t', 'jpg', tmp], check=True)
    with open(tmp, 'rb') as f:
        data = f.read()
    os.unlink(tmp)
    return base64.b64encode(data).decode()

def call_claude(api_key, b64img):
    prompt = """This is a Bovada live blackjack screenshot. Find MY hand (player seat) and extract:
{
  "dealer": "dealer face-up card e.g. K or 7 or A",
  "p1": "my first card",
  "p2": "my second card",
  "balance": "number only e.g. 164.12",
  "bet": "number only e.g. 10"
}
Use A=Ace, K/Q/J/T for face cards, 2-9 for numbers. Return ONLY valid JSON, nothing else. If cards not visible return null for p1/p2."""

    body = json.dumps({
        "model": MODEL,
        "max_tokens": 200,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": b64img}},
                {"type": "text", "text": prompt}
            ]
        }]
    }).encode()

    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=body,
        headers={
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01"
        }
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read())

    raw = data['content'][0]['text'].strip().strip('`').strip()
    if raw.startswith('json'): raw = raw[4:]
    return json.loads(raw)

# ── App ────────────────────────────────────────────────────────────────────
class BjAdvisor:
    def __init__(self):
        self.api_key = self.load_key()
        self.auto_on = False
        self.scanning = False

        self.root = tk.Tk()
        self.root.title("BJ Advisor")
        self.root.configure(bg='#0a0a0f')
        self.root.attributes('-topmost', True)        # always on top
        self.root.attributes('-alpha', 0.95)
        self.root.overrideredirect(False)             # keep title bar for dragging
        self.root.geometry("240x320+100+100")
        self.root.resizable(False, False)

        self.build_ui()

        if not self.api_key:
            self.show_key_dialog()

    def load_key(self):
        try:
            return open(API_KEY_FILE).read().strip()
        except:
            return None

    def save_key(self, key):
        with open(API_KEY_FILE, 'w') as f:
            f.write(key)
        self.api_key = key

    def build_ui(self):
        root = self.root

        # Title bar
        top = tk.Frame(root, bg='#13131c', pady=6)
        top.pack(fill='x')
        tk.Label(top, text="♠ BJ ADVISOR", bg='#13131c', fg='#f5c842',
                 font=('Courier', 11, 'bold'), letterSpacing=3).pack(side='left', padx=10)

        btn_frame = tk.Frame(top, bg='#13131c')
        btn_frame.pack(side='right', padx=8)

        self.auto_btn = tk.Button(btn_frame, text="AUTO", bg='#1a1a26', fg='#3a3a55',
                                   font=('Courier', 9, 'bold'), relief='flat', bd=0,
                                   padx=6, pady=3, cursor='hand2', command=self.toggle_auto)
        self.auto_btn.pack(side='left', padx=2)

        tk.Button(btn_frame, text="SCAN", bg='#1a1a26', fg='#55556a',
                  font=('Courier', 9, 'bold'), relief='flat', bd=0,
                  padx=6, pady=3, cursor='hand2', command=self.do_scan).pack(side='left', padx=2)

        tk.Button(btn_frame, text="KEY", bg='#1a1a26', fg='#55556a',
                  font=('Courier', 9, 'bold'), relief='flat', bd=0,
                  padx=6, pady=3, cursor='hand2', command=self.show_key_dialog).pack(side='left', padx=2)

        # Main display
        body = tk.Frame(root, bg='#0a0a0f')
        body.pack(fill='both', expand=True, padx=10, pady=10)

        self.icon_var = tk.StringVar(value='?')
        self.icon_lbl = tk.Label(body, textvariable=self.icon_var,
                                  bg='#0a0a0f', fg='#3a3a55',
                                  font=('Courier', 48, 'bold'))
        self.icon_lbl.pack()

        self.action_var = tk.StringVar(value='WAITING')
        self.action_lbl = tk.Label(body, textvariable=self.action_var,
                                    bg='#0a0a0f', fg='#3a3a55',
                                    font=('Courier', 22, 'bold'))
        self.action_lbl.pack()

        self.cards_var = tk.StringVar(value='')
        tk.Label(body, textvariable=self.cards_var,
                 bg='#0a0a0f', fg='#3a3a55',
                 font=('Courier', 9), wraplength=200).pack(pady=(6,0))

        self.info_var = tk.StringVar(value='')
        tk.Label(body, textvariable=self.info_var,
                 bg='#0a0a0f', fg='#2a2a45',
                 font=('Courier', 9)).pack()

        self.status_var = tk.StringVar(value='Click SCAN or AUTO')
        tk.Label(body, textvariable=self.status_var,
                 bg='#0a0a0f', fg='#2a2a45',
                 font=('Courier', 8), wraplength=200).pack(pady=(6,0))

    def set_result(self, action, cards_text='', info='', status='', color=None):
        c = color or COLORS.get(action, COLORS['WAIT'])
        self.icon_var.set(ICONS.get(action, '?'))
        self.action_var.set(action)
        self.icon_lbl.config(fg=c)
        self.action_lbl.config(fg=c)
        self.cards_var.set(cards_text)
        self.info_var.set(info)
        self.status_var.set(status)
        self.root.configure(highlightbackground=c, highlightthickness=2)

    def set_waiting(self, msg=''):
        self.icon_var.set('?')
        self.action_var.set('WAITING')
        self.icon_lbl.config(fg=COLORS['WAIT'])
        self.action_lbl.config(fg=COLORS['WAIT'])
        self.cards_var.set('')
        self.info_var.set('')
        self.status_var.set(msg)

    def do_scan(self):
        if self.scanning: return
        if not self.api_key:
            self.show_key_dialog(); return
        self.scanning = True
        self.status_var.set('READING TABLE...')
        threading.Thread(target=self._scan_thread, daemon=True).start()

    def _scan_thread(self):
        try:
            b64 = capture_screen()
            data = call_claude(self.api_key, b64)

            d  = parse_card(data.get('dealer'))
            p1 = parse_card(data.get('p1'))
            p2 = parse_card(data.get('p2'))

            if not d or not p1 or not p2:
                self.root.after(0, lambda: self.set_waiting('Cards not visible yet'))
            else:
                action = calc_action(p1, p2, d)
                cards_txt = f"YOU: {data['p1']}+{data['p2']} ({best_total([p1,p2])})  DEALER: {data['dealer']}"
                info = ''
                if data.get('balance'): info += f"${float(data['balance']):,.2f}"
                if data.get('bet'):     info += f"  BET ${float(data['bet']):,.0f}"
                ts = time.strftime('%H:%M:%S')
                self.root.after(0, lambda a=action, c=cards_txt, i=info, t=ts:
                    self.set_result(a, c, i, f'✓ {t}'))
        except Exception as e:
            err = str(e)[:60]
            self.root.after(0, lambda: self.set_waiting(f'Error: {err}'))
        finally:
            self.scanning = False

    def toggle_auto(self):
        self.auto_on = not self.auto_on
        if self.auto_on:
            self.auto_btn.config(fg='#00e87a', text='AUTO ●')
            self.do_scan()
            self._auto_loop()
        else:
            self.auto_btn.config(fg='#3a3a55', text='AUTO')
            self.set_waiting('Auto-scan off')

    def _auto_loop(self):
        if not self.auto_on: return
        self.do_scan()
        self.root.after(SCAN_INTERVAL * 1000, self._auto_loop)

    def show_key_dialog(self):
        dlg = tk.Toplevel(self.root)
        dlg.title("API Key")
        dlg.configure(bg='#0a0a0f')
        dlg.geometry("340x180")
        dlg.attributes('-topmost', True)
        dlg.grab_set()

        tk.Label(dlg, text="ANTHROPIC API KEY", bg='#0a0a0f', fg='#55556a',
                 font=('Courier', 9, 'bold')).pack(pady=(16,4))

        entry = tk.Entry(dlg, bg='#1a1a26', fg='#eeeeff', insertbackground='white',
                         font=('Courier', 11), relief='flat', bd=8, width=32)
        entry.pack(padx=16, fill='x')
        if self.api_key:
            entry.insert(0, self.api_key)

        status = tk.Label(dlg, text='', bg='#0a0a0f', fg='#55556a', font=('Courier', 9))
        status.pack(pady=4)

        def save():
            k = entry.get().strip()
            if len(k) < 8:
                status.config(text='Too short', fg='#ff2d55'); return
            self.save_key(k)
            status.config(text='✓ Saved!', fg='#00e87a')
            dlg.after(800, dlg.destroy)

        tk.Button(dlg, text="SAVE KEY", bg='#f5c842', fg='#000',
                  font=('Courier', 12, 'bold'), relief='flat', padx=10, pady=8,
                  cursor='hand2', command=save).pack(fill='x', padx=16, pady=8)

    def run(self):
        self.root.mainloop()

if __name__ == '__main__':
    BjAdvisor().run()

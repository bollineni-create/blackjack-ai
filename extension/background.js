// background.js — captures screen, calls Claude Vision, returns advice

const CARD_MAP = {'A':1,'2':2,'3':3,'4':4,'5':5,'6':6,'7':7,'8':8,'9':9,'10':10,'T':10,'J':10,'Q':10,'K':10};
const parseCard = s => CARD_MAP[(s||'').trim().toUpperCase()] ?? null;
const bestTotal = cards => { let t = cards.reduce((a,b)=>a+b,0); if(cards.includes(1)&&t+10<=21) t+=10; return t; };
const isSoft = cards => cards.includes(1) && cards.reduce((a,b)=>a+b,0)+10<=21;
const dealerIdx = d => ({2:0,3:1,4:2,5:3,6:4,7:5,8:6,9:7,10:8,1:9})[Math.min(d,10)];

const HARD = {4:'HHHHHHHHHH',5:'HHHHHHHHHH',6:'HHHHHHHHHH',7:'HHHHHHHHHH',8:'HHHHHHHHHH',9:'HDDDDHHHHH',10:'DDDDDDDDHH',11:'DDDDDDDDDH',12:'HHSSSHHHHH',13:'SSSSSHHHHH',14:'SSSSSHHHHH',15:'SSSSSHHHRH',16:'SSSSSHHRRH',17:'SSSSSSSSSS',18:'SSSSSSSSSS',19:'SSSSSSSSSS',20:'SSSSSSSSSS',21:'SSSSSSSSSS'};
const SOFT = {2:'HHHDDHHHHH',3:'HHHDDHHHHH',4:'HHDDDHHHHH',5:'HHDDDHHHHH',6:'HDDDDHHHHH',7:'SDDDDSSHHH',8:'SSSSSSSSSS',9:'SSSSSSSSSS'};
const PAIRS = {1:'PPPPPPPPPP',2:'PPPPPPHHHH',3:'PPPPPPHHHH',4:'HHHPHHHHHH',5:'DDDDDDDDHH',6:'PPPPPHHHHH',7:'PPPPPPHHHR',8:'PPPPPPPPPP',9:'PPPPPSPPSS',10:'SSSSSSSSSS'};

function calcAction(p1, p2, d) {
  const di = dealerIdx(d);
  const cards = [p1, p2];
  const soft = isSoft(cards);
  const tot = bestTotal(cards);
  if (p1 === p2) { if ((PAIRS[p1]||'HHHHHHHHHH')[di]==='P') return 'SPLIT'; }
  if (soft && tot < 21) {
    const a = (SOFT[Math.max(2,Math.min(9,tot-11))]||'HHHHHHHHHH')[di];
    if(a==='D') return 'DOUBLE'; if(a==='S') return 'STAND'; return 'HIT';
  }
  const a = (HARD[Math.min(Math.max(tot,4),21)]||'HHHHHHHHHH')[di];
  if(a==='D') return 'DOUBLE'; if(a==='S') return 'STAND'; if(a==='R') return 'SURRENDER'; return 'HIT';
}

async function scanTab(tabId) {
  const { apiKey } = await chrome.storage.local.get('apiKey');
  if (!apiKey) return { error: 'NO API KEY — open extension popup and enter your Anthropic API key' };

  // Capture screenshot
  let dataUrl;
  try {
    dataUrl = await chrome.tabs.captureVisibleTab(null, { format: 'jpeg', quality: 85 });
  } catch(e) {
    return { error: 'Screenshot failed: ' + e.message };
  }

  const base64 = dataUrl.split(',')[1];

  // Call Claude Vision
  try {
    const resp = await fetch('https://api.anthropic.com/v1/messages', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'x-api-key': apiKey,
        'anthropic-version': '2023-06-01',
        'anthropic-dangerous-direct-browser-access': 'true'
      },
      body: JSON.stringify({
        model: 'claude-sonnet-4-20250514',
        max_tokens: 200,
        messages: [{
          role: 'user',
          content: [
            { type: 'image', source: { type: 'base64', media_type: 'image/jpeg', data: base64 } },
            { type: 'text', text: `This is a Bovada live blackjack screenshot. Find MY seat (player) and extract these values. Respond ONLY with JSON, no explanation:
{
  "dealer": "dealer face-up card, e.g. K or 7 or A",
  "p1": "my first card",
  "p2": "my second card", 
  "balance": "balance number only e.g. 164.12",
  "bet": "bet number only e.g. 10"
}
Use A=Ace, K/Q/J/T for face cards, 2-9 for numbers. If you can't see my cards clearly, return null for p1/p2.` }
          ]
        }]
      })
    });

    const data = await resp.json();
    if (data.error) return { error: data.error.message };

    const raw = data.content[0].text.trim().replace(/```json|```/g,'').trim();
    const parsed = JSON.parse(raw);

    const d  = parseCard(parsed.dealer);
    const p1 = parseCard(parsed.p1);
    const p2 = parseCard(parsed.p2);

    if (!d || !p1 || !p2) {
      return {
        action: null,
        dealer: parsed.dealer,
        p1: parsed.p1,
        p2: parsed.p2,
        balance: parsed.balance,
        bet: parsed.bet,
        error: 'Could not read all cards clearly'
      };
    }

    const action = calcAction(p1, p2, d);
    const cards = [p1, p2];
    const tot = bestTotal(cards);
    const soft = isSoft(cards);

    return {
      action,
      dealer: parsed.dealer,
      p1: parsed.p1,
      p2: parsed.p2,
      total: `${soft ? 'Soft ' : ''}${tot}`,
      balance: parsed.balance,
      bet: parsed.bet,
      error: null
    };

  } catch(e) {
    return { error: 'API error: ' + e.message };
  }
}

// Listen for messages from content script
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.type === 'SCAN') {
    scanTab(sender.tab.id).then(sendResponse);
    return true; // keep channel open for async
  }
});

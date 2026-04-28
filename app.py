#!/usr/bin/env python3
"""PURE QUANT - No indicators, just pure math"""
import os, sys, json, urllib.request, urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
import statistics

TOKEN = "8680074762:AAFB6QAOx6xMJytKtLWc93xUUDpExxHQ_vg"
CHAT = "8745736212"

def zscore(val, data):
    """Z-score: how many std devs from mean"""
    if len(data) < 2: return 0
    mean = statistics.mean(data)
    std = statistics.stdev(data)
    return (val - mean) / std if std else 0

def get_signal():
    try:
        # Get raw data
        url = "https://query1.finance.yahoo.com/v8/finance/chart/XAUUSD?interval=1h&range=60d"
        resp = urllib.request.urlopen(url, timeout=10).read()
        data = json.loads(resp)
        
        close = [c for c in data["chart"]["result"][0]["indicators"]["quote"][0]["close"] if c]
        
        p = close[-1]
        
        # PURE MATH SIGNALS:
        
        # 1. Z-SCORE MEAN REVERSION
        # If price > 2 std devs above mean = sell
        # If price < -2 std devs below mean = buy
        z = zscore(p, close[-100:])
        
        # 2. STATISTICAL MOMENTUM (20h return)
        ret_20 = (close[-1] / close[-20] - 1) * 100 if len(close) >= 20 else 0
        
        # 3. HISTORICAL PERCENTILE
        # Where is price in last 1000h distribution?
        pct = sum(1 for x in close[-100:] if x < p) / 100
        
        # 4. MOMENTUM REVERSAL (5h vs 20h)
        mom_5 = (close[-1] / close[-5] - 1) * 100 if len(close) >= 5 else 0
        mom_20 = (close[-1] / close[-20] - 1) * 100 if len(close) >= 20 else 0
        mom_rev = mom_5 - mom_20  # Positive = momentum slowing
        
        # 5. VOLATILITY REGIME
        vol_now = statistics.stdev(close[-20:])
        vol_past = statistics.stdev(close[-100:-20]) if len(close) >= 100 else vol_now
        vol_ratio = vol_now / vol_past if vol_past else 1
        
        # COMBINE PURE SIGNALS
        buy_score = 0
        sell_score = 0
        reasons = []
        
        # Z-Score Mean Reversion
        if z < -1.5:
            buy_score += 40
            reasons.append(f"Z={z:.1f}")
        elif z > 1.5:
            sell_score += 40
            reasons.append(f"Z={z:.1f}")
        
        # Extreme Percentile (<10% or >90%)
        if pct < 0.10:
            buy_score += 30
            reasons.append(f"P={pct*100:.0f}%")
        elif pct > 0.90:
            sell_score += 30
            reasons.append(f"P={pct*100:.0f}%")
        
        # Strong Momentum (>5% in 20h)
        if ret_20 < -5:
            buy_score += 20
            reasons.append(f"R20={ret_20:.1f}%")
        elif ret_20 > 5:
            sell_score += 20
            reasons.append(f"R20={ret_20:.1f}%")
        
        # Low Vol Regime = higher confidence
        vol_bonus = 10 if vol_ratio < 0.8 else 0
        
        # Final Decision
        total_buy = buy_score + vol_bonus
        total_sell = sell_score + vol_bonus
        
        action = "HOLD"
        conf = 30
        
        if total_buy >= 50:
            action = "BUY"
            conf = min(total_buy, 95)
        elif total_sell >= 50:
            action = "SELL"
            conf = min(total_sell, 95)
        
        # ATR for stops
        atr = statistics.stdev(close[-20:]) * 2
        
        if action == "BUY":
            sl = round(p - atr, 2)
            tp = round(p + atr * 2, 2)
        elif action == "SELL":
            sl = round(p + atr, 2)
            tp = round(p - atr * 2, 2)
        else:
            sl = tp = None
        
        return {
            "action": action,
            "price": round(p, 2),
            "zscore": round(z, 2),
            "pctile": round(pct*100, 1),
            "ret20": round(ret_20, 2),
            "momentum": round(mom_rev, 2),
            "vol": round(vol_ratio, 2),
            "confidence": conf,
            "math": reasons
        }, sl, tp
        
    except Exception as e:
        return {"error": str(e)}, None, None

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/": self.send("Quant Bot - Pure Math")
        elif self.path == "/ping": self.send("OK")
        elif self.path == "/signal": self.signal()
        else: self.send_response(404); self.end_headers()
    
    def send(self, data):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(data.encode() if isinstance(data, str) else data)
    
    def signal(self):
        r, sl, tp = get_signal()
        
        if "error" in r:
            self.send(json.dumps(r))
        else:
            # Only telegram on trade
            if r["action"] != "HOLD":
                msg = f"XAUUSD\n{r['action']}\nPrice: {r['price']}\nConf: {r['confidence']}%\n\n"
                msg += "MATH SIGNALS:\n"
                for m in r["math"]:
                    msg += f"- {m}\n"
                if sl: msg += f"\nSL: {sl}\nTP: {tp}"
                
                tg = f"https://api.telegram.org/bot{TOKEN}/sendMessage?chat_id={CHAT}&text={urllib.parse.quote(msg)}"
                try: urllib.request.urlopen(tg, timeout=5)
                except: pass
            
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(r).encode())

port = int(os.environ.get("PORT", 5000))
HTTPServer(("0.0.0.0", port), Handler).serve_forever()
# -*- coding: utf-8 -*-
"""
FaLXi TREND TERMINAL — blood-terminal-style dashboard for the validated
trend portfolio (forward test).

Same honest engine as signals.py underneath (Donchian 40 + EMA 200,
Chandelier trail, closed daily bars only). The styling mimics the
"terminal" aesthetic; every number shown is real. The neural mesh is
decorative and labeled as such — it does not trade.

Run:  py dashboard.py            (port 8765, equity $10k, risk 0.75%)
      py dashboard.py 25000 0.5
"""
import csv, datetime as dt, json, os, sys, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import numpy as np
import signals as S

PORT = 8765
CACHE_TTL = 600          # seconds; don't hammer Yahoo on every page refresh
EQUITY = float(sys.argv[1]) if len(sys.argv) > 1 else 10000.0
RISK_PCT = float(sys.argv[2]) if len(sys.argv) > 2 else 0.75

_cache = {"t": 0.0, "data": None}
_lock = threading.Lock()

def build_state():
    today_utc = dt.datetime.now(dt.timezone.utc).date()
    risk_amt = EQUITY * RISK_PCT / 100.0
    out = {"updated": dt.datetime.now().strftime("%d/%m/%Y %H:%M"),
           "equity": EQUITY, "risk_pct": RISK_PCT, "instruments": [], "actions": []}

    for name, (symbol, dec) in S.UNIVERSE.items():
        try:
            rows = S.fetch_daily(symbol)
        except Exception as e:
            out["instruments"].append({"name": name, "symbol": symbol, "error": str(e)})
            continue
        if dt.datetime.fromtimestamp(rows[-1][0], dt.timezone.utc).date() >= today_utc:
            rows = rows[:-1]        # today's bar is still forming — closed bars only
        ts = np.array([r[0] for r in rows])
        o, h, l, c = (np.array([r[k] for r in rows]) for k in (1, 2, 3, 4))
        pos, last_atr, last_trend, last_close, last_ts = S.replay(ts, o, h, l, c, **S.PARAMS)
        bar_date = str(dt.datetime.fromtimestamp(int(last_ts), dt.timezone.utc).date())

        inst = {"name": name, "symbol": symbol, "dec": dec, "bar_date": bar_date,
                "close": last_close, "ema200": last_trend, "atr": last_atr,
                "trend": "up" if last_close > last_trend else "down",
                "ohlc": [[float(o[i]), float(h[i]), float(l[i]), float(c[i])]
                         for i in range(max(0, len(c) - 42), len(c))]}
        if pos is None:
            inst["state"] = "flat"
            S.log_state(bar_date, name, "flat", last_close, None)
        else:
            side = "long" if pos["dir"] == 1 else "short"
            inst["state"] = side
            inst["entry"] = pos["entry"]
            inst["entry_date"] = str(dt.datetime.fromtimestamp(int(pos["entry_ts"]),
                                                               dt.timezone.utc).date())
            inst["stop"] = pos["stop"]
            inst["new_signal"] = bool(pos["new"])
            upnl_r = pos["dir"] * (last_close - pos["entry"]) / pos["risk_dist"]
            inst["upnl_r"] = upnl_r
            inst["upnl_usd"] = risk_amt * upnl_r
            if pos["new"]:
                dist = S.PARAMS["stop_mult"] * last_atr
                inst["qty"] = risk_amt / dist
                out["actions"].append({"kind": "enter", "name": name, "side": side,
                                       "price": last_close, "stop": pos["stop"],
                                       "qty": inst["qty"]})
                S.log_state(bar_date, name, f"enter_{side}", last_close, pos["stop"])
            else:
                out["actions"].append({"kind": "trail", "name": name, "side": side,
                                       "stop": pos["stop"]})
                S.log_state(bar_date, name, side, last_close, pos["stop"])
        out["instruments"].append(inst)

    log = []
    if os.path.exists(S.LOG_FILE):
        with open(S.LOG_FILE, encoding="utf-8") as f:
            log = list(csv.DictReader(f))
    out["log"] = log[-60:]
    return out

def get_state():
    import time
    with _lock:
        if _cache["data"] is None or time.time() - _cache["t"] > CACHE_TTL:
            _cache["data"] = build_state()
            _cache["t"] = time.time()
        return _cache["data"]

PAGE = """<!DOCTYPE html>
<html lang="en" dir="ltr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>FaLXi // TREND TERMINAL</title>
<style>
 :root{--bg:#070404;--panel:#0d0606;--edge:#3a0d10;--edge2:#5c1218;
   --red:#ff2b3a;--red2:#ff5a4d;--dim:#8a4a4a;--dim2:#5a2e2e;--txt:#f2c9c4;
   --amber:#ffb03a;--grn:#37e07a}
 *{box-sizing:border-box;margin:0;padding:0}
 body{background:var(--bg);color:var(--txt);
   font:13px/1.45 "JetBrains Mono","Cascadia Mono",Consolas,monospace;
   padding:14px;letter-spacing:.02em}
 body::after{content:"";position:fixed;inset:0;pointer-events:none;
   background:repeating-linear-gradient(0deg,transparent 0 2px,rgba(0,0,0,.18) 2px 4px)}
 .glow{text-shadow:0 0 8px rgba(255,43,58,.65)}
 /* top bar */
 .top{display:flex;align-items:center;gap:14px;flex-wrap:wrap;
   border:1px solid var(--edge2);background:var(--panel);padding:8px 14px;margin-bottom:10px}
 .brand{color:var(--red);font-weight:700;font-size:15px}
 .brand small{color:var(--dim);font-weight:400}
 .live{color:var(--red);font-weight:700;animation:blink 1.1s infinite}
 @keyframes blink{50%{opacity:.25}}
 .chip{color:var(--dim);font-size:11.5px}
 .chip b{color:var(--txt)}
 .upd{margin-left:auto;color:var(--dim);font-size:11px}
 /* grid */
 .g{display:grid;gap:10px}
 .r1{grid-template-columns:1.1fr 1.6fr;margin-bottom:10px}
 .r2{grid-template-columns:repeat(4,1fr);margin-bottom:10px}
 .r3{grid-template-columns:1fr 1.4fr}
 @media(max-width:1000px){.r1,.r2,.r3{grid-template-columns:1fr}}
 .p{border:1px solid var(--edge);background:var(--panel);padding:10px 12px;position:relative}
 .p h3{font-size:10.5px;color:var(--dim);font-weight:700;letter-spacing:.14em;
   text-transform:uppercase;margin-bottom:8px;border-bottom:1px solid var(--edge);padding-bottom:5px}
 .p h3 .tag{float:right;color:var(--dim2);font-size:9px}
 /* pnl */
 .pnl{font-size:44px;font-weight:800;color:var(--red);line-height:1.1}
 .pnl.pos{color:var(--grn);text-shadow:0 0 10px rgba(55,224,122,.5)}
 .pnl-sub{color:var(--dim);font-size:10.5px;margin-top:2px}
 .kv{display:flex;justify-content:space-between;font-size:12px;margin-top:6px}
 .kv .k{color:var(--dim)}
 .warnline{margin-top:10px;border:1px dashed var(--edge2);color:var(--amber);
   padding:6px 8px;font-size:10.5px;direction:rtl;text-align:right}
 /* positions table */
 table{width:100%;border-collapse:collapse;font-size:11.5px}
 th{color:var(--dim2);text-align:left;font-weight:700;letter-spacing:.1em;
   font-size:9.5px;text-transform:uppercase;padding:3px 6px;border-bottom:1px solid var(--edge)}
 td{padding:4px 6px;border-bottom:1px solid #1c0a0c;color:var(--txt)}
 .red{color:var(--red)} .grn{color:var(--grn)} .dim{color:var(--dim)}
 /* instrument cards */
 .head{display:flex;justify-content:space-between;align-items:baseline}
 .head .nm{color:var(--red);font-weight:700}
 .head .st{font-size:10px;font-weight:700;letter-spacing:.1em}
 .st.short{color:var(--red)} .st.long{color:var(--grn)} .st.flat{color:var(--dim2)}
 .st.new{color:var(--amber);animation:blink .9s infinite}
 .big{font-size:20px;font-weight:700;margin:2px 0 4px}
 svg.cndl{width:100%;height:74px;display:block;margin:4px 0}
 canvas#mesh{width:100%;height:100%;display:block}
 .meshwrap{min-height:190px}
 /* pipeline */
 .flow{display:flex;align-items:center;gap:6px;flex-wrap:wrap;padding:6px 0}
 .node{border:1px solid var(--edge2);color:var(--red2);padding:5px 10px;
   font-size:10px;letter-spacing:.08em;background:#120708;white-space:nowrap}
 .arrow{color:var(--dim2)}
 /* log stream */
 .stream{max-height:230px;overflow-y:auto;font-size:11px}
 .stream div{padding:2px 0;border-bottom:1px solid #170a0b}
 .stream .t{color:var(--dim2)} .stream .i{color:var(--red2);font-weight:700}
 .loading{color:var(--dim);padding:50px;text-align:center;font-size:14px}
</style></head><body>

<div class="top">
 <span class="brand glow">FaLXi <small>//</small> TREND TERMINAL</span>
 <span class="live">&#9679; LIVE</span>
 <span id="chips"></span>
 <span class="upd" id="upd">connecting…</span>
</div>

<div id="root" class="loading">PULLING MARKET DATA…</div>

<script>
const F=(v,d)=>v==null?"—":Number(v).toLocaleString("en-US",{minimumFractionDigits:d,maximumFractionDigits:d});
const SIDE={long:"LONG",short:"SHORT",flat:"FLAT"};

function candles(ohlc){
 if(!ohlc||ohlc.length<2)return"";
 const W=250,H=74,n=ohlc.length,bw=W/n;
 let mn=1e18,mx=-1e18;
 for(const b of ohlc){mn=Math.min(mn,b[2]);mx=Math.max(mx,b[1]);}
 const y=v=>H-3-(v-mn)/(mx-mn||1)*(H-6);
 let s="";
 ohlc.forEach((b,i)=>{const[o,h,l,c]=b,x=i*bw+bw/2,up=c>=o,col=up?"#7e2a2f":"#ff2b3a";
  s+=`<line x1="${x.toFixed(1)}" y1="${y(h).toFixed(1)}" x2="${x.toFixed(1)}" y2="${y(l).toFixed(1)}" stroke="${col}" stroke-width="1"/>`;
  const t=Math.min(y(o),y(c)),hh=Math.max(1,Math.abs(y(o)-y(c)));
  s+=`<rect x="${(x-bw*.32).toFixed(1)}" y="${t.toFixed(1)}" width="${(bw*.64).toFixed(1)}" height="${hh.toFixed(1)}" fill="${up?"#170a0b":"#ff2b3a"}" stroke="${col}" stroke-width=".7"/>`});
 return `<svg class="cndl" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none">${s}</svg>`;
}

function mesh(){
 const cv=document.getElementById("mesh");if(!cv)return;
 const ctx=cv.getContext("2d"),W=cv.width=cv.offsetWidth,H=cv.height=cv.offsetHeight;
 const layers=[4,7,7,5,2],nodes=[];
 layers.forEach((n,li)=>{for(let i=0;i<n;i++)
   nodes.push({x:30+li*(W-60)/(layers.length-1),y:H*(i+1)/(n+1),l:li,p:Math.random()*6.28});});
 function draw(t){
  ctx.clearRect(0,0,W,H);
  for(const a of nodes)for(const b of nodes)if(b.l===a.l+1){
   const w=.5+.5*Math.sin(t/900+a.p+b.p);
   ctx.strokeStyle=`rgba(255,43,58,${(0.05+0.22*w).toFixed(3)})`;
   ctx.lineWidth=w>.8?1.1:.5;
   ctx.beginPath();ctx.moveTo(a.x,a.y);ctx.lineTo(b.x,b.y);ctx.stroke();}
  for(const n of nodes){const g=.6+.4*Math.sin(t/700+n.p);
   ctx.fillStyle=`rgba(255,80,80,${g.toFixed(2)})`;
   ctx.beginPath();ctx.arc(n.x,n.y,2.1,0,6.29);ctx.fill();}
  requestAnimationFrame(draw);}
 requestAnimationFrame(draw);
}

async function load(){
 const d=await(await fetch("/api/state")).json();
 document.getElementById("upd").textContent="UPD "+d.updated+" | EQ $"+F(d.equity,0)+" | RISK "+d.risk_pct+"%";
 document.getElementById("chips").innerHTML=d.instruments.filter(i=>!i.error)
  .map(i=>`<span class="chip">${i.name} SPOT <b>$${F(i.close,i.dec)}</b>&nbsp;&nbsp;</span>`).join("");

 const open=d.instruments.filter(i=>i.state&&i.state!=="flat");
 const pnl=open.reduce((s,i)=>s+(i.upnl_usd||0),0);

 let h='<div class="g r1">';
 // ---- session pnl + open positions ----
 h+=`<div class="p"><h3>OPEN P&L · COMPOUNDING <span class="tag">THEORETICAL / DEMO</span></h3>
   <div class="pnl ${pnl>=0?"pos":""}">${pnl>=0?"+":"−"}$${F(Math.abs(pnl),2)}</div>
   <div class="pnl-sub">unrealized, bot-tracked positions only · risk $${F(d.equity*d.risk_pct/100,0)}/trade</div>
   <div class="kv"><span class="k">EQUITY</span><span>$${F(d.equity,0)}</span></div>
   <div class="kv"><span class="k">OPEN POSITIONS</span><span>${open.length} / ${d.instruments.length}</span></div>
   <div class="kv"><span class="k">ENGINE</span><span>DONCHIAN-40 × EMA-200 · D1</span></div>
   <div class="warnline">⚠ מצב דמו/יומן. הפוזיציות תיאורטיות — נכנסים רק לסיגנל חדש (NEW), לא לאמצע עסקה.</div>
  </div>`;
 // ---- mesh ----
 h+=`<div class="p meshwrap"><h3>CONVERGENCE MESH · PIPELINE <span class="tag">DECORATIVE — DOES NOT TRADE</span></h3>
   <canvas id="mesh" style="height:150px"></canvas>
   <div class="flow"><span class="node">DATA FEED D1</span><span class="arrow">►</span>
    <span class="node">DONCHIAN 40</span><span class="arrow">►</span>
    <span class="node">EMA-200 FILTER</span><span class="arrow">►</span>
    <span class="node">RISK ${d.risk_pct}% · 2×ATR</span><span class="arrow">►</span>
    <span class="node">EXEC / TRAIL 3×ATR</span></div></div>`;
 h+='</div>';

 // ---- instrument panels ----
 h+='<div class="g r2">';
 for(const it of d.instruments){
  if(it.error){h+=`<div class="p"><h3>${it.name}</h3><div class="red">DATA ERROR</div><div class="dim" style="font-size:10px">${it.error}</div></div>`;continue}
  const st=it.new_signal?"new":it.state;
  h+=`<div class="p"><div class="head"><span class="nm glow">${it.name}</span>
    <span class="st ${st}">${it.new_signal?"★ NEW "+SIDE[it.state]:SIDE[it.state]}${it.entry_date?" · "+it.entry_date.slice(5):""}</span></div>
   <div class="big">$${F(it.close,it.dec)} <span style="font-size:10px" class="${it.trend==="up"?"grn":"red"}">${it.trend==="up"?"▲":"▼"} EMA200 ${F(it.ema200,it.dec)}</span></div>
   ${candles(it.ohlc)}
   ${it.state!=="flat"?`
    <div class="kv"><span class="k">ENTRY</span><span>${F(it.entry,it.dec)}</span></div>
    <div class="kv"><span class="k">TRAIL STOP</span><span class="red">${F(it.stop,it.dec)}</span></div>
    <div class="kv"><span class="k">UPNL</span><span class="${it.upnl_usd>=0?"grn":"red"}">${it.upnl_usd>=0?"+":"−"}$${F(Math.abs(it.upnl_usd),0)} · ${F(it.upnl_r,2)}R</span></div>`
   :`<div class="kv"><span class="k">STATUS</span><span class="dim">AWAITING BREAKOUT</span></div>
    <div class="kv"><span class="k">ATR-14</span><span>${F(it.atr,it.dec)}</span></div>`}
   ${it.new_signal?`<div class="kv"><span class="k">SIZE</span><span class="grn">${F(it.qty,4)} u</span></div>`:""}
  </div>`}
 h+='</div>';

 // ---- actions + log stream ----
 h+='<div class="g r3">';
 h+='<div class="p"><h3>OPERATOR QUEUE · TODAY</h3><table><tr><th>CMD</th><th>ASSET</th><th>DETAIL</th></tr>';
 h+=d.actions.length?d.actions.map(a=>a.kind==="enter"
  ?`<tr><td class="grn">ENTER ★</td><td class="red">${a.name}</td><td>${SIDE[a.side]} @ ~${F(a.price,2)} · SL ${F(a.stop,2)} · ${F(a.qty,4)}u</td></tr>`
  :`<tr><td class="dim">TRAIL</td><td class="red">${a.name}</td><td>hold ${SIDE[a.side]} · stop → ${F(a.stop,2)}</td></tr>`).join("")
  :'<tr><td class="dim" colspan="3">NO OPS — ALL FLAT / NO CHANGE</td></tr>';
 h+='</table></div>';
 h+='<div class="p"><h3>TRADE LOG · LIVE STREAM <span class="tag">forward_log.csv</span></h3><div class="stream">';
 h+=d.log.slice().reverse().map(r=>
  `<div><span class="t">${r.date}</span> <span class="i">${r.instrument.padEnd(8," ")}</span> ${r.state.toUpperCase()} <span class="dim">close</span> ${r.close}${r.stop?` <span class="dim">stop</span> <span class="red">${r.stop}</span>`:""}</div>`).join("");
 h+='</div></div></div>';

 document.getElementById("root").className="";
 document.getElementById("root").innerHTML=h;
 mesh();
}
load(); setInterval(load, 10*60*1000);
</script></body></html>"""

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/api/state"):
            try:
                body = json.dumps(get_state()).encode("utf-8")
                self._send(200, "application/json", body)
            except Exception as e:
                self._send(500, "application/json",
                           json.dumps({"error": str(e)}).encode("utf-8"))
        elif self.path == "/" or self.path.startswith("/index"):
            self._send(200, "text/html; charset=utf-8", PAGE.encode("utf-8"))
        else:
            self._send(404, "text/plain", b"not found")

    def _send(self, code, ctype, body):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        sys.stderr.write(f"{self.address_string()} - {fmt % args}\n")

if __name__ == "__main__":
    print(f"FaLXi TREND TERMINAL on http://localhost:{PORT}  "
          f"(equity ${EQUITY:,.0f}, risk {RISK_PCT}%)")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()

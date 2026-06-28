#!/usr/bin/env python3
"""
generate_dashboard.py v11 
- Self-contained: builds full HTML inline, no template file needed
- 60/30/15 day sections — past 15 days revealed, 15-30 collapsed, 30-60 collapsed
- Auto-deletes records older than 60 days with disclaimer
- Reads data/rtr_followup_tracker.csv → writes dashboard.html
"""
import csv, json, os, re
from datetime import datetime, date, timedelta

BASE_DIR       = os.path.dirname(os.path.abspath(__file__))
CSV_FILE       = os.path.join(BASE_DIR, "data", "rtr_followup_tracker.csv")
DASHBOARD_FILE = os.path.join(BASE_DIR, "dashboard.html")

# ── Load CSV ──────────────────────────────────────────────────────
rows = []
auto_deleted = 0
cutoff_60 = (date.today() - timedelta(days=60)).isoformat()
cutoff_30 = (date.today() - timedelta(days=30)).isoformat()
cutoff_15 = (date.today() - timedelta(days=15)).isoformat()

if os.path.exists(CSV_FILE):
    with open(CSV_FILE, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("status","").lower() == "deleted":
                continue
            det = (row.get("detected_at","") or "")[:10]
            if det and det < cutoff_60:
                auto_deleted += 1
                continue  # auto-remove older than 60 days
            rows.append(row)

print(f"[Dashboard] {len(rows)} records loaded ({auto_deleted} auto-removed >60 days)")
updated = datetime.now().strftime("%b %d, %Y %I:%M %p UTC")

# ── Convert to JS objects ─────────────────────────────────────────
js_rows = []
for r in rows:
    cat = r.get("category","")
    if cat == "reply_needed":
        cat = "reply"
    js_rows.append({
        "id":   abs(hash(r.get("notes","") + r.get("detected_at",""))),
        "cat":  cat,
        "acc":  r.get("account",""),
        "subj": r.get("subject","")[:200],
        "role": r.get("role","")[:100],
        "co":   r.get("company","")[:80],
        "rec":  r.get("recruiter_name","")[:80],
        "em":   r.get("sender_email", r.get("sender",""))[:120],
        "ph":   (r.get("phones","").split(";")[0] if r.get("phones") else "").strip(),
        "loc":  r.get("location_type",""),
        "rate": r.get("rate",""),
        "sk":   r.get("skills","")[:250],
        "det":  r.get("detected_at",""),
        "fup":  r.get("followup_due",""),
        "st":   r.get("status","open"),
    })

rows_json   = json.dumps(js_rows, ensure_ascii=False)
cutoff_vars = json.dumps({
    "d60": cutoff_60,
    "d30": cutoff_30,
    "d15": cutoff_15,
    "auto_deleted": auto_deleted,
})

# ── Build full HTML ───────────────────────────────────────────────
html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1">
<title>Job Campaign HQ</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@tabler/icons-webfont@3.19.0/dist/tabler-icons.min.css">
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
:root{{
  --bg:#f4f6f9;--surf:#fff;--card2:#f8f9fb;
  --border:#e4e8ef;--border2:#d0d7e3;
  --text:#1a2035;--muted:#6b7a99;--hint:#9aa4bc;
  --font:'Inter',-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
  --rtr:#d97706;--rtr-bg:#fffbeb;--rtr-b:#fde68a;--rtr-dot:#f59e0b;
  --rep:#dc2626;--rep-bg:#fef2f2;--rep-b:#fecaca;--rep-dot:#f87171;
  --out:#1d6fc4;--out-bg:#eff6ff;--out-b:#bfdbfe;--out-dot:#3b82f6;
  --int:#16a34a;--int-bg:#f0fdf4;--int-b:#bbf7d0;--int-dot:#22c55e;
  --ass:#7c3aed;--ass-bg:#f5f3ff;--ass-b:#ddd6fe;--ass-dot:#8b5cf6;
  --fol:#0369a1;--fol-bg:#f0f9ff;--fol-b:#bae6fd;--fol-dot:#38bdf8;
}}
body{{background:var(--bg);color:var(--text);font-family:var(--font);min-height:100vh;overflow-x:hidden;font-size:14px}}

/* HEADER */
.hdr{{background:var(--surf);border-bottom:1px solid var(--border);padding:14px 16px 11px;position:sticky;top:0;z-index:100;box-shadow:0 1px 4px rgba(0,0,0,.06)}}
.hdr-top{{display:flex;align-items:center;justify-content:space-between}}
.hdr h1{{font-size:17px;font-weight:700;letter-spacing:-.2px}}
.hdr h1 em{{font-style:normal;color:var(--out)}}
.upd{{font-size:11px;color:var(--muted);margin-top:2px}}
.search{{display:flex;align-items:center;gap:8px;margin-top:10px;background:var(--bg);border:1px solid var(--border2);border-radius:10px;padding:8px 12px;transition:.15s}}
.search:focus-within{{border-color:#93c5fd;box-shadow:0 0 0 3px rgba(59,130,246,.1)}}
.search input{{flex:1;background:none;border:none;color:var(--text);font-size:13px;font-family:var(--font);outline:none}}
.search input::placeholder{{color:var(--hint)}}

/* TABS */
.tab-wrap{{background:var(--surf);border-bottom:1px solid var(--border)}}
.tabs{{display:flex;gap:5px;padding:8px 14px;overflow-x:auto;scrollbar-width:none}}
.tabs::-webkit-scrollbar{{display:none}}
.tab{{flex-shrink:0;padding:6px 13px;border-radius:20px;font-size:11px;font-weight:600;cursor:pointer;border:1px solid var(--border);background:var(--bg);color:var(--muted);transition:all .15s;white-space:nowrap;user-select:none}}
.tab.a-all  {{background:#dbeafe;border-color:#93c5fd;color:#1e40af}}
.tab.a-rtr  {{background:var(--rtr-bg);border-color:var(--rtr-b);color:var(--rtr)}}
.tab.a-rep  {{background:var(--rep-bg);border-color:var(--rep-b);color:var(--rep)}}
.tab.a-out  {{background:var(--out-bg);border-color:var(--out-b);color:var(--out)}}
.tab.a-int  {{background:var(--int-bg);border-color:var(--int-b);color:var(--int)}}
.tab.a-ass  {{background:var(--ass-bg);border-color:var(--ass-b);color:var(--ass)}}
.tab.a-fol  {{background:var(--fol-bg);border-color:var(--fol-b);color:var(--fol)}}
.tab.a-co   {{background:#f8f9fb;border-color:var(--border2);color:var(--text)}}
.tab.a-cal  {{background:#fdf2f8;border-color:#f9a8d4;color:#9d174d}}

/* CAT-CAL ROW */
.cat-cal-row{{display:none;gap:5px;padding:5px 14px 7px;overflow-x:auto;scrollbar-width:none;border-top:1px solid var(--border)}}
.cat-cal-row::-webkit-scrollbar{{display:none}}
.cat-cal-row.show{{display:flex}}

/* STATS */
.stats{{display:grid;grid-template-columns:repeat(2,1fr);gap:8px;padding:13px}}
@media(min-width:600px){{.stats{{grid-template-columns:repeat(4,1fr)}}}}
.stat{{border-radius:14px;padding:14px 13px;cursor:pointer;border:1px solid;transition:transform .13s,box-shadow .13s;position:relative}}
.stat:hover{{transform:translateY(-2px);box-shadow:0 4px 16px rgba(0,0,0,.1)}}
.stat:active{{transform:scale(.97)}}
.stat::after{{content:'›';position:absolute;top:11px;right:12px;font-size:18px;opacity:.5}}
.stat .num{{font-size:38px;font-weight:700;line-height:1;letter-spacing:-1px}}
.stat .lbl{{font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.6px;margin-top:5px;opacity:.85}}
.stat .hint2{{font-size:10px;margin-top:2px;opacity:.6}}
.s-rtr  {{background:var(--rtr-bg);border-color:var(--rtr-b);color:var(--rtr)}}
.s-rep  {{background:var(--rep-bg);border-color:var(--rep-b);color:var(--rep)}}
.s-out  {{background:var(--out-bg);border-color:var(--out-b);color:var(--out)}}
.s-int  {{background:var(--int-bg);border-color:var(--int-b);color:var(--int)}}

/* DISCLAIMER */
.disclaimer{{margin:10px 14px;padding:10px 14px;background:#fffbeb;border:1px solid #fde68a;border-radius:10px;font-size:11px;color:#92400e;display:none}}
.disclaimer.show{{display:block}}

/* SECTION BANDS */
.section-band{{margin:0 14px 6px;border-radius:10px;overflow:hidden;border:1px solid var(--border)}}
.band-hdr{{display:flex;align-items:center;justify-content:space-between;padding:10px 14px;cursor:pointer;user-select:none;transition:background .12s}}
.band-hdr:hover{{background:var(--card2)}}
.band-hdr h3{{font-size:12px;font-weight:700;display:flex;align-items:center;gap:8px}}
.band-hdr .bcnt{{font-size:10px;font-weight:600;padding:2px 8px;border-radius:10px;background:var(--border);color:var(--muted)}}
.band-hdr .chev{{font-size:16px;color:var(--hint);transition:transform .2s}}
.band-hdr.open .chev{{transform:rotate(180deg)}}
.band-body{{display:none}}
.band-body.open{{display:block}}

/* TABLE */
.tbl-wrap{{overflow-x:auto;-webkit-overflow-scrolling:touch}}
.tbl{{width:100%;border-collapse:collapse;min-width:620px}}
.tbl thead th{{padding:9px 13px;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.5px;color:var(--muted);text-align:left;background:#f8f9fb;border-bottom:1px solid var(--border);white-space:nowrap}}
.tbl tbody tr{{border-bottom:1px solid var(--border);cursor:pointer;transition:background .1s}}
.tbl tbody tr:nth-child(4n+1){{background:#fff}}
.tbl tbody tr:nth-child(4n+3){{background:#f8f9fb}}
.tbl tbody tr.exp-row{{background:#f0f4ff!important;cursor:default}}
.tbl tbody tr:hover:not(.exp-row){{background:#eff6ff!important}}
.tbl tbody tr.sel{{background:#e0eeff!important;border-left:3px solid #3b82f6}}
.tbl td{{padding:14px 13px;vertical-align:top;font-size:12px;line-height:1.5;color:var(--text)}}
.badge{{display:inline-flex;align-items:center;gap:3px;padding:3px 8px;border-radius:6px;font-size:10px;font-weight:700;border:1px solid;white-space:nowrap}}
.b-rtr{{background:var(--rtr-bg);border-color:var(--rtr-b);color:var(--rtr)}}
.b-rep{{background:var(--rep-bg);border-color:var(--rep-b);color:var(--rep)}}
.b-out{{background:var(--out-bg);border-color:var(--out-b);color:var(--out)}}
.b-int{{background:var(--int-bg);border-color:var(--int-b);color:var(--int)}}
.b-ass{{background:var(--ass-bg);border-color:var(--ass-b);color:var(--ass)}}
.b-fol{{background:var(--fol-bg);border-color:var(--fol-b);color:var(--fol)}}
.pill{{display:inline-flex;align-items:center;padding:2px 6px;border-radius:4px;font-size:10px;font-weight:600;border:1px solid;margin-right:3px;margin-top:3px}}
.p-remote{{background:var(--out-bg);border-color:var(--out-b);color:var(--out)}}
.p-hybrid{{background:var(--rtr-bg);border-color:var(--rtr-b);color:var(--rtr)}}
.p-rate{{background:var(--int-bg);border-color:var(--int-b);color:var(--int)}}
.role-title{{font-weight:600;font-size:13px;line-height:1.3;margin-bottom:2px}}
.role-co{{font-size:11px;color:var(--muted)}}
.rec-name{{font-weight:600;font-size:12px;margin-bottom:1px}}
.rec-email{{font-size:11px;color:var(--out);word-break:break-all}}
.rec-phone{{font-size:11px;color:var(--int);margin-top:2px}}
.rec-date{{font-size:10px;color:var(--hint);margin-top:3px}}
.det-sm{{font-size:11px;color:var(--muted);margin-bottom:2px;display:flex;gap:6px;line-height:1.4}}
.det-sm strong{{color:var(--text);min-width:40px;flex-shrink:0;font-weight:600}}
.fup{{display:inline-block;font-size:10px;font-weight:700;padding:3px 7px;border-radius:5px;background:#f8f9fb;border:1px solid var(--border2);color:var(--muted)}}
.fup.ov{{background:var(--rep-bg);border-color:var(--rep-b);color:var(--rep)}}
.fup.td{{background:var(--rtr-bg);border-color:var(--rtr-b);color:var(--rtr)}}
.row-acts{{display:flex;gap:5px;margin-top:8px;flex-wrap:wrap}}
.ra{{padding:4px 9px;border-radius:6px;font-size:10px;font-weight:700;cursor:pointer;border:1px solid;transition:.12s;background:none;text-decoration:none;display:inline-flex;align-items:center;gap:3px;font-family:var(--font)}}
.ra:active{{transform:scale(.95)}}
.ra-c{{border-color:var(--int-b);color:var(--int);background:var(--int-bg)}}
.ra-e{{border-color:var(--out-b);color:var(--out);background:var(--out-bg)}}
.ra-d{{border-color:var(--rep-b);color:var(--rep);background:var(--rep-bg)}}
.exp-inner{{padding:12px 14px;background:#f0f4ff;border-top:1px solid #c7d9f8}}
.exp-inner .dl{{font-size:11px;color:var(--muted);margin-bottom:5px;display:flex;gap:8px;line-height:1.5}}
.exp-inner .dl b{{color:var(--text);min-width:50px;flex-shrink:0;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.3px;padding-top:1px}}

/* CALENDAR */
.cal-chrome{{padding:12px 14px 0}}
.cal-nav-row{{display:flex;align-items:center;justify-content:space-between;margin-bottom:10px}}
.cal-nav-row h2{{font-size:14px;font-weight:700}}
.cal-btn{{background:var(--surf);border:1px solid var(--border2);border-radius:9px;padding:6px 12px;font-size:11px;font-weight:600;cursor:pointer;color:var(--muted);transition:.13s}}
.cal-btn:hover{{border-color:#93c5fd;color:var(--out)}}
.cal-btn.today{{background:#eff6ff;border-color:#93c5fd;color:#1d6fc4}}
.month-box{{background:var(--surf);border:1px solid var(--border);border-radius:14px;padding:10px;margin-bottom:8px}}
.mo-grid{{display:grid;grid-template-columns:repeat(7,1fr);gap:2px}}
.dow{{font-size:9px;font-weight:700;text-align:center;color:var(--hint);text-transform:uppercase;padding-bottom:4px}}
.cd{{min-height:52px;border-radius:9px;border:1px solid transparent;background:var(--bg);padding:4px;cursor:pointer;transition:.12s}}
.cd:hover{{border-color:#93c5fd;background:#eff6ff}}
.cd.today{{border-color:#3b82f6;background:#eff6ff}}
.cd.sel{{border-color:#1d6fc4;background:#dbeafe}}
.cd.empty{{background:transparent;border-color:transparent;cursor:default}}
.cd-n{{font-size:10px;font-weight:600;color:var(--muted);text-align:center}}
.cd.today .cd-n{{color:#1d4ed8;font-weight:800}}
.cd.sel .cd-n{{color:#1d6fc4;font-weight:800}}
.cd-dots{{display:flex;flex-wrap:wrap;gap:1px;justify-content:center;margin-top:2px}}
.dot{{width:6px;height:6px;border-radius:50%}}
.cd-cnt{{font-size:8px;color:var(--hint);text-align:center;margin-top:1px}}
.day-strip{{display:flex;gap:5px;overflow-x:auto;padding:0 14px 6px;scrollbar-width:none;-webkit-overflow-scrolling:touch}}
.day-strip::-webkit-scrollbar{{display:none}}
.ds{{flex-shrink:0;width:48px;text-align:center;padding:7px 4px;border-radius:12px;cursor:pointer;border:1px solid var(--border);background:var(--surf);transition:.12s}}
.ds:hover{{border-color:#93c5fd;background:#eff6ff}}
.ds.sel{{background:#1d6fc4;border-color:#1d6fc4;color:#fff}}
.ds.tod{{border-color:#3b82f6}}
.ds-dow{{font-size:9px;font-weight:700;text-transform:uppercase;letter-spacing:.3px;opacity:.7}}
.ds-d{{font-size:17px;font-weight:700;line-height:1;margin:2px 0}}
.ds-dots{{display:flex;justify-content:center;gap:2px;margin-top:2px;min-height:7px}}
.ds-dot{{width:5px;height:5px;border-radius:50%}}
.day-tl{{padding:0 14px 80px}}
.day-hdr{{display:flex;align-items:center;justify-content:space-between;padding:8px 0 10px}}
.day-hdr h3{{font-size:14px;font-weight:700}}
.day-cnt{{font-size:11px;color:var(--muted);background:var(--bg);border:1px solid var(--border2);border-radius:20px;padding:3px 10px}}
.allday-wrap{{margin-bottom:10px}}
.allday-lbl{{font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.4px;color:var(--hint);margin-bottom:4px}}
.allday-ev{{border-radius:9px;border-left:3px solid transparent;padding:8px 11px;margin-bottom:4px;cursor:pointer;display:flex;align-items:center;gap:8px}}
.timeline{{position:relative}}
.ts{{display:flex;gap:8px;min-height:56px;position:relative}}
.tl-lbl{{width:40px;flex-shrink:0;font-size:9px;font-weight:600;color:var(--hint);text-align:right;margin-top:-5px;line-height:1}}
.tl-line{{position:absolute;left:48px;right:0;top:0;border-top:1px solid var(--border);pointer-events:none}}
.tl-evs{{flex:1;padding:0 0 4px;min-height:44px;position:relative}}
.ev{{border-radius:9px;border-left:3px solid transparent;padding:8px 11px;margin-bottom:5px;cursor:pointer;transition:transform .1s}}
.ev:hover{{transform:translateX(2px)}}
.ev-cat{{font-size:9px;font-weight:700;text-transform:uppercase;letter-spacing:.3px;margin-bottom:2px;opacity:.8}}
.ev-title{{font-size:12px;font-weight:600;line-height:1.35;margin-bottom:2px}}
.ev-meta{{font-size:10px;opacity:.7;line-height:1.4}}
.ev-pills{{display:flex;gap:3px;margin-top:4px;flex-wrap:wrap}}
.ep{{font-size:9px;font-weight:700;padding:2px 6px;border-radius:4px;border:1px solid}}
.now-line{{position:absolute;left:48px;right:0;pointer-events:none;z-index:5}}
.now-line::after{{content:'';position:absolute;left:0;right:0;top:-0.5px;height:2px;background:#dc2626}}
.now-dot{{position:absolute;left:-5px;top:-4px;width:9px;height:9px;border-radius:50%;background:#dc2626}}
.now-badge{{position:absolute;left:-46px;top:-9px;font-size:8px;font-weight:700;color:#dc2626;white-space:nowrap}}
.no-evs{{text-align:center;padding:32px 16px;color:var(--hint)}}
.no-evs i{{font-size:32px;display:block;margin-bottom:10px;opacity:.35}}

/* COMPANIES */
.co-card{{background:var(--surf);border:1px solid var(--border);border-radius:14px;margin:0 14px 8px;overflow:hidden}}
.co-hdr{{display:flex;align-items:center;gap:11px;padding:13px 14px;cursor:pointer;transition:.12s}}
.co-hdr:hover{{background:var(--bg)}}
.co-icon{{width:40px;height:40px;border-radius:10px;background:var(--out-bg);display:flex;align-items:center;justify-content:center;font-size:20px;flex-shrink:0;border:1px solid var(--out-b)}}
.co-events{{border-top:1px solid var(--border);display:none}}
.co-events.open{{display:block}}
.co-ev{{display:flex;gap:9px;padding:9px 13px;border-bottom:1px solid var(--border);align-items:flex-start}}
.co-ev:last-child{{border:none}}

/* MODAL */
.overlay{{position:fixed;inset:0;background:rgba(15,23,42,.5);z-index:200;opacity:0;pointer-events:none;transition:.2s;backdrop-filter:blur(3px)}}
.overlay.open{{opacity:1;pointer-events:all}}
.modal{{position:fixed;bottom:0;left:0;right:0;background:var(--surf);border-radius:18px 18px 0 0;border-top:1px solid var(--border);max-height:92vh;overflow-y:auto;z-index:201;transform:translateY(100%);transition:transform .3s cubic-bezier(.4,0,.2,1);box-shadow:0 -8px 32px rgba(0,0,0,.12)}}
.modal.open{{transform:translateY(0)}}
.modal-handle{{width:36px;height:4px;background:var(--border2);border-radius:2px;margin:12px auto 0}}
.modal-hdr{{padding:14px 20px 10px;border-bottom:1px solid var(--border);background:#f8f9fb}}
.modal-hdr h2{{font-size:14px;font-weight:700}}
.modal-body{{padding:16px 20px}}
.field{{margin-bottom:13px}}
.field label{{display:block;font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px;font-weight:700}}
.field input,.field select,.field textarea{{width:100%;background:var(--bg);border:1px solid var(--border2);border-radius:9px;padding:9px 12px;color:var(--text);font-size:13px;font-family:var(--font);outline:none;transition:.15s}}
.field input:focus,.field select:focus,.field textarea:focus{{border-color:#3b82f6;box-shadow:0 0 0 3px rgba(59,130,246,.1)}}
.field textarea{{min-height:65px;resize:vertical;line-height:1.5}}
.modal-acts{{display:flex;gap:9px;padding:4px 20px 46px}}
.mbtn{{flex:1;padding:12px;border-radius:10px;font-size:13px;font-weight:700;cursor:pointer;border:none;transition:.15s;font-family:var(--font)}}
.mbtn.save{{background:#1d6fc4;color:#fff}}
.mbtn.cancel{{background:var(--bg);color:var(--muted);border:1px solid var(--border2)}}
.toast{{position:fixed;bottom:80px;left:50%;transform:translateX(-50%) translateY(18px);background:var(--text);color:#fff;border-radius:12px;padding:10px 18px;font-size:12px;font-weight:600;z-index:300;opacity:0;transition:.25s;pointer-events:none;white-space:nowrap;box-shadow:0 4px 14px rgba(0,0,0,.2)}}
.toast.show{{opacity:1;transform:translateX(-50%) translateY(0)}}
.fab{{position:fixed;bottom:20px;right:16px;width:50px;height:50px;background:#1d6fc4;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:24px;cursor:pointer;z-index:150;box-shadow:0 4px 16px rgba(29,111,196,.4);border:none;color:#fff}}
.fab:active{{transform:scale(.92)}}
.empty{{text-align:center;padding:40px 20px;color:var(--muted)}}
.empty i{{font-size:36px;display:block;margin-bottom:10px;opacity:.35}}
.list-wrap{{padding:0 0 90px}}
.list-hdr{{display:flex;align-items:center;justify-content:space-between;padding:12px 14px 8px}}
.list-hdr h2{{font-size:14px;font-weight:700}}
.sort-btn{{background:var(--surf);border:1px solid var(--border2);border-radius:9px;padding:6px 12px;font-size:11px;font-weight:600;cursor:pointer;color:var(--muted)}}
</style>
</head>
<body>

<div class="hdr">
  <div class="hdr-top">
    <div>
      <h1>Job Campaign <em>HQ</em></h1>
      <div class="upd">Updated {updated} · auto-refresh 15 min</div>
    </div>
    <i class="ti ti-chart-bar" style="font-size:22px;color:var(--muted)"></i>
  </div>
  <div class="search">
    <i class="ti ti-search" style="color:var(--hint);font-size:15px"></i>
    <input type="text" id="srch" placeholder="Search role, recruiter, company, email…" oninput="doSearch()">
    <span id="clrBtn" onclick="clearSrch()" style="cursor:pointer;font-size:11px;color:var(--hint);display:none">✕</span>
  </div>
</div>

<div class="tab-wrap">
  <div class="tabs" id="topTabs">
    <div class="tab a-all" id="t-all" onclick="setTab('all')">All</div>
    <div class="tab" id="t-cal" onclick="setTab('cal')">📅 Calendar</div>
    <div class="tab" id="t-rtr" onclick="setTab('rtr')">📋 RTR</div>
    <div class="tab" id="t-rep" onclick="setTab('rep')">⚡ Reply Needed</div>
    <div class="tab" id="t-out" onclick="setTab('out')">🌐 Remote</div>
    <div class="tab" id="t-int" onclick="setTab('int')">📞 Interviews</div>
    <div class="tab" id="t-ass" onclick="setTab('ass')">🧪 Assessments</div>
    <div class="tab" id="t-fol" onclick="setTab('fol')">⏳ Follow-ups</div>
    <div class="tab" id="t-co" onclick="setTab('co')">🏢 Companies</div>
  </div>
  <div class="cat-cal-row" id="catCalRow">
    <div class="tab a-all" id="cc-all" onclick="setCal('all')">All together</div>
    <div class="tab" id="cc-rtr" onclick="setCal('rtr')">📋 RTR</div>
    <div class="tab" id="cc-rep" onclick="setCal('reply')">⚡ Reply Needed</div>
    <div class="tab" id="cc-out" onclick="setCal('outreach')">🌐 Remote</div>
    <div class="tab" id="cc-int" onclick="setCal('interview')">📞 Interviews</div>
    <div class="tab" id="cc-ass" onclick="setCal('assessment')">🧪 Assessments</div>
    <div class="tab" id="cc-fol" onclick="setCal('followup')">⏳ Follow-ups</div>
  </div>
</div>

<!-- DISCLAIMER -->
<div class="disclaimer" id="disclaimer">
  ℹ️ <strong>Auto-cleanup:</strong> Records older than 60 days are automatically removed to keep the dashboard fast.
  {auto_deleted} record(s) were removed this run. All data is preserved in <code>data/rtr_followup_tracker.csv</code> in your repo.
</div>

<!-- STATS VIEW -->
<div id="vStats">
  <div class="stats">
    <div class="stat s-rtr" onclick="setTab('rtr')"><div class="num" id="n-rtr">0</div><div class="lbl">📋 RTRs</div><div class="hint2">Tap to view →</div></div>
    <div class="stat s-rep" onclick="setTab('rep')"><div class="num" id="n-rep">0</div><div class="lbl">⚡ Reply Needed</div><div class="hint2">Act now →</div></div>
    <div class="stat s-out" onclick="setTab('out')"><div class="num" id="n-out">0</div><div class="lbl">🌐 Remote Roles</div><div class="hint2">Tap to view →</div></div>
    <div class="stat s-int" onclick="setTab('int')"><div class="num" id="n-int">0</div><div class="lbl">📞 Interviews</div><div class="hint2">Tap to view →</div></div>
  </div>
</div>

<!-- CALENDAR VIEW -->
<div id="vCal" style="display:none">
  <div class="cal-chrome">
    <div class="cal-nav-row">
      <button class="cal-btn" onclick="calPrev()"><i class="ti ti-arrow-left"></i></button>
      <h2 id="calLbl"></h2>
      <div style="display:flex;gap:5px">
        <button class="cal-btn today" onclick="goToday()">Today</button>
        <button class="cal-btn" onclick="calNext()"><i class="ti ti-arrow-right"></i></button>
      </div>
    </div>
    <div class="month-box"><div id="moGrid" class="mo-grid"></div></div>
  </div>
  <div class="day-strip" id="dayStrip"></div>
  <div class="day-tl">
    <div class="day-hdr"><h3 id="dayHdrLbl">Today</h3><span class="day-cnt" id="dayCnt">0 events</span></div>
    <div class="allday-wrap" id="alldayWrap" style="display:none">
      <div class="allday-lbl">Follow-ups due</div>
      <div id="alldayBody"></div>
    </div>
    <div class="timeline" id="timeline"></div>
  </div>
</div>

<!-- LIST VIEW (with time-banded sections) -->
<div id="vList" style="display:none">
  <div class="list-wrap">
    <div class="list-hdr">
      <h2 id="lstTitle">All Activity</h2>
      <button class="sort-btn" id="sortB" onclick="toggleSort()">↓ Newest</button>
    </div>

    <!-- LAST 15 DAYS — open by default -->
    <div class="section-band" id="band15">
      <div class="band-hdr open" onclick="toggleBand('band15')">
        <h3><span style="width:10px;height:10px;border-radius:50%;background:#22c55e;display:inline-block"></span> Last 15 days <span class="bcnt" id="cnt15">0</span></h3>
        <i class="ti ti-chevron-up chev"></i>
      </div>
      <div class="band-body open" id="body15">
        <div class="tbl-wrap"><table class="tbl"><thead><tr><th style="width:100px">Category</th><th style="min-width:160px">Role</th><th style="min-width:140px">Recruiter</th><th style="min-width:160px">Details</th><th style="width:85px">Follow-up</th></tr></thead><tbody id="tbody15"></tbody></table></div>
        <div id="empty15" class="empty" style="display:none"><i class="ti ti-inbox"></i><p>No activity in last 15 days</p></div>
      </div>
    </div>

    <!-- 15–30 DAYS — collapsed by default -->
    <div class="section-band" id="band30" style="margin-top:8px">
      <div class="band-hdr" onclick="toggleBand('band30')">
        <h3><span style="width:10px;height:10px;border-radius:50%;background:#f59e0b;display:inline-block"></span> 15 – 30 days ago <span class="bcnt" id="cnt30">0</span></h3>
        <i class="ti ti-chevron-down chev"></i>
      </div>
      <div class="band-body" id="body30">
        <div class="tbl-wrap"><table class="tbl"><thead><tr><th style="width:100px">Category</th><th style="min-width:160px">Role</th><th style="min-width:140px">Recruiter</th><th style="min-width:160px">Details</th><th style="width:85px">Follow-up</th></tr></thead><tbody id="tbody30"></tbody></table></div>
        <div id="empty30" class="empty" style="display:none"><i class="ti ti-inbox"></i><p>No activity in this range</p></div>
      </div>
    </div>

    <!-- 30–60 DAYS — collapsed by default -->
    <div class="section-band" id="band60" style="margin-top:8px">
      <div class="band-hdr" onclick="toggleBand('band60')">
        <h3><span style="width:10px;height:10px;border-radius:50%;background:#6b7a99;display:inline-block"></span> 30 – 60 days ago <span class="bcnt" id="cnt60">0</span></h3>
        <i class="ti ti-chevron-down chev"></i>
      </div>
      <div class="band-body" id="body60">
        <div class="tbl-wrap"><table class="tbl"><thead><tr><th style="width:100px">Category</th><th style="min-width:160px">Role</th><th style="min-width:140px">Recruiter</th><th style="min-width:160px">Details</th><th style="width:85px">Follow-up</th></tr></thead><tbody id="tbody60"></tbody></table></div>
        <div id="empty60" class="empty" style="display:none"><i class="ti ti-inbox"></i><p>No activity in this range</p></div>
      </div>
    </div>

    <div style="height:80px"></div>
  </div>
</div>

<!-- COMPANIES VIEW -->
<div id="vCo" style="display:none;padding:12px 0 90px"><div id="coBody"></div></div>

<!-- MODAL -->
<div class="overlay" id="overlay" onclick="closeModal()"></div>
<div class="modal" id="modal">
  <div class="modal-handle"></div>
  <div class="modal-hdr"><h2 id="mTitle">Edit entry</h2></div>
  <div class="modal-body" id="mBody"></div>
  <div class="modal-acts">
    <button class="mbtn cancel" onclick="closeModal()">Cancel</button>
    <button class="mbtn save" onclick="saveEdit()">💾 Save</button>
  </div>
</div>
<div class="toast" id="toast"></div>
<button class="fab" onclick="openAddModal()">＋</button>

<script>
const TODAY = new Date().toISOString().slice(0,10);
const CUTS  = {cutoff_vars};
let DATA = {rows_json};

const C = {{
  rtr:       {{lbl:'RTR',         cls:'b-rtr', col:'var(--rtr)',  bg:'var(--rtr-bg)', b:'var(--rtr-b)',  dot:'var(--rtr-dot)'}},
  reply:     {{lbl:'Reply Now',   cls:'b-rep', col:'var(--rep)',  bg:'var(--rep-bg)', b:'var(--rep-b)',  dot:'var(--rep-dot)'}},
  outreach:  {{lbl:'Remote Role', cls:'b-out', col:'var(--out)',  bg:'var(--out-bg)', b:'var(--out-b)',  dot:'var(--out-dot)'}},
  interview: {{lbl:'Interview',   cls:'b-int', col:'var(--int)',  bg:'var(--int-bg)', b:'var(--int-b)',  dot:'var(--int-dot)'}},
  assessment:{{lbl:'Assessment',  cls:'b-ass', col:'var(--ass)',  bg:'var(--ass-bg)', b:'var(--ass-b)',  dot:'var(--ass-dot)'}},
  followup:  {{lbl:'Follow-up',   cls:'b-fol', col:'var(--fol)',  bg:'var(--fol-bg)', b:'var(--fol-b)',  dot:'var(--fol-dot)'}},
}};
function Cg(c){{return C[c]||{{lbl:c,cls:'',col:'var(--muted)',bg:'var(--bg)',b:'var(--border2)',dot:'var(--hint)'}};}}

const MO=['January','February','March','April','May','June','July','August','September','October','November','December'];
const DW=['Su','Mo','Tu','We','Th','Fr','Sa'];
const DWF=['Sun','Mon','Tue','Wed','Thu','Fri','Sat'];
const TAB2CAT={{rtr:'rtr',rep:'reply',out:'outreach',int:'interview',ass:'assessment',fol:'followup'}};
const TAB_CLS={{all:'a-all',cal:'a-cal',rtr:'a-rtr',rep:'a-rep',out:'a-out',int:'a-int',ass:'a-ass',fol:'a-fol',co:'a-co'}};
const CC_CLS={{all:'a-all',rtr:'a-rtr',reply:'a-rep',outreach:'a-out',interview:'a-int',assessment:'a-ass',followup:'a-fol'}};

let curTab='all', calMode='all', sortAsc=false;
let calY=new Date().getFullYear(), calM=new Date().getMonth(), selDay=TODAY;
let editIdx=null, openRow=null, toastT=null;

// Show disclaimer if records were auto-deleted
if(CUTS.auto_deleted > 0) document.getElementById('disclaimer').classList.add('show');

function updateStats(){{
  const a=DATA.filter(r=>r.st!=='deleted');
  document.getElementById('n-rtr').textContent=a.filter(r=>r.cat==='rtr').length;
  document.getElementById('n-rep').textContent=a.filter(r=>r.cat==='reply').length;
  document.getElementById('n-out').textContent=a.filter(r=>r.cat==='outreach').length;
  document.getElementById('n-int').textContent=a.filter(r=>r.cat==='interview').length;
}}

function setTab(t){{
  curTab=t;
  document.querySelectorAll('#topTabs .tab').forEach(el=>el.className='tab');
  const el=document.getElementById('t-'+t); if(el) el.className='tab '+(TAB_CLS[t]||'a-all');
  const isCal=t==='cal', isCo=t==='co', isAll=t==='all';
  document.getElementById('catCalRow').classList.toggle('show', isCal);
  document.getElementById('vStats').style.display=isAll?'block':'none';
  document.getElementById('disclaimer').style.display=isAll?'':'none';
  document.getElementById('vCal').style.display=isCal?'block':'none';
  document.getElementById('vList').style.display=(!isCal&&!isCo&&!isAll)?'block':'none';
  document.getElementById('vCo').style.display=isCo?'block':'none';
  const tl=document.getElementById('lstTitle');
  if(tl) tl.textContent={{rtr:'RTR Submissions',rep:'⚡ Reply Needed — Act Now',out:'Remote Roles',int:'Interviews',ass:'Assessments',fol:'Follow-ups'}}[t]||t;
  if(isCal){{renderMo();renderStrip();renderTL();}}
  else if(isCo) renderCo();
  else if(!isAll) renderBands();
}}

function setCal(cc){{
  calMode=cc;
  document.querySelectorAll('#catCalRow .tab').forEach(el=>el.className='tab');
  const ccId={{all:'cc-all',rtr:'cc-rtr',reply:'cc-rep',outreach:'cc-out',interview:'cc-int',assessment:'cc-ass',followup:'cc-fol'}}[cc]||'cc-all';
  const el=document.getElementById(ccId); if(el) el.className='tab '+(CC_CLS[cc]||'a-all');
  renderMo(); renderStrip(); renderTL();
}}

function calFilter(){{return calMode==='all'?null:calMode;}}

function getFiltered(catOverride){{
  const q=(document.getElementById('srch').value||'').toLowerCase();
  const cf=catOverride!==undefined?catOverride:TAB2CAT[curTab]||null;
  return DATA.filter(r=>{{
    if(r.st==='deleted') return false;
    if(cf&&r.cat!==cf) return false;
    if(q&&!JSON.stringify(r).toLowerCase().includes(q)) return false;
    return true;
  }}).sort((a,b)=>sortAsc?(a.det||'').localeCompare(b.det||''):(b.det||'').localeCompare(a.det||''));
}}

function e(s){{return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');}}

function renderBands(){{
  const all=getFiltered();
  const b15=all.filter(r=>(r.det||'').slice(0,10)>=CUTS.d15);
  const b30=all.filter(r=>(r.det||'').slice(0,10)>=CUTS.d30&&(r.det||'').slice(0,10)<CUTS.d15);
  const b60=all.filter(r=>(r.det||'').slice(0,10)>=CUTS.d60&&(r.det||'').slice(0,10)<CUTS.d30);
  document.getElementById('cnt15').textContent=b15.length;
  document.getElementById('cnt30').textContent=b30.length;
  document.getElementById('cnt60').textContent=b60.length;
  renderBandRows('tbody15','empty15',b15);
  renderBandRows('tbody30','empty30',b30);
  renderBandRows('tbody60','empty60',b60);
}}

function renderBandRows(tbodyId, emptyId, rows){{
  const tbody=document.getElementById(tbodyId);
  const empty=document.getElementById(emptyId);
  if(!rows.length){{tbody.innerHTML='';empty.style.display='block';return;}}
  empty.style.display='none';
  tbody.innerHTML=rows.map(r=>buildRow(r)).join('');
}}

function buildRow(r){{
  const c=Cg(r.cat);
  const ov=r.fup&&r.fup<TODAY, td=r.fup===TODAY;
  const fc=ov?'fup ov':td?'fup td':'fup';
  const ft=r.fup?(ov?'⚠ ':'🔔 ')+r.fup:'—';
  const locP=r.loc==='remote'?'<span class="pill p-remote">🌐 Remote</span>':r.loc==='hybrid'?'<span class="pill p-hybrid">🔀 Hybrid</span>':'';
  const rateP=r.rate?`<span class="pill p-rate">💰 ${{e(r.rate)}}</span>`:'';
  const callBtn=r.ph?`<a href="tel:${{e(r.ph)}}" class="ra ra-c" onclick="event.stopPropagation()"><i class="ti ti-phone"></i></a>`:'';
  const idx=DATA.indexOf(r);
  return `<tr onclick="toggleRow(${{r.id}},this,'${{r.id}}')" id="tr${{r.id}}">
    <td><span class="badge ${{c.cls}}">${{e(c.lbl)}}</span><div style="font-size:10px;color:var(--muted);margin-top:4px">${{e(r.acc)}}</div></td>
    <td>
      <div class="role-title">${{e(r.role||r.subj.slice(0,60))}}</div>
      <div class="role-co">${{e(r.co||'')}}</div>
      <div style="margin-top:4px">${{locP}}${{rateP}}</div>
      <div class="row-acts">${{callBtn}}<button class="ra ra-e" onclick="event.stopPropagation();openEditModal(${{idx}})"><i class="ti ti-edit"></i></button><button class="ra ra-d" onclick="event.stopPropagation();deleteItem(${{idx}})"><i class="ti ti-trash"></i></button></div>
    </td>
    <td>
      <div class="rec-name">${{e(r.rec||'—')}}</div>
      <div class="rec-email">${{e(r.em||'')}}</div>
      ${{r.ph?`<div class="rec-phone"><i class="ti ti-phone" style="font-size:10px"></i> ${{e(r.ph)}}</div>`:''}}
      <div class="rec-date">${{e((r.det||'').slice(0,10))}}</div>
    </td>
    <td>
      ${{r.co?`<div class="det-sm"><strong>Client</strong>${{e(r.co)}}</div>`:''}}
      ${{r.sk?`<div class="det-sm"><strong>Skills</strong><span style="color:var(--muted)">${{e(r.sk.slice(0,90))}}</span></div>`:''}}
    </td>
    <td><div class="${{fc}}">${{e(ft)}}</div></td>
  </tr>
  <tr class="exp-row" id="exp${{r.id}}" style="display:none">
    <td colspan="5" style="padding:0">
      <div class="exp-inner">
        <div class="dl"><b>Subject</b><span>${{e(r.subj)}}</span></div>
        ${{r.sk?`<div class="dl"><b>Skills</b>${{e(r.sk)}}</div>`:''}}
        ${{r.rate?`<div class="dl"><b>Rate</b><span style="color:var(--int)">${{e(r.rate)}}</span></div>`:''}}
        <div class="dl"><b>Account</b>${{e(r.acc)}}</div>
      </div>
    </td>
  </tr>`;
}}

function toggleBand(id){{
  const hdr=document.querySelector(`#${{id}} .band-hdr`);
  const body=document.querySelector(`#${{id}} .band-body`);
  const chev=document.querySelector(`#${{id}} .chev`);
  const isOpen=body.classList.contains('open');
  body.classList.toggle('open',!isOpen);
  hdr.classList.toggle('open',!isOpen);
  chev.className=`ti ${{isOpen?'ti-chevron-down':'ti-chevron-up'}} chev`;
}}

function toggleRow(id,tr,uid){{
  const exp=document.getElementById('exp'+uid);
  if(openRow===uid){{exp.style.display='none';tr.classList.remove('sel');openRow=null;return;}}
  if(openRow){{const pe=document.getElementById('exp'+openRow);if(pe)pe.style.display='none';document.querySelectorAll('.tbl tbody tr.sel').forEach(t=>t.classList.remove('sel'));}}
  exp.style.display='table-row';tr.classList.add('sel');openRow=uid;
}}

function doSearch(){{document.getElementById('clrBtn').style.display=document.getElementById('srch').value?'inline':'none';renderBands();}}
function clearSrch(){{document.getElementById('srch').value='';document.getElementById('clrBtn').style.display='none';renderBands();}}
function toggleSort(){{sortAsc=!sortAsc;document.getElementById('sortB').textContent=sortAsc?'↑ Oldest':'↓ Newest';renderBands();}}

// ── CALENDAR ──────────────────────────────────────────────────────
function evMap(){{
  const cf=calFilter(), m={{}};
  DATA.filter(r=>r.st!=='deleted'&&(!cf||r.cat===cf)).forEach(r=>{{
    [(r.det||''),(r.fup||'')].filter(Boolean).forEach(dt=>{{
      const d=dt.slice(0,10);
      const [yr,mo]=d.split('-').map(Number);
      if(yr===calY&&mo-1===calM){{if(!m[d])m[d]=[];m[d].push(r);}}
    }});
  }});
  return m;
}}

function evForDay(ds){{
  const cf=calFilter();
  return DATA.filter(r=>r.st!=='deleted'&&(!cf||r.cat===cf)&&((r.det||'').slice(0,10)===ds||(r.fup||'').slice(0,10)===ds));
}}

function renderMo(){{
  const ccLbl={{all:'All',rtr:'RTR',reply:'Reply Needed',outreach:'Remote',interview:'Interviews',assessment:'Assessments',followup:'Follow-ups'}};
  document.getElementById('calLbl').textContent=`${{MO[calM]}} ${{calY}} — ${{ccLbl[calMode]||''}}`;
  const first=new Date(calY,calM,1).getDay(),days=new Date(calY,calM+1,0).getDate(),em=evMap();
  let h=DW.map(d=>`<div class="dow">${{d}}</div>`).join('');
  for(let i=0;i<first;i++) h+=`<div class="cd empty"></div>`;
  for(let d=1;d<=days;d++){{
    const ds=`${{calY}}-${{String(calM+1).padStart(2,'0')}}-${{String(d).padStart(2,'0')}}`;
    const evs=em[ds]||[],cats=[...new Set(evs.map(r=>r.cat))];
    const isT=ds===TODAY,isS=ds===selDay;
    h+=`<div class="cd${{isT?' today':''}}${{isS?' sel':''}}" onclick="selectDay('${{ds}}')">
      <div class="cd-n">${{d}}</div>
      <div class="cd-dots">${{cats.map(c=>`<div class="dot" style="background:${{Cg(c).dot}}"></div>`).join('')}}</div>
      ${{evs.length?`<div class="cd-cnt">${{evs.length}}</div>`:''}}
    </div>`;
  }}
  document.getElementById('moGrid').innerHTML=h;
}}

function calPrev(){{calM--;if(calM<0){{calM=11;calY--;}}renderMo();renderStrip();}}
function calNext(){{calM++;if(calM>11){{calM=0;calY++;}}renderMo();renderStrip();}}
function goToday(){{calY=new Date().getFullYear();calM=new Date().getMonth();selDay=TODAY;renderMo();renderStrip();renderTL();}}

function selectDay(ds){{
  selDay=ds;
  const[yr,mo]=ds.split('-').map(Number);
  if(yr!==calY||mo-1!==calM){{calY=yr;calM=mo-1;}}
  renderMo();renderStrip();renderTL();
}}

function renderStrip(){{
  const strip=document.getElementById('dayStrip'),em=evMap();
  const ctr=new Date(selDay+'T12:00:00'),days=[];
  for(let i=-7;i<=14;i++){{const d=new Date(ctr);d.setDate(d.getDate()+i);days.push(d);}}
  strip.innerHTML=days.map(d=>{{
    const ds=d.toISOString().slice(0,10),evs=em[ds]||[];
    const cats=[...new Set(evs.map(r=>r.cat))];
    const isT=ds===TODAY,isSel=ds===selDay;
    return `<div class="ds${{isT?' tod':''}}${{isSel?' sel':''}}" onclick="selectDay('${{ds}}')" id="dsd-${{ds}}">
      <div class="ds-dow">${{DWF[d.getDay()]}}</div>
      <div class="ds-d">${{d.getDate()}}</div>
      <div class="ds-dots">${{cats.slice(0,4).map(c=>`<div class="ds-dot" style="background:${{isSel?'rgba(255,255,255,.7)':Cg(c).dot}}"></div>`).join('')}}</div>
    </div>`;
  }}).join('');
  setTimeout(()=>{{const el=document.getElementById('dsd-'+selDay);if(el)el.scrollIntoView({{behavior:'smooth',block:'nearest',inline:'center'}});}},50);
}}

function renderTL(){{
  const evs=evForDay(selDay);
  const d=new Date(selDay+'T12:00:00');
  const lbl=selDay===TODAY?`Today — ${{d.toLocaleDateString('en-US',{{weekday:'long',month:'long',day:'numeric'}})}}`:d.toLocaleDateString('en-US',{{weekday:'long',month:'long',day:'numeric',year:'numeric'}});
  document.getElementById('dayHdrLbl').textContent=lbl;
  document.getElementById('dayCnt').textContent=`${{evs.length}} event${{evs.length!==1?'s':''}}`;
  const timedEvs=evs.filter(r=>(r.det||'').slice(0,10)===selDay);
  const fupEvs=evs.filter(r=>(r.fup||'').slice(0,10)===selDay&&(r.det||'').slice(0,10)!==selDay);
  const aw=document.getElementById('alldayWrap');
  if(fupEvs.length){{
    aw.style.display='block';
    document.getElementById('alldayBody').innerHTML=fupEvs.map(r=>{{
      const c=Cg(r.cat);
      return `<div class="allday-ev" style="border-color:${{c.col}};background:${{c.bg}}" onclick="openEditModal(${{DATA.indexOf(r)}})">
        <div style="flex:1;min-width:0">
          <div style="font-size:10px;font-weight:700;color:${{c.col}};margin-bottom:1px">${{c.lbl}} — follow-up due</div>
          <div style="font-size:12px;font-weight:600;line-height:1.3">${{e(r.role||r.subj.slice(0,55))}}</div>
          <div style="font-size:10px;color:var(--muted)">${{e(r.rec)}} · ${{e(r.em)}}</div>
        </div>
        ${{r.ph?`<a href="tel:${{e(r.ph)}}" style="font-size:11px;color:var(--int);text-decoration:none;font-weight:700;flex-shrink:0" onclick="event.stopPropagation()"><i class="ti ti-phone"></i></a>`:''}}
      </div>`;
    }}).join('');
  }} else {{ aw.style.display='none'; }}
  timedEvs.sort((a,b)=>(a.det||'').localeCompare(b.det||''));
  const tl=document.getElementById('timeline');
  if(!timedEvs.length&&!fupEvs.length){{tl.innerHTML=`<div class="no-evs"><i class="ti ti-calendar-off"></i><p>No events on this day</p></div>`;return;}}
  if(!timedEvs.length){{tl.innerHTML='';return;}}
  const hourEvs={{}};
  timedEvs.forEach(r=>{{
    const tp=(r.det||'').split(' ')[1]||'08:00';
    const hr=Math.max(6,Math.min(22,parseInt(tp)));
    if(!hourEvs[hr])hourEvs[hr]=[];
    hourEvs[hr].push(r);
  }});
  const now=new Date(),nowHr=now.getHours()+now.getMinutes()/60,isToday=selDay===TODAY;
  let html='';
  for(let hr=6;hr<=22;hr++){{
    const lbl=hr===12?'12 PM':hr<12?`${{hr}} AM`:`${{hr-12}} PM`;
    const evHtml=(hourEvs[hr]||[]).map(r=>{{
      const c=Cg(r.cat),tp=((r.det||'').split(' ')[1]||'').slice(0,5);
      const locP=r.loc==='remote'?`<span class="ep" style="color:var(--out);border-color:var(--out-b);background:var(--out-bg)">Remote</span>`:r.loc==='hybrid'?`<span class="ep" style="color:var(--rtr);border-color:var(--rtr-b);background:var(--rtr-bg)">Hybrid</span>`:'';
      const rateP=r.rate?`<span class="ep" style="color:var(--int);border-color:var(--int-b);background:var(--int-bg)">${{e(r.rate)}}</span>`:'';
      const idx=DATA.indexOf(r);
      return `<div class="ev" style="border-color:${{c.col}};background:${{c.bg}}" onclick="openEditModal(${{idx}})">
        <div class="ev-cat" style="color:${{c.col}}">${{c.lbl}} · ${{tp}} · ${{e(r.acc)}}</div>
        <div class="ev-title">${{e(r.role||r.subj.slice(0,60))}}</div>
        <div class="ev-meta">${{e(r.rec||'')}}</div>
        ${{r.co?`<div class="ev-meta">${{e(r.co)}}</div>`:''}}
        <div class="ev-pills">${{locP}}${{rateP}}${{r.ph?`<a href="tel:${{e(r.ph)}}" class="ep" style="color:var(--int);border-color:var(--int-b);background:var(--int-bg);text-decoration:none" onclick="event.stopPropagation()"><i class="ti ti-phone" style="font-size:10px"></i> ${{e(r.ph)}}</a>`:''}}</div>
      </div>`;
    }}).join('');
    let nowHtml='';
    if(isToday&&nowHr>=hr&&nowHr<hr+1){{
      const pct=(nowHr-hr)*100;
      nowHtml=`<div class="now-line" style="top:${{pct}}%"><div class="now-dot"></div><div class="now-badge">${{now.getHours()}}:${{String(now.getMinutes()).padStart(2,'0')}}</div></div>`;
    }}
    html+=`<div class="ts"><div class="tl-lbl">${{lbl}}</div><div class="tl-evs"><div class="tl-line"></div>${{nowHtml}}${{evHtml}}</div></div>`;
  }}
  tl.innerHTML=html;
}}

// ── COMPANIES ─────────────────────────────────────────────────────
function renderCo(){{
  const cos={{}};
  DATA.filter(r=>r.st!=='deleted'&&r.co).forEach(r=>{{
    if(!cos[r.co])cos[r.co]={{evs:[],lat:''}};
    cos[r.co].evs.push(r);
    if((r.det||'')>cos[r.co].lat)cos[r.co].lat=r.det||'';
  }});
  const sorted=Object.entries(cos).sort((a,b)=>b[1].lat.localeCompare(a[1].lat));
  document.getElementById('coBody').innerHTML=sorted.length?sorted.map(([name,d],i)=>{{
    const cats=[...new Set(d.evs.map(r=>r.cat))];
    const pills=cats.map(c=>`<span class="badge ${{Cg(c).cls}}">${{Cg(c).lbl}}</span>`).join(' ');
    const evs=d.evs.sort((a,b)=>(b.det||'').localeCompare(a.det||'')).map(r=>`
      <div class="co-ev">
        <div style="width:3px;border-radius:2px;flex-shrink:0;background:${{Cg(r.cat).dot}};min-height:28px;margin-top:2px"></div>
        <div><div style="font-size:12px;font-weight:600">${{e(r.role||r.subj.slice(0,60))}}</div>
        <div style="font-size:10px;color:var(--muted)">${{(r.det||'').slice(0,10)}} · ${{e(r.rec)}} · ${{Cg(r.cat).lbl}}</div></div>
      </div>`).join('');
    return `<div class="co-card">
      <div class="co-hdr" onclick="document.getElementById('ce${{i}}').classList.toggle('open')">
        <div class="co-icon">🏢</div>
        <div style="flex:1;min-width:0">
          <div style="font-weight:700;font-size:13px">${{e(name)}}</div>
          <div style="font-size:10px;color:var(--muted);margin-top:1px">${{d.evs.length}} events · ${{(d.lat||'').slice(0,10)}}</div>
          <div style="margin-top:4px;display:flex;flex-wrap:wrap;gap:3px">${{pills}}</div>
        </div>
        <i class="ti ti-chevron-down" style="color:var(--hint);font-size:16px;flex-shrink:0"></i>
      </div>
      <div class="co-events" id="ce${{i}}">${{evs}}</div>
    </div>`;
  }}).join(''):`<div class="empty" style="padding:40px 20px"><i class="ti ti-building"></i><p>No companies tracked yet</p></div>`;
}}

// ── EDIT MODAL ────────────────────────────────────────────────────
function openEditModal(idx){{editIdx=idx;const r=DATA[idx];document.getElementById('mTitle').textContent='Edit entry';document.getElementById('mBody').innerHTML=buildForm(r);document.getElementById('overlay').classList.add('open');document.getElementById('modal').classList.add('open');}}
function openAddModal(){{editIdx=null;document.getElementById('mTitle').textContent='Add entry';document.getElementById('mBody').innerHTML=buildForm(null);document.getElementById('overlay').classList.add('open');document.getElementById('modal').classList.add('open');}}
function buildForm(r){{
  const v=(f,d='')=>r?(r[f]||d):d;const s=(f,val)=>v(f)===val?'selected':'';
  return `<div class="field"><label>Category</label><select id="e-cat">
    <option value="rtr" ${{s('cat','rtr')}}>📋 RTR</option>
    <option value="reply" ${{s('cat','reply')}}>⚡ Reply Needed</option>
    <option value="outreach" ${{s('cat','outreach')}}>🌐 Remote Role</option>
    <option value="interview" ${{s('cat','interview')}}>📞 Interview</option>
    <option value="assessment" ${{s('cat','assessment')}}>🧪 Assessment</option>
    <option value="followup" ${{s('cat','followup')}}>⏳ Follow-up</option>
  </select></div>
  <div class="field"><label>Role title</label><input id="e-role" value="${{e(v('role'))}}" placeholder="Cloud Security Engineer"></div>
  <div class="field"><label>Recruiter</label><input id="e-rec" value="${{e(v('rec'))}}" placeholder="Jane Smith"></div>
  <div class="field"><label>Email</label><input id="e-em" value="${{e(v('em'))}}" placeholder="jane@company.com"></div>
  <div class="field"><label>Company / Client</label><input id="e-co" value="${{e(v('co'))}}" placeholder="Bloomberg, Cognizant…"></div>
  <div class="field"><label>Rate</label><input id="e-rate" value="${{e(v('rate'))}}" placeholder="$70/hr W2"></div>
  <div class="field"><label>Phone</label><input id="e-ph" value="${{e(v('ph'))}}" placeholder="646-820-3671"></div>
  <div class="field"><label>Location</label><select id="e-loc">
    <option value="remote" ${{s('loc','remote')}}>🌐 Remote</option>
    <option value="hybrid" ${{s('loc','hybrid')}}>🔀 Hybrid</option>
    <option value="onsite" ${{s('loc','onsite')}}>🏢 Onsite</option>
  </select></div>
  <div class="field"><label>Follow-up due</label><input type="date" id="e-fup" value="${{v('fup')}}"></div>
  <div class="field"><label>Status</label><select id="e-st">
    <option value="open" ${{s('st','open')}}>🔵 Open</option>
    <option value="done" ${{s('st','done')}}>✅ Done</option>
  </select></div>`;
}}
function closeModal(){{document.getElementById('overlay').classList.remove('open');document.getElementById('modal').classList.remove('open');editIdx=null;}}
function saveEdit(){{
  const vals={{cat:document.getElementById('e-cat').value,role:document.getElementById('e-role').value,rec:document.getElementById('e-rec').value,em:document.getElementById('e-em').value,co:document.getElementById('e-co').value,rate:document.getElementById('e-rate').value,ph:document.getElementById('e-ph').value,loc:document.getElementById('e-loc').value,fup:document.getElementById('e-fup').value,st:document.getElementById('e-st').value}};
  if(editIdx!==null){{Object.assign(DATA[editIdx],vals);showToast('✅ Saved');}}
  else{{DATA.unshift({{id:Date.now(),det:new Date().toISOString().slice(0,16).replace('T',' '),subj:vals.role,...vals}});showToast('✅ Added');}}
  updateStats();if(curTab==='cal'){{renderMo();renderStrip();renderTL();}}else if(curTab!=='all')renderBands();if(curTab==='co')renderCo();closeModal();
}}
function deleteItem(idx){{DATA[idx].st='deleted';updateStats();renderBands();showToast('🗑 Deleted');}}
function showToast(m){{const t=document.getElementById('toast');t.textContent=m;t.classList.add('show');clearTimeout(toastT);toastT=setTimeout(()=>t.classList.remove('show'),2500);}}

// ── INIT ──────────────────────────────────────────────────────────
updateStats();
// default: show all tab with stat tiles
setTab('all');
// Auto-refresh every 15 min
setTimeout(()=>location.reload(), 15*60*1000);
</script>
</body>
</html>"""

with open(DASHBOARD_FILE, "w", encoding="utf-8") as f:
    f.write(html)

print(f"[Dashboard] Generated {DASHBOARD_FILE} ({len(html):,} chars)")
print(f"[Dashboard] URL: https://eshwarjay0-dels.github.io/gmail-watcher/dashboard.html")

#!/usr/bin/env python3
"""
generate_dashboard.py v14
Enhanced Job Campaign HQ Dashboard - Full Feature Update
Features:
- 15/15-30/30-60 day bands for ALL categories
- Full deduplication: same role+email per category = 1 entry
- Remote & Reply-Needed: 3-day focus strip (phone/email sorted to top)
- Bigger date & time font (rec-date class)
- Smart role title extraction (no generic subjects)
- Rejection mail filter
- Initial screenings reclassified as Interview
- Role sorting: Cyber->DevOps->AI->Data/FullStack + color filter bar
- JD extraction from email body/notes
- Follow-up: last sent message field
- Reply-Needed primary = recruiter waiting on me (asked question / requested something)
"""
import csv, json, os, re
from datetime import datetime, date, timedelta

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_FILE  = os.path.join(BASE_DIR, "data", "rtr_followup_tracker.csv")
DASHBOARD_FILE = os.path.join(BASE_DIR, "dashboard.html")

REJECTION_PATTERNS = [
    r"thank.{0,10}(interest|applying)",
    r"we.{0,5}(will|ll) keep.{0,15}(file|mind)",
    r"not.{0,10}moving forward",
    r"decided to (move|go) with (another|other)",
    r"position.{0,10}filled",
    r"no longer.{0,15}consider",
    r"we regret",
    r"unfortunately.{0,10}not",
    r"not.{0,10}right.{0,10}fit",
    r"not selected",
    r"will not be moving",
    r"thank you for applying",
    r"after careful consideration",
    r"we have decided",
]

GENERIC_SUBJECT_PATTERNS = [
    r"^we.re inviting you",
    r"^invitation to apply",
    r"^your application (has|was)",
    r"^thanks for (your interest|applying)",
    r"^thank you for (your interest|applying)",
    r"^application (received|submitted|update)",
    r"^job alert",
    r"^new job",
    r"^jobs? (matching|for you)",
    r"^re: your application",
]

INITIAL_SCREENING_PATTERNS = [
    r"initial (screen|call|interview)",
    r"phone screen",
    r"screening (call|interview)",
    r"recruiter (screen|call)",
    r"first (round|interview|call)",
    r"intro (call|interview)",
    r"discovery call",
    r"30.?min(ute)? call",
    r"quick (call|chat|connect)",
]

def classify_role_category(role_text, skills_text=""):
    text = (role_text + " " + skills_text).lower()
    cyber_kw = ["security","cyber","siem","soc","iam","pentest","pen test",
                "devsecops","appsec","application security","cloud security",
                "infosec","firewall","vulnerability","threat","dlp","cspm",
                "qualys","splunk","sentinel","crowdstrike","okta","sailpoint",
                "pam","epv","zero trust","nist","risk analyst","compliance",
                "grc","incident response","forensic","endpoint","xdr","edr",
                "network security","architect","security engineer","security analyst",
                "cyber threat","ot security","ics security"]
    devops_kw = ["devops","kubernetes","k8s","terraform","ansible","jenkins",
                 "ci/cd","gitlab","docker","helm","argo","gitops","platform engineer",
                 "site reliability","sre","infrastructure","aws cloud","azure cloud",
                 "gcp cloud","cloud engineer","cloud architect","cloudformation"]
    ai_kw = ["machine learning","ml engineer","deep learning","llm","generative ai",
             "gen ai","nlp","computer vision","data science","ai engineer",
             "agentic","pytorch","tensorflow","mlops","artificial intelligence",
             "huggingface","langchain","rag","vector","embedding","agentic ai"]
    data_kw = ["data engineer","data pipeline","etl","spark","kafka","airflow",
               "databricks","snowflake","dbt","data analyst","bi developer",
               "tableau","power bi","looker","data warehouse","full stack",
               "fullstack","frontend","backend","react","angular","node.js",
               "java developer","spring boot","python developer","software engineer",
               "software developer","web developer"]
    for kw in cyber_kw:
        if kw in text: return "cyber"
    for kw in devops_kw:
        if kw in text: return "devops"
    for kw in ai_kw:
        if kw in text: return "ai"
    for kw in data_kw:
        if kw in text: return "data"
    return "other"

def extract_role_title(subject, role_field, notes=""):
    if role_field and len(role_field) > 5:
        low = role_field.lower()
        skip = ["we're inviting","invitation","thanks for","thank you for",
                "application","job alert","new job","your application","re: your"]
        if not any(s in low for s in skip):
            return role_field[:100]
    subj = subject or ""
    for pat in [
        r'^(re:|fwd?:|fw:|rate confirmation\s*[-|:]*|rtr\s*[-|:&]*|rtro\s*[-|:]*)',
        r'^(and\s+|as discussed\s*[-|:]*|for\s+(?=\w))',
        r'^(&\s*|regarding\s+|about\s+|update on\s+)',
    ]:
        subj = re.sub(pat, '', subj, flags=re.I).strip()
    m = re.match(r'^(.{10,80?})\s*([||]|â|â|::|\s{2,}|@\s)', subj)
    if m:
        return m.group(1).strip()[:100]
    return subj[:100] if subj else (role_field or "Unknown Role")[:100]

def is_rejection(subject, notes):
    text = (subject + " " + (notes or "")).lower()
    for pat in REJECTION_PATTERNS:
        if re.search(pat, text, re.I):
            return True
    return False

def is_generic_subject(subject):
    for pat in GENERIC_SUBJECT_PATTERNS:
        if re.search(pat, (subject or "").strip(), re.I):
            return True
    return False

def is_initial_screening(subject, notes, category):
    if category == "interview":
        return False
    text = (subject + " " + (notes or "")).lower()
    for pat in INITIAL_SCREENING_PATTERNS:
        if re.search(pat, text, re.I):
            return True
    return False

def normalize(s):
    return re.sub(r'\s+', ' ', (s or "").lower().strip())

def extract_jd_summary(notes, skills):
    if not notes:
        return skills[:200] if skills else ""
    m = re.search(r'(requirements?|qualifications?|responsibilities?|must have|job description)[:\s]+(.{50,400})', notes, re.I|re.S)
    if m:
        snippet = re.sub(r'\s+', ' ', m.group(2).strip())
        return snippet[:300]
    clean = re.sub(r'\s+', ' ', notes).strip()
    if len(clean) > 80:
        return clean[:250]
    return skills[:200] if skills else ""

def is_waiting_on_me(subject, notes, category):
    if category not in ("reply", "reply_needed"):
        return False
    text = (subject + " " + (notes or "")).lower()
    waiting_patterns = [
        r"please (send|share|provide|confirm|reply|respond|let me know)",
        r"(send|share|provide|attach|email).{0,30}(resume|cv|details|info|document)",
        r"(awaiting|waiting).{0,20}(your|response|reply|confirmation)",
        r"can you (send|share|confirm|let me know)",
        r"(checking in|following up).{0,30}(sent|asked|requested)",
        r"(please|kindly).{0,30}(confirm|update|advise)",
        r"are you (still |)available",
        r"haven.t heard",
        r"still interested",
    ]
    for pat in waiting_patterns:
        if re.search(pat, text, re.I):
            return True
    return False

rows = []
auto_deleted = 0
cutoff_60 = (date.today() - timedelta(days=60)).isoformat()
cutoff_30 = (date.today() - timedelta(days=30)).isoformat()
cutoff_15 = (date.today() - timedelta(days=15)).isoformat()
cutoff_3  = (date.today() - timedelta(days=3)).isoformat()

if os.path.exists(CSV_FILE):
    with open(CSV_FILE, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("status","").lower() == "deleted":
                continue
            det = (row.get("detected_at","") or "")[:10]
            if det and det < cutoff_60:
                auto_deleted += 1
                continue
            rows.append(row)

print(f"[Dashboard v12] {len(rows)} records loaded ({auto_deleted} auto-removed >60 days)")
updated = datetime.now().strftime("%b %d, %Y %I:%M %p UTC")

js_rows = []
seen_keys = {}

for r in rows:
    cat = r.get("category","")
    if cat == "reply_needed":
        cat = "reply"
    subject = r.get("subject","") or ""
    notes   = r.get("notes","") or ""
    skills  = r.get("skills","") or ""
    role_f  = r.get("role","") or ""
    em      = r.get("sender_email", r.get("sender","")) or ""
    if is_rejection(subject, notes):
        continue
    if is_initial_screening(subject, notes, cat):
        cat = "interview"
    smart_role = extract_role_title(subject, role_f, notes)
    if is_generic_subject(smart_role) and is_generic_subject(subject):
        continue
    role_cat = classify_role_category(smart_role, skills)
    jd_summary = extract_jd_summary(notes, skills)
    norm_key = (cat, normalize(em), normalize(smart_role))
    if norm_key in seen_keys:
        continue
    seen_keys[norm_key] = True
    waiting_on_me = is_waiting_on_me(subject, notes, cat)
    last_sent = ""
    ms = re.search(r'(last[_\s]sent|my reply|i replied|i sent)[:\s]+(.{10,200})', notes, re.I)
    if ms:
        last_sent = ms.group(2).strip()[:150]
    js_rows.append({
        "id": abs(hash(em + (r.get("detected_at","")) + cat)) % (10**15),
        "cat": cat,
        "acc": r.get("account",""),
        "subj": subject[:200],
        "role": smart_role,
        "role_cat": role_cat,
        "co": r.get("company","")[:80],
        "rec": r.get("recruiter_name","")[:80],
        "em": em[:120],
        "ph": (r.get("phones","").split(";")[0] if r.get("phones") else "").strip(),
        "loc": r.get("location_type",""),
        "rate": r.get("rate",""),
        "sk": skills[:250],
        "det": r.get("detected_at",""),
        "fup": r.get("followup_due",""),
        "st": r.get("status","open"),
        "jd": jd_summary,
        "wom": waiting_on_me,
        "last_sent": last_sent,
    })

rows_json = json.dumps(js_rows, ensure_ascii=True)
rows_json = rows_json.replace("</script>", "<\\/script>")
cutoff_vars = json.dumps({"d60":cutoff_60,"d30":cutoff_30,"d15":cutoff_15,"d3":cutoff_3,"auto_deleted":auto_deleted})

CSS = r"""
*{box-sizing:border-box;margin:0;padding:0}
:root{
--bg:#f4f6f9;--surf:#fff;--card2:#f8f9fb;--border:#e4e8ef;--border2:#d0d7e3;
--text:#1a2035;--muted:#6b7a99;--hint:#9aa4bc;
--font:'Inter',-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
--rtr:#d97706;--rtr-bg:#fffbeb;--rtr-b:#fde68a;--rtr-dot:#f59e0b;
--rep:#dc2626;--rep-bg:#fef2f2;--rep-b:#fecaca;--rep-dot:#f87171;
--out:#1d6fc4;--out-bg:#eff6ff;--out-b:#bfdbfe;--out-dot:#3b82f6;
--int:#16a34a;--int-bg:#f0fdf4;--int-b:#bbf7d0;--int-dot:#22c55e;
--ass:#7c3aed;--ass-bg:#f5f3ff;--ass-b:#ddd6fe;--ass-dot:#8b5cf6;
--fol:#0369a1;--fol-bg:#f0f9ff;--fol-b:#bae6fd;--fol-dot:#38bdf8;
--cyber:#dc2626;--cyber-bg:#fef2f2;--cyber-b:#fecaca;
--devops:#7c3aed;--devops-bg:#f5f3ff;--devops-b:#ddd6fe;
--ai:#0369a1;--ai-bg:#f0f9ff;--ai-b:#bae6fd;
--data:#16a34a;--data-bg:#f0fdf4;--data-b:#bbf7d0;
}
body{background:var(--bg);color:var(--text);font-family:var(--font);min-height:100vh;overflow-x:hidden;font-size:14px}
.hdr{background:var(--surf);border-bottom:1px solid var(--border);padding:14px 16px 11px;position:sticky;top:0;z-index:100;box-shadow:0 1px 4px rgba(0,0,0,.06)}
.hdr-top{display:flex;align-items:center;justify-content:space-between}
.hdr h1{font-size:17px;font-weight:700;letter-spacing:-.2px}
.hdr h1 em{font-style:normal;color:var(--out)}
.upd{font-size:11px;color:var(--muted);margin-top:2px}
.search{display:flex;align-items:center;gap:8px;margin-top:10px;background:var(--bg);border:1px solid var(--border2);border-radius:10px;padding:8px 12px;transition:.15s}
.search:focus-within{border-color:#93c5fd;box-shadow:0 0 0 3px rgba(59,130,246,.1)}
.search input{flex:1;background:none;border:none;color:var(--text);font-size:13px;font-family:var(--font);outline:none}
.search input::placeholder{color:var(--hint)}
.tab-wrap{background:var(--surf);border-bottom:1px solid var(--border)}
.tabs{display:flex;gap:5px;padding:8px 14px;overflow-x:auto;scrollbar-width:none}
.tabs::-webkit-scrollbar{display:none}
.tab{flex-shrink:0;padding:6px 13px;border-radius:20px;font-size:11px;font-weight:600;cursor:pointer;border:1px solid var(--border);background:var(--bg);color:var(--muted);transition:all .15s;white-space:nowrap;user-select:none}
.tab.a-all{background:#dbeafe;border-color:#93c5fd;color:#1e40af}
.tab.a-rtr{background:var(--rtr-bg);border-color:var(--rtr-b);color:var(--rtr)}
.tab.a-rep{background:var(--rep-bg);border-color:var(--rep-b);color:var(--rep)}
.tab.a-out{background:var(--out-bg);border-color:var(--out-b);color:var(--out)}
.tab.a-int{background:var(--int-bg);border-color:var(--int-b);color:var(--int)}
.tab.a-ass{background:var(--ass-bg);border-color:var(--ass-b);color:var(--ass)}
.tab.a-fol{background:var(--fol-bg);border-color:var(--fol-b);color:var(--fol)}
.tab.a-co{background:#f8f9fb;border-color:var(--border2);color:var(--text)}
.tab.a-cal{background:#fdf2f8;border-color:#f9a8d4;color:#9d174d}
.role-filter-bar{display:none;gap:5px;padding:6px 14px 8px;overflow-x:auto;scrollbar-width:none;border-top:1px solid var(--border);background:#fafbfc}
.role-filter-bar::-webkit-scrollbar{display:none}
.role-filter-bar.show{display:flex}
.rf-pill{flex-shrink:0;padding:5px 13px;border-radius:16px;font-size:11px;font-weight:700;cursor:pointer;border:2px solid;transition:all .13s;user-select:none;opacity:.75}
.rf-pill.active,.rf-pill:hover{opacity:1;transform:scale(1.05);box-shadow:0 2px 8px rgba(0,0,0,.12)}
.rf-cyber{background:var(--cyber-bg);border-color:var(--cyber-b);color:var(--cyber)}
.rf-devops{background:var(--devops-bg);border-color:var(--devops-b);color:var(--devops)}
.rf-ai{background:var(--ai-bg);border-color:var(--ai-b);color:var(--ai)}
.rf-data{background:var(--data-bg);border-color:var(--data-b);color:var(--data)}
.rf-other{background:#f8f9fb;border-color:var(--border2);color:var(--muted)}
.rf-all{background:#dbeafe;border-color:#93c5fd;color:#1e40af}
.cat-cal-row{display:none;gap:5px;padding:5px 14px 7px;overflow-x:auto;scrollbar-width:none;border-top:1px solid var(--border)}
.cat-cal-row::-webkit-scrollbar{display:none}
.cat-cal-row.show{display:flex}
.stats{display:grid;grid-template-columns:repeat(2,1fr);gap:8px;padding:13px}
@media(min-width:600px){.stats{grid-template-columns:repeat(4,1fr)}}
.stat{border-radius:14px;padding:14px 13px;cursor:pointer;border:1px solid;transition:transform .13s,box-shadow .13s;position:relative}
.stat:hover{transform:translateY(-2px);box-shadow:0 4px 16px rgba(0,0,0,.1)}
.stat::after{content:'âº';position:absolute;top:11px;right:12px;font-size:18px;opacity:.5}
.stat .num{font-size:38px;font-weight:700;line-height:1;letter-spacing:-1px}
.stat .lbl{font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.6px;margin-top:5px;opacity:.85}
.s-rtr{background:var(--rtr-bg);border-color:var(--rtr-b);color:var(--rtr)}
.s-rep{background:var(--rep-bg);border-color:var(--rep-b);color:var(--rep)}
.s-out{background:var(--out-bg);border-color:var(--out-b);color:var(--out)}
.s-int{background:var(--int-bg);border-color:var(--int-b);color:var(--int)}
.disclaimer{margin:10px 14px;padding:10px 14px;background:#fffbeb;border:1px solid #fde68a;border-radius:10px;font-size:11px;color:#92400e;display:none}
.disclaimer.show{display:block}
.section-band{margin:0 14px 6px;border-radius:10px;overflow:hidden;border:1px solid var(--border)}
.band-hdr{display:flex;align-items:center;justify-content:space-between;padding:10px 14px;cursor:pointer;user-select:none;transition:background .12s}
.band-hdr:hover{background:var(--card2)}
.band-hdr h3{font-size:12px;font-weight:700;display:flex;align-items:center;gap:8px}
.band-hdr .bcnt{font-size:10px;font-weight:600;padding:2px 8px;border-radius:10px;background:var(--border);color:var(--muted)}
.band-hdr .chev{font-size:16px;color:var(--hint);transition:transform .2s}
.band-hdr.open .chev{transform:rotate(180deg)}
.band-body{display:none}
.band-body.open{display:block}
.tbl-wrap{overflow-x:auto;-webkit-overflow-scrolling:touch}
.tbl{width:100%;border-collapse:collapse;min-width:620px}
.tbl thead th{padding:9px 13px;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.5px;color:var(--muted);text-align:left;background:#f8f9fb;border-bottom:1px solid var(--border);white-space:nowrap}
.tbl tbody tr{border-bottom:1px solid var(--border);cursor:pointer;transition:background .1s}
.tbl tbody tr:nth-child(4n+1){background:#fff}
.tbl tbody tr:nth-child(4n+3){background:#f8f9fb}
.tbl tbody tr.exp-row{background:#f0f4ff!important;cursor:default}
.tbl tbody tr:hover:not(.exp-row){background:#eff6ff!important}
.tbl tbody tr.sel{background:#e0eeff!important;border-left:3px solid #3b82f6}
.tbl td{padding:12px 13px;vertical-align:top;font-size:12px;line-height:1.5;color:var(--text)}
.badge{display:inline-flex;align-items:center;gap:3px;padding:3px 8px;border-radius:6px;font-size:10px;font-weight:700;border:1px solid;white-space:nowrap}
.b-rtr{background:var(--rtr-bg);border-color:var(--rtr-b);color:var(--rtr)}
.b-rep{background:var(--rep-bg);border-color:var(--rep-b);color:var(--rep)}
.b-out{background:var(--out-bg);border-color:var(--out-b);color:var(--out)}
.b-int{background:var(--int-bg);border-color:var(--int-b);color:var(--int)}
.b-ass{background:var(--ass-bg);border-color:var(--ass-b);color:var(--ass)}
.b-fol{background:var(--fol-bg);border-color:var(--fol-b);color:var(--fol)}
.pill{display:inline-flex;align-items:center;padding:2px 6px;border-radius:4px;font-size:10px;font-weight:600;border:1px solid;margin-right:3px;margin-top:3px}
.p-remote{background:var(--out-bg);border-color:var(--out-b);color:var(--out)}
.p-hybrid{background:var(--rtr-bg);border-color:var(--rtr-b);color:var(--rtr)}
.p-rate{background:var(--int-bg);border-color:var(--int-b);color:var(--int)}
.role-cat-dot{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:5px;flex-shrink:0;vertical-align:middle}
.role-title{font-weight:700;font-size:14px;line-height:1.35;margin-bottom:3px}
.role-co{font-size:11px;color:var(--muted);margin-top:1px}
.rec-name{font-weight:700;font-size:13px;margin-bottom:3px}
.rec-email{font-size:12px;color:var(--out);word-break:break-all;font-weight:600;margin-bottom:2px}
.rec-phone{font-size:13px;color:var(--int);margin-bottom:2px;font-weight:700}
.rec-date{font-size:15px;color:var(--text);margin-top:6px;font-weight:800;letter-spacing:-.3px}
.rec-time{font-size:12px;color:var(--muted);font-weight:500;margin-top:1px}
.det-sm{font-size:11px;color:var(--muted);margin-bottom:2px;display:flex;gap:6px;line-height:1.4}
.det-sm strong{color:var(--text);min-width:40px;flex-shrink:0;font-weight:600}
.fup{display:inline-block;font-size:10px;font-weight:700;padding:3px 7px;border-radius:5px;background:#f8f9fb;border:1px solid var(--border2);color:var(--muted)}
.fup.ov{background:var(--rep-bg);border-color:var(--rep-b);color:var(--rep)}
.fup.td{background:var(--rtr-bg);border-color:var(--rtr-b);color:var(--rtr)}
.row-acts{display:flex;gap:5px;margin-top:8px;flex-wrap:wrap}
.ra{padding:4px 9px;border-radius:6px;font-size:10px;font-weight:700;cursor:pointer;border:1px solid;transition:.12s;background:none;text-decoration:none;display:inline-flex;align-items:center;gap:3px;font-family:var(--font)}
.ra:active{transform:scale(.95)}
.ra-c{border-color:var(--int-b);color:var(--int);background:var(--int-bg)}
.ra-e{border-color:var(--out-b);color:var(--out);background:var(--out-bg)}
.ra-d{border-color:var(--rep-b);color:var(--rep);background:var(--rep-bg)}
.exp-inner{padding:12px 14px;background:#f0f4ff;border-top:1px solid #c7d9f8}
.exp-inner .dl{font-size:11px;color:var(--muted);margin-bottom:6px;display:flex;gap:8px;line-height:1.5}
.exp-inner .dl b{color:var(--text);min-width:55px;flex-shrink:0;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.3px;padding-top:1px}
.jd-box{background:#fff;border:1px solid var(--border2);border-radius:8px;padding:10px 13px;margin-top:8px;font-size:12px;line-height:1.65;color:var(--text)}
.jd-lbl{font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.4px;color:var(--muted);margin-bottom:5px}
.last-sent-box{background:#fffbeb;border:1px solid #fde68a;border-radius:8px;padding:8px 12px;margin-top:6px;font-size:12px;color:#92400e;line-height:1.5}
.ls-lbl{font-size:9px;font-weight:700;text-transform:uppercase;letter-spacing:.4px;margin-bottom:3px;color:#b45309}
.wom-badge{display:inline-flex;align-items:center;gap:3px;padding:3px 8px;border-radius:6px;font-size:10px;font-weight:700;background:#fef2f2;border:1px solid #fecaca;color:#dc2626;margin-top:4px}
.focus-strip{background:linear-gradient(135deg,#fef2f2,#fff7f7);border:1px solid h#fecaca;border-radius:12px;margin:8px 14px 10px;padding:10px 14px}
.focus-strip h4{font-size:11px;font-weight:700;color:#dc2626;margin-bottom:8px;text-transform:uppercase;letter-spacing:.4px}
.focus-row{display:flex;align-items:center;gap:10px;padding:7px 0;border-bottom:1px solid rgba(220,38,38,.1);flex-wrap:wrap}
.focus-row:last-child{border:none}
.fr-ph{font-size:13px;font-weight:700;color:var(--int);white-space:nowrap}
.fr-em{font-size:12px;font-weight:600;color:var(--out);word-break:break-all}
.fr-role{font-size:11px;color:var(--text);flex:1;min-width:120px}
.fr-date{font-size:12px;color:var(--text);flex-shrink:0;font-weight:700}
.cal-chrome{padding:12px 14px 0}
.cal-nav-row{display:flex;align-items:center;justify-content:space-between;margin-bottom:10px}
.cal-nav-row h2{font-size:14px;font-weight:700}
.cal-btn{background:var(--surf);border:1px solid var(--border2);border-radius:9px;padding:6px 12px;font-size:11px;font-weight:600;cursor:pointer;color:var(--muted);transition:.13s}
.cal-btn:hover{border-color:#93c5fd;color:var(--out)}
.cal-btn.today{background:#eff6ff;border-color:#93c5fd;color:#1d6fc4}
.month-box{background:var(--surf);border:1px solid var(--border);border-radius:14px;padding:10px;margin-bottom:8px}
.mo-grid{display:grid;grid-template-columns:repeat(7,1fr);gap:2px}
.dow{font-size:9px;font-weight:700;text-align:center;color:var(--hint);text-transform:uppercase;padding-bottom:4px}
.cd{min-height:52px;border-radius:9px;border:1px solid transparent;background:var(--bg);padding:4px;cursor:pointer;transition:.12s}
.cd:hover{border-color:#93c5fd;background:#eff6ff}
.cd.today{border-color:#3b82f6;background:#eff6ff}
.cd.sel{border-color:#1d6fc4;background:#dbeafe}
.cd.empty{background:transparent;border-color:transparent;cursor:default}
.cd-n{font-size:10px;font-weight:600;color:var(--muted);text-align:center}
.cd.today .cd-n{color:#1d4ed8;font-weight:800}
.cd.sel .cd-n{color:#1d6fc4;font-weight:800}
.cd-dots{display:flex;flex-wrap:wrap;gap:1px;justify-content:center;margin-top:2px}
.dot{width:6px;height:6px;border-radius:50%}
.cd-cnt{font-size:8px;color:var(--hint);text-align:center;margin-top:1px}
.day-strip{display:flex;gap:5px;overflow-x:auto;padding:0 14px 6px;scrollbar-width:none;-webkit-overflow-scrolling:touch}
.day-strip::-webkit-scrollbar{display:none}
.ds{flex-shrink:0;width:48px;text-align:center;padding:7px 4px;border-radius:12px;cursor:pointer;border:1px solid var(--border);background:var(--surf);transition:.12s}
.ds:hover{border-color:#93c5fd;background:#eff6ff}
.ds.sel{background:#1d6fc4;border-color:#1d6fc4;color:#fff}
.ds.tod{border-color:#3b82f6}
.ds-dow{font-size:9px;font-weight:700;text-transform:uppercase;letter-spacing:.3px;opacity:.7}
.ds-d{font-size:17px;font-weight:700;line-height:1;margin:2px 0}
.ds-dots{display:flex;justify-content:center;gap:2px;margin-top:2px;min-height:7px}
.ds-dot{width:5px;height:5px;border-radius:50%}
.day-tl{padding:0 14px 80px}
.day-hdr{display:flex;align-items:center;justify-content:space-between;padding:8px 0 10px}
.day-hdr h3{font-size:14px;font-weight:700}
.day-cnt{font-size:11px;color:var(--muted);background:var(--bg);border:1px solid var(--border2);border-radius:20px;padding:3px 10px}
.allday-wrap{margin-bottom:10px}
.allday-lbl{font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.4px;color:var(--hint);margin-bottom:4px}
.allday-ev{border-radius:9px;border-left:3px solid transparent;padding:8px 11px;margin-bottom:4px;cursor:pointer;display:flex;align-items:center;gap:8px}
.timeline{position:relative}
.ts{display:flex;gap:8px;min-height:56px;position:relative}
.tl-lbl{width:40px;flex-shrink:0;font-size:9px;font-weight:600;color:var(--hint);text-align:right;margin-top:-5px;line-height:1}
.tl-line{position:absolute;left:48px;right:0;top:0;border-top:1px solid var(--border);pointer-events:none}
.tl-evs{flex:1;padding:0 0 4px;min-height:44px;position:relative}
.ev{border-radius:9px;border-left:3px solid transparent;padding:8px 11px;margin-bottom:5px;cursor:pointer;transition:transform .1s}
.ev:hover{transform:translateX(2px)}
.ev-cat{font-size:9px;font-weight:700;text-transform:uppercase;letter-spacing:.3px;margin-bottom:2px;opacity:.8}
.ev-title{font-size:12px;font-weight:600;line-height:1.35;margin-bottom:2px}
.ev-meta{font-size:10px;opacity:.7;line-height:1.4}
.ev-pills{display:flex;gap:3px;margin-top:4px;flex-wrap:wrap}
.ep{font-size:9px;font-weight:700;padding:2px 6px;border-radius:4px;border:1px solid}
.now-line{position:absolute;left:48px;right:0;pointer-events:none;z-index:5}
.now-line::after{content:'';position:absolute;left:0;right:0;top:-0.5px;height:2px;background:#dc2626}
.now-dot{position:absolute;left:-5px;top:-4px;width:9px;height:9px;border-radius:50%;background:#dc2626}
.now-badge{position:absolute;left:-46px;top:-9px;font-size:8px;font-weight:700;color:#dc2626;white-space:nowrap}
.no-evs{text-align:center;padding:32px 16px;color:var(--hint)}
.no-evs i{font-size:32px;display:block;margin-bottom:10px;opacity:.35}
.co-card{background:var(--surf);border:1px solid var(--border);border-radius:14px;margin:0 14px 8px;overflow:hidden}
.co-hdr{display:flex;align-items:center;gap:11px;padding:13px 14px;cursor:pointer;transition:.12s}
.co-hdr:hover{background:var(--bg)}
.co-icon{width:40px;height:40px;border-radius:10px;background:var(--out-bg);display:flex;align-items:center;justify-content:center;font-size:20px;flex-shrink:0;border:1px solid var(--out-b)}
.co-events{border-top:1px solid var(--border);display:none}
.co-events.open{display:block}
.co-ev{display:flex;gap:9px;padding:9px 13px;border-bottom:1px solid var(--border);align-items:flex-start}
.co-ev:last-child{border:none}
.overlay{position:fixed;inset:0;background:rgba(15,23,42,.5);z-index:200;opacity:0;pointer-events:none;transition:.2s;backdrop-filter:blur(3px)}
.overlay.open{opacity:1;pointer-events:all}
.modal{position:fixed;bottom:0;left:0;right:0;background:var(--surf);border-radius:18px 18px 0 0;border-top:1px solid var(--border);max-height:92vh;overflow-y:auto;z-index:201;transform:translateY(100%);transition:transform .3s cubic-bezier(.4,0,.2,1);box-shadow:0 -8px 32px rgba(0,0,0,.12)}
.modal.open{transform:translateY(0)}
.modal-handle{width:36px;height:4px;background:var(--border2);border-radius:2px;margin:12px auto 0}
.modal-hdr{padding:14px 20px 10px;border-bottom:1px solid var(--border);background:#f8f9fb}
.modal-hdr h2{font-size:14px;font-weight:700}
.modal-body{padding:16px 20px}
.field{margin-bottom:13px}
.field label{display:block;font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px;font-weight:700}
.field input,.field select,.field textarea{width:100%;background:var(--bg);border:1px solid var(--border2);border-radius:9px;padding:9px 12px;color:var(--text);font-size:13px;font-family:var(--font);outline:none;transition:.15s}
.field input:focus,.field select:focus,.field textarea:focus{border-color:#3b82f6;box-shadow:0 0 0 3px rgba(59,130,246,.1)}
.field textarea{min-height:65px;resize:vertical;line-height:1.5}
.modal-acts{display:flex;gap:9px;padding:4px 20px 46px}
.mbtn{flex:1;padding:12px;border-radius:10px;font-size:13px;font-weight:700;cursor:pointer;border:none;transition:.15s;font-family:var(--font)}
.mbtn.save{background:#1d6fc4;color:#fff}
.mbtn.cancel{background:var(--bg);color:var(--muted);border:1px solid var(--border2)}
.toast{position:fixed;bottom:80px;left:50%;transform:translateX(-50%) translateY(18px);background:var(--text);color:#fff;border-radius:12px;padding:10px 18px;font-size:12px;font-weight:600;z-index:300;opacity:0;transition:.25s;pointer-events:none;white-space:nowrap;box-shadow:0 4px 14px rgba(0,0,0,.2)}
.toast.show{opacity:1;transform:translateX(-50%) translateY(0)}
.fab{position:fixed;bottom:20px;right:16px;width:50px;height:50px;background:#1d6fc4;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:24px;cursor:pointer;z-index:150;box-shadow:0 4px 16px rgba(29,111,196,.4);border:none;color:#fff}
.fab:active{transform:scale(.92)}
.empty{text-align:center;padding:40px 20px;color:var(--muted)}
.empty i{font-size:36px;display:block;margin-bottom:10px;opacity:.35}
.list-wrap{padding:0 0 90px}
.list-hdr{display:flex;align-items:center;justify-content:space-between;padding:12px 14px 8px}
.list-hdr h2{font-size:14px;font-weight:700}
.sort-btn{background:var(--surf);border:1px solid var(--border2);border-radius:9px;padding:6px 12px;font-size:11px;font-weight:600;cursor:pointer;color:var(--muted)}
"""


JS = r"""
const TODAY=new Date().toISOString().slice(0,10);
const CUTS=__CUTS__;
let DATA=__DATA__;
const C={rtr:{lbl:'RTR',cls:'b-rtr',col:'var(--rtr)',bg:'var(--rtr-bg)',b:'var(--rtr-b)',dot:'var(--rtr-dot)'},reply:{lbl:'Reply Now',cls:'b-rep',col:'var(--rep)',bg:'var(--rep-bg)',b:'var(--rep-b)',dot:'var(--rep-dot)'},outreach:{lbl:'Remote Role',cls:'b-out',col:'var(--out)',bg:'var(--out-bg)',b:'var(--out-b)',dot:'var(--out-dot)'},interview:{lbl:'Interview',cls:'b-int',col:'var(--int)',bg:'var(--int-bg)',b:'var(--int-b)',dot:'var(--int-dot)'},assessment:{lbl:'Assessment',cls:'b-ass',col:'var(--ass)',bg:'var(--ass-bg)',b:'var(--ass-b)',dot:'var(--ass-dot)'},followup:{lbl:'Follow-up',cls:'b-fol',col:'var(--fol)',bg:'var(--fol-bg)',b:'var(--fol-b)',dot:'var(--fol-dot)'}};
function Cg(c){return C[c]||{lbl:c,cls:'',col:'var(--muted)',bg:'var(--bg)',b:'var(--border2)',dot:'var(--hint)'};}
const RC={cyber:{dot:'var(--cyber)',bg:'var(--cyber-bg)',b:'var(--cyber-b)',lbl:'Shield Cyber'},devops:{dot:'var(--devops)',bg:'var(--devops-bg)',b:'var(--devops-b)',lbl:'Gear DevOps'},ai:{dot:'var(--ai)',bg:'var(--ai-bg)',b:'var(--ai-b)',lbl:'Brain AI/ML'},data:{dot:'var(--data)',bg:'var(--data-bg)',b:'var(--data-b)',lbl:'Chart Data/FS'},other:{dot:'var(--hint)',bg:'var(--bg)',b:'var(--border2)',lbl:'Folder Other'}};
const ROLE_ORDER=['cyber','devops','ai','data','other'];
const MO=['January','February','March','April','May','June','July','August','September','October','November','December'];
const DW=['Su','Mo','Tu','We','Th','Fr','Sa'];
const DWF=['Sun','Mon','Tue','Wed','Thu','Fri','Sat'];
const TAB2CAT={rtr:'rtr',rep:'reply',out:'outreach',int:'interview',ass:'assessment',fol:'followup'};
const TAB_CLS={all:'a-all',cal:'a-cal',rtr:'a-rtr',rep:'a-rep',out:'a-out',int:'a-int',ass:'a-ass',fol:'a-fol',co:'a-co'};
const CC_CLS={all:'a-all',rtr:'a-rtr',reply:'a-rep',outreach:'a-out',interview:'a-int',assessment:'a-ass',followup:'a-fol'};
let curTab='all',calMode='all',sortAsc=false,roleFilter='all';
let calY=new Date().getFullYear(),calM=new Date().getMonth(),selDay=TODAY;
let editIdx=null,openRow=null,toastT=null;
if(CUTS.auto_deleted>0)document.getElementById('disclaimer').classList.add('show');
function updateStats(){const a=DATA.filter(r=>r.st!=='deleted');document.getElementById('n-rtr').textContent=a.filter(r=>r.cat==='rtr').length;document.getElementById('n-rep').textContent=a.filter(r=>r.cat==='reply').length;document.getElementById('n-out').textContent=a.filter(r=>r.cat==='outreach').length;document.getElementById('n-int').textContent=a.filter(r=>r.cat==='interview').length;}
function setTab(t){
curTab=t;roleFilter='all';
document.querySelectorAll('#topTabs .tab').forEach(el=>el.className='tab');
const el=document.getElementById('t-'+t);if(el)el.className='tab '+(TAB_CLS[t]||'a-all');
const isCal=t==='cal',isCo=t==='co',isAll=t==='all';
const showRF=['rtr','out','int','ass','fol','rep'].includes(t)&&!isCal&&!isCo&&!isAll;
document.getElementById('catCalRow').classList.toggle('show',isCal);
document.getElementById('roleFilterBar').classList.toggle('show',showRF);
document.getElementById('vStats').style.display=isAll?'block':'none';
document.getElementById('disclaimer').style.display=isAll?'':'none';
document.getElementById('vCal').style.display=isCal?'block':'none';
document.getElementById('vList').style.display=(!isCal&&!isCo&&!isAll)?'block':'none';
document.getElementById('vCo').style.display=isCo?'block':'none';
const tl=document.getElementById('lstTitle');
if(tl)tl.textContent={rtr:'RTR Submissions',rep:'Reply Needed â Act Now',out:'Remote Roles',int:'Interviews',ass:'Assessments',fol:'Follow-ups'}[t]||t;
document.querySelectorAll('.rf-pill').forEach(p=>p.classList.remove('active'));
const ap=document.getElementById('rf-all');if(ap)ap.classList.add('active');
if(isCal){renderMo();renderStrip();renderTL();}else if(isCo)renderCo();else if(!isAll)renderBands();
}
function setRoleCatFilter(rc){roleFilter=rc;document.querySelectorAll('.rf-pill').forEach(p=>p.classList.remove('active'));const el=document.getElementById('rf-'+rc);if(el)el.classList.add('active');renderBands();}
function setCal(cc){calMode=cc;document.querySelectorAll('#catCalRow .tab').forEach(el=>el.className='tab');const ccId={all:'cc-all',rtr:'cc-rtr',reply:'cc-rep',outreach:'cc-out',interview:'cc-int',assessment:'cc-ass',followup:'cc-fol'}[cc]||'cc-all';const el=document.getElementById(ccId);if(el)el.className='tab '+(CC_CLS[cc]||'a-all');renderMo();renderStrip();renderTL();}
function calFilter(){return calMode==='all'?null:calMode;}
function getFiltered(catOverride){
const q=(document.getElementById('srch').value||'').toLowerCase();
const cf=catOverride!==undefined?catOverride:TAB2CAT[curTab]||null;
let rows=DATA.filter(r=>{
if(r.st==='deleted')return false;
if(cf&&r.cat!==cf)return false;
if(roleFilter!=='all'&&r.role_cat!==roleFilter)return false;
if(q&&!JSON.stringify(r).toLowerCase().includes(q))return false;
return true;
});
rows.sort((a,b)=>{
const ro=ROLE_ORDER.indexOf(a.role_cat||'other')-ROLE_ORDER.indexOf(b.role_cat||'other');
if(ro!==0)return ro;
return sortAsc?(a.det||'').localeCompare(b.det||''):(b.det||'').localeCompare(a.det||'');
});
return rows;
}
function getFiltered3day(cat){
const q=(document.getElementById('srch').value||'').toLowerCase();
const rows=DATA.filter(r=>{
if(r.st==='deleted')return false;
if(r.cat!==cat)return false;
if(q&&!JSON.stringify(r).toLowerCase().includes(q))return false;
return true;
});
rows.sort((a,b)=>{
if(cat==='reply'){if(a.wom&&!b.wom)return -1;if(!a.wom&&b.wom)return 1;}
const ro=ROLE_ORDER.indexOf(a.role_cat||'other')-ROLE_ORDER.indexOf(b.role_cat||'other');
if(ro!==0)return ro;
const aH=(a.ph?2:0)+(a.em?1:0),bH=(b.ph?2:0)+(b.em?1:0);
if(aH!==bH)return bH-aH;
return(b.det||'').localeCompare(a.det||'');
});
return rows;
}
function e(s){return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');}
function fdt(det){
if(!det)return{date:'â',time:''};
const[d,t]=(det+' ').split(' ');
if(!d)return{date:'â',time:''};
const[yr,mo,dy]=d.split('-');
const mn=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'][(parseInt(mo)||1)-1]||mo;
let ts='';
if(t&&t.length>1){const[hh,mm]=t.split(':');const h=parseInt(hh)||0;ts=(h%12||12)+':'+(mm||'00')+(h>=12?' PM':' AM');}
return{date:mn+' '+parseInt(dy)+', '+yr,time:ts};
}
function rcDot(rc){const i=RC[rc||'other']||RC.other;return '<span class="role-cat-dot" style="background:'+i.dot+'" title="'+i.lbl+'"></span>';}
function renderBands(){
const cf=TAB2CAT[curTab]||null;
let focusHTML='';
if((curTab==='out'||curTab==='rep')&&cf){
const recent=getFiltered3day(cf).filter(r=>(r.det||'').slice(0,10)>=CUTS.d3);
if(recent.length){
const rowsHTML=recent.slice(0,12).map(r=>{const dt=fdt(r.det);return '<div class="focus-row">'+(r.ph?'<span class="fr-ph"><i class="ti ti-phone" style="font-size:11px"></i> '+e(r.ph)+'</span>':'')+(r.em?'<span class="fr-em">'+e(r.em)+'</span>':'')+'<span class="fr-role">'+rcDot(r.role_cat)+e(r.role||r.subj.slice(0,45))+'</span><span class="fr-date">'+e(dt.date)+(dt.time?' '+e(dt.time):'')+'</span></div>';}).join('');
focusHTML='<div class="focus-strip"><h4>Last 3 Days â Sorted by Phone/Email</h4>'+rowsHTML+'</div>';
}
}
const fs=document.getElementById('focusStrip');fs.innerHTML=focusHTML;fs.style.display=focusHTML?'block':'none';
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
}
function renderBandRows(tbodyId,emptyId,rows){
const tbody=document.getElementById(tbodyId),empty=document.getElementById(emptyId);
if(!rows.length){tbody.innerHTML='';empty.style.display='block';return;}
empty.style.display='none';
tbody.innerHTML=rows.map(r=>buildRow(r)).join('');
}
function buildRow(r){
const c=Cg(r.cat),ov=r.fup&&r.fup<TODAY,td=r.fup===TODAY;
const fc=ov?'fup ov':td?'fup td':'fup';
const ft=r.fup?(ov?'â  ':'ð ')+r.fup:'â';
const locP=r.loc==='remote'?'<span class="pill p-remote">ð Remote</span>':r.loc==='hybrid'?'<span class="pill p-hybrid">ð Hybrid</span>':'';
const rateP=r.rate?'<span class="pill p-rate">ð° '+e(r.rate)+'</span>':'';
const callBtn=r.ph?'<a href="tel:'+e(r.ph)+'" class="ra ra-c" onclick="event.stopPropagation()"><i class="ti ti-phone"></i></a>':'';
const idx=DATA.indexOf(r),dt=fdt(r.det);
const wom=r.wom&&r.cat==='reply'?'<div class="wom-badge">ð´ Waiting on You</div>':'';
const jdPrev=r.jd?'<div class="det-sm" style="margin-top:3px"><strong>JD</strong><span>'+e((r.jd||'').slice(0,70))+'â¦</span></div>':'';
const lsBox=r.last_sent?'<div class="last-sent-box"><div class="ls-lbl">ð¤ Last Sent</div>'+e(r.last_sent)+'</div>':'';
return '<tr onclick="toggleRow('+r.id+',this,'+r.id+')" id="tr'+r.id+'">'
+'<td><span class="badge '+c.cls+'">'+e(c.lbl)+'</span><div style="font-size:10px;color:var(--muted);margin-top:3px">'+e(r.acc)+'</div></td>'
+'<td><div class="role-title">'+rcDot(r.role_cat)+e(r.role||r.subj.slice(0,60))+'</div><div class="role-co">'+e(r.co||'')+'</div><div style="margin-top:3px">'+locP+rateP+'</div>'+wom+'<div class="row-acts">'+callBtn+'<button class="ra ra-e" onclick="event.stopPropagation();openEditModal('+idx+')"><i class="ti ti-edit"></i></button><button class="ra ra-d" onclick="event.stopPropagation();deleteItem('+idx+')"><i class="ti ti-trash"></i></button></div></td>'
+'<td>'+(r.ph?'<div class="rec-phone"><i class="ti ti-phone" style="font-size:11px"></i> '+e(r.ph)+'</div>':'')+'<div class="rec-email">'+e(r.em||'')+'</div><div class="rec-name">'+e(r.rec||'â')+'</div><div class="rec-date">'+e(dt.date)+'</div>'+(dt.time?'<div class="rec-time">'+e(dt.time)+'</div>':'')+'</td>'
+'<td>'+(r.co?'<div class="det-sm"><strong>Client</strong>'+e(r.co)+'</div>':'')+(r.sk?'<div class="det-sm"><strong>Skills</strong><span>'+e(r.sk.slice(0,80))+'</span></div>':'')+jdPrev+lsBox+'</td>'
+'<td><div class="'+fc+'">'+e(ft)+'</div></td>'
+'</tr>'
+'<tr class="exp-row" id="exp'+r.id+'" style="display:none"><td colspan="5" style="padding:0"><div class="exp-inner">'
+'<div class="dl"><b>Subject</b><span>'+e(r.subj)+'</span></div>'
+(r.sk?'<div class="dl"><b>Skills</b>'+e(r.sk)+'</div>':'')
+(r.rate?'<div class="dl"><b>Rate</b><span style="color:var(--int)">'+e(r.rate)+'</span></div>':'')
+(r.jd?'<div class="jd-box"><div class="jd-lbl">Job Description / Summary</div>'+e(r.jd)+'</div>':'')
+(r.last_sent?'<div class="last-sent-box"><div class="ls-lbl">ð¤ Last Sent Message</div>'+e(r.last_sent)+'</div>':'')
+'<div class="dl"><b>Account</b>'+e(r.acc)+'</div>'
+'<div class="dl"><b>Role Type</b><span>'+(RC[r.role_cat||'other']||RC.other).lbl+'</span></div>'
+'</div></td></tr>';
}
function toggleBand(id){const hdr=document.querySelector('#'+id+' .band-hdr'),body=document.querySelector('#'+id+' .band-body'),chev=document.querySelector('#'+id+' .chev'),isOpen=body.classList.contains('open');body.classList.toggle('open',!isOpen);hdr.classList.toggle('open',!isOpen);chev.className='ti '+(isOpen?'ti-chevron-down':'ti-chevron-up')+' chev';}
function toggleRow(id,tr,uid){const exp=document.getElementById('exp'+uid);if(openRow===uid){exp.style.display='none';tr.classList.remove('sel');openRow=null;return;}if(openRow){const pe=document.getElementById('exp'+openRow);if(pe)pe.style.display='none';document.querySelectorAll('.tbl tbody tr.sel').forEach(t=>t.classList.remove('sel'));}exp.style.display='table-row';tr.classList.add('sel');openRow=uid;}
function doSearch(){document.getElementById('clrBtn').style.display=document.getElementById('srch').value?'inline':'none';renderBands();}
function clearSrch(){document.getElementById('srch').value='';document.getElementById('clrBtn').style.display='none';renderBands();}
function toggleSort(){sortAsc=!sortAsc;document.getElementById('sortB').textContent=sortAsc?'Oldest':'Newest';renderBands();}
function evMap(){const cf=calFilter(),m={};DATA.filter(r=>r.st!=='deleted'&&(!cf||r.cat===cf)).forEach(r=>{[(r.det||''),(r.fup||'')].filter(Boolean).forEach(dt=>{const d=dt.slice(0,10),[yr,mo]=d.split('-').map(Number);if(yr===calY&&mo-1===calM){if(!m[d])m[d]=[];m[d].push(r);}});});return m;}
function evForDay(ds){const cf=calFilter();return DATA.filter(r=>r.st!=='deleted'&&(!cf||r.cat===cf)&&((r.det||'').slice(0,10)===ds||(r.fup||'').slice(0,10)===ds));}
function renderMo(){const ccL={all:'All',rtr:'RTR',reply:'Reply Needed',outreach:'Remote',interview:'Interviews',assessment:'Assessments',followup:'Follow-ups'};document.getElementById('calLbl').textContent=MO[calM]+' '+calY+' â '+(ccL[calMode]||'');const first=new Date(calY,calM,1).getDay(),days=new Date(calY,calM+1,0).getDate(),em=evMap();let h=DW.map(d=>'<div class="dow">'+d+'</div>').join('');for(let i=0;i<first;i++)h+='<div class="cd empty"></div>';for(let d=1;d<=days;d++){const ds=calY+'-'+String(calM+1).padStart(2,'0')+'-'+String(d).padStart(2,'0'),evs=em[ds]||[],cats=[...new Set(evs.map(r=>r.cat))],isT=ds===TODAY,isS=ds===selDay;h+='<div class="cd'+(isT?' today':'')+(isS?' sel':'')+'" onclick="selectDay(''+ds+'')"><div class="cd-n">'+d+'</div><div class="cd-dots">'+cats.map(c=>'<div class="dot" style="background:'+Cg(c).dot+'"></div>').join('')+'</div>'+(evs.length?'<div class="cd-cnt">'+evs.length+'</div>':'')+'</div>';}document.getElementById('moGrid').innerHTML=h;}
function calPrev(){calM--;if(calM<0){calM=11;calY--;}renderMo();renderStrip();}
function calNext(){calM++;if(calM>11){calM=0;calY++;}renderMo();renderStrip();}
function goToday(){calY=new Date().getFullYear();calM=new Date().getMonth();selDay=TODAY;renderMo();renderStrip();renderTL();}
function selectDay(ds){selDay=ds;const[yr,mo]=ds.split('-').map(Number);if(yr!==calY||mo-1!==calM){calY=yr;calM=mo-1;}renderMo();renderStrip();renderTL();}
function renderStrip(){const strip=document.getElementById('dayStrip'),em=evMap(),ctr=new Date(selDay+'T12:00:00'),days=[];for(let i=-7;i<=14;i++){const d=new Date(ctr);d.setDate(d.getDate()+i);days.push(d);}strip.innerHTML=days.map(d=>{const ds=d.toISOString().slice(0,10),evs=em[ds]||[],cats=[...new Set(evs.map(r=>r.cat))],isT=ds===TODAY,isSel=ds===selDay;return'<div class="ds'+(isT?' tod':'')+(isSel?' sel':'')+'" onclick="selectDay(''+ds+'')" id="dsd-'+ds+'"><div class="ds-dow">'+DWF[d.getDay()]+'</div><div class="ds-d">'+d.getDate()+'</div><div class="ds-dots">'+cats.slice(0,4).map(c=>'<div class="ds-dot" style="background:'+(isSel?'rgba(255,255,255,.7)':Cg(c).dot)+'"></div>').join('')+'</div></div>';}).join('');setTimeout(()=>{const el=document.getElementById('dsd-'+selDay);if(el)el.scrollIntoView({behavior:'smooth',block:'nearest',inline:'center'});},50);}
function renderTL(){const evs=evForDay(selDay),d=new Date(selDay+'T12:00:00'),lbl=selDay===TODAY?'Today â '+d.toLocaleDateString('en-US',{weekday:'long',month:'long',day:'numeric'}):d.toLocaleDateString('en-US',{weekday:'long',month:'long',day:'numeric',year:'numeric'});document.getElementById('dayHdrLbl').textContent=lbl;document.getElementById('dayCnt').textContent=evs.length+' event'+(evs.length!==1?'s':'');const timedEvs=evs.filter(r=>(r.det||'').slice(0,10)===selDay),fupEvs=evs.filter(r=>(r.fup||'').slice(0,10)===selDay&&(r.det||'').slice(0,10)!==selDay),aw=document.getElementById('alldayWrap');if(fupEvs.length){aw.style.display='block';document.getElementById('alldayBody').innerHTML=fupEvs.map(r=>{const c=Cg(r.cat);return'<div class="allday-ev" style="border-color:'+c.col+';background:'+c.bg+'" onclick="openEditModal('+DATA.indexOf(r)+')"><div style="flex:1;min-width:0"><div style="font-size:10px;font-weight:700;color:'+c.col+';margin-bottom:1px">'+c.lbl+' â follow-up due</div><div style="font-size:12px;font-weight:600;line-height:1.3">'+e(r.role||r.subj.slice(0,55))+'</div><div style="font-size:10px;color:var(--muted)">'+e(r.rec)+' Â· '+e(r.em)+'</div></div>'+(r.ph?'<a href="tel:'+e(r.ph)+'" style="font-size:11px;color:var(--int);text-decoration:none;font-weight:700;flex-shrink:0" onclick="event.stopPropagation()"><i class="ti ti-phone"></i></a>':'')+'</div>';}).join('');}else{aw.style.display='none';}timedEvs.sort((a,b)=>(a.det||'').localeCompare(b.det||''));const tl=document.getElementById('timeline');if(!timedEvs.length&&!fupEvs.length){tl.innerHTML='<div class="no-evs"><i class="ti ti-calendar-off"></i><p>No events on this day</p></div>';return;}if(!timedEvs.length){tl.innerHTML='';return;}const hourEvs={};timedEvs.forEach(r=>{const tp=(r.det||'').split(' ')[1]||'08:00',hr=Math.max(6,Math.min(22,parseInt(tp)));if(!hourEvs[hr])hourEvs[hr]=[];hourEvs[hr].push(r);});const now=new Date(),nowHr=now.getHours()+now.getMinutes()/60,isToday=selDay===TODAY;let html='';for(let hr=6;hr<=22;hr++){const lbl2=hr===12?'12 PM':hr<12?(hr+' AM'):((hr-12)+' PM'),evH=(hourEvs[hr]||[]).map(r=>{const c=Cg(r.cat),tp=((r.det||'').split(' ')[1]||'').slice(0,5),locP=r.loc==='remote'?'<span class="ep" style="color:var(--out);border-color:var(--out-b);background:var(--out-bg)">Remote</span>':r.loc==='hybrid'?'<span class="ep" style="color:var(--rtr);border-color:var(--rtr-b);background:var(--rtr-bg)">Hybrid</span>':'',rateP=r.rate?'<span class="ep" style="color:var(--int);border-color:var(--int-b);background:var(--int-bg)">'+e(r.rate)+'</span>':'';return'<div class="ev" style="border-color:'+c.col+';background:'+c.bg+'" onclick="openEditModal('+DATA.indexOf(r)+')"><div class="ev-cat" style="color:'+c.col+'">'+c.lbl+' Â· '+tp+'</div><div class="ev-title">'+e(r.role||r.subj.slice(0,60))+'</div><div class="ev-meta">'+e(r.rec||'')+'</div>'+(r.co?'<div class="ev-meta">'+e(r.co)+'</div>':'')+'<div class="ev-pills">'+locP+rateP+(r.ph?'<a href="tel:'+e(r.ph)+'" class="ep" style="color:var(--int);border-color:var(--int-b);background:var(--int-bg);text-decoration:none" onclick="event.stopPropagation()"><i class="ti ti-phone" style="font-size:10px"></i> '+e(r.ph)+'</a>':'')+'</div></div>';}).join('');let nowH='';if(isToday&&nowHr>=hr&&nowHr<hr+1){const pct=(nowHr-hr)*100;nowH='<div class="now-line" style="top:'+pct+'%"><div class="now-dot"></div><div class="now-badge">'+now.getHours()+':'+String(now.getMinutes()).padStart(2,'0')+'</div></div>';}html+='<div class="ts"><div class="tl-lbl">'+lbl2+'</div><div class="tl-evs"><div class="tl-line"></div>'+nowH+evH+'</div></div>';}tl.innerHTML=html;}
function toggleCo(i){const el=document.getElementById('ce'+i);if(el)el.classList.toggle('open');}
function renderCo(){const cos={};DATA.filter(r=>r.st!=='deleted'&&r.co).forEach(r=>{if(!cos[r.co])cos[r.co]={evs:[],lat:''};cos[r.co].evs.push(r);if((r.det||'')>cos[r.co].lat)cos[r.co].lat=r.det||'';});const sorted=Object.entries(cos).sort((a,b)=>b[1].lat.localeCompare(a[1].lat));document.getElementById('coBody').innerHTML=sorted.length?sorted.map(([name,d],i)=>{const cats=[...new Set(d.evs.map(r=>r.cat))],pills=cats.map(c=>'<span class="badge '+Cg(c).cls+'">'+Cg(c).lbl+'</span>').join(' '),evs=d.evs.sort((a,b)=>(b.det||'').localeCompare(a.det||'')).map(r=>{const dt=fdt(r.det);return'<div class="co-ev"><div style="width:3px;border-radius:2px;flex-shrink:0;background:'+Cg(r.cat).dot+';min-height:28px;margin-top:2px"></div><div><div style="font-size:12px;font-weight:600">'+e(r.role||r.subj.slice(0,60))+'</div><div style="font-size:10px;color:var(--muted)">'+e(dt.date)+(dt.time?' '+e(dt.time):'')+'&nbsp;Â·&nbsp;'+e(r.rec)+' Â· '+Cg(r.cat).lbl+'</div></div></div>';}).join('');return'<div class="co-card"><div class="co-hdr" onclick="toggleCo('+i+')"><div class="co-icon">ð¢</div><div style="flex:1;min-width:0"><div style="font-weight:700;font-size:13px">'+e(name)+'</div><div style="font-size:10px;color:var(--muted);margin-top:1px">'+d.evs.length+' events Â· '+(d.lat||'').slice(0,10)+'</div><div style="margin-top:4px;display:flex;flex-wrap:wrap;gap:3px">'+pills+'</div></div><i class="ti ti-chevron-down" style="color:var(--hint);font-size:16px;flex-shrink:0"></i></div><div class="co-events" id="ce'+i+'">'+evs+'</div></div>';}).join(''):'<div class="empty" style="padding:40px 20px"><i class="ti ti-building"></i><p>No companies tracked yet</p></div>';}
function openEditModal(idx){editIdx=idx;const r=DATA[idx];document.getElementById('mTitle').textContent='Edit entry';document.getElementById('mBody').innerHTML=buildForm(r);document.getElementById('overlay').classList.add('open');document.getElementById('modal').classList.add('open');}
function openAddModal(){editIdx=null;document.getElementById('mTitle').textContent='Add entry';document.getElementById('mBody').innerHTML=buildForm(null);document.getElementById('overlay').classList.add('open');document.getElementById('modal').classList.add('open');}
function buildForm(r){const v=(f,d='')=>r?(r[f]||d):d,s=(f,val)=>v(f)===val?'selected':'';return'<div class="field"><label>Category</label><select id="e-cat"><option value="rtr" '+s('cat','rtr')+'>RTR</option><option value="reply" '+s('cat','reply')+'>Reply Needed</option><option value="outreach" '+s('cat','outreach')+'>Remote Role</option><option value="interview" '+s('cat','interview')+'>Interview</option><option value="assessment" '+s('cat','assessment')+'>Assessment</option><option value="followup" '+s('cat','followup')+'>Follow-up</option></select></div><div class="field"><label>Role title</label><input id="e-role" value="'+e(v('role'))+'" placeholder="Cloud Security Engineer"></div><div class="field"><label>Recruiter</label><input id="e-rec" value="'+e(v('rec'))+'" placeholder="Jane Smith"></div><div class="field"><label>Email</label><input id="e-em" value="'+e(v('em'))+'" placeholder="jane@company.com"></div><div class="field"><label>Company / Client</label><input id="e-co" value="'+e(v('co'))+'" placeholder="Bloombergâ¦"></div><div class="field"><label>Rate</label><input id="e-rate" value="'+e(v('rate'))+'" placeholder="$70/hr W2"></div><div class="field"><label>Phone</label><input id="e-ph" value="'+e(v('ph'))+'" placeholder="646-820-3671"></div><div class="field"><label>Location</label><select id="e-loc"><option value="remote" '+s('loc','remote')+'>Remote</option><option value="hybrid" '+s('loc','hybrid')+'>Hybrid</option><option value="onsite" '+s('loc','onsite')+'>Onsite</option></select></div><div class="field"><label>Follow-up due</label><input type="date" id="e-fup" value="'+v('fup')+'"></div><div class="field"><label>Last Sent Message</label><textarea id="e-ls" placeholder="What did you last sendâ¦">'+e(v('last_sent'))+'</textarea></div><div class="field"><label>JD Summary</label><textarea id="e-jd" placeholder="Job description summaryâ¦">'+e(v('jd'))+'</textarea></div><div class="field"><label>Status</label><select id="e-st"><option value="open" '+s('st','open')+'>Open</option><option value="done" '+s('st','done')+'>Done</option></select></div>';}
function closeModal(){document.getElementById('overlay').classList.remove('open');document.getElementById('modal').classList.remove('open');editIdx=null;}
function saveEdit(){const vals={cat:document.getElementById('e-cat').value,role:document.getElementById('e-role').value,rec:document.getElementById('e-rec').value,em:document.getElementById('e-em').value,co:document.getElementById('e-co').value,rate:document.getElementById('e-rate').value,ph:document.getElementById('e-ph').value,loc:document.getElementById('e-loc').value,fup:document.getElementById('e-fup').value,last_sent:document.getElementById('e-ls').value,jd:document.getElementById('e-jd').value,st:document.getElementById('e-st').value};if(editIdx!==null){Object.assign(DATA[editIdx],vals);showToast('Saved');}else{DATA.unshift({id:Date.now()%1e15,det:new Date().toISOString().slice(0,16).replace('T',' '),subj:vals.role,role_cat:'other',wom:false,...vals});showToast('Added');}updateStats();if(curTab==='cal'){renderMo();renderStrip();renderTL();}else if(curTab!=='all')renderBands();if(curTab==='co')renderCo();closeModal();}
function deleteItem(idx){DATA[idx].st='deleted';updateStats();renderBands();showToast('Deleted');}
function showToast(m){const t=document.getElementById('toast');t.textContent=m;t.classList.add('show');clearTimeout(toastT);toastT=setTimeout(()=>t.classList.remove('show'),2500);}
updateStats();setTab('all');setTimeout(()=>location.reload(),15*60*1000);
"""


# ââ Assemble and write HTML âââââââââââââââââââââââââââââââââââââââ
js_final = JS.replace('__CUTS__', cutoff_vars).replace('__DATA__', rows_json)


_parts = []
_parts.append('<!DOCTYPE html>\n<html lang="en">\n<head>\n')
_parts.append('<meta charset="UTF-8">\n')
_parts.append('<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1">\n')
_parts.append('<title>Job Campaign HQ</title>\n')
_parts.append('<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@tabler/icons-webfont@3.19.0/dist/tabler-icons.min.css">\n')
_parts.append('<style>\n')
_parts.append(CSS)
_parts.append('</style>\n</head>\n<body>\n')
_parts.append('<div class="hdr"><div class="hdr-top"><div>')
_parts.append('<h1>Job Campaign <em>HQ</em></h1>')
_parts.append('<div class="upd">Updated ' + updated + ' &middot; auto-refresh 15 min</div>')
_parts.append('</div><i class="ti ti-chart-bar" style="font-size:22px;color:var(--muted)"></i></div>')
_parts.append('<div class="search"><i class="ti ti-search" style="color:var(--hint);font-size:15px"></i>')
_parts.append('<input type="text" id="srch" placeholder="Search role, recruiter, company, email&hellip;" oninput="doSearch()">')
_parts.append('<span id="clrBtn" onclick="clearSrch()" style="cursor:pointer;font-size:11px;color:var(--hint);display:none">&times;</span></div></div>')
_parts.append('<div class="tab-wrap">')
_parts.append('<div class="tabs" id="topTabs">')
_parts.append('<div class="tab a-all" id="t-all" onclick="setTab(\'all\')">All</div>')
_parts.append('<div class="tab" id="t-cal" onclick="setTab(\'cal\')">&#128197; Calendar</div>')
_parts.append('<div class="tab" id="t-rtr" onclick="setTab(\'rtr\')">&#128203; RTR</div>')
_parts.append('<div class="tab" id="t-rep" onclick="setTab(\'rep\')">&#9889; Reply Needed</div>')
_parts.append('<div class="tab" id="t-out" onclick="setTab(\'out\')">&#127760; Remote</div>')
_parts.append('<div class="tab" id="t-int" onclick="setTab(\'int\')">&#128222; Interviews</div>')
_parts.append('<div class="tab" id="t-ass" onclick="setTab(\'ass\')">&#129514; Assessments</div>')
_parts.append('<div class="tab" id="t-fol" onclick="setTab(\'fol\')">&#9203; Follow-ups</div>')
_parts.append('<div class="tab" id="t-co" onclick="setTab(\'co\')">&#127970; Companies</div>')
_parts.append('</div>')
_parts.append('<div class="role-filter-bar" id="roleFilterBar">')
_parts.append('<div class="rf-pill rf-all active" id="rf-all" onclick="setRoleCatFilter(\'all\')">&#11088; All</div>')
_parts.append('<div class="rf-pill rf-cyber" id="rf-cyber" onclick="setRoleCatFilter(\'cyber\')">&#128737; Cyber</div>')
_parts.append('<div class="rf-pill rf-devops" id="rf-devops" onclick="setRoleCatFilter(\'devops\')">&#9881; DevOps</div>')
_parts.append('<div class="rf-pill rf-ai" id="rf-ai" onclick="setRoleCatFilter(\'ai\')">&#129504; AI/ML</div>')
_parts.append('<div class="rf-pill rf-data" id="rf-data" onclick="setRoleCatFilter(\'data\')">&#128202; Data/FS</div>')
_parts.append('<div class="rf-pill rf-other" id="rf-other" onclick="setRoleCatFilter(\'other\')">&#128193; Other</div>')
_parts.append('</div>')
_parts.append('<div class="cat-cal-row" id="catCalRow">')
_parts.append('<div class="tab a-all" id="cc-all" onclick="setCal(\'all\')">All</div>')
_parts.append('<div class="tab" id="cc-rtr" onclick="setCal(\'rtr\')">RTR</div>')
_parts.append('<div class="tab" id="cc-rep" onclick="setCal(\'reply\')">Reply</div>')
_parts.append('<div class="tab" id="cc-out" onclick="setCal(\'outreach\')">Remote</div>')
_parts.append('<div class="tab" id="cc-int" onclick="setCal(\'interview\')">Interviews</div>')
_parts.append('<div class="tab" id="cc-ass" onclick="setCal(\'assessment\')">Assessments</div>')
_parts.append('<div class="tab" id="cc-fol" onclick="setCal(\'followup\')">Follow-ups</div>')
_parts.append('</div></div>')
_parts.append('<div class="disclaimer" id="disclaimer">&#8505; <strong>Auto-cleanup:</strong> ')
_parts.append(str(auto_deleted) + ' record(s) removed (&gt;60 days). Data preserved in <code>data/rtr_followup_tracker.csv</code>.</div>')
_parts.append('<div id="vStats"><div class="stats">')
_parts.append('<div class="stat s-rtr" onclick="setTab(\'rtr\')"><div class="num" id="n-rtr">0</div><div class="lbl">&#128203; RTRs</div></div>')
_parts.append('<div class="stat s-rep" onclick="setTab(\'rep\')"><div class="num" id="n-rep">0</div><div class="lbl">&#9889; Reply Needed</div></div>')
_parts.append('<div class="stat s-out" onclick="setTab(\'out\')"><div class="num" id="n-out">0</div><div class="lbl">&#127760; Remote</div></div>')
_parts.append('<div class="stat s-int" onclick="setTab(\'int\')"><div class="num" id="n-int">0</div><div class="lbl">&#128222; Interviews</div></div>')
_parts.append('</div></div>')
_parts.append('<div id="vCal" style="display:none">')
_parts.append('<div class="cal-chrome"><div class="cal-nav-row">')
_parts.append('<button class="cal-btn" onclick="calPrev()"><i class="ti ti-arrow-left"></i></button>')
_parts.append('<h2 id="calLbl"></h2>')
_parts.append('<div style="display:flex;gap:5px"><button class="cal-btn today" onclick="goToday()">Today</button>')
_parts.append('<button class="cal-btn" onclick="calNext()"><i class="ti ti-arrow-right"></i></button></div>')
_parts.append('</div><div class="month-box"><div id="moGrid" class="mo-grid"></div></div></div>')
_parts.append('<div class="day-strip" id="dayStrip"></div>')
_parts.append('<div class="day-tl"><div class="day-hdr"><h3 id="dayHdrLbl">Today</h3><span class="day-cnt" id="dayCnt">0 events</span></div>')
_parts.append('<div class="allday-wrap" id="alldayWrap" style="display:none"><div class="allday-lbl">Follow-ups due</div><div id="alldayBody"></div></div>')
_parts.append('<div class="timeline" id="timeline"></div></div></div>')
_parts.append('<div id="vList" style="display:none"><div class="list-wrap">')
_parts.append('<div class="list-hdr"><h2 id="lstTitle">Activity</h2><button class="sort-btn" id="sortB" onclick="toggleSort()">&darr; Newest</button></div>')
_parts.append('<div id="focusStrip" style="display:none"></div>')
_parts.append('<div class="section-band" id="band15"><div class="band-hdr open" onclick="toggleBand(\'band15\')">')
_parts.append('<h3><span style="width:10px;height:10px;border-radius:50%;background:#22c55e;display:inline-block"></span>&nbsp;Last 15 days <span class="bcnt" id="cnt15">0</span></h3>')
_parts.append('<i class="ti ti-chevron-up chev"></i></div><div class="band-body open" id="body15">')
_parts.append('<div class="tbl-wrap"><table class="tbl"><thead><tr><th>Category</th><th>Role</th><th>Recruiter</th><th>Details</th><th>Follow-up</th></tr></thead><tbody id="tbody15"></tbody></table></div>')
_parts.append('<div id="empty15" class="empty" style="display:none"><i class="ti ti-inbox"></i><p>No activity in last 15 days</p></div></div></div>')
_parts.append('<div class="section-band" id="band30" style="margin-top:8px"><div class="band-hdr" onclick="toggleBand(\'band30\')">')
_parts.append('<h3><span style="width:10px;height:10px;border-radius:50%;background:#f59e0b;display:inline-block"></span>&nbsp;15&ndash;30 days ago <span class="bcnt" id="cnt30">0</span></h3>')
_parts.append('<i class="ti ti-chevron-down chev"></i></div><div class="band-body" id="body30">')
_parts.append('<div class="tbl-wrap"><table class="tbl"><thead><tr><th>Category</th><th>Role</th><th>Recruiter</th><th>Details</th><th>Follow-up</th></tr></thead><tbody id="tbody30"></tbody></table></div>')
_parts.append('<div id="empty30" class="empty" style="display:none"><i class="ti ti-inbox"></i><p>No activity in 15-30 day range</p></div></div></div>')
_parts.append('<div class="section-band" id="band60" style="margin-top:8px"><div class="band-hdr" onclick="toggleBand(\'band60\')">')
_parts.append('<h3><span style="width:10px;height:10px;border-radius:50%;background:#6b7a99;display:inline-block"></span>&nbsp;30&ndash;60 days ago <span class="bcnt" id="cnt60">0</span></h3>')
_parts.append('<i class="ti ti-chevron-down chev"></i></div><div class="band-body" id="body60">')
_parts.append('<div class="tbl-wrap"><table class="tbl"><thead><tr><th>Category</th><th>Role</th><th>Recruiter</th><th>Details</th><th>Follow-up</th></tr></thead><tbody id="tbody60"></tbody></table></div>')
_parts.append('<div id="empty60" class="empty" style="display:none"><i class="ti ti-inbox"></i><p>No activity in 30-60 day range</p></div></div></div>')
_parts.append('<div style="height:80px"></div></div></div>')
_parts.append('<div id="vCo" style="display:none;padding:12px 0 90px"><div id="coBody"></div></div>')
_parts.append('<div class="overlay" id="overlay" onclick="closeModal()"></div>')
_parts.append('<div class="modal" id="modal"><div class="modal-handle"></div>')
_parts.append('<div class="modal-hdr"><h2 id="mTitle">Edit entry</h2></div>')
_parts.append('<div class="modal-body" id="mBody"></div>')
_parts.append('<div class="modal-acts"><button class="mbtn cancel" onclick="closeModal()">Cancel</button>')
_parts.append('<button class="mbtn save" onclick="saveEdit()">&#128190; Save</button></div></div>')
_parts.append('<div class="toast" id="toast"></div>')
_parts.append('<button class="fab" onclick="openAddModal()">&#xFF0B;</button>')
_parts.append('<script>\n')
_parts.append(js_final)
_parts.append('\n</scr' + 'ipt>\n</body>\n</html>')
html = ''.join(_parts)

with open(DASHBOARD_FILE, "w", encoding="utf-8") as f:
    f.write(html)

print(f"[Dashboard v12] {len(js_rows)} unique entries ({len(rows)-len(js_rows)} filtered/deduped)")
print(f"[Dashboard v12] Wrote {DASHBOARD_FILE} ({len(html):,} chars)")
print(f"[Dashboard v12] Live: https://eshwarjay0-dels.github.io/gmail-watcher/dashboard.html")

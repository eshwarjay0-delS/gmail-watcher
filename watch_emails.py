#!/usr/bin/env python3
"""
Gmail Watcher v9
- 30-day backfill on first run, UNSEEN-only after state exists
- Decodes encoded email subjects properly
- Clean WhatsApp messages (screenshot-style)
- Hybrid alerts only for Cyber roles
- All 6 categories → both WhatsApp + dashboard CSV
- Throttled to 25 WhatsApp/run with 2s gap
"""

import imaplib, email, email.header, re, json, os, time, base64, pickle, csv, traceback
from datetime import datetime, timedelta, date
from urllib.request import urlopen, Request
from urllib.parse import urlencode

try:
    from googleapiclient.discovery import build
    from google.auth.transport.requests import Request as GRequest
    CALENDAR_ENABLED = True
except ImportError:
    CALENDAR_ENABLED = False

try:
    import dateparser
    DATEPARSER_ENABLED = True
except ImportError:
    DATEPARSER_ENABLED = False

# =============================================================================
# CONFIG
# =============================================================================
TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN  = os.environ.get("TWILIO_AUTH_TOKEN", "")
TWILIO_FROM        = os.environ.get("TWILIO_FROM", "whatsapp:+14155238886")
TWILIO_TO          = os.environ.get("TWILIO_TO",   "whatsapp:+13142559156")
GOOGLE_TOKEN_B64   = os.environ.get("GOOGLE_TOKEN_B64", "")
GITHUB_TOKEN       = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPO        = os.environ.get("GITHUB_REPO", "")

WHATSAPP_PER_RUN_LIMIT = 25

BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
CSV_FILE   = os.path.join(BASE_DIR, "data", "rtr_followup_tracker.csv")
STATE_FILE = os.path.join(BASE_DIR, "data", "watcher_state.json")
os.makedirs(os.path.join(BASE_DIR, "data"), exist_ok=True)

ACCOUNTS = [
    {"email": "jayeshwar24@gmail.com", "password": os.environ.get("GMAIL_PASS_1", ""), "label": "Personal Cyber",  "is_cyber": True},
    {"email": "eshwarjay05@gmail.com", "password": os.environ.get("GMAIL_PASS_2", ""), "label": "GC Other",        "is_cyber": False},
    {"email": "eshwarjay06@gmail.com", "password": os.environ.get("GMAIL_PASS_3", ""), "label": "Cyber OPT",       "is_cyber": True},
    {"email": "eshwarjay0@gmail.com",  "password": os.environ.get("GMAIL_PASS_4", ""), "label": "OPT Other",       "is_cyber": False},
]

CALENDAR_SCOPES = ["https://www.googleapis.com/auth/calendar"]

# =============================================================================
# METRICS
# =============================================================================
_metrics = {
    "run_start": datetime.now().isoformat(),
    "emails_scanned": 0, "emails_classified": 0,
    "calendar_success": 0, "calendar_fail": 0,
    "whatsapp_success": 0, "whatsapp_fail": 0, "whatsapp_skipped": 0,
    "imap_errors": [], "errors": [],
}
_whatsapp_sent_this_run = 0

def record_error(context, exc):
    _metrics["errors"].append({
        "context": context, "error": str(exc),
        "trace": traceback.format_exc()[-600:],
        "time": datetime.now().isoformat(),
    })

# =============================================================================
# SUBJECT DECODER — fixes =?utf-8?B?...?= garbage
# =============================================================================
def decode_subject(raw_subject: str) -> str:
    if not raw_subject:
        return ""
    try:
        parts = email.header.decode_header(raw_subject)
        decoded = []
        for part, charset in parts:
            if isinstance(part, bytes):
                decoded.append(part.decode(charset or "utf-8", errors="replace"))
            else:
                decoded.append(str(part))
        return " ".join(decoded).strip()
    except Exception:
        return raw_subject

# =============================================================================
# HARD EXCLUSIONS
# =============================================================================
HARD_EXCLUDE = re.compile(
    r"unsubscribe|newsletter|no.?reply@linkedin|jobs-noreply@linkedin"
    r"|notifications@linkedin|noreply@indeed|jobalert|job alert"
    r"|new jobs for you|recommended jobs|people also viewed"
    r"|your profile was viewed|you appeared in"
    r"|congratulations.*connections|marketing@|promotions@"
    r"|noreply@|no-reply@|donotreply@|alert@|digest@"
    r"|updates@|info@linkedin|messages-noreply"
    r"|ziprecruiter\.com|glassdoor\.com|monster\.com|careerbuilder"
    r"|thank you for applying|thanks for applying|application received"
    r"|we received your application|your application has been"
    r"|application submitted|we.ll be in touch|we will be in touch"
    r"|under review|keep you posted|application is under"
    r"|no longer accepting|position has been filled|moved forward"
    r"|not moving forward|unfortunately|we regret|not selected"
    r"|auto.?reply|out of office|vacation reply|auto-response"
    r"|benchinfo|reqs@bench",  # bench info spam
    re.IGNORECASE
)

# =============================================================================
# CLASSIFICATION (threshold 12)
# =============================================================================
CATEGORY_KEYWORDS = {
    "rtr": [
        ("right to represent", 15), ("rtr ", 15), ("rtr:", 15), ("rtr-", 15),
        ("rate confirmation", 15), ("rate confirm", 15), ("rate_confirmation", 15),
        ("confirm the rate", 15), ("confirm rate", 12), ("resume shortlisted", 12),
        ("resume selected", 12), ("exclusive rights to represent", 15),
        ("grant.*represent", 12), ("submit your resume", 8), ("$/hr", 6),
        ("per hour", 5), ("all inclusive", 6), ("no benefits", 5),
        ("w2 rate", 8), ("c2c rate", 8),
    ],
    "reply_needed": [
        ("full name ?", 12), ("full name?", 12), ("legal name", 10),
        ("passport number", 10), ("passport no", 10), ("last four digit", 10),
        ("photo id", 10), ("ead copy", 10), ("visa copy", 10),
        ("please share the", 8), ("please provide", 8), ("kindly provide", 8),
        ("share the above details", 12), ("job seekers id", 12),
        ("still no resume", 12), ("awaiting your resume", 10),
        ("send your resume", 8), ("share your updated", 8),
        ("dob ?", 10), ("date of birth", 8), ("location?", 8),
        ("your availability", 8), ("convenient time", 8),
        ("schedule a time", 8), ("can you come", 8),
        ("mailing address", 8), ("current address", 8),
        ("immigration questionnaire", 12), ("ssn", 10),
    ],
    "outreach": [
        ("excellent opportunity", 8), ("exciting opportunity", 8),
        ("job opportunity", 8), ("opening for", 8), ("looking for", 7),
        ("urgent requirement", 8), ("immediate requirement", 8),
        ("hot requirement", 8), ("we have a role", 8),
        ("position available", 7), ("job description below", 8),
        ("find the jd", 7), ("find the job description", 8),
        ("kindly share your resume", 8), ("share your resume", 8),
        ("share updated resume", 8), ("let me know if.*interest", 7),
        ("if you are interested", 7), ("staffing specialist", 6),
        ("talent acquisition", 5), ("recruiting for", 7), ("hiring for", 7),
        ("reach out to you", 5), ("one of our clients", 8),
        ("our client", 6),
    ],
    "interview": [
        ("phone screen", 15), ("zoom interview", 15), ("teams interview", 15),
        ("google meet interview", 15), ("video interview", 15),
        ("invited to interview", 15), ("invitation to interview", 15),
        ("interview invitation", 15), ("schedule.*interview", 15),
        ("interview.*schedule", 15), ("technical round", 12),
        ("hr round", 12), ("panel interview", 12), ("onsite interview", 12),
        ("final round", 10), ("screening call", 12), ("first round", 10),
        ("second round", 10), ("we would like to interview", 15),
        ("calendar invite", 10), ("meeting invite", 8),
        ("interested in speaking", 8),
    ],
    "assessment": [
        ("coding challenge", 15), ("take-home", 15), ("hackerrank", 15),
        ("codility", 15), ("technical test", 12), ("aptitude test", 12),
        ("complete the assessment", 15), ("complete the test", 15),
        ("submit your solution", 12), ("coding round", 12),
    ],
    "followup": [
        ("no news yet", 12), ("still waiting", 10), ("any update", 10),
        ("status update", 10), ("checking in", 10), ("touching base", 10),
        ("circling back", 10), ("following up", 10),
        ("we appreciate your patience", 12), ("will let you know", 10),
        ("emailed the manager", 10), ("hear back", 8),
        ("re: follow up", 12), ("re: followup", 12),
    ],
}

CATEGORY_THRESHOLD = 12

def classify_email(subject: str, sender: str, body: str):
    if HARD_EXCLUDE.search(subject + " " + sender):
        return None, 0
    blob = (subject + " " + body).lower()
    best_cat, best_score = None, 0
    for cat, kw_list in CATEGORY_KEYWORDS.items():
        score = sum(w for kw, w in kw_list if kw.lower() in blob)
        if score > best_score:
            best_cat, best_score = cat, score
    if best_score >= CATEGORY_THRESHOLD:
        return best_cat, best_score
    return None, 0

# =============================================================================
# LOCATION DETECTION
# =============================================================================
REMOTE_RE = re.compile(r"\bremote\b|100% remote|fully remote|work from home|\bwfh\b", re.IGNORECASE)
HYBRID_RE = re.compile(r"\bhybrid\b", re.IGNORECASE)
CYBER_RE  = re.compile(
    r"cyber|security|soc|siem|iam|devsecops|pentest|grc|firewall|endpoint"
    r"|network security|cloud security|infosec|splunk|qualys|crowdstrike",
    re.IGNORECASE
)

def detect_location(subject: str, body: str) -> str:
    text = subject + " " + body[:1500]
    if REMOTE_RE.search(text):
        return "remote"
    if HYBRID_RE.search(text):
        return "hybrid"
    return "onsite"

def is_cyber_role(subject: str, body: str) -> bool:
    return bool(CYBER_RE.search(subject + " " + body[:500]))

# =============================================================================
# HELPERS
# =============================================================================
PHONE_RE = re.compile(r"(?:\+?1[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}|\d{10})")
RATE_RE  = re.compile(r"\$\s*(\d+(?:\.\d+)?)\s*/?\s*(?:hr|hour|per hour)", re.IGNORECASE)

# Links to SKIP in WhatsApp messages
JUNK_LINK_RE = re.compile(
    r"google\.com/maps|avg\.com|linkedin\.com/in/|utm_|unsubscribe"
    r"|aka\.ms|LearnAbout|refermeiq|indeedemail|srl-soft|benchinfo"
    r"|\.gif|\.png|\.jpg|track\.|click\.",
    re.IGNORECASE
)

def extract_phones(text: str):
    raw = PHONE_RE.findall(text)
    cleaned = []
    for p in raw:
        digits = re.sub(r"\D", "", p)
        if 10 <= len(digits) <= 11:
            cleaned.append(p.strip())
    return list(dict.fromkeys(cleaned))[:3]

def extract_useful_links(text: str):
    """Only keep actual job/company links, drop tracking/noise links."""
    all_links = re.findall(r"https?://\S+", text)
    useful = [l.rstrip('>').rstrip('"') for l in all_links if not JUNK_LINK_RE.search(l)]
    return list(dict.fromkeys(useful))[:2]  # max 2 clean links

def extract_rate(text: str) -> str:
    m = RATE_RE.search(text)
    return f"${m.group(1)}/hr" if m else ""

def extract_role(subject: str) -> str:
    s = re.sub(r"^(re:|fwd?:|fw:)\s*", "", subject, flags=re.IGNORECASE).strip()
    s = re.sub(r"^(RTR|Right to Represent|Rate Confirmation|Opening for|Looking for"
               r"|Hiring for|URGENT|Immediate|Hot Req)[:\s–-]*", "", s, flags=re.IGNORECASE).strip()
    s = re.sub(r"^[|:–\-\s]+", "", s)
    s = re.split(r"\s*[|–\-]{1,2}\s*(Remote|Hybrid|Onsite|Location|\d{2,} years)", s, flags=re.IGNORECASE)[0]
    return s.strip()[:100]

def extract_company(subject: str, body: str) -> str:
    m = re.search(r"(?:client[:\s]+|with client[:\s]+|client\s*[:\-–>]+\s*)([A-Z][A-Za-z0-9 &.,]+?)(?:\s*[|–\-\n]|$)", body[:2000], re.IGNORECASE)
    if m:
        return m.group(1).strip()[:60]
    m = re.search(r"(?:at|with|for)\s+([A-Z][A-Za-z0-9 &]+?)(?:\s*[|–\-]|,|\s*$)", subject)
    if m:
        return m.group(1).strip()[:60]
    return ""

def recruiter_name(sender: str) -> str:
    m = re.match(r'^"?([^"<@\n]{2,40})"?\s*<', sender)
    return m.group(1).strip() if m else sender.split("@")[0][:30]

def body_text(msg) -> str:
    text = ""
    if msg.is_multipart():
        for part in msg.walk():
            if (part.get_content_type() == "text/plain"
                    and "attachment" not in str(part.get("Content-Disposition", ""))):
                try:
                    text += part.get_payload(decode=True).decode("utf-8", errors="replace")
                except Exception:
                    pass
    else:
        try:
            text = msg.get_payload(decode=True).decode("utf-8", errors="replace")
        except Exception:
            text = str(msg.get_payload())
    return text

# =============================================================================
# WHATSAPP MESSAGE BUILDERS — clean, screenshot-style
# =============================================================================
def fmt_whatsapp(category_label: str, account: str, recruiter: str,
                 sender_email: str, role: str, company: str,
                 rate: str, location: str, phones: list,
                 links: list, extra_line: str = "") -> str:
    """Builds a clean, readable WhatsApp message."""
    lines = [
        f"{'='*28}",
        f"*{category_label}* | {account}",
        f"{'='*28}",
        f"👤 *{recruiter}*",
        f"📧 {sender_email}",
    ]
    if role:
        lines.append(f"💼 {role}")
    if company:
        lines.append(f"🏢 {company}")
    if rate:
        lines.append(f"💰 {rate}")
    if location:
        loc_emoji = {"remote": "🌐", "hybrid": "🔀", "onsite": "🏢"}.get(location, "📍")
        lines.append(f"{loc_emoji} {location.upper()}")
    if phones:
        lines.append(f"📞 {' | '.join(phones)}")
    if extra_line:
        lines.append(f"{'─'*28}")
        lines.append(extra_line)
    if links:
        lines.append(f"🔗 {links[0]}")
    return "\n".join(lines)

def build_rtr_msg(r):
    return fmt_whatsapp(
        "📋 RTR", r["account"], r["recruiter_name"],
        r["sender_email"], r["role"], r["company"],
        r["rate"], r["location_type"], r["phones"],
        r["links"], "✅ CONFIRM + send resume. Call back."
    )

def build_outreach_msg(r):
    return fmt_whatsapp(
        "📨 REMOTE ROLE", r["account"], r["recruiter_name"],
        r["sender_email"], r["role"], r["company"],
        r["rate"], r["location_type"], r["phones"],
        r["links"], "⚡ Reply with resume ASAP."
    )

def build_reply_needed_msg(r):
    return fmt_whatsapp(
        "⚡ REPLY NEEDED", r["account"], r["recruiter_name"],
        r["sender_email"], r["role"], r["company"],
        r["rate"], r["location_type"], r["phones"],
        r["links"], "💬 They asked for info — REPLY NOW."
    )

def build_interview_msg(r, cal_added):
    extra = "📅 Added to Calendar." if cal_added else "⚠️ No date found — add manually to calendar."
    return fmt_whatsapp(
        "📞 INTERVIEW", r["account"], r["recruiter_name"],
        r["sender_email"], r["role"], r["company"],
        r["rate"], r["location_type"], r["phones"],
        r["links"], extra
    )

def build_assessment_msg(r):
    return fmt_whatsapp(
        "🧪 ASSESSMENT", r["account"], r["recruiter_name"],
        r["sender_email"], r["role"], r["company"],
        r["rate"], r["location_type"], r["phones"],
        r["links"], "📝 Complete the test ASAP."
    )

def build_followup_msg(r):
    return fmt_whatsapp(
        "⏳ FOLLOW-UP", r["account"], r["recruiter_name"],
        r["sender_email"], r["role"], r["company"],
        r["rate"], r["location_type"], r["phones"],
        r["links"], "🔔 Reply or call to stay in the loop."
    )

# =============================================================================
# WHATSAPP SEND — stop on 429, queue remainder for next run
# =============================================================================
_wa_blocked = False  # once we hit 429, stop all further attempts this run

def send_whatsapp(text: str, state: dict = None):
    global _whatsapp_sent_this_run, _wa_blocked

    # If already 429-blocked this run, queue and return immediately
    if _wa_blocked:
        if state is not None:
            state.setdefault("wa_queue", []).append(text)
        _metrics["whatsapp_skipped"] += 1
        return

    if _whatsapp_sent_this_run >= WHATSAPP_PER_RUN_LIMIT:
        _metrics["whatsapp_skipped"] += 1
        if state is not None:
            state.setdefault("wa_queue", []).append(text)
        print(f"    [WhatsApp THROTTLED — queued for next run]")
        return

    if not TWILIO_ACCOUNT_SID or not TWILIO_AUTH_TOKEN:
        print(f"    [WhatsApp SKIPPED — no creds]")
        return

    try:
        url  = f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_ACCOUNT_SID}/Messages.json"
        data = urlencode({"From": TWILIO_FROM, "To": TWILIO_TO, "Body": text}).encode()
        cred = base64.b64encode(f"{TWILIO_ACCOUNT_SID}:{TWILIO_AUTH_TOKEN}".encode()).decode()
        req  = Request(url, data=data, headers={
            "Authorization": f"Basic {cred}",
            "Content-Type": "application/x-www-form-urlencoded",
        })
        urlopen(req, timeout=10)
        _whatsapp_sent_this_run += 1
        _metrics["whatsapp_success"] += 1
        print("    [+] WhatsApp sent.")
        time.sleep(2)
    except Exception as exc:
        err_str = str(exc)
        if "429" in err_str:
            # Rate limited — stop immediately, queue this message for next run
            _wa_blocked = True
            if state is not None:
                state.setdefault("wa_queue", []).append(text)
            _metrics["whatsapp_fail"] += 1
            print(f"    [!] WhatsApp 429 — rate limited. Stopping WA for this run, queuing remainder.")
        else:
            record_error("whatsapp_send", exc)
            _metrics["whatsapp_fail"] += 1
            print(f"    [!] WhatsApp failed: {exc}")

# =============================================================================
# CSV
# =============================================================================
CSV_HEADERS = [
    "detected_at", "category", "account", "subject", "sender",
    "sender_email", "recruiter_name", "role", "company", "location_type",
    "phones", "links", "rate", "notes", "followup_due", "status", "calendar_added",
]

def load_csv_uid_set() -> set:
    seen = set()
    if not os.path.exists(CSV_FILE):
        return seen
    with open(CSV_FILE, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            m = re.search(r"uid:(\S+)", row.get("notes", ""))
            if m:
                seen.add(m.group(1))
    return seen

def write_csv_row(row: dict):
    exists = os.path.exists(CSV_FILE)
    with open(CSV_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_HEADERS, extrasaction="ignore")
        if not exists:
            writer.writeheader()
        writer.writerow(row)

# =============================================================================
# STATE — smart: SINCE 30d on first run, UNSEEN after state exists
# =============================================================================
def load_state() -> dict:
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"seen_uids": {}, "wa_queue": []}

def save_state(state: dict):
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
    except Exception as exc:
        record_error("state_save", exc)

# =============================================================================
# CALENDAR
# =============================================================================
CALENDAR_CATS = {
    "interview":  {"emoji": "📞", "mins": 60},
    "assessment": {"emoji": "🧪", "mins": 90},
    "rtr":        {"emoji": "📋", "mins": 30},
}
_cal_svc = None

_DATE_RE = re.compile(
    r"(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),?\s+"
    r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?"
    r"|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
    r"\s+\d{1,2},?\s+\d{4}\s+at\s+\d{1,2}:\d{2}\s*(?:AM|PM)(?:\s+[A-Z]{2,5})?|"
    r"\d{1,2}/\d{1,2}/\d{4}\s+\d{1,2}:\d{2}\s*(?:AM|PM)?|"
    r"\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}",
    re.IGNORECASE
)

def get_calendar_service():
    global _cal_svc
    if _cal_svc:
        return _cal_svc
    if not CALENDAR_ENABLED or not GOOGLE_TOKEN_B64:
        return None
    try:
        creds = pickle.loads(base64.b64decode(GOOGLE_TOKEN_B64))
        if creds.expired and creds.refresh_token:
            creds.refresh(GRequest())
        _cal_svc = build("calendar", "v3", credentials=creds)
        return _cal_svc
    except Exception as exc:
        record_error("calendar_auth", exc)
        return None

def add_to_calendar(subject, sender, body, links, category) -> bool:
    cat_meta = CALENDAR_CATS.get(category)
    if not cat_meta:
        return False
    dt = None
    m = _DATE_RE.search(body)
    if m and DATEPARSER_ENABLED:
        dt = dateparser.parse(m.group(0), settings={"PREFER_DATES_FROM": "future"})
    if not dt and DATEPARSER_ENABLED:
        dt = dateparser.parse(body[:2000], settings={"PREFER_DATES_FROM": "future"})
        if dt and dt < datetime.now():
            dt = None
    if not dt:
        if category in ("rtr", "assessment"):
            dt = datetime.now().replace(hour=9, minute=0, second=0, microsecond=0)
            if dt < datetime.now():
                dt += timedelta(days=1)
        else:
            _metrics["calendar_fail"] += 1
            return False
    event = {
        "summary": f"{cat_meta['emoji']} [{category.upper()}] {subject[:80]}",
        "description": f"From: {sender}\n" + ("\n".join(links) if links else ""),
        "start": {"dateTime": dt.isoformat(), "timeZone": "America/Chicago"},
        "end":   {"dateTime": (dt + timedelta(minutes=cat_meta["mins"])).isoformat(), "timeZone": "America/Chicago"},
        "reminders": {"useDefault": False, "overrides": [
            {"method": "popup", "minutes": 30},
            {"method": "email", "minutes": 60},
        ]},
    }
    try:
        svc = get_calendar_service()
        if not svc:
            _metrics["calendar_fail"] += 1
            return False
        svc.events().insert(calendarId="eshwarjay05@gmail.com", body=event).execute()
        _metrics["calendar_success"] += 1
        return True
    except Exception as exc:
        record_error("calendar_insert", exc)
        _metrics["calendar_fail"] += 1
        return False

# =============================================================================
# PER-ACCOUNT WATCHER
# =============================================================================
def process_account(acct: dict, state: dict, csv_uid_set: set):
    label    = acct["label"]
    user     = acct["email"]
    is_cyber = acct.get("is_cyber", False)
    seen     = state.setdefault("seen_uids", {}).setdefault(user, {})

    print(f"[*] {label} ({user}) — scanning last 60 days")
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com", 993)
        mail.login(user, acct["password"])
        mail.select("INBOX")

        # Always scan last 60 days — seen_uids dedup prevents re-processing
        since = (datetime.now() - timedelta(days=60)).strftime("%d-%b-%Y")
        status, data = mail.search(None, f'(SINCE "{since}")')

        if status != "OK" or not data[0]:
            print(f"    No mail.")
            mail.logout()
            return

        uids = data[0].split()
        print(f"    {len(uids)} emails to process")

        for uid in uids:
            uid_s   = uid.decode() if isinstance(uid, (bytes, bytearray)) else str(uid)
            uid_key = f"{user}:{uid_s}"

            if uid_s in seen:
                continue

            _, msg_data = mail.fetch(uid, "(RFC822)")
            raw     = msg_data[0][1]
            msg     = email.message_from_bytes(raw)

            # Decode subject properly
            raw_subject = msg.get("Subject", "") or ""
            subject     = decode_subject(raw_subject)
            sender      = msg.get("From", "") or ""
            body        = body_text(msg)

            _metrics["emails_scanned"] += 1
            cat, score = classify_email(subject, sender, body)
            seen[uid_s] = datetime.utcnow().isoformat()

            if not cat:
                continue

            loc_type   = detect_location(subject, body)
            cyber_role = is_cyber_role(subject, body)
            phones     = extract_phones(body + " " + sender)
            links      = extract_useful_links(body)
            rate       = extract_rate(subject + " " + body)
            company    = extract_company(subject, body)
            role       = extract_role(subject)
            rname      = recruiter_name(sender)
            cal_added  = False

            # Extract clean sender email
            em = re.search(r"<([^>]+)>", sender)
            sender_email = em.group(1) if em else sender.strip()

            # Should we send WhatsApp?
            should_alert = False
            if cat == "rtr":
                should_alert = True
                if cat in CALENDAR_CATS:
                    cal_added = add_to_calendar(subject, sender, body, links, cat)
            elif cat == "reply_needed":
                should_alert = True
            elif cat == "outreach":
                if loc_type == "remote":
                    should_alert = True
                elif loc_type == "hybrid" and (is_cyber or cyber_role):
                    should_alert = True
            elif cat == "interview":
                should_alert = True
                if cat in CALENDAR_CATS:
                    cal_added = add_to_calendar(subject, sender, body, links, cat)
            elif cat == "assessment":
                should_alert = True
                if cat in CALENDAR_CATS:
                    cal_added = add_to_calendar(subject, sender, body, links, cat)
            elif cat == "followup":
                should_alert = True

            _metrics["emails_classified"] += 1

            followup_due = ""
            if cat in ("reply_needed", "rtr"):
                followup_due = (date.today() + timedelta(days=2)).isoformat()
            elif cat in ("interview", "assessment"):
                followup_due = (date.today() + timedelta(days=1)).isoformat()
            elif cat == "followup":
                followup_due = (date.today() + timedelta(days=3)).isoformat()

            # Build row dict for both CSV and WhatsApp builders
            row = {
                "detected_at":    datetime.now().strftime("%Y-%m-%d %H:%M"),
                "category":       cat,
                "account":        label,
                "subject":        subject[:200],
                "sender":         sender[:150],
                "sender_email":   sender_email[:100],
                "recruiter_name": rname,
                "role":           role,
                "company":        company,
                "location_type":  loc_type,
                "phones":         ";".join(phones),
                "links":          ";".join(links),
                "rate":           rate,
                "notes":          f"uid:{uid_key} score:{score}",
                "followup_due":   followup_due,
                "status":         "open",
                "calendar_added": "yes" if cal_added else "no",
            }

            # Write to CSV (dedup by uid_key)
            if uid_key not in csv_uid_set:
                write_csv_row(row)
                csv_uid_set.add(uid_key)

            # Send WhatsApp
            if should_alert:
                if cat == "rtr":
                    msg_text = build_rtr_msg(row)
                elif cat == "reply_needed":
                    msg_text = build_reply_needed_msg(row)
                elif cat == "outreach":
                    msg_text = build_outreach_msg(row)
                elif cat == "interview":
                    msg_text = build_interview_msg(row, cal_added)
                elif cat == "assessment":
                    msg_text = build_assessment_msg(row)
                elif cat == "followup":
                    msg_text = build_followup_msg(row)
                else:
                    msg_text = None

                if msg_text:
                    send_whatsapp(msg_text, state)

            print(f"    [{'✓' if should_alert else '–'}] [{cat}|{loc_type}|{score}] {subject[:70]}")

        mail.logout()

    except Exception as exc:
        record_error(f"imap_{label}", exc)
        _metrics["imap_errors"].append(f"{label}: {str(exc)}")
        print(f"[!] Error {label}: {exc}")

# =============================================================================
# GITHUB ISSUE
# =============================================================================
def report_if_needed():
    issues = []
    if _metrics["imap_errors"]:
        issues.append(f"- IMAP errors: {_metrics['imap_errors']}")
    if _metrics["errors"]:
        for e in _metrics["errors"][:3]:
            issues.append(f"- [{e['context']}] {e['error']}")
    if not issues:
        print("[+] Run clean.")
        return
    body = f"## Diagnostic\n**Run:** {_metrics['run_start']}\n\n## Issues\n" + "\n".join(issues)
    try:
        url  = f"https://api.github.com/repos/{GITHUB_REPO}/issues"
        data = json.dumps({"title": f"[AUTO] Watcher issues {datetime.now():%Y-%m-%d %H:%M}",
                           "body": body, "labels": ["auto-diagnostic"]}).encode()
        req  = Request(url, data=data, headers={
            "Authorization": f"Bearer {GITHUB_TOKEN}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
        })
        urlopen(req, timeout=10)
    except Exception as exc:
        print(f"[!] GitHub issue failed: {exc}")

# =============================================================================
# MAIN
# =============================================================================
def main():
    print("=== Gmail Watcher v9 ===")
    print(f"Started: {datetime.now():%Y-%m-%d %H:%M:%S}")

    state       = load_state()
    csv_uid_set = load_csv_uid_set()

    # Drain queued WhatsApp messages from previous rate-limited run
    wa_queue = state.pop("wa_queue", [])
    if wa_queue:
        print(f"[*] Draining {len(wa_queue)} queued WhatsApp messages from previous run...")
        for queued_msg in wa_queue[:WHATSAPP_PER_RUN_LIMIT]:
            if _wa_blocked:
                # Still rate limited — re-queue remainder
                state.setdefault("wa_queue", []).append(queued_msg)
            else:
                send_whatsapp(queued_msg, state)
        # Any that didn't fit back in queue
        remaining = wa_queue[WHATSAPP_PER_RUN_LIMIT:]
        if remaining:
            state.setdefault("wa_queue", []).extend(remaining)
        print(f"    Done. Sent: {_metrics['whatsapp_success']} Queued: {len(state.get('wa_queue', []))}")

    for acct in ACCOUNTS:
        try:
            process_account(acct, state, csv_uid_set)
        except Exception as exc:
            record_error(f"account_{acct['email']}", exc)
        finally:
            save_state(state)



    report_if_needed()
    print(f"Done: {datetime.now():%Y-%m-%d %H:%M:%S}")
    print(f"Scanned:{_metrics['emails_scanned']} Classified:{_metrics['emails_classified']} Queued:{len(state.get('wa_queue',[]))} "
          f"WA:{_metrics['whatsapp_success']}✓ {_metrics['whatsapp_fail']}✗ {_metrics['whatsapp_skipped']}skip "
          f"Cal:{_metrics['calendar_success']}✓ {_metrics['calendar_fail']}✗")

if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"[FATAL] {exc}")
        traceback.print_exc()
        raise

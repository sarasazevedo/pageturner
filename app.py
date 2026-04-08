import json
import csv
import io
from datetime import datetime, date
from pathlib import Path

import html as html_lib
import requests
import streamlit as st
import pandas as pd

# ── Storage ────────────────────────────────────────────────────────────────────

DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)
BOOKS_FILE = DATA_DIR / "books.json"
GOALS_FILE = DATA_DIR / "goals.json"


def load_books() -> list[dict]:
    if BOOKS_FILE.exists():
        return json.loads(BOOKS_FILE.read_text(encoding="utf-8"))
    return []


def save_books(books: list[dict]) -> None:
    BOOKS_FILE.write_text(json.dumps(books, indent=2, ensure_ascii=False), encoding="utf-8")


def load_goals() -> dict:
    if GOALS_FILE.exists():
        return json.loads(GOALS_FILE.read_text(encoding="utf-8"))
    return {}


def save_goals(goals: dict) -> None:
    GOALS_FILE.write_text(json.dumps(goals, indent=2, ensure_ascii=False), encoding="utf-8")


# ── Helpers ────────────────────────────────────────────────────────────────────

STATUSES = ["Read", "Want to Read", "Currently Reading"]
STATUS_EMOJI = {"Read": "✅", "Want to Read": "📚", "Currently Reading": "📖"}
STATUS_COLOR = {"Read": "#2ecc71", "Want to Read": "#3498db", "Currently Reading": "#e67e22"}

GENRES = [
    "Fiction", "Non-Fiction", "Self-Help", "Business", "Biography",
    "History", "Science", "Technology", "Philosophy", "Psychology",
    "Economics", "Politics", "Travel", "Poetry", "Other",
]

PRIORITY_LABEL = {1: "🔴 High", 2: "🟡 Medium", 3: "🟢 Low"}
PRIORITY_OPTIONS = [0, 1, 2, 3]

# (sort key fn, reverse?)
SORT_OPTIONS: dict[str, tuple] = {
    "Date finished (newest)": (lambda b: b.get("date_finished") or "", True),
    "Date added (newest)":    (lambda b: b.get("added_at") or "", True),
    "Title (A–Z)":            (lambda b: b.get("title", "").lower(), False),
    "Author (A–Z)":           (lambda b: b.get("author", "").lower(), False),
    "Rating (highest)":       (lambda b: b.get("rating") or 0, True),
    "Priority":               (lambda b: b.get("priority") or 99, False),
}


def star_display(rating: int | None) -> str:
    if not rating:
        return ""
    return "★" * rating + "☆" * (5 - rating)


def month_key(year: int, month: int) -> str:
    return f"{year}-{month:02d}"


def current_month_key() -> str:
    today = date.today()
    return month_key(today.year, today.month)


def books_read_this_month(books: list[dict]) -> int:
    key = current_month_key()
    return sum(
        1 for b in books
        if b["status"] == "Read" and b.get("date_finished", "")[:7] == key
    )


def books_read_this_year(books: list[dict]) -> int:
    year = str(date.today().year)
    return sum(
        1 for b in books
        if b["status"] == "Read" and (b.get("date_finished") or "").startswith(year)
    )


def books_to_csv(books: list[dict]) -> str:
    output = io.StringIO()
    fields = ["title", "author", "status", "priority", "rating", "genres",
              "date_finished", "pages_total", "pages_read", "notes", "added_at"]
    writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for b in books:
        row = dict(b)
        row["genres"] = ", ".join(b.get("genres") or [])
        row["priority"] = PRIORITY_LABEL.get(b.get("priority") or 0, "")
        writer.writerow(row)
    return output.getvalue()


# ── Genre → Open Library subject mapping ──────────────────────────────────────

GENRE_TO_OL_SUBJECT: dict[str, str] = {
    "Self-Help":  "self_help",
    "Business":   "business",
    "Philosophy": "philosophy",
    "Psychology": "psychology",
    "Biography":  "biography",
    "History":    "history",
    "Science":    "science",
    "Technology": "technology",
    "Fiction":    "fiction",
    "Non-Fiction":"nonfiction",
    "Economics":  "economics",
    "Politics":   "politics",
}


@st.cache_data(ttl=86400, show_spinner=False)
def fetch_genre_books(genre: str, limit: int = 50) -> list[dict]:
    """Return popular recent books (2000+) for a genre from Open Library search API."""
    subject = GENRE_TO_OL_SUBJECT.get(genre, genre.lower().replace(" ", "_"))
    try:
        r = requests.get(
            "https://openlibrary.org/search.json",
            params={
                "subject": subject,
                "limit": limit,
                "sort": "rating",
                "fields": "title,author_name,first_publish_year",
            },
            timeout=10,
        )
        if r.status_code == 200:
            results = []
            for doc in r.json().get("docs", []):
                title   = doc.get("title", "").strip()
                authors = doc.get("author_name", [])
                author  = authors[0].strip() if authors else ""
                year    = doc.get("first_publish_year")
                if title and author and year and int(year) >= 2000:
                    results.append({"title": title, "author": author, "genres": [genre]})
            return results
    except Exception:
        pass
    return []


# ── Open Library book details ──────────────────────────────────────────────────

def _strip_html(text: str) -> str:
    import re
    return re.sub(r"<[^>]+>", " ", text).strip()


@st.cache_data(ttl=86400, show_spinner=False)
def fetch_book_details(title: str, author: str) -> dict:
    """
    1. Open Library search → work details (pages, year, description)
    2. Wikipedia fallback for description if OL has none
    """
    result = {"summary": "", "description": "", "pages": None, "year": None}

    # ── Open Library: search for work key + metadata ───────────────────────
    try:
        r = requests.get(
            "https://openlibrary.org/search.json",
            params={"title": title, "author": author, "limit": 1,
                    "fields": "key,number_of_pages_median,first_publish_year"},
            timeout=10,
        )
        if r.status_code == 200:
            docs = r.json().get("docs", [])
            if docs:
                doc = docs[0]
                result["pages"] = doc.get("number_of_pages_median") or None
                result["year"]  = str(doc.get("first_publish_year") or "") or None
                # Fetch work details for description
                work_key = doc.get("key", "")  # e.g. "/works/OL12345W"
                if work_key:
                    r2 = requests.get(
                        f"https://openlibrary.org{work_key}.json",
                        timeout=10,
                    )
                    if r2.status_code == 200:
                        work = r2.json()
                        desc_raw = work.get("description", "")
                        if isinstance(desc_raw, dict):
                            desc_raw = desc_raw.get("value", "")
                        desc = _strip_html(str(desc_raw)).strip()
                        if desc:
                            result["description"] = desc
                            result["summary"] = (desc[:220] + "…") if len(desc) > 220 else desc
    except Exception:
        pass

    # ── Wikipedia fallback for description ────────────────────────────────
    if not result["description"]:
        try:
            r = requests.get(
                "https://en.wikipedia.org/w/api.php",
                params={"action": "query", "list": "search", "format": "json",
                        "srsearch": f"{title} {author} book", "srlimit": 1},
                timeout=8,
            )
            if r.status_code == 200:
                hits = r.json().get("query", {}).get("search", [])
                if hits:
                    pid = hits[0]["pageid"]
                    r2 = requests.get(
                        "https://en.wikipedia.org/w/api.php",
                        params={"action": "query", "prop": "extracts", "exintro": 1,
                                "explaintext": 1, "pageids": pid, "format": "json"},
                        timeout=8,
                    )
                    if r2.status_code == 200:
                        raw = (r2.json().get("query", {})
                               .get("pages", {}).get(str(pid), {})
                               .get("extract", "").strip())
                        paras = [p.strip() for p in raw.split("\n") if p.strip()]
                        desc  = " ".join(paras[:2])
                        if desc:
                            result["description"] = desc
                            result["summary"] = (desc[:220] + "…") if len(desc) > 220 else desc
        except Exception:
            pass

    # Don't cache completely empty results — next call will retry
    if not result["description"] and not result["pages"] and not result["year"]:
        raise RuntimeError("No data — skipping cache")

    return result


@st.dialog("📚 Book details")
def _book_dialog(b: dict, details: dict) -> None:
    priority = b.get("priority")
    c = get_theme()

    st.markdown(f"## {b['title']}")
    st.markdown(f"*by **{b['author']}***")

    col1, col2 = st.columns(2)
    col1.markdown(f"**📅 Published:** {details.get('year') or '—'}")
    col2.markdown(f"**📄 Pages:** {details.get('pages') or '—'}")

    meta_parts = []
    if priority:
        meta_parts.append(f'<span class="priority-badge priority-{priority}">{PRIORITY_LABEL[priority]}</span>')
    for g in (b.get("genres") or []):
        meta_parts.append(f'<span class="genre-tag">{html_lib.escape(g)}</span>')
    if meta_parts:
        st.markdown(" ".join(meta_parts), unsafe_allow_html=True)

    st.divider()

    desc = details.get("description") or details.get("summary") or ""
    if desc:
        st.markdown("**About this book**")
        st.write(desc)
    else:
        st.info("No description available for this book.")


# ── Theme ──────────────────────────────────────────────────────────────────────

DARK = {
    "bg":           "#0f1117",
    "card":         "#1a1d27",
    "border":       "#2a2d3e",
    "border2":      "#3a3d4e",
    "text":         "#ffffff",
    "muted":        "#8b949e",
    "body":         "#c9d1d9",
    "input_bg":     "#0f1117",
    "sidebar_bg":   "#1a1d27",
    "sidebar_border": "#2a2d3e",
}

LIGHT = {
    "bg":           "#f6f8fa",
    "card":         "#ffffff",
    "border":       "#d0d7de",
    "border2":      "#b6bdc4",
    "text":         "#1f2328",
    "muted":        "#57606a",
    "body":         "#24292f",
    "input_bg":     "#ffffff",
    "sidebar_bg":   "#f0f2f5",
    "sidebar_border": "#d0d7de",
}


def get_theme() -> dict:
    return LIGHT if st.session_state.get("light_mode") else DARK


# ── CSS ────────────────────────────────────────────────────────────────────────

def inject_css(c: dict) -> None:
    st.markdown(f"""
    <style>
    [data-testid="stAppViewContainer"] {{ background-color: {c['bg']}; }}
    [data-testid="stSidebar"] {{
        background-color: {c['sidebar_bg']};
        border-right: 1px solid {c['sidebar_border']};
    }}
    [data-testid="stSidebar"] * {{ color: {c['body']} !important; }}

    .page-title {{
        font-size: 28px; font-weight: 700; color: {c['text']}; margin-bottom: 4px;
    }}
    .page-subtitle {{
        font-size: 14px; color: {c['muted']}; margin-bottom: 28px;
    }}

    .metric-grid {{
        display: grid; grid-template-columns: repeat(4, 1fr);
        gap: 16px; margin-bottom: 28px;
    }}
    .metric-card {{
        background: {c['card']}; border: 1px solid {c['border']};
        border-radius: 14px; padding: 20px; text-align: center;
        transition: transform 0.2s;
    }}
    .metric-card:hover {{ transform: translateY(-2px); }}
    .metric-value {{
        font-size: 32px; font-weight: 700; color: {c['text']};
        line-height: 1; margin-bottom: 6px;
    }}
    .metric-label {{
        font-size: 12px; color: {c['muted']};
        text-transform: uppercase; letter-spacing: 0.05em;
    }}

    .section-card {{
        background: {c['card']}; border: 1px solid {c['border']};
        border-radius: 14px; padding: 24px; margin-bottom: 20px;
    }}
    .section-title {{
        font-size: 16px; font-weight: 600; color: {c['text']};
        margin-bottom: 16px; display: flex; align-items: center; gap: 8px;
    }}

    .book-item {{
        display: flex; align-items: center; gap: 14px;
        padding: 12px 0; border-bottom: 1px solid {c['border']};
    }}
    .book-item:last-child {{ border-bottom: none; }}
    .book-cover {{
        width: 36px; height: 50px; border-radius: 4px;
        display: flex; align-items: center; justify-content: center;
        font-size: 20px; flex-shrink: 0;
    }}
    .book-info {{ flex: 1; min-width: 0; }}
    .book-title {{
        font-weight: 600; color: {c['text']}; font-size: 14px;
        white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
    }}
    .book-author {{ font-size: 12px; color: {c['muted']}; margin-top: 2px; }}
    .book-meta {{ text-align: right; flex-shrink: 0; }}
    .stars {{ color: #f0c040; font-size: 13px; letter-spacing: 1px; }}
    .book-date {{ font-size: 11px; color: {c['muted']}; margin-top: 2px; }}

    .genre-tag {{
        display: inline-block; padding: 2px 8px; border-radius: 12px;
        font-size: 11px; font-weight: 500; margin: 2px 2px 0 0;
        background: #6c63ff22; color: #a78bfa; border: 1px solid #6c63ff44;
    }}
    .status-badge {{
        display: inline-block; padding: 3px 10px; border-radius: 20px;
        font-size: 11px; font-weight: 600;
    }}
    .priority-badge {{
        display: inline-block; padding: 2px 8px; border-radius: 12px;
        font-size: 11px; font-weight: 600; margin: 2px 2px 0 0;
    }}
    .priority-1 {{ background:#ff444422; color:#ff6b6b; border:1px solid #ff444444; }}
    .priority-2 {{ background:#f0c04022; color:#f0c040; border:1px solid #f0c04044; }}
    .priority-3 {{ background:#2ecc7122; color:#2ecc71; border:1px solid #2ecc7144; }}

    .goal-bar-bg {{
        background: {c['border']}; border-radius: 8px; height: 10px;
        margin: 10px 0; overflow: hidden;
    }}
    .goal-bar-fill {{
        height: 100%; border-radius: 8px;
        background: linear-gradient(90deg, #6c63ff, #a78bfa);
        transition: width 0.4s ease;
    }}
    .goal-text {{ font-size: 13px; color: {c['muted']}; margin-top: 6px; }}

    .progress-bar-bg {{
        background: {c['border']}; border-radius: 6px; height: 5px;
        margin: 8px 0 3px; overflow: hidden; width: 100%;
    }}
    .progress-bar-fill {{
        height: 100%; border-radius: 6px;
        background: linear-gradient(90deg, #e67e22, #f39c12);
        transition: width 0.4s ease;
    }}
    .progress-text {{ font-size: 11px; color: {c['muted']}; }}

    /* ── Book cards (dashboard) ── */
    .book-card {{
        display: flex; align-items: stretch; gap: 0;
        background: {'#12151f' if c['bg'] == '#0f1117' else '#f0f2f5'}; border: 1px solid {c['border']};
        border-radius: 12px; overflow: hidden;
        margin-bottom: 10px; transition: transform 0.15s, border-color 0.15s;
    }}
    .book-card:hover {{ transform: translateY(-2px); border-color: #6c63ff66; }}
    .book-card-spine {{ width: 4px; flex-shrink: 0; }}
    .book-card-body {{ flex: 1; padding: 14px 14px 12px; min-width: 0; }}
    .book-card-title {{
        font-size: 14px; font-weight: 700; color: {c['text']};
        white-space: nowrap; overflow: hidden; text-overflow: ellipsis; margin-bottom: 2px;
    }}
    .book-card-author {{ font-size: 12px; color: {c['muted']}; margin-bottom: 6px; }}
    .book-card-tags {{ display: flex; flex-wrap: wrap; gap: 4px; margin-bottom: 4px; }}
    .book-card-footer {{
        display: flex; align-items: center; justify-content: space-between; margin-top: 6px;
    }}
    .book-card-stars {{ color: #f0c040; font-size: 13px; letter-spacing: 1px; }}
    .book-card-date {{ font-size: 11px; color: {c['muted']}; }}

    /* confirm-delete */
    .delete-confirm {{
        background: #3d1a1a; border: 1px solid #7f1d1d;
        border-radius: 10px; padding: 12px 16px; margin-top: 8px;
        color: #fca5a5; font-size: 13px;
    }}

    [data-testid="stTextInput"] input,
    [data-testid="stTextArea"] textarea {{
        background-color: {c['input_bg']} !important;
        border: 1px solid {c['border']} !important;
        border-radius: 8px !important; color: {c['text']} !important;
    }}
    [data-testid="stFormSubmitButton"] button {{
        background: linear-gradient(135deg, #6c63ff, #a78bfa) !important;
        border: none !important; border-radius: 8px !important;
        color: white !important; font-weight: 600 !important;
        padding: 10px 24px !important; width: 100% !important;
    }}
    h1, h2, h3 {{ color: {c['text']} !important; }}
    p, label, div {{ color: {c['body']}; }}
    [data-testid="stMetric"] {{ display: none; }}
    .stExpander {{
        background: {c['card']} !important; border: 1px solid {c['border']} !important;
        border-radius: 10px !important; margin-bottom: 8px !important;
    }}
    .stButton button {{
        background: {c['card']} !important; border: 1px solid {c['border2']} !important;
        color: {c['body']} !important; border-radius: 8px !important;
    }}
    .stButton button:hover {{
        background: {c['border']} !important; color: {c['text']} !important;
    }}
    </style>
    """, unsafe_allow_html=True)


# ── Sidebar ────────────────────────────────────────────────────────────────────

PAGES = [
    ("Dashboard",    "🏠"),
    ("My Books",     "📖"),
    ("Add Book",     "➕"),
    ("For You",      "✨"),
    ("Stats",        "📊"),
]


def render_sidebar() -> str:
    if "page" not in st.session_state:
        st.session_state.page = "Dashboard"
    if "light_mode" not in st.session_state:
        st.session_state.light_mode = False

    c = get_theme()

    with st.sidebar:
        st.markdown(f"""
        <div style='padding:20px 16px 20px;'>
            <div style='font-size:22px;font-weight:700;color:{c["text"]};letter-spacing:-0.5px;'>
                📚 Pageturner
            </div>
            <div style='font-size:12px;color:{c["muted"]};margin-top:4px;'>Your personal library</div>
        </div>
        """, unsafe_allow_html=True)

        for label, icon in PAGES:
            active = st.session_state.page == label
            if active:
                st.markdown(f"""
                <div style='display:flex;align-items:center;gap:12px;padding:12px 16px;
                     margin:3px 0;border-radius:10px;border-left:3px solid #6c63ff;
                     background:linear-gradient(135deg,#6c63ff22,#6c63ff44);
                     font-size:15px;font-weight:600;color:#ffffff;'>
                    {icon}&nbsp;&nbsp;{label}
                </div>""", unsafe_allow_html=True)
            else:
                if st.button(f"{icon}  {label}", key=f"nav_{label}", use_container_width=True):
                    st.session_state.page = label
                    st.rerun()

        st.markdown(f"<hr style='border-color:{c['border']};margin:20px 0;'>", unsafe_allow_html=True)

        books = load_books()
        read_count    = sum(1 for b in books if b["status"] == "Read")
        reading_count = sum(1 for b in books if b["status"] == "Currently Reading")
        want_count    = sum(1 for b in books if b["status"] == "Want to Read")

        st.markdown(f"""
        <div style='padding:0 8px;'>
            <div style='font-size:11px;color:{c["muted"]};text-transform:uppercase;
                 letter-spacing:.05em;margin-bottom:12px;'>Library</div>
            <div style='display:flex;justify-content:space-between;margin-bottom:8px;'>
                <span style='font-size:13px;color:{c["muted"]};'>✅ Read</span>
                <span style='font-size:13px;font-weight:600;color:{c["text"]};'>{read_count}</span>
            </div>
            <div style='display:flex;justify-content:space-between;margin-bottom:8px;'>
                <span style='font-size:13px;color:{c["muted"]};'>📖 Reading</span>
                <span style='font-size:13px;font-weight:600;color:{c["text"]};'>{reading_count}</span>
            </div>
            <div style='display:flex;justify-content:space-between;margin-bottom:16px;'>
                <span style='font-size:13px;color:{c["muted"]};'>📚 Want to Read</span>
                <span style='font-size:13px;font-weight:600;color:{c["text"]};'>{want_count}</span>
            </div>
        </div>
        """, unsafe_allow_html=True)

        # Dark / Light toggle
        theme_label = "☀️  Light mode" if not st.session_state.light_mode else "🌙  Dark mode"
        if st.button(theme_label, use_container_width=True, key="theme_toggle"):
            st.session_state.light_mode = not st.session_state.light_mode
            st.rerun()

    return st.session_state.page


# ── Page: Dashboard ────────────────────────────────────────────────────────────

def page_dashboard(books: list[dict], goals: dict) -> None:
    c = get_theme()
    today = date.today()
    month_label = today.strftime("%B %Y")
    year_str    = str(today.year)

    read    = [b for b in books if b["status"] == "Read"]
    want    = [b for b in books if b["status"] == "Want to Read"]
    current = [b for b in books if b["status"] == "Currently Reading"]

    finished_month = books_read_this_month(books)
    finished_year  = books_read_this_year(books)

    month_key_  = current_month_key()
    monthly_goal = goals.get(month_key_, 0)
    yearly_goal  = goals.get(year_str, 0)
    monthly_pct  = int(finished_month / monthly_goal * 100) if monthly_goal else 0
    yearly_pct   = int(finished_year  / yearly_goal  * 100) if yearly_goal  else 0

    st.markdown('<div class="page-title">Dashboard</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="page-subtitle">{today.strftime("%A, %d %B %Y")}</div>', unsafe_allow_html=True)

    st.markdown(f"""
    <div class="metric-grid">
        <div class="metric-card">
            <div class="metric-value">{len(read)}</div>
            <div class="metric-label">Books Read</div>
        </div>
        <div class="metric-card">
            <div class="metric-value">{len(current)}</div>
            <div class="metric-label">Currently Reading</div>
        </div>
        <div class="metric-card">
            <div class="metric-value">{len(want)}</div>
            <div class="metric-label">Want to Read</div>
        </div>
        <div class="metric-card">
            <div class="metric-value">{finished_year}<span style="font-size:18px;color:{c['muted']};">/{yearly_goal or '—'}</span></div>
            <div class="metric-label">This Year</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Goals row
    col_m, col_y = st.columns(2)

    with col_m:
        st.markdown(f'<div class="section-card"><div class="section-title">🎯 Monthly Goal — {month_label}</div>', unsafe_allow_html=True)
        cg1, cg2 = st.columns([3, 1])
        new_monthly = cg1.number_input("Monthly goal", min_value=0, max_value=100,
                                        value=int(monthly_goal), step=1, label_visibility="collapsed")
        if cg2.button("Save", key="save_monthly", use_container_width=True):
            goals[month_key_] = new_monthly
            save_goals(goals)
            st.rerun()
        if monthly_goal > 0:
            fill = min(finished_month / monthly_goal * 100, 100)
            st.markdown(f"""
            <div class="goal-bar-bg"><div class="goal-bar-fill" style="width:{fill}%"></div></div>
            <div class="goal-text">{finished_month} of {monthly_goal} books — {monthly_pct}% complete</div>
            """, unsafe_allow_html=True)
        else:
            st.markdown('<div class="goal-text">Set a goal to track monthly progress.</div>', unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

    with col_y:
        st.markdown(f'<div class="section-card"><div class="section-title">🏁 Yearly Goal — {year_str}</div>', unsafe_allow_html=True)
        cy1, cy2 = st.columns([3, 1])
        new_yearly = cy1.number_input("Yearly goal", min_value=0, max_value=365,
                                       value=int(yearly_goal), step=1, label_visibility="collapsed")
        if cy2.button("Save", key="save_yearly", use_container_width=True):
            goals[year_str] = new_yearly
            save_goals(goals)
            st.rerun()
        if yearly_goal > 0:
            fill_y = min(finished_year / yearly_goal * 100, 100)
            st.markdown(f"""
            <div class="goal-bar-bg"><div class="goal-bar-fill" style="width:{fill_y}%"></div></div>
            <div class="goal-text">{finished_year} of {yearly_goal} books — {yearly_pct}% complete</div>
            """, unsafe_allow_html=True)
        else:
            st.markdown('<div class="goal-text">Set a goal to track yearly progress.</div>', unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

    # Currently reading | Recently finished
    col_left, col_right = st.columns(2)

    with col_left:
        st.markdown('<div class="section-card"><div class="section-title">📖 Currently Reading</div>', unsafe_allow_html=True)
        if current:
            for b in current:
                genres_html = "".join(f'<span class="genre-tag">{g}</span>' for g in (b.get("genres") or []))
                pages_total = b.get("pages_total") or 0
                pages_read  = b.get("pages_read") or 0
                if pages_total > 0:
                    pct = min(int(pages_read / pages_total * 100), 100)
                    progress_html = f"""
                    <div style="margin-top:8px;">
                        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px;">
                            <span style="font-size:11px;color:{c['muted']};">Progress</span>
                            <span style="font-size:11px;font-weight:600;color:#f39c12;">{pct}%</span>
                        </div>
                        <div class="progress-bar-bg">
                            <div class="progress-bar-fill" style="width:{pct}%"></div>
                        </div>
                        <div class="progress-text">{pages_read:,} of {pages_total:,} pages</div>
                    </div>
                    """
                else:
                    progress_html = f'<div style="margin-top:6px;font-size:11px;color:{c["muted"]};">No page info</div>'
                st.markdown(f"""
                <div class="book-card">
                    <div class="book-card-spine" style="background:linear-gradient(180deg,#e67e22,#f39c12);"></div>
                    <div class="book-card-body">
                        <div class="book-card-title">{b['title']}</div>
                        <div class="book-card-author">{b['author']}</div>
                        <div class="book-card-tags">{genres_html}</div>
                        {progress_html}
                    </div>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.markdown('<div class="goal-text">No books in progress.</div>', unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

    with col_right:
        st.markdown('<div class="section-card"><div class="section-title">✅ Recently Finished</div>', unsafe_allow_html=True)
        if read:
            recent = sorted(read, key=lambda b: b.get("date_finished", ""), reverse=True)[:4]
            for b in recent:
                stars       = star_display(b.get("rating"))
                date_str    = (b.get("date_finished") or "")[:10] or "—"
                genres_html = "".join(f'<span class="genre-tag">{g}</span>' for g in (b.get("genres") or []))
                stars_html  = f'<div class="book-card-stars">{stars}</div>' if stars else ""
                st.markdown(f"""
                <div class="book-card">
                    <div class="book-card-spine" style="background:linear-gradient(180deg,#2ecc71,#27ae60);"></div>
                    <div class="book-card-body">
                        <div class="book-card-title">{b['title']}</div>
                        <div class="book-card-author">{b['author']}</div>
                        <div class="book-card-tags">{genres_html}</div>
                        <div class="book-card-footer">
                            {stars_html}
                            <div class="book-card-date">📅 {date_str}</div>
                        </div>
                    </div>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.markdown('<div class="goal-text">No books finished yet.</div>', unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

    # Up Next (top priority want-to-read)
    priority_want = [b for b in want if b.get("priority")]
    no_priority   = [b for b in want if not b.get("priority")]
    up_next = sorted(priority_want, key=lambda b: b.get("priority") or 99) + no_priority
    up_next = up_next[:4]

    if up_next:
        st.markdown('<div class="section-card"><div class="section-title">📚 Up Next</div>', unsafe_allow_html=True)
        cols = st.columns(len(up_next))
        for col, b in zip(cols, up_next):
            priority = b.get("priority")
            p_html = f'<span class="priority-badge priority-{priority}">{PRIORITY_LABEL[priority]}</span>' if priority else ""
            genres_html = "".join(f'<span class="genre-tag">{g}</span>' for g in (b.get("genres") or []))
            col.markdown(f"""
            <div class="book-card" style="height:100%;">
                <div class="book-card-spine" style="background:linear-gradient(180deg,#3498db,#2980b9);"></div>
                <div class="book-card-body">
                    <div class="book-card-title">{b['title']}</div>
                    <div class="book-card-author">{b['author']}</div>
                    <div class="book-card-tags" style="margin-top:6px;">{p_html}{genres_html}</div>
                </div>
            </div>
            """, unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)


# ── Page: My Books ─────────────────────────────────────────────────────────────

def page_my_books(books: list[dict]) -> None:
    st.markdown('<div class="page-title">My Books</div>', unsafe_allow_html=True)

    if not books:
        st.info("No books yet. Go to **Add Book** to get started.")
        return

    # ── Toolbar
    col1, col2, col3, col4 = st.columns([1.2, 1.5, 1.5, 1])
    status_filter = col1.selectbox("Status", ["All"] + STATUSES, label_visibility="collapsed")
    genre_filter  = col2.selectbox("Genre", ["All genres"] + GENRES, label_visibility="collapsed")

    # Auto-select Priority sort when filtering Want to Read
    default_sort = "Priority" if status_filter == "Want to Read" else "Date added (newest)"
    sort_keys    = list(SORT_OPTIONS.keys())
    sort_label   = col3.selectbox("Sort", sort_keys,
                                   index=sort_keys.index(default_sort),
                                   label_visibility="collapsed")
    search = col4.text_input("Search", placeholder="Search…", label_visibility="collapsed")

    csv_data = books_to_csv(books)
    st.download_button(
        label="⬇ Export CSV",
        data=csv_data,
        file_name=f"reading_tracker_{date.today()}.csv",
        mime="text/csv",
    )

    # ── Filter
    filtered = books
    if status_filter != "All":
        filtered = [b for b in filtered if b["status"] == status_filter]
    if genre_filter != "All genres":
        filtered = [b for b in filtered if genre_filter in (b.get("genres") or [])]
    if search:
        q = search.lower()
        filtered = [b for b in filtered if q in b["title"].lower() or q in b["author"].lower()]

    if not filtered:
        st.warning("No books match your filters.")
        return

    # ── Sort
    sort_fn, reverse = SORT_OPTIONS[sort_label]
    filtered = sorted(filtered, key=sort_fn, reverse=reverse)

    st.markdown(f"<div style='color:#8b949e;font-size:13px;margin:8px 0 16px;'>{len(filtered)} book{'s' if len(filtered)!=1 else ''}</div>", unsafe_allow_html=True)

    if "confirm_delete" not in st.session_state:
        st.session_state.confirm_delete = None

    for book in filtered:
        emoji    = STATUS_EMOJI[book["status"]]
        stars    = star_display(book.get("rating"))
        genres   = book.get("genres") or []
        priority = book.get("priority")
        p_str    = f"  {PRIORITY_LABEL[priority]}" if priority else ""
        label    = f"{emoji} {book['title']}  —  {book['author']}"
        if stars:
            label += f"  ({stars})"
        if p_str:
            label += p_str

        with st.expander(label):
            # Quick status buttons
            st.markdown("<div style='margin-bottom:10px;font-size:12px;color:#8b949e;'>Quick move:</div>", unsafe_allow_html=True)
            qc1, qc2, qc3 = st.columns(3)
            for col, status in zip([qc1, qc2, qc3], STATUSES):
                is_current = book["status"] == status
                btn_label  = f"{'✓ ' if is_current else ''}{STATUS_EMOJI[status]} {status}"
                if col.button(btn_label, key=f"quick_{status}_{book['id']}", use_container_width=True, disabled=is_current):
                    for b in books:
                        if b["id"] == book["id"]:
                            b["status"] = status
                            break
                    save_books(books)
                    st.rerun()

            st.divider()

            # Edit form
            col_a, col_b = st.columns(2)
            new_status = col_a.selectbox(
                "Status", STATUSES,
                index=STATUSES.index(book["status"]),
                key=f"status_{book['id']}",
            )
            new_rating = col_b.selectbox(
                "Rating",
                options=[0, 1, 2, 3, 4, 5],
                format_func=lambda x: star_display(x) if x else "No rating",
                index=book.get("rating") or 0,
                key=f"rating_{book['id']}",
            )
            new_genres = st.multiselect(
                "Genres", GENRES,
                default=[g for g in genres if g in GENRES],
                key=f"genres_{book['id']}",
            )
            new_priority = st.selectbox(
                "Priority",
                options=PRIORITY_OPTIONS,
                format_func=lambda x: PRIORITY_LABEL.get(x, "— No priority"),
                index=PRIORITY_OPTIONS.index(priority if priority in PRIORITY_OPTIONS else 0),
                key=f"priority_{book['id']}",
            )
            col_pages1, col_pages2 = st.columns(2)
            new_pages_total = col_pages1.number_input(
                "Total pages", min_value=0, max_value=9999,
                value=int(book.get("pages_total") or 0),
                key=f"pages_total_{book['id']}",
            )
            new_pages_read = col_pages2.number_input(
                "Pages read", min_value=0, max_value=9999,
                value=int(book.get("pages_read") or 0),
                key=f"pages_read_{book['id']}",
            )
            new_date = st.date_input(
                "Date finished",
                value=datetime.strptime(book["date_finished"], "%Y-%m-%d").date()
                if book.get("date_finished") else None,
                key=f"date_{book['id']}",
            )
            new_notes = st.text_area("Notes / Review", value=book.get("notes", ""), key=f"notes_{book['id']}")

            col_save, col_del = st.columns([2, 1])
            if col_save.button("Save changes", key=f"save_{book['id']}", use_container_width=True):
                for b in books:
                    if b["id"] == book["id"]:
                        b["status"]        = new_status
                        b["rating"]        = new_rating or None
                        b["genres"]        = new_genres
                        b["priority"]      = new_priority or None
                        b["pages_total"]   = int(new_pages_total) or None
                        b["pages_read"]    = int(new_pages_read) or None
                        b["date_finished"] = (
                            new_date.isoformat()
                            if new_date and new_status == "Read"
                            else b.get("date_finished")
                        )
                        b["notes"] = new_notes
                        break
                save_books(books)
                st.success("Saved!")
                st.rerun()

            # Delete with confirmation
            if st.session_state.confirm_delete == book["id"]:
                st.markdown('<div class="delete-confirm">⚠️ Are you sure you want to delete this book? This cannot be undone.</div>', unsafe_allow_html=True)
                cc1, cc2 = st.columns(2)
                if cc1.button("Yes, delete", key=f"confirm_yes_{book['id']}", use_container_width=True):
                    books[:] = [b for b in books if b["id"] != book["id"]]
                    save_books(books)
                    st.session_state.confirm_delete = None
                    st.rerun()
                if cc2.button("Cancel", key=f"confirm_no_{book['id']}", use_container_width=True):
                    st.session_state.confirm_delete = None
                    st.rerun()
            else:
                if col_del.button("🗑 Delete", key=f"del_{book['id']}", use_container_width=True):
                    st.session_state.confirm_delete = book["id"]
                    st.rerun()


# ── Page: Add Book ─────────────────────────────────────────────────────────────

def page_add_book(books: list[dict]) -> None:
    st.markdown('<div class="page-title">Add a Book</div>', unsafe_allow_html=True)
    st.markdown('<div class="page-subtitle">Add a new book to your library</div>', unsafe_allow_html=True)

    with st.form("add_book_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        title  = col1.text_input("Title *")
        author = col2.text_input("Author *")

        col3, col4 = st.columns(2)
        status = col3.selectbox("Status", STATUSES)
        rating = col4.select_slider(
            "Rating",
            options=[0, 1, 2, 3, 4, 5],
            format_func=lambda x: star_display(x) if x else "No rating",
            value=0,
        )
        col_g, col_p = st.columns(2)
        genres   = col_g.multiselect("Genres", GENRES)
        priority = col_p.selectbox(
            "Priority",
            options=PRIORITY_OPTIONS,
            format_func=lambda x: PRIORITY_LABEL.get(x, "— No priority"),
        )
        col5, col6    = st.columns(2)
        pages_total   = col5.number_input("Total pages", min_value=0, max_value=9999, value=0)
        pages_read    = col6.number_input("Pages read",  min_value=0, max_value=9999, value=0)
        date_finished = st.date_input("Date finished", value=None)
        notes         = st.text_area("Notes / Review", height=120)
        submitted     = st.form_submit_button("Add Book", use_container_width=True)

    if submitted:
        if not title.strip() or not author.strip():
            st.error("Title and Author are required.")
            return

        duplicate = next(
            (b for b in books
             if b["title"].lower() == title.strip().lower()
             and b["author"].lower() == author.strip().lower()),
            None,
        )
        if duplicate:
            st.warning(f'"{title}" by {author} is already in your library (status: {duplicate["status"]}).')
            return

        new_book = {
            "id":            datetime.utcnow().isoformat(),
            "title":         title.strip(),
            "author":        author.strip(),
            "status":        status,
            "rating":        rating or None,
            "genres":        genres,
            "priority":      priority or None,
            "pages_total":   int(pages_total) or None,
            "pages_read":    int(pages_read) or None,
            "date_finished": date_finished.isoformat() if date_finished and status == "Read" else None,
            "notes":         notes.strip(),
            "added_at":      datetime.utcnow().isoformat(),
        }
        books.append(new_book)
        save_books(books)
        st.success(f'"{title}" added to your library!')


# ── Page: For You (Recommendations) ───────────────────────────────────────────

def page_recommendations(books: list[dict]) -> None:
    c = get_theme()
    card_bg = "#12151f" if c["bg"] == "#0f1117" else "#f0f2f5"

    def _e(t: str) -> str:
        return html_lib.escape(str(t))

    st.markdown('<div class="page-title">For You</div>', unsafe_allow_html=True)
    st.markdown('<div class="page-subtitle">Personalized picks based on your reading taste</div>', unsafe_allow_html=True)

    read = [b for b in books if b["status"] == "Read"]

    if not read:
        st.info("No books read yet. Add and rate some books to get recommendations.")
        return

    # ── Build taste profile ───────────────────────────────────────────────────
    liked = [b for b in read if (b.get("rating") or 0) >= 4] or read

    liked_genres: dict[str, int] = {}
    for b in liked:
        for g in (b.get("genres") or []):
            liked_genres[g] = liked_genres.get(g, 0) + (b.get("rating") or 3)

    if not liked_genres:
        st.info("Add genres to your read books to get recommendations.")
        return

    top_genre_names = [g for g, _ in sorted(liked_genres.items(), key=lambda x: x[1], reverse=True)[:6]]

    # All titles already in library — never recommend these
    in_library = {b["title"].lower() for b in books}

    # ── Fetch candidates per genre, then round-robin to mix them ─────────────
    per_genre: dict[str, list[dict]] = {}

    with st.spinner("Finding books you'll love…"):
        seen: set[str] = set()
        for genre in top_genre_names:
            pool = []
            for b in fetch_genre_books(genre):
                key = b["title"].lower()
                if key not in in_library and key not in seen:
                    seen.add(key)
                    b["reason"] = f"Because you love {genre}"
                    pool.append(b)
            per_genre[genre] = pool

    # Round-robin: 1 book from each genre in turn until we have 8
    candidates: list[dict] = []
    queues = [per_genre[g] for g in top_genre_names if per_genre.get(g)]
    i = 0
    while len(candidates) < 8 and any(queues):
        q = queues[i % len(queues)]
        if q:
            candidates.append(q.pop(0))
        i += 1
        if i > 200:  # safety cap
            break

    if not candidates:
        st.info("Could not load recommendations right now. Try again later.")
        return

    top8 = candidates[:8]

    with st.spinner("Loading book details…"):
        for b in top8:
            try:
                b["_details"] = fetch_book_details(b["title"], b["author"])
            except Exception:
                b["_details"] = {"summary": "", "description": "", "pages": None, "year": None}

    top3  = top8[:3]
    rest5 = top8[3:8]

    # ── Top 3 Picks ───────────────────────────────────────────────────────────
    st.markdown(
        '<div class="section-card" style="border:1px solid #6c63ff44;">'
        '<div class="section-title">⭐ Top Picks For You</div>',
        unsafe_allow_html=True,
    )
    cols = st.columns(3)
    for col, b in zip(cols, top3):
        details     = b["_details"]
        genres_html = "".join(f'<span class="genre-tag">{_e(g)}</span>' for g in (b.get("genres") or []))
        summary     = details.get("summary") or ""
        short_sum   = (summary[:110] + "…") if len(summary) > 110 else summary

        with col:
            st.markdown(f"""
            <div style="background:{card_bg};border:1px solid #6c63ff44;border-radius:14px;
                 padding:18px 16px 14px;margin-bottom:8px;">
                <div style="font-size:26px;margin-bottom:10px;">📘</div>
                <div style="font-size:14px;font-weight:700;color:{c['text']};
                     margin-bottom:3px;line-height:1.3;">{_e(b['title'])}</div>
                <div style="font-size:12px;color:{c['muted']};margin-bottom:8px;">{_e(b['author'])}</div>
                <div style="margin-bottom:6px;">{genres_html}</div>
                <div style="font-size:12px;color:{c['body']};line-height:1.5;min-height:36px;">{_e(short_sum)}</div>
                <div style="font-size:11px;color:#a78bfa;margin-top:6px;">✦ {_e(b.get('reason', ''))}</div>
            </div>
            """, unsafe_allow_html=True)
            if st.button("View details", key=f"top_{b['title']}", use_container_width=True):
                _book_dialog(b, details)

    st.markdown("</div>", unsafe_allow_html=True)

    # ── 5 More Recommendations ────────────────────────────────────────────────
    if rest5:
        st.markdown(
            '<div class="section-card"><div class="section-title">📚 More Recommendations</div>',
            unsafe_allow_html=True,
        )
        for b in rest5:
            details     = b["_details"]
            genres_html = "".join(f'<span class="genre-tag">{_e(g)}</span>' for g in (b.get("genres") or []))
            summary     = details.get("summary") or ""
            short_sum   = (summary[:130] + "…") if len(summary) > 130 else summary

            st.markdown(f"""
            <div class="book-card">
                <div class="book-card-spine" style="background:linear-gradient(180deg,#6c63ff,#a78bfa);"></div>
                <div class="book-card-body">
                    <div style="font-size:14px;font-weight:700;color:{c['text']};margin-bottom:2px;">{_e(b['title'])}</div>
                    <div style="font-size:12px;color:{c['muted']};margin-bottom:6px;">{_e(b['author'])}</div>
                    <div class="book-card-tags">{genres_html}</div>
                    <div style="font-size:12px;color:{c['body']};line-height:1.5;margin-top:6px;">{_e(short_sum)}</div>
                    <div style="font-size:11px;color:#a78bfa;margin-top:4px;">✦ {_e(b.get('reason', ''))}</div>
                </div>
            </div>
            """, unsafe_allow_html=True)
            if st.button("View details", key=f"rec_{b['title']}", use_container_width=False):
                _book_dialog(b, details)

        st.markdown("</div>", unsafe_allow_html=True)

    # ── Taste profile ─────────────────────────────────────────────────────────
    st.markdown('<div class="section-card"><div class="section-title">🎨 Your taste profile</div>', unsafe_allow_html=True)
    profile_genres = sorted(liked_genres.items(), key=lambda x: x[1], reverse=True)[:6]
    cols = st.columns(len(profile_genres))
    for col, (genre, score) in zip(cols, profile_genres):
        col.markdown(f"""
        <div style="text-align:center;padding:12px 8px;background:{card_bg};
             border-radius:10px;border:1px solid {c['border']};">
            <div style="font-size:20px;margin-bottom:4px;">📖</div>
            <div style="font-size:12px;font-weight:600;color:{c['text']};">{genre}</div>
            <div style="font-size:10px;color:{c['muted']};margin-top:2px;">score {score}</div>
        </div>
        """, unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)


# ── Page: Stats ────────────────────────────────────────────────────────────────

def page_stats(books: list[dict], goals: dict) -> None:
    st.markdown('<div class="page-title">Stats</div>', unsafe_allow_html=True)
    st.markdown('<div class="page-subtitle">Your reading at a glance</div>', unsafe_allow_html=True)

    read = [b for b in books if b["status"] == "Read"]

    if not read:
        st.info("No books read yet. Stats will appear once you mark books as Read.")
        return

    avg_rating = round(
        sum(b["rating"] for b in read if b.get("rating")) /
        max(1, sum(1 for b in read if b.get("rating"))),
        1,
    )
    this_year    = str(date.today().year)
    yearly_count = sum(1 for b in read if (b.get("date_finished") or "").startswith(this_year))
    yearly_goal  = goals.get(this_year, 0)
    attained     = {k: 1 for k, v in goals.items() if v > 0 and len(k) == 7 and
                    sum(1 for b in read if (b.get("date_finished") or "")[:7] == k) >= v}
    monthly_goals_set = len([k for k, v in goals.items() if v > 0 and len(k) == 7])

    st.markdown(f"""
    <div class="metric-grid">
        <div class="metric-card">
            <div class="metric-value">{len(read)}</div>
            <div class="metric-label">Total Read</div>
        </div>
        <div class="metric-card">
            <div class="metric-value">{yearly_count}<span style="font-size:18px;color:#8b949e;">/{yearly_goal or '—'}</span></div>
            <div class="metric-label">Read in {this_year}</div>
        </div>
        <div class="metric-card">
            <div class="metric-value">{avg_rating}</div>
            <div class="metric-label">Avg Rating</div>
        </div>
        <div class="metric-card">
            <div class="metric-value">{len(attained)}<span style="font-size:18px;color:#8b949e;">/{monthly_goals_set}</span></div>
            <div class="metric-label">Monthly Goals Met</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Yearly goal progress bar
    if yearly_goal > 0:
        fill_y = min(yearly_count / yearly_goal * 100, 100)
        yearly_pct = int(fill_y)
        st.markdown(f"""
        <div class="section-card">
            <div class="section-title">🏁 Yearly Goal — {this_year}</div>
            <div class="goal-bar-bg"><div class="goal-bar-fill" style="width:{fill_y}%"></div></div>
            <div class="goal-text">{yearly_count} of {yearly_goal} books — {yearly_pct}% complete</div>
        </div>
        """, unsafe_allow_html=True)

    # Charts
    monthly: dict[str, int] = {}
    yearly:  dict[str, int] = {}
    for b in read:
        mkey = (b.get("date_finished") or "")[:7]
        ykey = (b.get("date_finished") or "")[:4]
        if mkey:
            monthly[mkey] = monthly.get(mkey, 0) + 1
        if ykey:
            yearly[ykey] = yearly.get(ykey, 0) + 1

    col1, col2 = st.columns(2)
    with col1:
        st.markdown('<div class="section-card"><div class="section-title">📅 Books per month</div>', unsafe_allow_html=True)
        if monthly:
            df = pd.DataFrame(sorted(monthly.items()), columns=["Month", "Books"]).set_index("Month")
            st.bar_chart(df, color="#6c63ff")
        st.markdown("</div>", unsafe_allow_html=True)

    with col2:
        st.markdown('<div class="section-card"><div class="section-title">📆 Books per year</div>', unsafe_allow_html=True)
        if yearly:
            df_y = pd.DataFrame(sorted(yearly.items()), columns=["Year", "Books"]).set_index("Year")
            st.bar_chart(df_y, color="#a78bfa")
        st.markdown("</div>", unsafe_allow_html=True)

    col3, col4 = st.columns(2)
    with col3:
        st.markdown('<div class="section-card"><div class="section-title">⭐ Rating distribution</div>', unsafe_allow_html=True)
        ratings = [b["rating"] for b in read if b.get("rating")]
        if ratings:
            df_r = pd.DataFrame({"Rating": ratings})
            counts = df_r["Rating"].value_counts().sort_index()
            counts.index = [star_display(i) for i in counts.index]
            st.bar_chart(counts, color="#f0c040")
        else:
            st.markdown('<div class="goal-text">No ratings yet.</div>', unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

    with col4:
        st.markdown('<div class="section-card"><div class="section-title">🏷 Books by genre</div>', unsafe_allow_html=True)
        genre_counts: dict[str, int] = {}
        for b in read:
            for g in (b.get("genres") or []):
                genre_counts[g] = genre_counts.get(g, 0) + 1
        if genre_counts:
            df_g = pd.DataFrame(
                sorted(genre_counts.items(), key=lambda x: x[1], reverse=True),
                columns=["Genre", "Books"],
            ).set_index("Genre")
            st.bar_chart(df_g, color="#2ecc71")
        else:
            st.markdown('<div class="goal-text">No genres tagged yet.</div>', unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

    top = sorted([b for b in read if b.get("rating")], key=lambda b: b["rating"], reverse=True)[:5]
    if top:
        st.markdown('<div class="section-card"><div class="section-title">🏆 Top Rated</div>', unsafe_allow_html=True)
        for b in top:
            genres_html = "".join(f'<span class="genre-tag">{g}</span>' for g in (b.get("genres") or []))
            st.markdown(f"""
            <div class="book-item">
                <div class="book-cover" style="background:#6c63ff22;">📘</div>
                <div class="book-info">
                    <div class="book-title">{b['title']}</div>
                    <div class="book-author">{b['author']}</div>
                    <div style="margin-top:4px;">{genres_html}</div>
                </div>
                <div class="stars">{star_display(b['rating'])}</div>
            </div>
            """, unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    st.set_page_config(
        page_title="Pageturner",
        page_icon="📚",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    inject_css(get_theme())
    page = render_sidebar()

    books = load_books()
    goals = load_goals()

    st.markdown("<div style='padding:8px 16px;'>", unsafe_allow_html=True)

    if page == "Dashboard":
        page_dashboard(books, goals)
    elif page == "My Books":
        page_my_books(books)
    elif page == "Add Book":
        page_add_book(books)
    elif page == "For You":
        page_recommendations(books)
    elif page == "Stats":
        page_stats(books, goals)

    st.markdown("</div>", unsafe_allow_html=True)


if __name__ == "__main__":
    main()

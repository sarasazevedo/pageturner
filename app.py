import json
import csv
import io
from datetime import datetime, date
from pathlib import Path

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

SORT_OPTIONS = {
    "Date finished (newest)": lambda b: b.get("date_finished") or "",
    "Date added (newest)":    lambda b: b.get("added_at") or "",
    "Title (A–Z)":            lambda b: b.get("title", "").lower(),
    "Author (A–Z)":           lambda b: b.get("author", "").lower(),
    "Rating (highest)":       lambda b: b.get("rating") or 0,
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


def books_to_csv(books: list[dict]) -> str:
    output = io.StringIO()
    fields = ["title", "author", "status", "rating", "genres", "date_finished", "notes", "added_at"]
    writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for b in books:
        row = dict(b)
        row["genres"] = ", ".join(b.get("genres") or [])
        writer.writerow(row)
    return output.getvalue()


# ── CSS ────────────────────────────────────────────────────────────────────────

def inject_css() -> None:
    st.markdown("""
    <style>
    [data-testid="stAppViewContainer"] { background-color: #0f1117; }
    [data-testid="stSidebar"] {
        background-color: #1a1d27;
        border-right: 1px solid #2a2d3e;
    }
    [data-testid="stSidebar"] * { color: #c9d1d9 !important; }

    .page-title {
        font-size: 28px; font-weight: 700; color: #ffffff; margin-bottom: 4px;
    }
    .page-subtitle {
        font-size: 14px; color: #8b949e; margin-bottom: 28px;
    }

    .metric-grid {
        display: grid; grid-template-columns: repeat(4, 1fr);
        gap: 16px; margin-bottom: 28px;
    }
    .metric-card {
        background: #1a1d27; border: 1px solid #2a2d3e;
        border-radius: 14px; padding: 20px; text-align: center;
        transition: transform 0.2s;
    }
    .metric-card:hover { transform: translateY(-2px); }
    .metric-value {
        font-size: 32px; font-weight: 700; color: #ffffff;
        line-height: 1; margin-bottom: 6px;
    }
    .metric-label {
        font-size: 12px; color: #8b949e;
        text-transform: uppercase; letter-spacing: 0.05em;
    }

    .section-card {
        background: #1a1d27; border: 1px solid #2a2d3e;
        border-radius: 14px; padding: 24px; margin-bottom: 20px;
    }
    .section-title {
        font-size: 16px; font-weight: 600; color: #ffffff;
        margin-bottom: 16px; display: flex; align-items: center; gap: 8px;
    }

    .book-item {
        display: flex; align-items: center; gap: 14px;
        padding: 12px 0; border-bottom: 1px solid #2a2d3e;
    }
    .book-item:last-child { border-bottom: none; }
    .book-cover {
        width: 36px; height: 50px; border-radius: 4px;
        display: flex; align-items: center; justify-content: center;
        font-size: 20px; flex-shrink: 0;
    }
    .book-info { flex: 1; min-width: 0; }
    .book-title {
        font-weight: 600; color: #ffffff; font-size: 14px;
        white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
    }
    .book-author { font-size: 12px; color: #8b949e; margin-top: 2px; }
    .book-meta { text-align: right; flex-shrink: 0; }
    .stars { color: #f0c040; font-size: 13px; letter-spacing: 1px; }
    .book-date { font-size: 11px; color: #8b949e; margin-top: 2px; }

    .genre-tag {
        display: inline-block; padding: 2px 8px; border-radius: 12px;
        font-size: 11px; font-weight: 500; margin: 2px 2px 0 0;
        background: #6c63ff22; color: #a78bfa; border: 1px solid #6c63ff44;
    }
    .status-badge {
        display: inline-block; padding: 3px 10px; border-radius: 20px;
        font-size: 11px; font-weight: 600;
    }

    .goal-bar-bg {
        background: #2a2d3e; border-radius: 8px; height: 10px;
        margin: 10px 0; overflow: hidden;
    }
    .goal-bar-fill {
        height: 100%; border-radius: 8px;
        background: linear-gradient(90deg, #6c63ff, #a78bfa);
        transition: width 0.4s ease;
    }
    .goal-text { font-size: 13px; color: #8b949e; margin-top: 6px; }

    /* confirm-delete warning style */
    .delete-confirm {
        background: #3d1a1a; border: 1px solid #7f1d1d;
        border-radius: 10px; padding: 12px 16px; margin-top: 8px;
        color: #fca5a5; font-size: 13px;
    }

    [data-testid="stTextInput"] input,
    [data-testid="stTextArea"] textarea {
        background-color: #0f1117 !important;
        border: 1px solid #2a2d3e !important;
        border-radius: 8px !important; color: #ffffff !important;
    }
    [data-testid="stFormSubmitButton"] button {
        background: linear-gradient(135deg, #6c63ff, #a78bfa) !important;
        border: none !important; border-radius: 8px !important;
        color: white !important; font-weight: 600 !important;
        padding: 10px 24px !important; width: 100% !important;
    }
    h1, h2, h3 { color: #ffffff !important; }
    p, label, div { color: #c9d1d9; }
    [data-testid="stMetric"] { display: none; }
    .stExpander {
        background: #1a1d27 !important; border: 1px solid #2a2d3e !important;
        border-radius: 10px !important; margin-bottom: 8px !important;
    }
    .stButton button {
        background: #2a2d3e !important; border: 1px solid #3a3d4e !important;
        color: #c9d1d9 !important; border-radius: 8px !important;
    }
    .stButton button:hover {
        background: #3a3d4e !important; color: #ffffff !important;
    }
    </style>
    """, unsafe_allow_html=True)


# ── Sidebar ────────────────────────────────────────────────────────────────────

PAGES = [
    ("Dashboard", "🏠"),
    ("My Books",  "📖"),
    ("Add Book",  "➕"),
    ("Stats",     "📊"),
]


def render_sidebar() -> str:
    if "page" not in st.session_state:
        st.session_state.page = "Dashboard"

    with st.sidebar:
        st.markdown("""
        <div style='padding:20px 16px 28px;'>
            <div style='font-size:22px;font-weight:700;color:#ffffff;letter-spacing:-0.5px;'>
                📚 Pageturner
            </div>
            <div style='font-size:12px;color:#8b949e;margin-top:4px;'>Your personal library</div>
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

        st.markdown("<hr style='border-color:#2a2d3e;margin:20px 0;'>", unsafe_allow_html=True)

        books = load_books()
        read_count    = sum(1 for b in books if b["status"] == "Read")
        reading_count = sum(1 for b in books if b["status"] == "Currently Reading")
        want_count    = sum(1 for b in books if b["status"] == "Want to Read")

        st.markdown(f"""
        <div style='padding:0 8px;'>
            <div style='font-size:11px;color:#8b949e;text-transform:uppercase;
                 letter-spacing:.05em;margin-bottom:12px;'>Library</div>
            <div style='display:flex;justify-content:space-between;margin-bottom:8px;'>
                <span style='font-size:13px;color:#8b949e;'>✅ Read</span>
                <span style='font-size:13px;font-weight:600;color:#fff;'>{read_count}</span>
            </div>
            <div style='display:flex;justify-content:space-between;margin-bottom:8px;'>
                <span style='font-size:13px;color:#8b949e;'>📖 Reading</span>
                <span style='font-size:13px;font-weight:600;color:#fff;'>{reading_count}</span>
            </div>
            <div style='display:flex;justify-content:space-between;'>
                <span style='font-size:13px;color:#8b949e;'>📚 Want to Read</span>
                <span style='font-size:13px;font-weight:600;color:#fff;'>{want_count}</span>
            </div>
        </div>
        """, unsafe_allow_html=True)

    return st.session_state.page


# ── Page: Dashboard ────────────────────────────────────────────────────────────

def page_dashboard(books: list[dict], goals: dict) -> None:
    today = date.today()
    month_label = today.strftime("%B %Y")

    read    = [b for b in books if b["status"] == "Read"]
    want    = [b for b in books if b["status"] == "Want to Read"]
    current = [b for b in books if b["status"] == "Currently Reading"]
    finished_month = books_read_this_month(books)
    goal_key     = current_month_key()
    monthly_goal = goals.get(goal_key, 0)
    progress_pct = int(finished_month / monthly_goal * 100) if monthly_goal else 0

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
            <div class="metric-value">{finished_month}<span style="font-size:18px;color:#8b949e;">/{monthly_goal or '—'}</span></div>
            <div class="metric-label">This Month</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Monthly goal
    st.markdown(f'<div class="section-card"><div class="section-title">🎯 Goal for {month_label}</div>', unsafe_allow_html=True)
    col_goal, col_btn = st.columns([3, 1])
    new_goal = col_goal.number_input(
        "Monthly goal", min_value=0, max_value=100,
        value=int(monthly_goal), step=1, label_visibility="collapsed",
    )
    if col_btn.button("Save", use_container_width=True):
        goals[goal_key] = new_goal
        save_goals(goals)
        st.rerun()

    if monthly_goal > 0:
        fill = min(finished_month / monthly_goal * 100, 100)
        st.markdown(f"""
        <div class="goal-bar-bg"><div class="goal-bar-fill" style="width:{fill}%"></div></div>
        <div class="goal-text">{finished_month} of {monthly_goal} books — {progress_pct}% complete</div>
        """, unsafe_allow_html=True)
    else:
        st.markdown('<div class="goal-text">Set a goal to track your monthly progress.</div>', unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

    col_left, col_right = st.columns(2)

    with col_left:
        st.markdown('<div class="section-card"><div class="section-title">📖 Currently Reading</div>', unsafe_allow_html=True)
        if current:
            for b in current:
                genres_html = "".join(f'<span class="genre-tag">{g}</span>' for g in (b.get("genres") or []))
                st.markdown(f"""
                <div class="book-item">
                    <div class="book-cover" style="background:#e67e2222;">📖</div>
                    <div class="book-info">
                        <div class="book-title">{b['title']}</div>
                        <div class="book-author">{b['author']}</div>
                        <div style="margin-top:4px;">{genres_html}</div>
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
                stars    = star_display(b.get("rating"))
                date_str = (b.get("date_finished") or "")[:10] or "—"
                st.markdown(f"""
                <div class="book-item">
                    <div class="book-cover" style="background:#2ecc7122;">✅</div>
                    <div class="book-info">
                        <div class="book-title">{b['title']}</div>
                        <div class="book-author">{b['author']}</div>
                    </div>
                    <div class="book-meta">
                        <div class="stars">{stars}</div>
                        <div class="book-date">{date_str}</div>
                    </div>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.markdown('<div class="goal-text">No books finished yet.</div>', unsafe_allow_html=True)
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
    genre_filter  = col2.selectbox(
        "Genre", ["All genres"] + GENRES, label_visibility="collapsed"
    )
    sort_label    = col3.selectbox("Sort", list(SORT_OPTIONS.keys()), label_visibility="collapsed")
    search        = col4.text_input("Search", placeholder="Search…", label_visibility="collapsed")

    # Export button
    csv_data = books_to_csv(books)
    st.download_button(
        label="⬇ Export CSV",
        data=csv_data,
        file_name=f"reading_tracker_{date.today()}.csv",
        mime="text/csv",
        use_container_width=False,
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
    sort_fn  = SORT_OPTIONS[sort_label]
    reverse  = sort_label not in ("Title (A–Z)", "Author (A–Z)")
    filtered = sorted(filtered, key=sort_fn, reverse=reverse)

    st.markdown(f"<div style='color:#8b949e;font-size:13px;margin:8px 0 16px;'>{len(filtered)} book{'s' if len(filtered)!=1 else ''}</div>", unsafe_allow_html=True)

    if "confirm_delete" not in st.session_state:
        st.session_state.confirm_delete = None

    for book in filtered:
        emoji    = STATUS_EMOJI[book["status"]]
        stars    = star_display(book.get("rating"))
        genres   = book.get("genres") or []
        label    = f"{emoji} {book['title']}  —  {book['author']}"
        if stars:
            label += f"  ({stars})"

        with st.expander(label):
            # ── Quick status buttons
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

            # ── Edit form
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

            # ── Delete with confirmation
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
        genres        = st.multiselect("Genres", GENRES)
        date_finished = st.date_input("Date finished", value=None)
        notes         = st.text_area("Notes / Review", height=120)
        submitted     = st.form_submit_button("Add Book", use_container_width=True)

    if submitted:
        if not title.strip() or not author.strip():
            st.error("Title and Author are required.")
            return

        # Duplicate detection
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
            "date_finished": date_finished.isoformat() if date_finished and status == "Read" else None,
            "notes":         notes.strip(),
            "added_at":      datetime.utcnow().isoformat(),
        }
        books.append(new_book)
        save_books(books)
        st.success(f'"{title}" added to your library!')


# ── Page: Stats ────────────────────────────────────────────────────────────────

def page_stats(books: list[dict], goals: dict) -> None:
    st.markdown('<div class="page-title">Stats</div>', unsafe_allow_html=True)
    st.markdown('<div class="page-subtitle">Your reading at a glance</div>', unsafe_allow_html=True)

    read = [b for b in books if b["status"] == "Read"]

    if not read:
        st.info("No books read yet. Stats will appear once you mark books as Read.")
        return

    # ── Top stat cards
    avg_rating = round(
        sum(b["rating"] for b in read if b.get("rating")) /
        max(1, sum(1 for b in read if b.get("rating"))),
        1,
    )
    this_year    = str(date.today().year)
    yearly_count = sum(1 for b in read if (b.get("date_finished") or "").startswith(this_year))
    attained     = {k: 1 for k, v in goals.items() if goals.get(k, 0) > 0 and
                    sum(1 for b in read if (b.get("date_finished") or "")[:7] == k) >= v}

    st.markdown(f"""
    <div class="metric-grid">
        <div class="metric-card">
            <div class="metric-value">{len(read)}</div>
            <div class="metric-label">Total Read</div>
        </div>
        <div class="metric-card">
            <div class="metric-value">{yearly_count}</div>
            <div class="metric-label">Read in {this_year}</div>
        </div>
        <div class="metric-card">
            <div class="metric-value">{avg_rating}</div>
            <div class="metric-label">Avg Rating</div>
        </div>
        <div class="metric-card">
            <div class="metric-value">{len(attained)}<span style="font-size:18px;color:#8b949e;">/{len([k for k,v in goals.items() if v>0])}</span></div>
            <div class="metric-label">Goals Met</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # ── Charts
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

    # ── Top rated
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

    inject_css()
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
    elif page == "Stats":
        page_stats(books, goals)

    st.markdown("</div>", unsafe_allow_html=True)


if __name__ == "__main__":
    main()

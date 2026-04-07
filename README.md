# 📚 Pageturner

A personal reading tracker built with Streamlit. Keep track of books you've read, books you want to read, set monthly goals, and rate each book.

## Features

- Track books across three statuses: Read, Currently Reading, Want to Read
- Monthly reading goals with progress tracking
- Ratings, genres, notes and date finished per book
- Stats dashboard: books per month/year, rating distribution, genre breakdown
- Export your library to CSV

## Run locally

```bash
# Clone the repo
git clone https://github.com/sarasazevedo/pageturner.git
cd pageturner

# Create and activate virtual environment
python -m venv .venv
.venv\Scripts\activate  # Windows
source .venv/bin/activate  # macOS/Linux

# Install dependencies
pip install -r requirements.txt

# Run the app
streamlit run app.py
```

Then open `http://localhost:8501` in your browser.

## Tech stack

- [Streamlit](https://streamlit.io) — UI framework
- [pandas](https://pandas.pydata.org) — data handling
- JSON flat files — local storage

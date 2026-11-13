# K-Drama Universe: "What should I watch tonight?"
# Run with:  python -m streamlit run app.py
import html
import itertools
import json
import re
import urllib.error
import urllib.request
from decimal import Decimal
from urllib.parse import quote_plus, urlencode

import altair as alt
import pandas as pd
import psycopg2
import streamlit as st

# ---- 1) database settings ----
# On your laptop: put DB_PASSWORD in the file  .streamlit/secrets.toml  (next to this app.py).
# Online (Streamlit Cloud): paste the same settings into the app's "Secrets" box.
# Never write a real password in this file, because this file goes to GitHub.
def setting(name, default):
    try:
        return st.secrets[name]
    except Exception:                    # no secrets file or no such key: use the default
        return default


DB_HOST = setting("DB_HOST", "localhost")
DB_PORT = int(setting("DB_PORT", 5432))
DB_NAME = setting("DB_NAME", "kdrama")
DB_USER = setting("DB_USER", "postgres")
DB_PASSWORD = setting("DB_PASSWORD", "YOUR_PASSWORD")
DB_SSLMODE = setting("DB_SSLMODE", "prefer")      # online databases need "require"
YOUTUBE_API_KEY = setting("YOUTUBE_API_KEY", "")   # optional: lets the app play trailers inside the page

st.set_page_config(page_title="K-Drama Universe", page_icon="🎬", layout="wide")


def new_connection():
    return psycopg2.connect(host=DB_HOST, port=DB_PORT, dbname=DB_NAME, user=DB_USER,
                            password=DB_PASSWORD, sslmode=DB_SSLMODE, connect_timeout=15,
                            keepalives=1, keepalives_idle=30, keepalives_interval=10, keepalives_count=3)


@st.cache_resource                       # connect once and reuse the connection
def get_connection():
    return new_connection()


def run_query(sql, params=None):
    """Run a SELECT and return the result as a table (DataFrame)."""
    for attempt in (1, 2):
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                cols = [c[0] for c in cur.description]
                rows = cur.fetchall()
            return pd.DataFrame(rows, columns=cols)
        except (psycopg2.OperationalError, psycopg2.InterfaceError):
            get_connection.clear()       # online databases go to sleep: connect again once
            if attempt == 2:
                raise
        except Exception:
            conn.rollback()              # a failed query must not block the next one
            raise


def run_command(sql, params=None):
    """Run an INSERT, UPDATE or DELETE and save it (commit)."""
    for attempt in (1, 2):
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(sql, params)
            conn.commit()
            return
        except (psycopg2.OperationalError, psycopg2.InterfaceError):
            get_connection.clear()
            if attempt == 2:
                raise
        except Exception:
            conn.rollback()
            raise


def has(value):
    """True when a cell really holds something (not None, NaN or empty text)."""
    if value is None:
        return False
    if isinstance(value, float) and pd.isna(value):
        return False
    return str(value).strip() != ""


_button_counter = itertools.count()      # gives every Trailer button its own key


def youtube_search_url(title, year=None):
    year_text = f" {int(year)}" if has(year) else ""
    return ("https://www.youtube.com/results?search_query="
            + quote_plus(f"{title}{year_text} korean drama official trailer"))


@st.cache_data(ttl=30 * 24 * 3600, max_entries=1000, show_spinner=False)
def find_trailer(title, year):
    """Ask YouTube for the top result for '<title> <year> korean drama official trailer'.
    Returns (video id, video title). A failed search raises an error, so it is never cached.
    A search costs 100 of the 10,000 free units per day, so every answer is remembered for 30 days."""
    year_text = f" {year}" if year else ""
    params = {"part": "snippet", "type": "video", "videoEmbeddable": "true", "maxResults": 1,
              "q": f"{title}{year_text} korean drama official trailer", "key": YOUTUBE_API_KEY}
    try:
        with urllib.request.urlopen("https://www.googleapis.com/youtube/v3/search?" + urlencode(params),
                                    timeout=10) as resp:
            data = json.load(resp)
    except urllib.error.HTTPError as e:
        try:
            err = json.load(e)["error"]
            reason = f'{err["errors"][0]["reason"]}: {err.get("message", "")}'[:220]   # what YouTube says
        except Exception:
            reason = f"HTTP {e.code}"
        raise RuntimeError(reason)
    items = data.get("items", [])
    if not items:
        raise LookupError("YouTube found no video")
    return items[0]["id"]["videoId"], html.unescape(items[0]["snippet"]["title"])


def set_trailer(title, year, where):
    st.session_state["trailer"] = {"title": title, "year": year, "where": where}


def clear_trailer():
    st.session_state.pop("trailer", None)


def trailer_button(title, year=None, where=""):
    """Small button under a drama. It only remembers the choice; the player is drawn at the top of the page."""
    st.button("▶ Trailer", key=f"trailer_{where}_{next(_button_counter)}",
              on_click=set_trailer, args=(title, year, where))


def trailer_player(where):
    """Plays the chosen trailer inside the page (call it near the top of a screen)."""
    t = st.session_state.get("trailer")
    if not t or t["where"] != where:
        return
    title, year = t["title"], t["year"]
    year_text = f" ({int(year)})" if has(year) else ""
    with st.container(border=True):
        head, close = st.columns([6, 1])
        head.subheader(f"Trailer: {title}{year_text}")
        close.button("Close", key=f"trailer_close_{where}", on_click=clear_trailer)
        if not YOUTUBE_API_KEY:
            st.info("To play trailers inside the app, add YOUTUBE_API_KEY to the secrets. "
                    "Until then, use the YouTube link below.")
        else:
            try:
                video_id, video_title = find_trailer(title, int(year) if has(year) else None)
                st.video(f"https://www.youtube.com/watch?v={video_id}")
                st.caption(f"Top YouTube result: {video_title}")
            except Exception as e:
                st.warning(f"Could not load the trailer ({e}).")
        st.markdown(f"[Not the right video? Search YouTube yourself]({youtube_search_url(title, year)})")


def show_posters(df, per_row=5):
    """Show dramas as a wall of posters, one card per drama."""
    for start in range(0, len(df), per_row):
        cols = st.columns(per_row)
        for col, (_, row) in zip(cols, df.iloc[start:start + per_row].iterrows()):
            with col:
                if has(row["poster_url"]):
                    st.image(row["poster_url"], width="stretch")
                else:
                    st.caption("(no poster)")
                year = "" if pd.isna(row["start_year"]) else f" ({int(row['start_year'])})"
                st.markdown(f"**{row['title']}**{year}")
                st.caption(f"Rating {row['rating']} | {int(row['votes']):,} votes")
                st.caption(row["lead_actors"] if has(row["lead_actors"]) else "Leads: unknown")
                trailer_button(row["title"], row["start_year"], "disc")


# ---------------------------------------------------------------------------
# Screen 1: Discover (mood picker, beginner picks, poster wall, surprise me)
# Query behind it: Q7 in 3_questions.sql
# ---------------------------------------------------------------------------
PICKS_SQL = """
SELECT d.title, d.start_year, d.rating, d.votes, d.poster_url,
       STRING_AGG(a.name, ', ' ORDER BY dl.lead_order) AS lead_actors      -- main leads in one cell
FROM drama d
JOIN drama_lead dl ON dl.drama_id = d.drama_id                             -- join 1: drama -> its leads
JOIN actor a       ON a.actor_id  = dl.actor_id                            -- join 2: lead -> actor name
WHERE d.rating >= %s                                                       -- well rated...
  AND d.votes  >= %s                                                       -- ...and popular enough
  AND EXISTS (SELECT 1                                                     -- only the chosen genre
              FROM drama_genre dg
              JOIN genre g ON g.genre_id = dg.genre_id
              WHERE dg.drama_id = d.drama_id AND g.name = %s)
GROUP BY d.drama_id, d.title, d.start_year, d.rating, d.votes, d.poster_url
ORDER BY {order}
LIMIT %s
"""


def discover_page():
    st.header("Discover")
    trailer_player("disc")
    genres = run_query("SELECT name FROM genre ORDER BY name")["name"].tolist()

    left, mid, right = st.columns([2, 2, 2])
    with left:
        mood = st.selectbox("What is your mood?", genres,
                            index=genres.index("Romance") if "Romance" in genres else 0)
    with mid:
        level = st.radio("Who is watching?",
                         ["New to K-drama (famous ones)", "I watch a lot (hidden gems too)"])
    with right:
        min_rating = st.slider("Minimum rating", 5.0, 9.5, 8.0, 0.1)

    # beginners get popular dramas (many votes); fans also see less famous ones
    min_votes = 20000 if level.startswith("New") else 1000

    c1, c2 = st.columns([1, 5])
    surprise = c1.button("Surprise me")
    if surprise:
        df = run_query(PICKS_SQL.format(order="random()"), (min_rating, min_votes, mood, 1))
        st.subheader("Tonight's surprise")
    else:
        df = run_query(PICKS_SQL.format(order="d.rating DESC, d.votes DESC"),
                       (min_rating, min_votes, mood, 10))
        st.subheader(f"Top picks for a {mood.lower()} mood")

    if df.empty:
        st.info("No drama matches. Try a lower rating or the other viewer type.")
    else:
        show_posters(df)


# ---------------------------------------------------------------------------
# Screen 2: Trends (rating heatmap and yearly trend)
# Queries behind it: Q8 (heatmap) and Q6 (yearly trend) in 3_questions.sql
# ---------------------------------------------------------------------------
HEATMAP_SQL = """
SELECT d.start_year,                                      -- row of the heatmap
       g.name                  AS genre,                  -- column of the heatmap
       COUNT(*)                AS dramas,                 -- how many dramas are behind the average
       ROUND(AVG(d.rating), 2) AS avg_rating              -- the colour of the cell
FROM drama d
JOIN drama_genre dg ON dg.drama_id = d.drama_id           -- join 1: drama -> its genres
JOIN genre g        ON g.genre_id  = dg.genre_id          -- join 2: genre id -> genre name
WHERE d.rating IS NOT NULL
  AND d.start_year BETWEEN %s AND %s                      -- chosen years
GROUP BY d.start_year, g.name
HAVING COUNT(*) >= %s                                     -- skip cells with too few dramas to trust
ORDER BY d.start_year, g.name
"""

YEARLY_SQL = """
SELECT start_year,                                        -- year the drama started
       COUNT(*)                AS dramas,                 -- rated dramas that started that year
       ROUND(AVG(rating), 2)   AS avg_rating              -- average IMDb rating
FROM drama
WHERE rating IS NOT NULL AND start_year BETWEEN %s AND %s
GROUP BY start_year
ORDER BY start_year
"""


def trends_page():
    st.header("Trends")
    years = st.slider("Years", 2000, 2025, (2010, 2025))
    min_dramas = st.slider("Minimum dramas behind each cell", 1, 10, 3)

    # --- yearly trend (Q6) ---
    yearly = run_query(YEARLY_SQL, years)
    st.subheader("Average rating by year")
    if yearly.empty:
        st.info("No data for these years.")
    else:
        yearly["avg_rating"] = yearly["avg_rating"].astype(float)
        line = (alt.Chart(yearly).mark_line(point=True)
                .encode(x=alt.X("start_year:O", title="Year"),
                        y=alt.Y("avg_rating:Q", title="Average rating", scale=alt.Scale(zero=False)),
                        tooltip=["start_year", "dramas", "avg_rating"]))
        st.altair_chart(line, width="stretch")
        best = yearly.loc[yearly["avg_rating"].idxmax()]
        st.caption(f"Best year in this range: {int(best['start_year'])} "
                   f"(average {best['avg_rating']:.2f} over {int(best['dramas'])} dramas)")

    # --- heatmap (Q8) ---
    heat = run_query(HEATMAP_SQL, (years[0], years[1], min_dramas))
    st.subheader("Rating heatmap: year x genre")
    if heat.empty:
        st.info("No cell has enough dramas. Lower the minimum.")
    else:
        heat["avg_rating"] = heat["avg_rating"].astype(float)
        chart = (alt.Chart(heat).mark_rect()
                 .encode(x=alt.X("genre:N", title="Genre"),
                         y=alt.Y("start_year:O", title="Year"),
                         color=alt.Color("avg_rating:Q", title="Avg rating",
                                         scale=alt.Scale(scheme="redyellowgreen", domain=[6, 9])),
                         tooltip=["start_year", "genre", "dramas", "avg_rating"]))
        st.altair_chart(chart, width="stretch")
        top = heat.loc[heat["avg_rating"].idxmax()]
        st.caption(f"Best cell: {top['genre']} dramas of {int(top['start_year'])} "
                   f"(average {top['avg_rating']:.2f} over {int(top['dramas'])} dramas)")


# ---------------------------------------------------------------------------
# Screen 3: Connections (Six Degrees of K-Drama and writer-actor network)
# Queries behind it: Q9 (Six Degrees, recursive) and Q10 (network) in 3_questions.sql
# ---------------------------------------------------------------------------
SIX_DEGREES_SQL = """
WITH RECURSIVE edges AS (                                  -- two actors are linked if they are leads of the same drama
    SELECT l1.actor_id AS a, l2.actor_id AS b
    FROM drama_lead l1
    JOIN drama_lead l2 ON l2.drama_id = l1.drama_id AND l2.actor_id <> l1.actor_id
),
paths AS (
    SELECT e.b AS actor_id, ARRAY[s.actor_id, e.b] AS path, 1 AS degrees   -- degree 1: co-stars of the start actor
    FROM actor s
    JOIN edges e ON e.a = s.actor_id
    WHERE s.name = %s                                       -- the start actor
    UNION ALL
    SELECT e.b, p.path || e.b, p.degrees + 1                -- extend every path by one more co-star
    FROM paths p
    JOIN edges e ON e.a = p.actor_id
    WHERE e.b <> ALL (p.path)                               -- never visit the same actor twice
      AND p.degrees < %s                                    -- stop after the chosen number of steps
)
SELECT p.degrees, p.path
FROM paths p
JOIN actor t ON t.actor_id = p.actor_id
WHERE t.name = %s                                           -- the target actor
ORDER BY p.degrees
LIMIT 1
"""

WRITER_NETWORK_SQL = """
SELECT a.name AS actor,                                     -- lead actor
       COUNT(DISTINCT d.drama_id)  AS dramas,               -- dramas with this writer
       ROUND(AVG(d.rating), 2)     AS avg_rating            -- average rating of those dramas
FROM writer w
JOIN drama_writer dw ON dw.writer_id = w.writer_id          -- writer -> dramas
JOIN drama d         ON d.drama_id   = dw.drama_id
JOIN drama_lead dl   ON dl.drama_id  = d.drama_id           -- drama -> leads
JOIN actor a         ON a.actor_id   = dl.actor_id
WHERE w.name = %s
GROUP BY a.name
ORDER BY dramas DESC, avg_rating DESC NULLS LAST, a.name
LIMIT 15
"""

ACTOR_NETWORK_SQL = """
SELECT w.name AS writer,                                    -- writer of the actor's dramas
       COUNT(DISTINCT d.drama_id)  AS dramas,
       ROUND(AVG(d.rating), 2)     AS avg_rating
FROM actor a
JOIN drama_lead dl   ON dl.actor_id  = a.actor_id           -- actor -> dramas
JOIN drama d         ON d.drama_id   = dl.drama_id
JOIN drama_writer dw ON dw.drama_id  = d.drama_id           -- drama -> writers
JOIN writer w        ON w.writer_id  = dw.writer_id
WHERE a.name = %s
GROUP BY w.name
ORDER BY dramas DESC, avg_rating DESC NULLS LAST, w.name
LIMIT 15
"""


def six_degrees_tab():
    st.subheader("Six Degrees of K-Drama")
    st.caption("Two actors are linked if they were the leads of the same drama. "
               "How many steps connect them?")
    names = run_query("""SELECT DISTINCT a.name FROM actor a
                         JOIN drama_lead l1 ON l1.actor_id = a.actor_id
                         JOIN drama_lead l2 ON l2.drama_id = l1.drama_id AND l2.actor_id <> l1.actor_id
                         ORDER BY a.name""")["name"].tolist()
    c1, c2, c3 = st.columns(3)
    start = c1.selectbox("From", names, index=names.index("Hyun Bin") if "Hyun Bin" in names else 0)
    target = c2.selectbox("To", names, index=names.index("Lee Jong-suk") if "Lee Jong-suk" in names else 1)
    max_steps = c3.slider("Look up to this many steps", 2, 6, 6)

    if start == target:
        st.info("Choose two different actors.")
        return
    res = run_query(SIX_DEGREES_SQL, (start, max_steps, target))
    if res.empty:
        st.warning(f"No connection found within {max_steps} steps. "
                   "They may belong to separate groups of actors.")
        return
    path = [int(x) for x in res.loc[0, "path"]]
    degrees = int(res.loc[0, "degrees"])
    id_name = run_query("SELECT actor_id, name FROM actor WHERE actor_id = ANY(%s)", (path,))
    name_of = dict(zip(id_name["actor_id"], id_name["name"]))
    st.success(f"{degrees} step(s):  " + "  ->  ".join(name_of[i] for i in path))

    rows = []
    for a, b in zip(path, path[1:]):          # find one drama that links each pair
        link = run_query("""SELECT d.title, d.start_year
                            FROM drama_lead l1
                            JOIN drama_lead l2 ON l2.drama_id = l1.drama_id
                            JOIN drama d       ON d.drama_id  = l1.drama_id
                            WHERE l1.actor_id = %s AND l2.actor_id = %s
                            ORDER BY d.rating DESC NULLS LAST LIMIT 1""", (a, b))
        title = link.loc[0, "title"] if not link.empty else "?"
        rows.append({"Actor": name_of[a], "worked with": name_of[b], "in the drama": title})
    st.table(pd.DataFrame(rows))


def network_tab():
    st.subheader("Writer-actor network")
    mode = st.radio("Start from", ["A writer", "An actor"], horizontal=True)
    if mode == "A writer":
        names = run_query("""SELECT w.name FROM writer w
                             JOIN drama_writer dw ON dw.writer_id = w.writer_id
                             JOIN drama_lead dl   ON dl.drama_id  = dw.drama_id
                             GROUP BY w.name HAVING COUNT(DISTINCT dw.drama_id) >= 3
                             ORDER BY COUNT(DISTINCT dw.drama_id) DESC, w.name""")["name"].tolist()
        centre = st.selectbox("Writer", names)
        df = run_query(WRITER_NETWORK_SQL, (centre,))
        other = "actor"
    else:
        names = run_query("""SELECT a.name FROM actor a
                             JOIN drama_lead dl   ON dl.actor_id = a.actor_id
                             JOIN drama_writer dw ON dw.drama_id = dl.drama_id
                             GROUP BY a.name HAVING COUNT(DISTINCT dl.drama_id) >= 3
                             ORDER BY COUNT(DISTINCT dl.drama_id) DESC, a.name""")["name"].tolist()
        centre = st.selectbox("Actor", names)
        df = run_query(ACTOR_NETWORK_SQL, (centre,))
        other = "writer"

    if df.empty:
        st.info("No connections found.")
        return
    esc = lambda t: str(t).replace('"', '\\"')
    lines = ["digraph G {", "rankdir=LR;", 'node [fontname="Helvetica"];',
             f'"{esc(centre)}" [shape=box, style=filled, fillcolor="#cfe8ff"];']
    for _, r in df.iterrows():
        lines.append(f'"{esc(r[other])}" [shape=ellipse, style=filled, fillcolor="#ffd6e7"];')
        lines.append(f'"{esc(centre)}" -> "{esc(r[other])}" [label="{int(r["dramas"])} drama(s)"];')
    lines.append("}")
    st.graphviz_chart("\n".join(lines))
    df["avg_rating"] = df["avg_rating"].astype(float)
    st.dataframe(df, hide_index=True)


def connections_page():
    st.header("Connections")
    tab1, tab2 = st.tabs(["Six Degrees", "Writer-actor network"])
    with tab1:
        six_degrees_tab()
    with tab2:
        network_tab()



# ---------------------------------------------------------------------------
# Screen: Find similar (type or pick a drama you like, get dramas like it)
# Query behind it: Q4 in 3_questions.sql (same writer or same lead), extended with shared genres
# ---------------------------------------------------------------------------
SIMILAR_SQL = """
SELECT * FROM (
    SELECT d.drama_id, d.title, d.start_year, d.rating, d.votes, d.poster_url,
           (SELECT STRING_AGG(DISTINCT w.name, ', ')                       -- writers shared with the chosen drama
            FROM drama_writer x
            JOIN drama_writer y ON y.writer_id = x.writer_id
            JOIN writer w       ON w.writer_id = x.writer_id
            WHERE x.drama_id = d.drama_id AND y.drama_id = %(given)s) AS shared_writers,
           (SELECT STRING_AGG(DISTINCT a.name, ', ')                       -- leads shared with the chosen drama
            FROM drama_lead x
            JOIN drama_lead y ON y.actor_id = x.actor_id
            JOIN actor a      ON a.actor_id = x.actor_id
            WHERE x.drama_id = d.drama_id AND y.drama_id = %(given)s) AS shared_leads,
           (SELECT COUNT(*)                                                -- genres shared with the chosen drama
            FROM drama_genre x
            JOIN drama_genre y ON y.genre_id = x.genre_id
            WHERE x.drama_id = d.drama_id AND y.drama_id = %(given)s) AS shared_genres
    FROM drama d
    WHERE d.drama_id <> %(given)s                                          -- do not suggest the drama itself
      AND d.rating >= %(min_rating)s
      AND d.votes  >= %(min_votes)s
) t
WHERE shared_writers IS NOT NULL OR shared_leads IS NOT NULL OR shared_genres >= 2
ORDER BY (CASE WHEN shared_writers IS NOT NULL THEN 3 ELSE 0 END)         -- same writer counts most...
       + (CASE WHEN shared_leads   IS NOT NULL THEN 2 ELSE 0 END)         -- ...then same lead...
       + shared_genres DESC,                                              -- ...then each shared genre
         rating DESC, votes DESC
LIMIT 10
"""


def show_similar(df, per_row=5):
    """Poster wall where every card also says WHY the drama was suggested."""
    for start in range(0, len(df), per_row):
        cols = st.columns(per_row)
        for col, (_, row) in zip(cols, df.iloc[start:start + per_row].iterrows()):
            with col:
                if has(row["poster_url"]):
                    st.image(row["poster_url"], width="stretch")
                else:
                    st.caption("(no poster)")
                year = "" if pd.isna(row["start_year"]) else f" ({int(row['start_year'])})"
                st.markdown(f"**{row['title']}**{year}")
                st.caption(f"Rating {row['rating']} | {int(row['votes']):,} votes")
                reasons = []
                if has(row["shared_writers"]):
                    reasons.append(f"Same writer: {row['shared_writers']}")
                if has(row["shared_leads"]):
                    reasons.append(f"Same lead: {row['shared_leads']}")
                if has(row["shared_genres"]):
                    reasons.append(f"{int(row['shared_genres'])} shared genre(s)")
                st.caption(" | ".join(reasons))
                trailer_button(row["title"], row["start_year"], "sim")


def find_similar_page():
    st.header("Find similar")
    trailer_player("sim")
    st.caption("Pick a drama you liked. We suggest dramas with the same writer, "
               "the same lead actor or the same genres, and tell you why.")
    dramas = run_query("SELECT drama_id, title, start_year FROM drama ORDER BY title, start_year")
    labels = []
    for _, r in dramas.iterrows():
        year = "" if pd.isna(r["start_year"]) else f" ({int(r['start_year'])})"
        labels.append(f"{r['title']}{year}")
    seen = {}
    for i, lab in enumerate(labels):                      # keep labels unique if two dramas look the same
        seen[lab] = seen.get(lab, 0) + 1
        if seen[lab] > 1:
            labels[i] = f"{lab} [{dramas.loc[i, 'drama_id']}]"
    default = labels.index("Crash Landing on You (2019)") if "Crash Landing on You (2019)" in labels else 0

    choice = st.selectbox("Type or pick a drama", labels, index=default)
    c1, c2 = st.columns(2)
    min_rating = c1.slider("Suggest only dramas rated at least", 5.0, 9.0, 7.0, 0.1)
    min_votes = c2.select_slider("...with at least this many votes", options=[0, 100, 1000, 5000, 20000], value=1000)

    given = dramas.loc[labels.index(choice), "drama_id"]
    df = run_query(SIMILAR_SQL, {"given": given, "min_rating": min_rating, "min_votes": min_votes})
    st.subheader("You may also like")
    if df.empty:
        st.info("No similar drama found with these filters. Try a lower rating or fewer votes.")
    else:
        show_similar(df)


# ---------------------------------------------------------------------------
# Screen: Taste Card (pick 3 favourite dramas, get your K-drama DNA card)
# Queries behind it: genre mix, average rating, favourite writer and lead (3_questions.sql, Q11)
# ---------------------------------------------------------------------------
BADGES = {"Romance": "The Hopeless Romantic", "Thriller": "The Thrill-Seeker", "Comedy": "The Laugh-Seeker",
          "Fantasy": "The Dreamer", "Action": "The Action Fan", "Horror": "The Night Owl",
          "Mystery": "The Detective", "History": "The History Buff", "Crime": "The Case Solver",
          "Family": "The Family Viewer", "Music": "The Music Lover", "Sci-Fi": "The Futurist"}


def taste_card_page():
    st.header("Your K-drama Taste Card")
    trailer_player("taste")
    st.caption("Pick three dramas you love. We turn them into your K-drama DNA.")
    dramas = run_query("SELECT drama_id, title, start_year FROM drama ORDER BY title, start_year")
    labels = []
    for _, r in dramas.iterrows():
        year = "" if pd.isna(r["start_year"]) else f" ({int(r['start_year'])})"
        labels.append(f"{r['title']}{year}")
    seen = {}
    for i, lab in enumerate(labels):
        seen[lab] = seen.get(lab, 0) + 1
        if seen[lab] > 1:
            labels[i] = f"{lab} [{dramas.loc[i, 'drama_id']}]"
    defaults = [x for x in ["Crash Landing on You (2019)", "Squid Game (2021)", "Kingdom (2019)"] if x in labels]
    picks = st.multiselect("Your 3 favourite dramas", labels, default=defaults, max_selections=3)
    if len(picks) < 3:
        st.info("Pick three dramas to see your card.")
        return
    ids = [dramas.loc[labels.index(x), "drama_id"] for x in picks]

    info = run_query("SELECT title, start_year, rating, poster_url FROM drama WHERE drama_id = ANY(%s)", (ids,))
    genres = run_query("""SELECT g.name AS genre, COUNT(*) AS how_many                  -- genre mix of the picks
                          FROM drama_genre dg JOIN genre g ON g.genre_id = dg.genre_id
                          WHERE dg.drama_id = ANY(%s)
                          GROUP BY g.name ORDER BY how_many DESC, g.name""", (ids,))
    writer = run_query("""SELECT w.name, COUNT(*) AS n                                   -- most frequent writer
                          FROM drama_writer dw JOIN writer w ON w.writer_id = dw.writer_id
                          WHERE dw.drama_id = ANY(%s) GROUP BY w.name ORDER BY n DESC, w.name LIMIT 1""", (ids,))
    lead = run_query("""SELECT a.name, COUNT(*) AS n                                     -- most frequent lead actor
                        FROM drama_lead dl JOIN actor a ON a.actor_id = dl.actor_id
                        WHERE dl.drama_id = ANY(%s) GROUP BY a.name ORDER BY n DESC, a.name LIMIT 1""", (ids,))

    specific = [g for g in genres["genre"] if g != "Drama"]
    top = specific[0] if specific else (genres["genre"][0] if not genres.empty else "Drama")
    badge = BADGES.get(top, f"The {top} Fan")
    ratings = [float(x) for x in info["rating"] if has(x)]
    avg = f"{sum(ratings) / len(ratings):.1f}" if ratings else "n/a"

    with st.container(border=True):
        st.caption("Your K-drama DNA")
        st.subheader(badge)
        cols = st.columns(3)
        for col, (_, r) in zip(cols, info.iterrows()):
            with col:
                if has(r["poster_url"]):
                    st.image(r["poster_url"], width="stretch")
                st.markdown(f"**{r['title']}**")
                trailer_button(r["title"], None, "taste")
        m1, m2, m3 = st.columns(3)
        m1.metric("Average rating", avg)
        m2.metric("Favourite writer", writer["name"][0] if not writer.empty else "unknown")
        m3.metric("Favourite lead", lead["name"][0] if not lead.empty else "unknown")
        if not genres.empty:
            chart = (alt.Chart(genres).mark_bar()
                     .encode(x=alt.X("how_many:Q", title="Dramas", axis=alt.Axis(tickMinStep=1)),
                             y=alt.Y("genre:N", sort="-x", title=None),
                             tooltip=["genre", "how_many"]))
            st.altair_chart(chart, width="stretch")


# ---------------------------------------------------------------------------
# Screen: Data stories (four questions answered from the data)
# Queries behind it: Q12 to Q15 (3_questions.sql)
# ---------------------------------------------------------------------------
FAME_SQL = """
SELECT CASE WHEN votes < 1000  THEN '1) under 1K votes'
            WHEN votes < 10000 THEN '2) 1K to 10K'
            WHEN votes < 50000 THEN '3) 10K to 50K'
            ELSE '4) 50K or more' END      AS fame,                -- how famous the drama is
       COUNT(*)                            AS dramas,
       ROUND(AVG(rating), 2)               AS avg_rating
FROM drama
WHERE rating IS NOT NULL AND votes IS NOT NULL
GROUP BY 1
ORDER BY 1
"""

CORR_SQL = "SELECT ROUND(CORR(rating, LN(votes))::numeric, 3) AS r FROM drama WHERE rating IS NOT NULL AND votes > 0"

SLUMP_SQL = """
WITH ordered AS (                                              -- number each writer's dramas by year
    SELECT dw.writer_id, d.title, d.rating,
           ROW_NUMBER() OVER (PARTITION BY dw.writer_id ORDER BY d.start_year, d.drama_id) AS rn
    FROM drama_writer dw
    JOIN drama d ON d.drama_id = dw.drama_id
    WHERE d.rating IS NOT NULL AND d.start_year IS NOT NULL
)
SELECT w.name AS writer, f.title AS first_drama, f.rating AS first_rating,
       s.title AS second_drama, s.rating AS second_rating,
       ROUND(s.rating - f.rating, 1) AS change
FROM ordered f
JOIN ordered s ON s.writer_id = f.writer_id AND f.rn = 1 AND s.rn = 2     -- first and second drama
JOIN writer w  ON w.writer_id = f.writer_id
"""

GEMS_SQL = """
SELECT title, start_year, rating, votes FROM drama
WHERE rating >= 8.5 AND votes BETWEEN 100 AND 1999             -- loved by few, but enough votes to trust
ORDER BY rating DESC, votes DESC LIMIT 10
"""

GUILTY_SQL = """
SELECT title, start_year, rating, votes FROM drama
WHERE votes >= 50000 AND rating < 7.0                          -- watched by many, rated low
ORDER BY votes DESC LIMIT 10
"""


def stories_page():
    st.header("Data stories")
    st.caption("Four questions, answered from the database.")

    st.subheader("1. Does fame change the rating?")
    fame = run_query(FAME_SQL)
    fame["avg_rating"] = fame["avg_rating"].astype(float)
    bars = (alt.Chart(fame).mark_bar()
            .encode(x=alt.X("fame:N", title="How many people voted"),
                    y=alt.Y("avg_rating:Q", title="Average rating", scale=alt.Scale(zero=False)),
                    tooltip=["fame", "dramas", "avg_rating"]))
    st.altair_chart(bars, width="stretch")
    r = run_query(CORR_SQL)["r"][0]
    st.caption(f"Correlation between rating and log(votes): {float(r):.3f}. "
               "Closer to 1 means more famous dramas tend to be rated higher.")

    st.subheader("2. Does a writer's second drama do worse than the first?")
    slump = run_query(SLUMP_SQL)
    slump["change"] = slump["change"].astype(float)
    lower = (slump["change"] < 0).mean() * 100
    st.write(f"Writers with at least two rated dramas: {len(slump)}. "
             f"Average change from first to second: {slump['change'].mean():+.2f} rating points. "
             f"Second drama rated lower for {lower:.0f}% of writers.")
    st.caption("Biggest drops:")
    st.dataframe(slump.sort_values("change").head(8), hide_index=True)

    c1, c2 = st.columns(2)
    with c1:
        st.subheader("3. Hidden gems")
        st.caption("Rated 8.5 or more, with 100 to 1,999 votes.")
        st.dataframe(run_query(GEMS_SQL), hide_index=True)
    with c2:
        st.subheader("4. Guilty pleasures")
        st.caption("Watched by 50,000 or more people, but rated below 7.")
        st.dataframe(run_query(GUILTY_SQL), hide_index=True)


# ---------------------------------------------------------------------------
# Screen: My list (username, watchlist, watched dramas with your own rating, recommendations)
# Tables: app_user, watchlist, user_rating. Queries behind it: Q16 and Q17 (3_questions.sql)
# ---------------------------------------------------------------------------
RECOMMEND_SQL = """
WITH liked AS (                                            -- dramas this user rated 7 or more
    SELECT drama_id FROM user_rating WHERE user_id = %(uid)s AND my_rating >= 7
),
seen AS (                                                  -- dramas already watched or on the watchlist
    SELECT drama_id FROM user_rating WHERE user_id = %(uid)s
    UNION
    SELECT drama_id FROM watchlist   WHERE user_id = %(uid)s
),
w_score AS (                                               -- writers shared with liked dramas
    SELECT w2.drama_id, COUNT(DISTINCT w1.writer_id) AS n
    FROM liked l
    JOIN drama_writer w1 ON w1.drama_id  = l.drama_id
    JOIN drama_writer w2 ON w2.writer_id = w1.writer_id
    GROUP BY w2.drama_id
),
l_score AS (                                               -- lead actors shared with liked dramas
    SELECT l2.drama_id, COUNT(DISTINCT l1.actor_id) AS n
    FROM liked l
    JOIN drama_lead l1 ON l1.drama_id = l.drama_id
    JOIN drama_lead l2 ON l2.actor_id = l1.actor_id
    GROUP BY l2.drama_id
),
g_score AS (                                               -- genres shared with liked dramas
    SELECT g2.drama_id, COUNT(DISTINCT g1.genre_id) AS n
    FROM liked l
    JOIN drama_genre g1 ON g1.drama_id = l.drama_id
    JOIN drama_genre g2 ON g2.genre_id = g1.genre_id
    GROUP BY g2.drama_id
)
SELECT * FROM (
    SELECT d.drama_id, d.title, d.start_year, d.rating, d.votes, d.poster_url,
           COALESCE(w.n, 0) AS shared_writers,
           COALESCE(l.n, 0) AS shared_leads,
           COALESCE(g.n, 0) AS shared_genres,
           3 * COALESCE(w.n, 0) + 2 * COALESCE(l.n, 0) + COALESCE(g.n, 0) AS score   -- writer 3, lead 2, genre 1
    FROM drama d
    LEFT JOIN w_score w ON w.drama_id = d.drama_id
    LEFT JOIN l_score l ON l.drama_id = d.drama_id
    LEFT JOIN g_score g ON g.drama_id = d.drama_id
    WHERE d.drama_id NOT IN (SELECT drama_id FROM seen)    -- never suggest what the user already knows
      AND d.rating >= %(min_rating)s
      AND d.votes  >= 1000
) t
WHERE score > 0
ORDER BY score DESC, rating DESC, votes DESC
LIMIT 10
"""


def drama_choices():
    """All dramas as 'Title (year)' labels (made unique) with their ids."""
    dramas = run_query("SELECT drama_id, title, start_year FROM drama ORDER BY title, start_year")
    labels, seen = [], {}
    for _, r in dramas.iterrows():
        year = "" if pd.isna(r["start_year"]) else f" ({int(r['start_year'])})"
        lab = f"{r['title']}{year}"
        seen[lab] = seen.get(lab, 0) + 1
        labels.append(lab if seen[lab] == 1 else f"{lab} [{r['drama_id']}]")
    return dict(zip(labels, dramas["drama_id"]))


def my_list_page():
    st.header("My list")
    st.caption("Only a username is stored (no personal data). Save dramas, rate the ones you watched, "
               "and get suggestions based on what you liked.")

    name = st.text_input("Your username", value=st.session_state.get("username", ""))
    if st.button("Sign in / create"):
        name = name.strip()
        if not name:
            st.warning("Type a username first.")
        else:
            run_command("INSERT INTO app_user (username) VALUES (%s) ON CONFLICT (username) DO NOTHING", (name,))
            row = run_query("SELECT user_id FROM app_user WHERE username = %s", (name,))
            st.session_state["user_id"] = int(row["user_id"][0])
            st.session_state["username"] = name
    if "user_id" not in st.session_state:
        st.info("Sign in with any username to start your list.")
        return
    uid = st.session_state["user_id"]
    st.success(f"Signed in as {st.session_state['username']}")

    choices = drama_choices()
    tab1, tab2, tab3 = st.tabs(["Watchlist", "Watched and my ratings", "Recommended for you"])

    # ---------------- watchlist ----------------
    with tab1:
        pick = st.selectbox("Add a drama to your watchlist", list(choices), key="wl_pick")
        if st.button("Add to watchlist"):
            run_command("INSERT INTO watchlist (user_id, drama_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                        (uid, choices[pick]))
        wl = run_query("""SELECT d.drama_id, d.title, d.start_year, d.rating, w.added_on
                          FROM watchlist w JOIN drama d ON d.drama_id = w.drama_id
                          WHERE w.user_id = %s ORDER BY w.added_on DESC, d.title""", (uid,))
        if wl.empty:
            st.info("Your watchlist is empty.")
        else:
            st.dataframe(wl.drop(columns=["drama_id"]), hide_index=True)
            wl_map = {f"{r['title']} ({'' if pd.isna(r['start_year']) else int(r['start_year'])})": r["drama_id"]
                      for _, r in wl.iterrows()}
            chosen = st.selectbox("Pick one from your watchlist", list(wl_map), key="wl_chosen")
            my = st.slider("If you watched it, your rating", 0.0, 10.0, 8.0, 0.5, key="wl_rating")
            b1, b2 = st.columns(2)
            if b1.button("I watched it (save rating)"):
                run_command("""INSERT INTO user_rating (user_id, drama_id, my_rating) VALUES (%s, %s, %s)
                               ON CONFLICT (user_id, drama_id) DO UPDATE SET my_rating = EXCLUDED.my_rating""",
                            (uid, wl_map[chosen], my))
                run_command("DELETE FROM watchlist WHERE user_id = %s AND drama_id = %s", (uid, wl_map[chosen]))
                st.rerun()
            if b2.button("Remove from watchlist"):
                run_command("DELETE FROM watchlist WHERE user_id = %s AND drama_id = %s", (uid, wl_map[chosen]))
                st.rerun()

    # ---------------- watched and my ratings ----------------
    with tab2:
        pick2 = st.selectbox("A drama you watched", list(choices), key="seen_pick")
        my2 = st.slider("Your rating", 0.0, 10.0, 8.0, 0.5, key="seen_rating")
        if st.button("Save my rating"):
            run_command("""INSERT INTO user_rating (user_id, drama_id, my_rating) VALUES (%s, %s, %s)
                           ON CONFLICT (user_id, drama_id) DO UPDATE SET my_rating = EXCLUDED.my_rating""",
                        (uid, choices[pick2], my2))
            run_command("DELETE FROM watchlist WHERE user_id = %s AND drama_id = %s", (uid, choices[pick2]))
            st.rerun()
        seen_df = run_query("""SELECT d.title, d.start_year, ur.my_rating, d.rating AS imdb_rating,
                                      ROUND(ur.my_rating - d.rating, 1) AS you_minus_imdb
                               FROM user_rating ur JOIN drama d ON d.drama_id = ur.drama_id
                               WHERE ur.user_id = %s ORDER BY ur.my_rating DESC, d.title""", (uid,))
        if seen_df.empty:
            st.info("You have not rated any drama yet.")
        else:
            st.dataframe(seen_df, hide_index=True)

    # ---------------- recommendations ----------------
    with tab3:
        liked = run_query("SELECT COUNT(*) AS n FROM user_rating WHERE user_id = %s AND my_rating >= 7", (uid,))
        if int(liked["n"][0]) == 0:
            st.info("Rate at least one drama 7 or higher (in the previous tab) to get suggestions.")
        else:
            min_rating = st.slider("Suggest only dramas rated at least (IMDb)", 5.0, 9.0, 7.0, 0.1, key="rec_min")
            recs = run_query(RECOMMEND_SQL, {"uid": uid, "min_rating": min_rating})
            if recs.empty:
                st.info("No suggestion with this filter. Try a lower rating.")
            else:
                trailer_player("rec")
                for start in range(0, len(recs), 5):
                    cols = st.columns(5)
                    for col, (_, r) in zip(cols, recs.iloc[start:start + 5].iterrows()):
                        with col:
                            if has(r["poster_url"]):
                                st.image(r["poster_url"], width="stretch")
                            year = "" if pd.isna(r["start_year"]) else f" ({int(r['start_year'])})"
                            st.markdown(f"**{r['title']}**{year}")
                            st.caption(f"IMDb {r['rating']} | {int(r['votes']):,} votes")
                            why = []
                            if int(r["shared_writers"]):
                                why.append("same writer as a drama you liked")
                            if int(r["shared_leads"]):
                                why.append("same lead as a drama you liked")
                            if int(r["shared_genres"]):
                                why.append(f"{int(r['shared_genres'])} genre(s) you like")
                            st.caption(" | ".join(why))
                            trailer_button(r["title"], r["start_year"], "rec")

# ---------------------------------------------------------------------------
# Screen: Ask the data (no AI, no key, free)
# Pick a question, fill in the blanks, and see the SQL and the answer.
# ---------------------------------------------------------------------------
ASK_QUESTIONS = {
    "Best dramas of a genre": """
SELECT d.title, d.start_year, d.rating, d.votes
FROM drama d
JOIN drama_genre dg ON dg.drama_id = d.drama_id            -- join 1: drama -> its genres
JOIN genre g        ON g.genre_id  = dg.genre_id           -- join 2: genre id -> name
WHERE g.name = %(genre)s
  AND d.start_year >= %(year)s
  AND d.votes >= %(votes)s
  AND d.rating IS NOT NULL
ORDER BY d.rating DESC, d.votes DESC
LIMIT 15
""",
    "Dramas of a writer": """
SELECT d.title, d.start_year, d.rating, d.votes
FROM writer w
JOIN drama_writer dw ON dw.writer_id = w.writer_id         -- join 1: writer -> dramas
JOIN drama d         ON d.drama_id   = dw.drama_id         -- join 2: drama details
WHERE w.name = %(writer)s
ORDER BY d.start_year
""",
    "Best writers by average rating": """
SELECT w.name AS writer,
       COUNT(*)                AS dramas,
       ROUND(AVG(d.rating), 2) AS avg_rating
FROM writer w
JOIN drama_writer dw ON dw.writer_id = w.writer_id
JOIN drama d         ON d.drama_id   = dw.drama_id
WHERE d.rating IS NOT NULL
GROUP BY w.writer_id, w.name
HAVING COUNT(*) >= %(min_dramas)s                          -- enough dramas to trust the average
ORDER BY avg_rating DESC, dramas DESC
LIMIT 15
""",
    "Dramas of an actor (as a lead)": """
SELECT d.title, d.start_year, d.rating, dl.lead_order
FROM actor a
JOIN drama_lead dl ON dl.actor_id = a.actor_id
JOIN drama d       ON d.drama_id  = dl.drama_id
WHERE a.name = %(actor)s
ORDER BY d.start_year
""",
    "Who worked with this actor?": """
SELECT a2.name AS co_lead, COUNT(*) AS dramas_together,
       ROUND(AVG(d.rating), 2) AS avg_rating
FROM actor a1
JOIN drama_lead l1 ON l1.actor_id = a1.actor_id
JOIN drama_lead l2 ON l2.drama_id = l1.drama_id AND l2.actor_id <> l1.actor_id
JOIN actor a2      ON a2.actor_id = l2.actor_id
JOIN drama d       ON d.drama_id  = l1.drama_id
WHERE a1.name = %(actor)s
GROUP BY a2.actor_id, a2.name
ORDER BY dramas_together DESC, avg_rating DESC
LIMIT 15
""",
    "Directors with the most dramas": """
SELECT dr.name AS director, COUNT(*) AS dramas,
       ROUND(AVG(d.rating), 2) AS avg_rating
FROM director dr
JOIN drama_director dd ON dd.director_id = dr.director_id
JOIN drama d           ON d.drama_id     = dd.drama_id
GROUP BY dr.director_id, dr.name
ORDER BY dramas DESC, avg_rating DESC
LIMIT 15
""",
    "Average rating of each genre": """
SELECT g.name AS genre, COUNT(*) AS dramas,
       ROUND(AVG(d.rating), 2) AS avg_rating
FROM genre g
JOIN drama_genre dg ON dg.genre_id = g.genre_id
JOIN drama d        ON d.drama_id  = dg.drama_id
WHERE d.rating IS NOT NULL
GROUP BY g.genre_id, g.name
ORDER BY avg_rating DESC
""",
}


def ask_page():
    st.header("Ask the data")
    st.caption("Pick a question and fill in the blanks. You get the answer and the SQL behind it.")
    q = st.selectbox("Question", list(ASK_QUESTIONS))
    params = {}

    if q == "Best dramas of a genre":
        genres = run_query("SELECT name FROM genre ORDER BY name")["name"].tolist()
        c1, c2, c3 = st.columns(3)
        params["genre"] = c1.selectbox("Genre", genres)
        params["year"] = c2.slider("Started in or after", 1969, 2025, 2015)
        params["votes"] = c3.select_slider("Minimum votes", [100, 1000, 5000, 20000, 50000], 1000)
    elif q == "Dramas of a writer":
        names = run_query("SELECT DISTINCT w.name FROM writer w JOIN drama_writer dw "
                          "ON dw.writer_id = w.writer_id ORDER BY w.name")["name"].tolist()
        params["writer"] = st.selectbox("Writer (type to search)", names)
    elif q == "Best writers by average rating":
        params["min_dramas"] = st.slider("At least this many rated dramas", 2, 8, 3)
    elif q in ("Dramas of an actor (as a lead)", "Who worked with this actor?"):
        names = run_query("SELECT DISTINCT a.name FROM actor a JOIN drama_lead dl "
                          "ON dl.actor_id = a.actor_id ORDER BY a.name")["name"].tolist()
        params["actor"] = st.selectbox("Actor (type to search)", names)

    sql = ASK_QUESTIONS[q]
    try:
        df = run_query(sql, params)
    except Exception as e:
        st.error(f"Query failed: {e}")
        return
    if df.empty:
        st.info("No rows found.")
    else:
        for c in df.columns:                               # Decimal -> float so numbers show nicely
            if df[c].map(lambda v: isinstance(v, Decimal)).any():
                df[c] = df[c].astype(float)
        st.dataframe(df, hide_index=True)
    with st.expander("SQL used"):
        st.code(sql.strip(), language="sql")


# ---------------------------------------------------------------------------
# Screen: Under the Hood (proof of the database work: Part B schema and Part C cleaning)
# Everything here is read live from PostgreSQL's own catalog, so it always matches the database.
# ---------------------------------------------------------------------------
CORE_TABLES = ["drama", "writer", "director", "actor", "genre",
               "drama_writer", "drama_director", "drama_lead", "drama_genre"]

CONSTRAINTS_SQL = """
SELECT c.conrelid::regclass::text AS table_name,              -- table the rule belongs to
       CASE c.contype WHEN 'p' THEN 'PRIMARY KEY'
                      WHEN 'f' THEN 'FOREIGN KEY'
                      WHEN 'u' THEN 'UNIQUE'
                      WHEN 'c' THEN 'CHECK'
                      ELSE c.contype::text END AS kind,        -- type of rule
       c.conname                 AS rule_name,
       pg_get_constraintdef(c.oid) AS definition               -- the rule itself
FROM pg_constraint c
WHERE c.conrelid::regclass::text = ANY(%s)
ORDER BY table_name, kind, rule_name
"""

INDEXES_SQL = """
SELECT tablename AS table_name, indexname AS index_name, indexdef AS definition
FROM pg_indexes
WHERE schemaname = 'public' AND tablename = ANY(%s)
ORDER BY tablename, indexname
"""

SPEED_TESTS = {
    "Dramas that started in 2019":
        "SELECT title, rating FROM drama WHERE start_year = 2019",
    "Dramas rated 9 or more":
        "SELECT title, rating FROM drama WHERE rating >= 9",
    "Leads of one drama (2 joins)":
        "SELECT d.title, a.name FROM drama d "
        "JOIN drama_lead dl ON dl.drama_id = d.drama_id "
        "JOIN actor a ON a.actor_id = dl.actor_id "
        "WHERE d.title = 'Crash Landing on You'",
}


def explain_plan(sql, indexes_off):
    """Run EXPLAIN ANALYZE on a SELECT, optionally with index scans switched off for this one test."""
    conn = new_connection()
    conn.set_session(readonly=True)                          # this test can only read
    try:
        with conn.cursor() as cur:
            cur.execute("SET LOCAL statement_timeout = 10000")
            if indexes_off:                                  # SET LOCAL lasts only for this test
                cur.execute("SET LOCAL enable_indexscan = off")
                cur.execute("SET LOCAL enable_indexonlyscan = off")
                cur.execute("SET LOCAL enable_bitmapscan = off")
            cur.execute("EXPLAIN (ANALYZE) " + sql)
            lines = [r[0] for r in cur.fetchall()]
        conn.rollback()
    finally:
        conn.close()
    return lines


def plan_summary(lines):
    """(scan type, execution time in ms) taken from the plan text."""
    text = "\n".join(lines)
    scan = re.search(r"(Index Only Scan|Index Scan|Bitmap Heap Scan|Seq Scan)", text)
    ms = re.search(r"Execution Time: ([0-9.]+) ms", text)
    return (scan.group(1) if scan else "?"), (float(ms.group(1)) if ms else None)


def under_hood_page():
    st.header("Database overview")
    st.caption("The database behind the app, read live from PostgreSQL: table sizes, missing values, "
               "rules, indexes and a speed test.")
    tab1, tab2, tab3, tab4 = st.tabs(["Tables and NULLs", "Rules", "Indexes and speed", "Cleaning log"])

    with tab1:
        union = " UNION ALL ".join(
            f"SELECT '{t}' AS table_name, COUNT(*) AS row_count FROM {t}" for t in CORE_TABLES)
        counts = run_query(union + " ORDER BY row_count DESC")
        counts["row_count"] = counts["row_count"].astype(int)
        left, right = st.columns([2, 3])
        left.metric("Total rows in the 9 tables", f"{int(counts['row_count'].sum()):,}")
        left.dataframe(counts, hide_index=True)
        right.bar_chart(counts.set_index("table_name")["row_count"])

        st.subheader("Look inside a table")
        table = st.selectbox("Table", CORE_TABLES)
        cols = run_query("""SELECT column_name, data_type
                            FROM information_schema.columns
                            WHERE table_schema = 'public' AND table_name = %s
                            ORDER BY ordinal_position""", (table,))
        parts = ", ".join(f'COUNT(*) FILTER (WHERE "{c}" IS NULL) AS "n_{i}"'
                          for i, c in enumerate(cols["column_name"]))
        res = run_query(f"SELECT COUNT(*) AS total, {parts} FROM {table}").iloc[0]
        total = int(res["total"])
        cols["null_rows"] = [int(res[f"n_{i}"]) for i in range(len(cols))]
        cols["null_percent"] = [round(100 * n / total, 1) if total else 0.0 for n in cols["null_rows"]]
        st.caption(f"{table}: {total:,} rows. NULL means the value is missing.")
        st.dataframe(cols, hide_index=True)

    with tab2:
        rules = run_query(CONSTRAINTS_SQL, (CORE_TABLES,))
        kinds = rules["kind"].value_counts()
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Primary keys", int(kinds.get("PRIMARY KEY", 0)))
        c2.metric("Foreign keys", int(kinds.get("FOREIGN KEY", 0)))
        c3.metric("CHECK rules", int(kinds.get("CHECK", 0)))
        c4.metric("UNIQUE rules", int(kinds.get("UNIQUE", 0)))
        pick = st.selectbox("Show", ["All"] + sorted(rules["kind"].unique().tolist()))
        shown = rules if pick == "All" else rules[rules["kind"] == pick]
        st.dataframe(shown, hide_index=True)
        st.caption("Primary key = every row is unique. Foreign key = a link must point to a row that exists. "
                   "CHECK = a value must pass a test (for example a rating between 0 and 10).")

    with tab3:
        idx = run_query(INDEXES_SQL, (CORE_TABLES,))
        st.metric("Indexes", len(idx))
        st.dataframe(idx, hide_index=True)
        st.caption("Includes the automatic indexes that PostgreSQL makes for every primary key and UNIQUE rule.")

        st.subheader("Speed test (EXPLAIN ANALYZE)")
        name = st.selectbox("Query to test", list(SPEED_TESTS))
        sql = SPEED_TESTS[name]
        st.code(sql, language="sql")
        if st.button("Run speed test"):
            try:
                explain_plan(sql, False)                     # warm-up run so both tests start fair
                normal = explain_plan(sql, False)
                forced = explain_plan(sql, True)
            except Exception as e:
                st.error(f"Speed test failed: {e}")
                return
            (scan_a, ms_a), (scan_b, ms_b) = plan_summary(normal), plan_summary(forced)
            a, b = st.columns(2)
            a.markdown("**Normal (PostgreSQL chooses)**")
            a.metric(scan_a, f"{ms_a} ms")
            a.code("\n".join(normal))
            b.markdown("**Index scans switched off**")
            b.metric(scan_b, f"{ms_b} ms")
            b.code("\n".join(forced))
            st.caption("Our tables are small, so PostgreSQL may choose a Seq Scan even when an index exists. "
                       "That is normal: for a few thousand rows, reading the whole table can be as fast. "
                       "Indexes matter more as the data grows.")

    with tab4:
        st.write("Decisions taken while cleaning the data (queries C1 to C14 in 2_cleaning.sql):")
        st.markdown(
            "- **No duplicate ids** in the 3,550 dramas.\n"
            "- **37 repeated titles kept**: they are different dramas (different ids, years).\n"
            "- **Synopsis placeholder `\\N` turned into real NULLs** (680 rows).\n"
            "- **45 writer and 21 director names were IMDb codes** (nm...), so they were deleted with their links.\n"
            "- **32 groups of similar spellings NOT merged.** Example: Kim Bora and Kim Bo-ra were checked on IMDb "
            "and are two different people.\n"
            "- **Reality and kids shows kept** in the data and noted as a limitation.\n"
            "- The temporary table `kdramas_raw` is kept as evidence of the original data.")


# ---------------------------------------------------------------------------
# Navigation
# ---------------------------------------------------------------------------
st.title("What should I watch tonight?")
page = st.sidebar.radio("Screens", ["Discover", "Find similar", "Taste Card", "My list", "Trends", "Data stories", "Connections", "Ask the data", "Database overview"])
if page == "Discover":
    discover_page()
elif page == "Find similar":
    find_similar_page()
elif page == "Taste Card":
    taste_card_page()
elif page == "My list":
    my_list_page()
elif page == "Trends":
    trends_page()
elif page == "Data stories":
    stories_page()
elif page == "Connections":
    connections_page()
elif page == "Ask the data":
    ask_page()
else:
    under_hood_page()

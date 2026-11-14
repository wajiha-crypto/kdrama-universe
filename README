# K-Drama Universe

**"What should I watch tonight?"** A Streamlit app on a PostgreSQL database of 3,550 Korean dramas (IMDb data from Kaggle). Databases course project, ITU Lahore.

**Live app:** https://kdrama-universe-fxzknzesb4yucwekqiot2p.streamlit.app
(It may be asleep: open it and wait a few seconds.)

## Screens
- **Discover:** pick a mood, beginner picks, poster wall, "Surprise me"
- **Find similar:** dramas with the same writer, lead actor or genres
- **Taste Card:** pick 3 favourite dramas and get your "K-drama DNA"
- **My list:** username, watchlist, own ratings and recommendations
- **Trends:** average rating per year and a year x genre heatmap
- **Data stories:** fame vs rating, a writer's second drama, hidden gems, guilty pleasures
- **Connections:** Six Degrees between two actors, writer-actor network
- **Ask the data:** ready-made questions with the SQL shown
- **Database overview:** table sizes, missing values, rules, indexes and a speed test

A **Trailer** button under every drama plays the top YouTube trailer inside the app.

## Tech
PostgreSQL, Python, Streamlit, pandas, Altair, psycopg2. Hosted on Streamlit Community Cloud with the database on Neon. Trailers use the YouTube Data API v3.

## SQL files
- `1_schema.sql`: tables, keys, constraints, indexes
- `2_cleaning.sql`: checks and fixes on the raw data
- `3_questions.sql`: the queries behind the screens

## Run it on your laptop
1. Create a PostgreSQL database named `kdrama` and run the SQL files.
2. Create `.streamlit/secrets.toml` next to `app.py` with `DB_PASSWORD = "..."` (and `YOUTUBE_API_KEY = "..."` for trailers).
3. `pip install -r requirements.txt`
4. `python -m streamlit run app.py`

Passwords and API keys are never stored in this repository.

## Data
"The Ultimate Korean Drama Dataset 1969-2025" from Kaggle (built from IMDb). The data file is not included here; download it from Kaggle. It includes a few reality and kids shows.

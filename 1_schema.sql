-- PART B: SCHEMA (Korean Drama Universe, database: kdrama)


-- main table; drama_id is the IMDb id from the dataset (e.g. tt10919420)
CREATE TABLE drama (
    drama_id        TEXT PRIMARY KEY,
    title           TEXT NOT NULL,
    start_year      INT,
    end_year        INT,
    rating          NUMERIC(3,1),
    votes           INT,
    synopsis        TEXT,
    age_rating      TEXT,
    runtime_minutes INT,
    CONSTRAINT chk_rating  CHECK (rating BETWEEN 0 AND 10),      -- IMDb scale is 0 to 10
    CONSTRAINT chk_votes   CHECK (votes >= 0),                   -- votes cannot be negative
    CONSTRAINT chk_years   CHECK (end_year >= start_year),       -- a drama cannot end before it starts
    CONSTRAINT chk_runtime CHECK (runtime_minutes > 0)           -- runtime must be positive
);

-- entity tables: ids auto-numbered by PostgreSQL, names must be unique
CREATE TABLE writer   (writer_id   INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY, name TEXT NOT NULL UNIQUE);
CREATE TABLE director (director_id INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY, name TEXT NOT NULL UNIQUE);
CREATE TABLE actor    (actor_id    INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY, name TEXT NOT NULL UNIQUE);
CREATE TABLE genre    (genre_id    INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY, name TEXT NOT NULL UNIQUE);

-- bridge tables: composite primary key + foreign keys to both sides
CREATE TABLE drama_writer (
    drama_id  TEXT REFERENCES drama(drama_id),
    writer_id INT  REFERENCES writer(writer_id),
    PRIMARY KEY (drama_id, writer_id)
);
CREATE TABLE drama_director (
    drama_id    TEXT REFERENCES drama(drama_id),
    director_id INT  REFERENCES director(director_id),
    PRIMARY KEY (drama_id, director_id)
);
CREATE TABLE drama_lead (
    drama_id   TEXT REFERENCES drama(drama_id),
    actor_id   INT  REFERENCES actor(actor_id),
    lead_order INT,  -- 1 = mainLead1, 2 = mainLead2
    PRIMARY KEY (drama_id, actor_id),
    CONSTRAINT chk_lead_order CHECK (lead_order IN (1, 2))       -- only lead 1 or lead 2
);
CREATE TABLE drama_genre (
    drama_id TEXT REFERENCES drama(drama_id),
    genre_id INT  REFERENCES genre(genre_id),
    PRIMARY KEY (drama_id, genre_id)
);
-- app users: only a username, no personal data
CREATE TABLE app_user (
    user_id  INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    username TEXT NOT NULL UNIQUE
);
-- dramas a user wants to watch later (M:N between user and drama)
CREATE TABLE watchlist (
    user_id  INT  REFERENCES app_user(user_id),
    drama_id TEXT REFERENCES drama(drama_id),
    added_on DATE DEFAULT CURRENT_DATE,
    PRIMARY KEY (user_id, drama_id)
);
-- dramas a user has watched, with the user's own rating
CREATE TABLE user_rating (
    user_id   INT  REFERENCES app_user(user_id),
    drama_id  TEXT REFERENCES drama(drama_id),
    my_rating NUMERIC(3,1) CHECK (my_rating BETWEEN 0 AND 10),
    PRIMARY KEY (user_id, drama_id)
);

-- indexes on the columns used for searching and joining
CREATE INDEX idx_drama_title      ON drama (title);              -- search a drama by title
CREATE INDEX idx_drama_rating     ON drama (rating);             -- rating filters and sorting
CREATE INDEX idx_drama_writer_w   ON drama_writer (writer_id);   -- find dramas of a writer
CREATE INDEX idx_drama_director_d ON drama_director (director_id);
CREATE INDEX idx_drama_lead_a     ON drama_lead (actor_id);
CREATE INDEX idx_drama_genre_g    ON drama_genre (genre_id);

-- B-COUNT: number of rows in each table (run this one, it is safe)
SELECT 'drama' AS tbl, COUNT(*) AS total_rows FROM drama
UNION ALL SELECT 'writer',         COUNT(*) FROM writer
UNION ALL SELECT 'director',       COUNT(*) FROM director
UNION ALL SELECT 'actor',          COUNT(*) FROM actor
UNION ALL SELECT 'genre',          COUNT(*) FROM genre
UNION ALL SELECT 'drama_writer',   COUNT(*) FROM drama_writer
UNION ALL SELECT 'drama_director', COUNT(*) FROM drama_director
UNION ALL SELECT 'drama_lead',     COUNT(*) FROM drama_lead
UNION ALL SELECT 'drama_genre',    COUNT(*) FROM drama_genre;

SELECT table_name FROM information_schema.tables
WHERE table_name IN ('app_user', 'watchlist', 'user_rating');

-- rows in each table plus the grand total (kdramas_raw and the app tables are left out on purpose)
SELECT tbl, total_rows FROM (
    SELECT 1 AS ord, 'drama'          AS tbl, COUNT(*) AS total_rows FROM drama
    UNION ALL SELECT 2,  'writer',         COUNT(*) FROM writer
    UNION ALL SELECT 3,  'director',       COUNT(*) FROM director
    UNION ALL SELECT 4,  'actor',          COUNT(*) FROM actor
    UNION ALL SELECT 5,  'genre',          COUNT(*) FROM genre
    UNION ALL SELECT 6,  'drama_writer',   COUNT(*) FROM drama_writer
    UNION ALL SELECT 7,  'drama_director', COUNT(*) FROM drama_director
    UNION ALL SELECT 8,  'drama_lead',     COUNT(*) FROM drama_lead
    UNION ALL SELECT 9,  'drama_genre',    COUNT(*) FROM drama_genre
    UNION ALL SELECT 10, 'TOTAL', (SELECT COUNT(*) FROM drama) + (SELECT COUNT(*) FROM writer)
                                + (SELECT COUNT(*) FROM director) + (SELECT COUNT(*) FROM actor)
                                + (SELECT COUNT(*) FROM genre) + (SELECT COUNT(*) FROM drama_writer)
                                + (SELECT COUNT(*) FROM drama_director) + (SELECT COUNT(*) FROM drama_lead)
                                + (SELECT COUNT(*) FROM drama_genre)
) t
ORDER BY ord;
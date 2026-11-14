-- PART C: ENGAGING WITH THE DATA (checks and cleaning)
-- The raw CSV was imported as-is into kdramas_raw (all columns TEXT).

CREATE TABLE kdramas_raw (
    title TEXT, rating TEXT, genres TEXT, votes TEXT, synopsis TEXT, age_rating TEXT,
    mainlead1 TEXT, mainlead2 TEXT, startyear TEXT, endyear TEXT, writer TEXT,
    director TEXT, id TEXT, runtimeminutes TEXT, image_url TEXT
);

-- C1: are there duplicate dramas in the raw data?
SELECT id, COUNT(*) AS copies          -- same IMDb id appearing more than once
FROM kdramas_raw
GROUP BY id
HAVING COUNT(*) > 1;

-- C2: do any titles appear more than once (possible duplicates with different ids)?
SELECT title,
       COUNT(*)                          AS copies,       -- how many rows share this title
       STRING_AGG(id, ', ')              AS imdb_ids,     -- their ids
       STRING_AGG(startyear, ', ')       AS start_years   -- their start years
FROM kdramas_raw
GROUP BY title
HAVING COUNT(*) > 1
ORDER BY copies DESC, title;

-- C3: same title AND same start year but different ids: real duplicates or different works?
SELECT a.title, a.startyear,
       a.id AS id_1, a.rating AS rating_1, a.votes AS votes_1, a.genres AS genres_1,
       b.id AS id_2, b.rating AS rating_2, b.votes AS votes_2, b.genres AS genres_2
FROM kdramas_raw a
JOIN kdramas_raw b ON a.title = b.title            -- same title...
                  AND a.startyear = b.startyear    -- ...same start year...
                  AND a.id < b.id                  -- ...different row (and each pair only once)
ORDER BY a.title;

-- C4: how many values are missing in each column of the raw data? (NULL, empty text or the \N placeholder)
SELECT COUNT(*)                                                                   AS total_rows,
       COUNT(*) FILTER (WHERE rating         IS NULL OR rating         IN ('', '\N')) AS missing_rating,
       COUNT(*) FILTER (WHERE votes          IS NULL OR votes          IN ('', '\N')) AS missing_votes,
       COUNT(*) FILTER (WHERE startyear      IS NULL OR startyear      IN ('', '\N')) AS missing_start_year,
       COUNT(*) FILTER (WHERE endyear        IS NULL OR endyear        IN ('', '\N')) AS missing_end_year,
       COUNT(*) FILTER (WHERE synopsis       IS NULL OR synopsis       IN ('', '\N')) AS missing_synopsis,
       COUNT(*) FILTER (WHERE age_rating     IS NULL OR age_rating     IN ('', '\N')) AS missing_age_rating,
       COUNT(*) FILTER (WHERE runtimeminutes IS NULL OR runtimeminutes IN ('', '\N')) AS missing_runtime,
       COUNT(*) FILTER (WHERE mainlead1      IS NULL OR mainlead1      IN ('', '\N')) AS missing_lead1,
       COUNT(*) FILTER (WHERE mainlead2      IS NULL OR mainlead2      IN ('', '\N')) AS missing_lead2,
       COUNT(*) FILTER (WHERE genres         IS NULL OR genres         IN ('', '\N')) AS missing_genres
FROM kdramas_raw;

-- C5: names that are really IMDb person ids (like nm1234567) instead of real names
SELECT 'writer' AS tbl, COUNT(*) AS id_instead_of_name FROM writer   WHERE name ~ '^nm[0-9]+$'
UNION ALL
SELECT 'director',      COUNT(*)                        FROM director WHERE name ~ '^nm[0-9]+$'
UNION ALL
SELECT 'actor',         COUNT(*)                        FROM actor    WHERE name ~ '^nm[0-9]+$';

-- C6: same person stored under slightly different spellings (case, hyphen or spaces)
SELECT tbl, norm_name, COUNT(*) AS spellings, STRING_AGG(name, ' | ') AS names
FROM (
    SELECT 'writer'   AS tbl, name, regexp_replace(lower(name), '[^a-z]', '', 'g') AS norm_name FROM writer   WHERE name !~ '^nm[0-9]+$'
    UNION ALL
    SELECT 'director' AS tbl, name, regexp_replace(lower(name), '[^a-z]', '', 'g') AS norm_name FROM director WHERE name !~ '^nm[0-9]+$'
    UNION ALL
    SELECT 'actor'    AS tbl, name, regexp_replace(lower(name), '[^a-z]', '', 'g') AS norm_name FROM actor    WHERE name !~ '^nm[0-9]+$'
) t
GROUP BY tbl, norm_name
HAVING COUNT(*) > 1          -- more than one spelling maps to the same normalized name
ORDER BY tbl, norm_name;

-- C7: synopsis stored the missing values as the text '\N'; check what is stored in the raw data
SELECT synopsis, COUNT(*) AS n FROM kdramas_raw GROUP BY synopsis ORDER BY n DESC LIMIT 5;

-- C7 fix: turn '\N' and empty strings into real NULLs in the drama table (already done, 680 rows)
UPDATE drama SET synopsis = NULL WHERE synopsis IN ('\N', '') OR synopsis IS NULL;

-- C7 check after the fix
SELECT COUNT(*) FROM drama WHERE synopsis IS NULL;  -- expected 680

-- C8: any '\N' placeholders left in text columns? (expected: 0 everywhere)
SELECT 'writer' AS tbl, COUNT(*) AS bad FROM writer   WHERE position(E'\\N' in name) > 0
UNION ALL SELECT 'director', COUNT(*) FROM director   WHERE position(E'\\N' in name) > 0
UNION ALL SELECT 'actor',    COUNT(*) FROM actor      WHERE position(E'\\N' in name) > 0
UNION ALL SELECT 'genre',    COUNT(*) FROM genre      WHERE position(E'\\N' in name) > 0
UNION ALL SELECT 'drama.age_rating', COUNT(*) FROM drama WHERE age_rating IN ('\N', '');

-- C9: how many NULLs are in the cleaned drama table? (expected 1412 / 1412 / 164 / 970 / 680 / 3117 / 2050)
SELECT COUNT(*) FILTER (WHERE rating          IS NULL) AS null_rating,
       COUNT(*) FILTER (WHERE votes           IS NULL) AS null_votes,
       COUNT(*) FILTER (WHERE start_year      IS NULL) AS null_start_year,
       COUNT(*) FILTER (WHERE end_year        IS NULL) AS null_end_year,
       COUNT(*) FILTER (WHERE synopsis        IS NULL) AS null_synopsis,
       COUNT(*) FILTER (WHERE age_rating      IS NULL) AS null_age_rating,
       COUNT(*) FILTER (WHERE runtime_minutes IS NULL) AS null_runtime
FROM drama;

-- C10: do any existing rows break the rules we want to add? (expected: 0 everywhere)
SELECT COUNT(*) FILTER (WHERE rating NOT BETWEEN 0 AND 10)            AS bad_rating,
       COUNT(*) FILTER (WHERE votes < 0)                              AS bad_votes,
       COUNT(*) FILTER (WHERE end_year < start_year)                  AS end_before_start,
       COUNT(*) FILTER (WHERE runtime_minutes <= 0)                   AS bad_runtime
FROM drama;

SELECT COUNT(*) AS bad_lead_order FROM drama_lead WHERE lead_order NOT IN (1, 2);   -- expected 0

-- C11: do two spellings of "the same" actor ever appear in the same drama? (if yes, they are different people)
SELECT a1.name AS spelling_1, a2.name AS spelling_2, COUNT(*) AS shared_dramas
FROM drama_lead l1
JOIN drama_lead l2 ON l2.drama_id = l1.drama_id AND l2.actor_id > l1.actor_id   -- two leads of the same drama
JOIN actor a1 ON a1.actor_id = l1.actor_id
JOIN actor a2 ON a2.actor_id = l2.actor_id
WHERE regexp_replace(lower(a1.name), '[^a-z]', '', 'g') = regexp_replace(lower(a2.name), '[^a-z]', '', 'g')   -- same normalized name
GROUP BY a1.name, a2.name;

-- compare the two spellings: their dramas, years, co-lead and writer
SELECT a.name AS spelling, d.title, d.start_year,
       (SELECT STRING_AGG(a2.name, ', ') FROM drama_lead l2                 -- the other lead(s) in the same drama
        JOIN actor a2 ON a2.actor_id = l2.actor_id
        WHERE l2.drama_id = d.drama_id AND l2.actor_id <> a.actor_id) AS co_lead,
       (SELECT STRING_AGG(w.name, ', ') FROM drama_writer dw                -- the writer(s) of the drama
        JOIN writer w ON w.writer_id = dw.writer_id
        WHERE dw.drama_id = d.drama_id) AS writers
FROM actor a
JOIN drama_lead dl ON dl.actor_id = a.actor_id
JOIN drama d ON d.drama_id = dl.drama_id
WHERE a.name IN ('Kim Bora', 'Kim Bo-ra')       -- change to any other pair from C6
ORDER BY a.name, d.start_year;

-- C12: remove writers whose "name" is an IMDb code: first their links, then the rows themselves
DELETE FROM drama_writer WHERE writer_id IN (SELECT writer_id FROM writer WHERE name ~ '^nm[0-9]+$');   -- expected 47 rows
DELETE FROM writer WHERE name ~ '^nm[0-9]+$';                                                           -- expected 45 rows

-- C13: same for directors
DELETE FROM drama_director WHERE director_id IN (SELECT director_id FROM director WHERE name ~ '^nm[0-9]+$');   -- expected 22 rows
DELETE FROM director WHERE name ~ '^nm[0-9]+$';                                                         -- expected 21 rows

-- rows in each table plus the grand total (kdramas_raw is left out on purpose)
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

-- C14: add a poster link column to drama (it is also in the CREATE TABLE above, so IF NOT EXISTS keeps this safe)
ALTER TABLE drama ADD COLUMN IF NOT EXISTS poster_url TEXT;
-- fill it from the raw table; '\N' and empty text become NULL
UPDATE drama d
SET poster_url = NULLIF(NULLIF(r.image_url, ''), '\N')
FROM kdramas_raw r
WHERE r.id = d.drama_id;                               -- expected: 3550 rows updated
-- check: how many dramas have a poster link
SELECT COUNT(poster_url) AS with_poster,               -- expected 3281
       COUNT(*)          AS total
FROM drama;



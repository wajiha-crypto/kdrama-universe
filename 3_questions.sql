-- PART D: ANSWERING OUR QUESTIONS (Korean Drama Universe, database: kdrama)
-- Run each query on its own: click inside it and press Ctrl + Enter.

-- Q1: Which lead actor has the most hit dramas with the same writer?
SELECT a.name AS actor,                       -- lead actor
       w.name AS writer,                      -- writer of the same drama
       COUNT(*) AS hit_dramas                 -- number of hit dramas they share
FROM drama d
JOIN drama_lead   dl ON dl.drama_id  = d.drama_id     -- drama -> its lead actors
JOIN actor        a  ON a.actor_id   = dl.actor_id
JOIN drama_writer dw ON dw.drama_id  = d.drama_id     -- drama -> its writers
JOIN writer       w  ON w.writer_id  = dw.writer_id
WHERE d.rating >= 8.0                         -- "hit" = high rating...
  AND d.votes  >= 1000                        -- ...with enough votes to trust it
GROUP BY a.name, w.name                       -- one row per actor-writer pair
ORDER BY hit_dramas DESC, a.name              -- biggest pairs first
LIMIT 10;                                     -- top 10 only

-- Q2: Which writers have the highest average rating across their dramas?
SELECT w.name AS writer,                           -- writer name
       COUNT(d.drama_id)       AS dramas,          -- how many rated dramas they wrote
       ROUND(AVG(d.rating), 2) AS avg_rating       -- average IMDb rating, 2 decimals
FROM writer w
JOIN drama_writer dw ON dw.writer_id = w.writer_id -- writer -> their dramas
JOIN drama d         ON d.drama_id   = dw.drama_id
WHERE d.rating IS NOT NULL                         -- ignore dramas with no rating
GROUP BY w.name                                    -- one row per writer
HAVING COUNT(d.drama_id) >= 3                      -- only writers with 3+ rated dramas
ORDER BY avg_rating DESC, dramas DESC              -- best average first
LIMIT 10;                                          -- top 10 only

-- Q3: What is the average rating of each genre?
SELECT g.name AS genre,                            -- genre name
       COUNT(d.drama_id)       AS dramas,          -- how many rated dramas have this genre
       ROUND(AVG(d.rating), 2) AS avg_rating       -- average IMDb rating, 2 decimals
FROM genre g
JOIN drama_genre dg ON dg.genre_id = g.genre_id    -- genre -> its dramas
JOIN drama d        ON d.drama_id  = dg.drama_id
WHERE d.rating IS NOT NULL                         -- ignore dramas with no rating
GROUP BY g.name                                    -- one row per genre
ORDER BY avg_rating DESC;                          -- best genre first

-- Q4: Which dramas share the same writer or lead actor as a given drama, ranked by rating?
SELECT title, start_year, rating, votes,
       CASE WHEN same_writer THEN 'yes' ELSE 'no' END AS same_writer,   -- show words instead of ticks
       CASE WHEN same_lead   THEN 'yes' ELSE 'no' END AS same_lead
FROM (
    SELECT d.title, d.start_year, d.rating, d.votes,
           EXISTS (SELECT 1                                   -- same writer as the given drama?
                   FROM drama_writer x
                   JOIN drama_writer y ON y.writer_id = x.writer_id
                   WHERE x.drama_id = d.drama_id AND y.drama_id = g.drama_id) AS same_writer,
           EXISTS (SELECT 1                                   -- same lead actor as the given drama?
                   FROM drama_lead x
                   JOIN drama_lead y ON y.actor_id = x.actor_id
                   WHERE x.drama_id = d.drama_id AND y.drama_id = g.drama_id) AS same_lead
    FROM drama d,
         (SELECT drama_id FROM drama WHERE title = 'Crash Landing on You') g   -- the given drama: change this title
    WHERE d.drama_id <> g.drama_id                            -- do not suggest the drama itself
      AND d.rating IS NOT NULL                                -- only rated dramas
) t
WHERE same_writer OR same_lead                                -- keep dramas sharing a writer or a lead
ORDER BY rating DESC, votes DESC                              -- best rated first
LIMIT 10;

-- Q5: Which directors have made the most dramas?
SELECT dr.name AS director,                       -- director name
       COUNT(dd.drama_id)       AS dramas,        -- how many dramas they directed
       ROUND(AVG(d.rating), 2)  AS avg_rating     -- bonus: their average rating (ignores unrated dramas)
FROM director dr
JOIN drama_director dd ON dd.director_id = dr.director_id   -- director -> their dramas
JOIN drama d           ON d.drama_id     = dd.drama_id
GROUP BY dr.name                                  -- one row per director
ORDER BY dramas DESC, dr.name                     -- most dramas first
LIMIT 10;                                         -- top 10 only

-- Q6 (extra): How has the average drama rating changed year over year?
SELECT start_year,                                 -- year the drama started
       COUNT(*)                AS dramas,          -- rated dramas that started that year
       ROUND(AVG(rating), 2)   AS avg_rating       -- average IMDb rating, 2 decimals
FROM drama
WHERE rating IS NOT NULL                           -- ignore dramas with no rating
  AND start_year IS NOT NULL                       -- ignore dramas with no year
  AND start_year >= 2000                           -- recent years only (older years have few dramas)
GROUP BY start_year                                -- one row per year
ORDER BY start_year;                               -- oldest to newest

-- Q7: Beginner picks: popular, well-rated dramas in a chosen genre, with their lead actors
SELECT d.title, d.start_year, d.rating, d.votes,
       STRING_AGG(a.name, ', ' ORDER BY dl.lead_order) AS lead_actors      -- the main leads in one cell
FROM drama d
JOIN drama_lead dl ON dl.drama_id = d.drama_id                             -- join 1: drama -> its leads
JOIN actor a       ON a.actor_id  = dl.actor_id                            -- join 2: lead -> actor name
WHERE d.rating >= 8.0                                                      -- well rated...
  AND d.votes  >= 20000                                                    -- ...and popular, so it is safe for a first-timer
  AND EXISTS (SELECT 1                                                     -- only the chosen genre
              FROM drama_genre dg
              JOIN genre g ON g.genre_id = dg.genre_id
              WHERE dg.drama_id = d.drama_id AND g.name = 'Romance')       -- change 'Romance' to any genre
GROUP BY d.drama_id, d.title, d.start_year, d.rating, d.votes
ORDER BY d.rating DESC, d.votes DESC
LIMIT 10;

-- Q8: Rating heatmap data: average rating for every year and genre
SELECT d.start_year,                                      -- row of the heatmap
       g.name                  AS genre,                  -- column of the heatmap
       COUNT(*)                AS dramas,                 -- how many dramas are behind the average
       ROUND(AVG(d.rating), 2) AS avg_rating              -- the colour of the cell
FROM drama d
JOIN drama_genre dg ON dg.drama_id = d.drama_id           -- join 1: drama -> its genres
JOIN genre g        ON g.genre_id  = dg.genre_id          -- join 2: genre id -> genre name
WHERE d.rating IS NOT NULL                                -- only rated dramas
  AND d.start_year BETWEEN 2010 AND 2025                  -- recent years
GROUP BY d.start_year, g.name                             -- one row per year and genre
HAVING COUNT(*) >= 3                                      -- skip cells with too few dramas to trust
ORDER BY d.start_year, g.name;

-- Q9: Six Degrees of K-Drama: shortest chain of co-stars between two actors
WITH RECURSIVE edges AS (                                  -- two actors are linked if they are leads of the same drama
    SELECT l1.actor_id AS a, l2.actor_id AS b
    FROM drama_lead l1
    JOIN drama_lead l2 ON l2.drama_id = l1.drama_id AND l2.actor_id <> l1.actor_id
),
paths AS (
    SELECT e.b AS actor_id, ARRAY[s.actor_id, e.b] AS path, 1 AS degrees   -- degree 1: co-stars of the start actor
    FROM actor s
    JOIN edges e ON e.a = s.actor_id
    WHERE s.name = 'Hyun Bin'                               -- the start actor: change this name
    UNION ALL
    SELECT e.b, p.path || e.b, p.degrees + 1                -- extend every path by one more co-star
    FROM paths p
    JOIN edges e ON e.a = p.actor_id
    WHERE e.b <> ALL (p.path)                               -- never visit the same actor twice
      AND p.degrees < 6                                     -- stop after 6 steps
)
SELECT p.degrees,
       (SELECT STRING_AGG(a.name, ' -> ' ORDER BY u.ord)    -- turn the id path into names
        FROM unnest(p.path) WITH ORDINALITY AS u(id, ord)
        JOIN actor a ON a.actor_id = u.id) AS chain
FROM paths p
JOIN actor t ON t.actor_id = p.actor_id
WHERE t.name = 'Lee Jong-suk'                               -- the target actor: change this name
ORDER BY p.degrees
LIMIT 1;

-- Q10: Writer-actor network: which lead actors worked most with one writer?
SELECT a.name AS actor,                                     -- lead actor
       COUNT(DISTINCT d.drama_id)  AS dramas,               -- dramas with this writer
       ROUND(AVG(d.rating), 2)     AS avg_rating            -- average rating of those dramas
FROM writer w
JOIN drama_writer dw ON dw.writer_id = w.writer_id          -- writer -> dramas
JOIN drama d         ON d.drama_id   = dw.drama_id
JOIN drama_lead dl   ON dl.drama_id  = d.drama_id           -- drama -> leads
JOIN actor a         ON a.actor_id   = dl.actor_id
WHERE w.name = 'Kim Eun-sook'                               -- change the writer
GROUP BY a.name
ORDER BY dramas DESC, avg_rating DESC NULLS LAST, a.name
LIMIT 15;

-- Q11: Taste Card: genre mix of three favourite dramas
SELECT g.name AS genre, COUNT(*) AS how_many              -- how many of the 3 picks have this genre
FROM drama d
JOIN drama_genre dg ON dg.drama_id = d.drama_id           -- join 1: drama -> its genres
JOIN genre g        ON g.genre_id  = dg.genre_id          -- join 2: genre id -> genre name
WHERE d.title IN ('Crash Landing on You', 'Squid Game', 'Kingdom')   -- the 3 picks (change these)
GROUP BY g.name
ORDER BY how_many DESC, g.name;

-- Q12: Does fame change the rating? average rating by number of votes
SELECT CASE WHEN votes < 1000  THEN '1) under 1K votes'
            WHEN votes < 10000 THEN '2) 1K to 10K'
            WHEN votes < 50000 THEN '3) 10K to 50K'
            ELSE '4) 50K or more' END AS fame,
       COUNT(*)              AS dramas,
       ROUND(AVG(rating), 2) AS avg_rating
FROM drama
WHERE rating IS NOT NULL AND votes IS NOT NULL
GROUP BY 1
ORDER BY 1;

-- Q12 (correlation): rating against log(votes)
SELECT ROUND(CORR(rating, LN(votes))::numeric, 3) AS correlation
FROM drama WHERE rating IS NOT NULL AND votes > 0;

-- Q13: Does a writer's second drama do worse than the first? (window function)
WITH ordered AS (                                         -- number each writer's dramas by year
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
JOIN ordered s ON s.writer_id = f.writer_id AND f.rn = 1 AND s.rn = 2
JOIN writer w  ON w.writer_id = f.writer_id
ORDER BY change
LIMIT 10;

-- Q14: Hidden gems: rated 8.5+, but few votes (at least 100 so the rating is not a fluke)
SELECT title, start_year, rating, votes FROM drama
WHERE rating >= 8.5 AND votes BETWEEN 100 AND 1999
ORDER BY rating DESC, votes DESC
LIMIT 10;

-- Q15: Guilty pleasures: watched by many, rated low
SELECT title, start_year, rating, votes FROM drama
WHERE votes >= 50000 AND rating < 7.0
ORDER BY votes DESC
LIMIT 10;
-- SQL practice on the Macro Quant Lab store.
-- Build the database first:  python -m mql.store --duckdb
-- Tables: obs(date, series_id, value), series(series_id, name, source, code, unit, grp); table: wide (one column per series)
-- Run all:  python scripts/sql.py notebooks/sql_practice.sql
-- Then write five questions of your own below the examples.

-- 1. What is in the store?
SELECT grp, count(*) AS series FROM series GROUP BY grp ORDER BY series DESC;

-- 2. Latest value of each US rates series
SELECT o.series_id, s.name, max(o.date) AS last_date, arg_max(o.value, o.date) AS last_value
FROM obs o JOIN series s USING (series_id)
WHERE s.grp = 'rates_us'
GROUP BY o.series_id, s.name
ORDER BY o.series_id;

-- 3. How often has the US 2s10s curve been inverted, by year?
SELECT year(date) AS yr,
       round(100 * avg(CASE WHEN UST_10Y - UST_2Y < 0 THEN 1 ELSE 0 END), 1) AS pct_days_inverted
FROM wide
WHERE UST_10Y IS NOT NULL AND UST_2Y IS NOT NULL
GROUP BY yr ORDER BY yr;

-- 4. Biggest one-day moves in the US 10-year yield (bp), with a window function
SELECT date, round(100 * (value - lag(value) OVER (ORDER BY date)), 1) AS move_bp
FROM obs WHERE series_id = 'UST_10Y'
QUALIFY move_bp IS NOT NULL
ORDER BY abs(move_bp) DESC
LIMIT 10;

-- 5. Monthly average of US 10y breakeven versus Brent
SELECT date_trunc('month', date) AS month,
       round(avg(US_10Y_BE), 2) AS breakeven_10y,
       round(avg(BRENT), 1) AS brent
FROM wide
GROUP BY month ORDER BY month DESC LIMIT 24;

-- Your questions:
-- 6.
-- 7.
-- 8.
-- 9.
-- 10.

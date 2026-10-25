-- SQL practice on the Macro Quant Lab store.
-- Build the database first:  python -m mql.store --duckdb
-- Tables: obs(date, series_id, value) and series(series_id, name, source, code, unit, grp)
-- Table wide: one row per date, one column per series
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

-- ---------------------------------------------------------------------------------------------
-- My questions (6-10). Each one practises one SQL idea; the takeaway under each is my read.
-- ---------------------------------------------------------------------------------------------

-- SQL idea: CTEs, a named window, CASE, and count(*) FILTER to pivot counts into columns.
-- Weekly close = last value in each Monday-to-Sunday week. Level = average change of 2y and 10y;
-- slope = change in 10y minus change in 2y (both in bp). Unchanged weeks are left out.
-- 6. US curve regimes by year: how many weeks were bear or bull steepeners and flatteners?
WITH weekly AS (
    SELECT date_trunc('week', date) AS week,
           arg_max(UST_2Y, date)  AS y2,
           arg_max(UST_10Y, date) AS y10
    FROM wide
    WHERE UST_2Y IS NOT NULL AND UST_10Y IS NOT NULL
    GROUP BY week
),
moves AS (
    SELECT week,
           100 * ((y2 - lag(y2) OVER w) + (y10 - lag(y10) OVER w)) / 2 AS level_bp,
           100 * ((y10 - lag(y10) OVER w) - (y2 - lag(y2) OVER w))     AS slope_bp
    FROM weekly
    WINDOW w AS (ORDER BY week)
),
regimes AS (
    SELECT week,
           CASE WHEN level_bp > 0 AND slope_bp > 0 THEN 'bear steepener'
                WHEN level_bp < 0 AND slope_bp > 0 THEN 'bull steepener'
                WHEN level_bp > 0 AND slope_bp < 0 THEN 'bear flattener'
                WHEN level_bp < 0 AND slope_bp < 0 THEN 'bull flattener'
           END AS regime
    FROM moves
)
SELECT year(week) AS yr,
       count(*) FILTER (WHERE regime = 'bear steepener') AS bear_steep,
       count(*) FILTER (WHERE regime = 'bull steepener') AS bull_steep,
       count(*) FILTER (WHERE regime = 'bear flattener') AS bear_flat,
       count(*) FILTER (WHERE regime = 'bull flattener') AS bull_flat
FROM regimes
WHERE regime IS NOT NULL
GROUP BY yr
ORDER BY yr;
-- Takeaway:

-- SQL idea: lag() for daily changes, a rolling window frame, and row_number() to keep one row per quarter.
-- Days where both series have a value; breakeven move in bp, Brent move in %. A full window is 60 days.
-- 7. Do US 10y breakevens trade with oil? Rolling 60-day correlation of daily moves, at each quarter end
WITH both_days AS (
    SELECT date, US_10Y_BE AS be, BRENT AS brent
    FROM wide
    WHERE US_10Y_BE IS NOT NULL AND BRENT IS NOT NULL
),
moves AS (
    SELECT date,
           100 * (be - lag(be) OVER (ORDER BY date))            AS be_bp,
           100 * (brent / lag(brent) OVER (ORDER BY date) - 1) AS brent_pct
    FROM both_days
),
rolling AS (
    SELECT date,
           corr(be_bp, brent_pct) OVER last60 AS corr_60d,
           count(be_bp)           OVER last60 AS n_days
    FROM moves
    WINDOW last60 AS (ORDER BY date ROWS BETWEEN 59 PRECEDING AND CURRENT ROW)
),
quarter_end AS (
    SELECT date_trunc('quarter', date) AS quarter, date, corr_60d,
           row_number() OVER (PARTITION BY date_trunc('quarter', date) ORDER BY date DESC) AS rn
    FROM rolling
    WHERE n_days = 60
)
SELECT quarter::DATE AS quarter, date::DATE AS as_of, round(corr_60d, 2) AS corr_60d
FROM quarter_end
WHERE rn = 1
ORDER BY quarter DESC
LIMIT 12;
-- Takeaway:

-- SQL idea: aggregate daily data to months, join two series, and percent_rank() over the whole history.
-- The India 10y here is a monthly average (OECD via FRED, about three months late),
-- so it is compared with the US 10y's monthly average. pct_rank 0 = narrowest month since 2018, 1 = widest.
-- 8. Is the India-US 10y spread historically narrow? Last 12 months, in bp, with its rank since 2018
WITH us AS (
    SELECT date_trunc('month', date) AS month, avg(value) AS us_10y
    FROM obs
    WHERE series_id = 'UST_10Y'
    GROUP BY month
),
india AS (
    SELECT date_trunc('month', date) AS month, value AS in_10y
    FROM obs
    WHERE series_id = 'IN_10Y_M'
),
spread AS (
    SELECT month, in_10y, us_10y,
           100 * (in_10y - us_10y) AS spread_bp,
           percent_rank() OVER (ORDER BY in_10y - us_10y) AS pct_rank
    FROM india JOIN us USING (month)
)
SELECT month::DATE AS month,
       round(in_10y, 2)    AS india_10y,
       round(us_10y, 2)    AS us_10y,
       round(spread_bp)    AS spread_bp,
       round(pct_rank, 2)  AS pct_rank
FROM spread
ORDER BY month DESC
LIMIT 12;
-- Takeaway:

-- SQL idea: a running maximum (window frame from the first row) and arg_max / arg_min.
-- Nifty in dollars = Nifty / USDINR: the drawdown a dollar-based foreign investor sees.
-- 9. How far is the Nifty below its peak in rupees and in dollars, and how bad was the worst drawdown?
WITH px AS (
    SELECT date, NIFTY AS nifty_inr, NIFTY / USDINR AS nifty_usd
    FROM wide
    WHERE NIFTY IS NOT NULL AND USDINR IS NOT NULL
),
drawdowns AS (
    SELECT date,
           nifty_inr / max(nifty_inr) OVER since_start - 1 AS dd_inr,
           nifty_usd / max(nifty_usd) OVER since_start - 1 AS dd_usd
    FROM px
    WINDOW since_start AS (ORDER BY date ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
)
SELECT round(100 * arg_max(dd_inr, date), 1) AS now_inr_pct,
       round(100 * arg_max(dd_usd, date), 1) AS now_usd_pct,
       round(100 * min(dd_inr), 1)           AS worst_inr_pct,
       arg_min(date, dd_inr)::DATE           AS worst_inr_date,
       round(100 * min(dd_usd), 1)           AS worst_usd_pct,
       arg_min(date, dd_usd)::DATE           AS worst_usd_date
FROM drawdowns;
-- Takeaway:

-- SQL idea: month-end values with arg_max, month-on-month changes with lag(), and a CASE label.
-- Bank of England zero-coupon curves: nominal = real yield + implied inflation, so the two parts
-- add up to the nominal move. The latest month is month-to-date.
-- 10. UK 10y gilt: did real yields or inflation compensation drive each month's move?
WITH month_end AS (
    SELECT date_trunc('month', date) AS month,
           arg_max(UK_10Y, date)      AS nominal,
           arg_max(UK_10Y_REAL, date) AS real_yield,
           arg_max(UK_10Y_BE, date)   AS inflation
    FROM wide
    WHERE UK_10Y IS NOT NULL AND UK_10Y_REAL IS NOT NULL AND UK_10Y_BE IS NOT NULL
    GROUP BY month
),
changes AS (
    SELECT month,
           100 * (nominal    - lag(nominal)    OVER (ORDER BY month)) AS nominal_bp,
           100 * (real_yield - lag(real_yield) OVER (ORDER BY month)) AS real_bp,
           100 * (inflation  - lag(inflation)  OVER (ORDER BY month)) AS inflation_bp
    FROM month_end
)
SELECT month::DATE AS month,
       round(nominal_bp)   AS nominal_bp,
       round(real_bp)      AS real_bp,
       round(inflation_bp) AS inflation_bp,
       CASE WHEN abs(real_bp) >= abs(inflation_bp) THEN 'real yields' ELSE 'inflation' END AS main_driver
FROM changes
WHERE nominal_bp IS NOT NULL
ORDER BY month DESC
LIMIT 13;
-- Takeaway:

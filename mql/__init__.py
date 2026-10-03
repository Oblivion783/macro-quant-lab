"""Macro Quant Lab: a personal, public-data research toolkit for multi-asset and rates markets.

Modules
-------
config      paths and YAML config loading
sources     downloaders for FRED, Bank of England, ECB and Yahoo Finance
store       CSV history store (plus an optional DuckDB view for SQL)
quality     data-quality checks
monitor     the daily snapshot: levels, changes, z-scores
charts      static charts for the site and README
narrative   template narrative, optional LLM narrative, numeric grounding check
llm         optional Gemini client (free API key); never required
brief       renders the daily brief into the site and README
decoder     central-bank statement redlines and tone scores (Project 2)
portfolio   paper model portfolio: NAV, risk, Brinson attribution (Project 3)
podcast     turns the brief into a short audio episode and an RSS feed
compliance  blocks commits that contain employer or other sensitive terms
"""

__version__ = "0.1.0"

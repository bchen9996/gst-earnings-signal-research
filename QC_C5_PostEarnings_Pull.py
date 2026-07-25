# ============================================================================
# C5 POST-EARNINGS CONTINUATION/REVERSAL PULL -- pulls the 9:45am ET price
# and Day0/Day2/Day5/Day20 closes for BOTH the stock and its sector ETF,
# for every usable row in Live Signal Engine/C5_PostEarnings_Population.csv.
# See Live Signal Engine/C5_PostEarnings_PreRegistration.md for the full
# locked methodology this pull implements -- this script ONLY pulls the raw
# prices and computes C5 mechanically from the locked formula; it does not
# run the regression, bootstrap, or LOTO/LOYO checks (those happen locally
# after these results are pasted back, same division of labor as every
# other QC pull in this project).
#
# WHY QUANTCONNECT: yfinance cannot supply true intraday (minute-resolution)
# equity prices for this population's date range (2021-2025) -- confirmed
# directly before this test was designed (1m data: last 30 days only, 5m:
# last 60 days, even 1h: last 730 days only -- see the pre-registration
# doc's section 4 for the exact check). AlgoSeek minute-resolution equity
# data in QuantConnect Research reaches back through this project's full
# date range.
#
# *** TIMEZONE, VERIFY BEFORE TRUSTING RESULTS: get_945_price() below
# assumes QuantBook's minute-bar history index is already in US Eastern
# time (QuantConnect Research's typical default for US equities) and picks
# the first bar timestamped >= 9:45:00. The very first printed row for
# event #0 includes its raw resolved timestamp -- if that is NOT ~9:45am,
# the tz handling needs adjusting for your notebook's actual index
# convention (uncomment the diagnostic print near the top of the loop). ***
#
# HOW TO USE: paste this entire file into an empty cell in your
# QuantConnect Research notebook and run it. No file upload needed.
# ============================================================================

import pandas as pd
import numpy as np
from datetime import timedelta, time as dtime
from QuantConnect.Research import QuantBook

qb = QuantBook()

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------
TICKER_OVERRIDES = {"BRK-B": "BRK.B"}
HORIZONS = {"day0": 0, "day2": 2, "day5": 5, "day20": 20}   # trading days after Day 0

# ---------------------------------------------------------------------------
# EMBEDDED_SAMPLE -- generated programmatically from
# Live Signal Engine/C5_PostEarnings_Population.csv by
# GST_C5_PostEarnings_GenerateQCPull.py (not hand-typed -- see
# CandidateB_PreRegistration.md's own note on why generated tables matter:
# an earlier hand-typed sample table in this project had transcription
# errors caught only after the fact).
# Each entry: pair_id, role ("signal"/"control"), ticker, sector_etf,
# earnings_date (Day0 is derived from this + bmo_amc), bmo_amc, gap
# (already signed, from the population builder's daily-OHLC computation),
# zscore.
# ---------------------------------------------------------------------------
EMBEDDED_SAMPLE = [
    {"pair_id": 0, "role": "signal", "ticker": "AAPL", "sector_etf": "XLK", "earnings_date": "2022-10-27", "bmo_amc": "AMC", "gap": 0.023209, "zscore": 6.1518},
    {"pair_id": 1, "role": "signal", "ticker": "AAPL", "sector_etf": "XLK", "earnings_date": "2023-02-02", "bmo_amc": "AMC", "gap": -0.018672, "zscore": 6.6056},
    {"pair_id": 2, "role": "signal", "ticker": "AAPL", "sector_etf": "XLK", "earnings_date": "2023-05-04", "bmo_amc": "AMC", "gap": 0.030824, "zscore": 7.2824},
    {"pair_id": 3, "role": "signal", "ticker": "AAPL", "sector_etf": "XLK", "earnings_date": "2025-01-30", "bmo_amc": "AMC", "gap": 0.039611, "zscore": 8.6168},
    {"pair_id": 4, "role": "signal", "ticker": "AAPL", "sector_etf": "XLK", "earnings_date": "2025-07-31", "bmo_amc": "AMC", "gap": 0.015773, "zscore": 5.7387},
    {"pair_id": 5, "role": "signal", "ticker": "ABBV", "sector_etf": "XLV", "earnings_date": "2024-10-30", "bmo_amc": "BMO", "gap": 0.011389, "zscore": 6.6894},
    {"pair_id": 6, "role": "signal", "ticker": "ADBE", "sector_etf": "XLK", "earnings_date": "2021-03-23", "bmo_amc": "AMC", "gap": 0.009860, "zscore": 5.3815},
    {"pair_id": 7, "role": "signal", "ticker": "ADBE", "sector_etf": "XLK", "earnings_date": "2021-09-21", "bmo_amc": "AMC", "gap": -0.033214, "zscore": 8.3912},
    {"pair_id": 8, "role": "signal", "ticker": "ADBE", "sector_etf": "XLK", "earnings_date": "2021-12-16", "bmo_amc": "BMO", "gap": -0.085978, "zscore": 7.0014},
    {"pair_id": 9, "role": "signal", "ticker": "ADBE", "sector_etf": "XLK", "earnings_date": "2022-03-22", "bmo_amc": "AMC", "gap": -0.064051, "zscore": 6.9888},
    {"pair_id": 10, "role": "signal", "ticker": "ADBE", "sector_etf": "XLK", "earnings_date": "2022-09-15", "bmo_amc": "BMO", "gap": -0.139486, "zscore": 24.1066},
    {"pair_id": 11, "role": "signal", "ticker": "ADBE", "sector_etf": "XLK", "earnings_date": "2023-03-15", "bmo_amc": "AMC", "gap": 0.032325, "zscore": 6.1013},
    {"pair_id": 12, "role": "signal", "ticker": "ADBE", "sector_etf": "XLK", "earnings_date": "2023-12-13", "bmo_amc": "AMC", "gap": -0.051373, "zscore": 15.6618},
    {"pair_id": 13, "role": "signal", "ticker": "ADBE", "sector_etf": "XLK", "earnings_date": "2024-03-14", "bmo_amc": "AMC", "gap": -0.132538, "zscore": 8.7884},
    {"pair_id": 14, "role": "signal", "ticker": "ADBE", "sector_etf": "XLK", "earnings_date": "2024-06-13", "bmo_amc": "AMC", "gap": 0.144865, "zscore": 8.9431},
    {"pair_id": 15, "role": "signal", "ticker": "ADBE", "sector_etf": "XLK", "earnings_date": "2024-12-11", "bmo_amc": "AMC", "gap": -0.120501, "zscore": 14.6653},
    {"pair_id": 16, "role": "signal", "ticker": "ADBE", "sector_etf": "XLK", "earnings_date": "2025-03-12", "bmo_amc": "AMC", "gap": -0.079034, "zscore": 6.8769},
    {"pair_id": 17, "role": "signal", "ticker": "ADBE", "sector_etf": "XLK", "earnings_date": "2025-06-12", "bmo_amc": "AMC", "gap": -0.052556, "zscore": 8.2885},
    {"pair_id": 18, "role": "signal", "ticker": "ADBE", "sector_etf": "XLK", "earnings_date": "2025-09-11", "bmo_amc": "AMC", "gap": 0.029652, "zscore": 16.9269},
    {"pair_id": 19, "role": "signal", "ticker": "ADBE", "sector_etf": "XLK", "earnings_date": "2025-12-10", "bmo_amc": "AMC", "gap": -0.004323, "zscore": 5.8006},
    {"pair_id": 20, "role": "signal", "ticker": "AMZN", "sector_etf": "XLY", "earnings_date": "2021-07-29", "bmo_amc": "AMC", "gap": -0.072563, "zscore": 5.5190},
    {"pair_id": 21, "role": "signal", "ticker": "AMZN", "sector_etf": "XLY", "earnings_date": "2022-10-27", "bmo_amc": "AMC", "gap": -0.125121, "zscore": 5.7597},
    {"pair_id": 22, "role": "signal", "ticker": "AMZN", "sector_etf": "XLY", "earnings_date": "2023-02-02", "bmo_amc": "AMC", "gap": -0.070158, "zscore": 5.1792},
    {"pair_id": 23, "role": "signal", "ticker": "AMZN", "sector_etf": "XLY", "earnings_date": "2023-08-03", "bmo_amc": "AMC", "gap": 0.090071, "zscore": 7.4572},
    {"pair_id": 24, "role": "signal", "ticker": "AMZN", "sector_etf": "XLY", "earnings_date": "2024-02-01", "bmo_amc": "AMC", "gap": 0.060359, "zscore": 7.2373},
    {"pair_id": 25, "role": "signal", "ticker": "AMZN", "sector_etf": "XLY", "earnings_date": "2024-04-30", "bmo_amc": "AMC", "gap": 0.037241, "zscore": 7.7223},
    {"pair_id": 26, "role": "signal", "ticker": "AMZN", "sector_etf": "XLY", "earnings_date": "2024-08-01", "bmo_amc": "AMC", "gap": -0.098820, "zscore": 5.1032},
    {"pair_id": 27, "role": "signal", "ticker": "AMZN", "sector_etf": "XLY", "earnings_date": "2025-07-31", "bmo_amc": "AMC", "gap": -0.074926, "zscore": 5.1145},
    {"pair_id": 28, "role": "signal", "ticker": "AMZN", "sector_etf": "XLY", "earnings_date": "2025-10-30", "bmo_amc": "AMC", "gap": 0.115317, "zscore": 8.7855},
    {"pair_id": 29, "role": "signal", "ticker": "BKR", "sector_etf": "XLE", "earnings_date": "2022-01-20", "bmo_amc": "BMO", "gap": 0.037698, "zscore": 9.7434},
    {"pair_id": 30, "role": "signal", "ticker": "BKR", "sector_etf": "XLE", "earnings_date": "2022-07-20", "bmo_amc": "BMO", "gap": -0.104495, "zscore": 5.3522},
    {"pair_id": 31, "role": "signal", "ticker": "BKR", "sector_etf": "XLE", "earnings_date": "2025-07-22", "bmo_amc": "AMC", "gap": 0.036314, "zscore": 11.4518},
    {"pair_id": 33, "role": "signal", "ticker": "COHR", "sector_etf": "XLK", "earnings_date": "2024-02-05", "bmo_amc": "AMC", "gap": 0.168330, "zscore": 11.4444},
    {"pair_id": 34, "role": "signal", "ticker": "COHR", "sector_etf": "XLK", "earnings_date": "2024-08-15", "bmo_amc": "AMC", "gap": 0.037449, "zscore": 5.4132},
    {"pair_id": 35, "role": "signal", "ticker": "CTSH", "sector_etf": "XLK", "earnings_date": "2022-11-02", "bmo_amc": "AMC", "gap": -0.145312, "zscore": 7.8797},
    {"pair_id": 36, "role": "signal", "ticker": "CTSH", "sector_etf": "XLK", "earnings_date": "2023-08-02", "bmo_amc": "AMC", "gap": 0.068891, "zscore": 5.5886},
    {"pair_id": 37, "role": "signal", "ticker": "DELL", "sector_etf": "XLK", "earnings_date": "2021-08-26", "bmo_amc": "AMC", "gap": -0.028872, "zscore": 10.6750},
    {"pair_id": 38, "role": "signal", "ticker": "DELL", "sector_etf": "XLK", "earnings_date": "2025-11-25", "bmo_amc": "AMC", "gap": 0.059054, "zscore": 5.8041},
    {"pair_id": 39, "role": "signal", "ticker": "DVN", "sector_etf": "XLE", "earnings_date": "2023-02-14", "bmo_amc": "AMC", "gap": -0.082953, "zscore": 10.2790},
    {"pair_id": 40, "role": "signal", "ticker": "GME", "sector_etf": "XLY", "earnings_date": "2023-03-21", "bmo_amc": "AMC", "gap": 0.410175, "zscore": 8.5408},
    {"pair_id": 41, "role": "signal", "ticker": "GME", "sector_etf": "XLY", "earnings_date": "2024-03-26", "bmo_amc": "AMC", "gap": -0.172052, "zscore": 5.7715},
    {"pair_id": 42, "role": "signal", "ticker": "GME", "sector_etf": "XLY", "earnings_date": "2025-09-09", "bmo_amc": "AMC", "gap": 0.066418, "zscore": 5.5837},
    {"pair_id": 43, "role": "signal", "ticker": "GOOGL", "sector_etf": "XLC", "earnings_date": "2022-10-25", "bmo_amc": "AMC", "gap": -0.080178, "zscore": 5.1797},
    {"pair_id": 44, "role": "signal", "ticker": "GOOGL", "sector_etf": "XLC", "earnings_date": "2023-10-24", "bmo_amc": "AMC", "gap": -0.079827, "zscore": 7.0455},
    {"pair_id": 45, "role": "signal", "ticker": "GOOGL", "sector_etf": "XLC", "earnings_date": "2024-10-29", "bmo_amc": "AMC", "gap": 0.062813, "zscore": 7.2061},
    {"pair_id": 46, "role": "signal", "ticker": "GOOGL", "sector_etf": "XLC", "earnings_date": "2025-10-29", "bmo_amc": "AMC", "gap": 0.060142, "zscore": 6.8394},
    {"pair_id": 47, "role": "signal", "ticker": "GPN", "sector_etf": "XLI", "earnings_date": "2021-08-02", "bmo_amc": "BMO", "gap": 0.003355, "zscore": 13.5740},
    {"pair_id": 48, "role": "signal", "ticker": "GPN", "sector_etf": "XLI", "earnings_date": "2022-10-31", "bmo_amc": "BMO", "gap": -0.010509, "zscore": 5.8377},
    {"pair_id": 49, "role": "signal", "ticker": "GPN", "sector_etf": "XLI", "earnings_date": "2024-08-07", "bmo_amc": "BMO", "gap": 0.047756, "zscore": 5.2022},
    {"pair_id": 50, "role": "signal", "ticker": "INTC", "sector_etf": "XLK", "earnings_date": "2021-10-21", "bmo_amc": "AMC", "gap": -0.105559, "zscore": 5.7690},
    {"pair_id": 51, "role": "signal", "ticker": "INTC", "sector_etf": "XLK", "earnings_date": "2022-07-28", "bmo_amc": "AMC", "gap": -0.109257, "zscore": 9.8934},
    {"pair_id": 52, "role": "signal", "ticker": "INTC", "sector_etf": "XLK", "earnings_date": "2023-01-26", "bmo_amc": "AMC", "gap": -0.105767, "zscore": 8.8728},
    {"pair_id": 53, "role": "signal", "ticker": "INTC", "sector_etf": "XLK", "earnings_date": "2024-01-25", "bmo_amc": "AMC", "gap": -0.114710, "zscore": 6.7212},
    {"pair_id": 54, "role": "signal", "ticker": "INTC", "sector_etf": "XLK", "earnings_date": "2024-08-01", "bmo_amc": "AMC", "gap": -0.280707, "zscore": 9.8784},
    {"pair_id": 55, "role": "signal", "ticker": "INTC", "sector_etf": "XLK", "earnings_date": "2025-07-24", "bmo_amc": "AMC", "gap": -0.090109, "zscore": 5.0230},
    {"pair_id": 56, "role": "signal", "ticker": "LDOS", "sector_etf": "XLK", "earnings_date": "2021-08-03", "bmo_amc": "BMO", "gap": -0.029562, "zscore": 5.8446},
    {"pair_id": 57, "role": "signal", "ticker": "LDOS", "sector_etf": "XLK", "earnings_date": "2023-05-02", "bmo_amc": "BMO", "gap": -0.044775, "zscore": 5.5987},
    {"pair_id": 58, "role": "signal", "ticker": "LDOS", "sector_etf": "XLK", "earnings_date": "2023-10-31", "bmo_amc": "BMO", "gap": 0.039832, "zscore": 5.5514},
    {"pair_id": 59, "role": "signal", "ticker": "LDOS", "sector_etf": "XLK", "earnings_date": "2024-02-13", "bmo_amc": "BMO", "gap": 0.043472, "zscore": 8.2752},
    {"pair_id": 60, "role": "signal", "ticker": "LDOS", "sector_etf": "XLK", "earnings_date": "2024-10-29", "bmo_amc": "BMO", "gap": 0.069798, "zscore": 6.3776},
    {"pair_id": 61, "role": "signal", "ticker": "MSFT", "sector_etf": "XLK", "earnings_date": "2021-07-27", "bmo_amc": "AMC", "gap": 0.008514, "zscore": 5.7949},
    {"pair_id": 62, "role": "signal", "ticker": "MSFT", "sector_etf": "XLK", "earnings_date": "2021-10-26", "bmo_amc": "AMC", "gap": 0.018815, "zscore": 9.5574},
    {"pair_id": 63, "role": "signal", "ticker": "MSFT", "sector_etf": "XLK", "earnings_date": "2022-01-25", "bmo_amc": "AMC", "gap": 0.065407, "zscore": 13.4780},
    {"pair_id": 64, "role": "signal", "ticker": "MSFT", "sector_etf": "XLK", "earnings_date": "2022-04-26", "bmo_amc": "AMC", "gap": 0.043025, "zscore": 6.5625},
    {"pair_id": 65, "role": "signal", "ticker": "MSFT", "sector_etf": "XLK", "earnings_date": "2022-07-26", "bmo_amc": "AMC", "gap": 0.036101, "zscore": 5.1824},
    {"pair_id": 66, "role": "signal", "ticker": "MSFT", "sector_etf": "XLK", "earnings_date": "2022-10-25", "bmo_amc": "AMC", "gap": -0.080944, "zscore": 13.1069},
    {"pair_id": 67, "role": "signal", "ticker": "MSFT", "sector_etf": "XLK", "earnings_date": "2023-01-24", "bmo_amc": "AMC", "gap": -0.031733, "zscore": 11.7806},
    {"pair_id": 68, "role": "signal", "ticker": "MSFT", "sector_etf": "XLK", "earnings_date": "2023-04-25", "bmo_amc": "AMC", "gap": 0.074425, "zscore": 7.3757},
    {"pair_id": 69, "role": "signal", "ticker": "MSFT", "sector_etf": "XLK", "earnings_date": "2023-10-24", "bmo_amc": "AMC", "gap": 0.042905, "zscore": 8.2717},
    {"pair_id": 70, "role": "signal", "ticker": "MSFT", "sector_etf": "XLK", "earnings_date": "2024-07-30", "bmo_amc": "AMC", "gap": -0.005739, "zscore": 6.5740},
    {"pair_id": 71, "role": "signal", "ticker": "MSFT", "sector_etf": "XLK", "earnings_date": "2024-10-30", "bmo_amc": "AMC", "gap": -0.040506, "zscore": 5.0283},
    {"pair_id": 72, "role": "signal", "ticker": "MSFT", "sector_etf": "XLK", "earnings_date": "2025-01-29", "bmo_amc": "AMC", "gap": -0.054734, "zscore": 11.4508},
    {"pair_id": 73, "role": "signal", "ticker": "MSFT", "sector_etf": "XLK", "earnings_date": "2025-07-30", "bmo_amc": "AMC", "gap": 0.078639, "zscore": 13.3765},
    {"pair_id": 74, "role": "signal", "ticker": "MSFT", "sector_etf": "XLK", "earnings_date": "2025-10-29", "bmo_amc": "AMC", "gap": -0.020653, "zscore": 7.9107},
    {"pair_id": 75, "role": "signal", "ticker": "NCLH", "sector_etf": "XLY", "earnings_date": "2025-11-04", "bmo_amc": "BMO", "gap": -0.083656, "zscore": 7.5524},
    {"pair_id": 76, "role": "signal", "ticker": "NFLX", "sector_etf": "XLC", "earnings_date": "2021-04-20", "bmo_amc": "AMC", "gap": -0.078655, "zscore": 13.9663},
    {"pair_id": 77, "role": "signal", "ticker": "NFLX", "sector_etf": "XLC", "earnings_date": "2021-07-20", "bmo_amc": "AMC", "gap": -0.009308, "zscore": 10.2794},
    {"pair_id": 78, "role": "signal", "ticker": "NFLX", "sector_etf": "XLC", "earnings_date": "2021-10-19", "bmo_amc": "AMC", "gap": -0.021241, "zscore": 15.2739},
    {"pair_id": 79, "role": "signal", "ticker": "NFLX", "sector_etf": "XLC", "earnings_date": "2022-01-20", "bmo_amc": "AMC", "gap": -0.238435, "zscore": 31.0985},
    {"pair_id": 80, "role": "signal", "ticker": "NFLX", "sector_etf": "XLC", "earnings_date": "2022-04-19", "bmo_amc": "AMC", "gap": -0.351880, "zscore": 13.6261},
    {"pair_id": 81, "role": "signal", "ticker": "NFLX", "sector_etf": "XLC", "earnings_date": "2022-10-18", "bmo_amc": "AMC", "gap": 0.095514, "zscore": 16.4636},
    {"pair_id": 82, "role": "signal", "ticker": "NFLX", "sector_etf": "XLC", "earnings_date": "2023-01-19", "bmo_amc": "AMC", "gap": 0.064414, "zscore": 8.9970},
    {"pair_id": 83, "role": "signal", "ticker": "NFLX", "sector_etf": "XLC", "earnings_date": "2023-04-18", "bmo_amc": "AMC", "gap": -0.028851, "zscore": 7.5055},
    {"pair_id": 84, "role": "signal", "ticker": "NFLX", "sector_etf": "XLC", "earnings_date": "2023-07-19", "bmo_amc": "AMC", "gap": -0.066194, "zscore": 15.8142},
    {"pair_id": 85, "role": "signal", "ticker": "NFLX", "sector_etf": "XLC", "earnings_date": "2023-10-18", "bmo_amc": "AMC", "gap": 0.156257, "zscore": 8.5654},
    {"pair_id": 86, "role": "signal", "ticker": "NFLX", "sector_etf": "XLC", "earnings_date": "2024-01-23", "bmo_amc": "AMC", "gap": 0.088529, "zscore": 26.7917},
    {"pair_id": 87, "role": "signal", "ticker": "NFLX", "sector_etf": "XLC", "earnings_date": "2024-07-18", "bmo_amc": "AMC", "gap": 0.027002, "zscore": 13.6586},
    {"pair_id": 88, "role": "signal", "ticker": "NFLX", "sector_etf": "XLC", "earnings_date": "2024-10-17", "bmo_amc": "AMC", "gap": 0.070176, "zscore": 17.0766},
    {"pair_id": 89, "role": "signal", "ticker": "NFLX", "sector_etf": "XLC", "earnings_date": "2025-01-21", "bmo_amc": "AMC", "gap": 0.137658, "zscore": 12.7874},
    {"pair_id": 90, "role": "signal", "ticker": "NFLX", "sector_etf": "XLC", "earnings_date": "2025-07-17", "bmo_amc": "AMC", "gap": -0.025604, "zscore": 5.4542},
    {"pair_id": 91, "role": "signal", "ticker": "NFLX", "sector_etf": "XLC", "earnings_date": "2025-10-21", "bmo_amc": "AMC", "gap": -0.082631, "zscore": 8.9863},
    {"pair_id": 92, "role": "signal", "ticker": "NKE", "sector_etf": "XLY", "earnings_date": "2021-06-24", "bmo_amc": "AMC", "gap": 0.131724, "zscore": 11.9064},
    {"pair_id": 93, "role": "signal", "ticker": "NKE", "sector_etf": "XLY", "earnings_date": "2021-12-20", "bmo_amc": "AMC", "gap": 0.060017, "zscore": 5.7069},
    {"pair_id": 94, "role": "signal", "ticker": "NKE", "sector_etf": "XLY", "earnings_date": "2022-03-21", "bmo_amc": "AMC", "gap": 0.053028, "zscore": 10.4459},
    {"pair_id": 95, "role": "signal", "ticker": "NKE", "sector_etf": "XLY", "earnings_date": "2022-06-27", "bmo_amc": "AMC", "gap": -0.021034, "zscore": 13.4434},
    {"pair_id": 96, "role": "signal", "ticker": "NKE", "sector_etf": "XLY", "earnings_date": "2022-09-29", "bmo_amc": "AMC", "gap": -0.134896, "zscore": 22.5318},
    {"pair_id": 97, "role": "signal", "ticker": "NKE", "sector_etf": "XLY", "earnings_date": "2023-03-21", "bmo_amc": "AMC", "gap": -0.015646, "zscore": 12.2236},
    {"pair_id": 98, "role": "signal", "ticker": "NKE", "sector_etf": "XLY", "earnings_date": "2023-06-29", "bmo_amc": "AMC", "gap": -0.015825, "zscore": 11.2982},
    {"pair_id": 99, "role": "signal", "ticker": "NKE", "sector_etf": "XLY", "earnings_date": "2023-09-28", "bmo_amc": "AMC", "gap": 0.103160, "zscore": 8.3175},
    {"pair_id": 100, "role": "signal", "ticker": "NKE", "sector_etf": "XLY", "earnings_date": "2023-12-21", "bmo_amc": "AMC", "gap": -0.123820, "zscore": 5.3922},
    {"pair_id": 101, "role": "signal", "ticker": "NKE", "sector_etf": "XLY", "earnings_date": "2024-03-21", "bmo_amc": "AMC", "gap": -0.071639, "zscore": 10.7769},
    {"pair_id": 102, "role": "signal", "ticker": "NKE", "sector_etf": "XLY", "earnings_date": "2024-06-27", "bmo_amc": "AMC", "gap": -0.199822, "zscore": 22.4678},
    {"pair_id": 103, "role": "signal", "ticker": "NKE", "sector_etf": "XLY", "earnings_date": "2025-03-20", "bmo_amc": "AMC", "gap": -0.076166, "zscore": 9.3732},
    {"pair_id": 104, "role": "signal", "ticker": "NKE", "sector_etf": "XLY", "earnings_date": "2025-09-30", "bmo_amc": "AMC", "gap": 0.064153, "zscore": 9.0445},
    {"pair_id": 105, "role": "signal", "ticker": "NVDA", "sector_etf": "XLK", "earnings_date": "2022-02-16", "bmo_amc": "AMC", "gap": -0.033797, "zscore": 6.1675},
    {"pair_id": 106, "role": "signal", "ticker": "NVDA", "sector_etf": "XLK", "earnings_date": "2022-05-25", "bmo_amc": "AMC", "gap": -0.056906, "zscore": 5.8399},
    {"pair_id": 107, "role": "signal", "ticker": "NVDA", "sector_etf": "XLK", "earnings_date": "2023-05-24", "bmo_amc": "AMC", "gap": 0.232284, "zscore": 17.1935},
    {"pair_id": 108, "role": "signal", "ticker": "NVDA", "sector_etf": "XLK", "earnings_date": "2023-08-23", "bmo_amc": "AMC", "gap": 0.063721, "zscore": 9.4449},
    {"pair_id": 109, "role": "signal", "ticker": "NVDA", "sector_etf": "XLK", "earnings_date": "2023-11-21", "bmo_amc": "AMC", "gap": -0.001844, "zscore": 5.5047},
    {"pair_id": 110, "role": "signal", "ticker": "NVDA", "sector_etf": "XLK", "earnings_date": "2024-02-21", "bmo_amc": "AMC", "gap": 0.106109, "zscore": 7.1643},
    {"pair_id": 111, "role": "signal", "ticker": "QCOM", "sector_etf": "XLK", "earnings_date": "2021-07-28", "bmo_amc": "AMC", "gap": 0.028105, "zscore": 5.8734},
    {"pair_id": 112, "role": "signal", "ticker": "QCOM", "sector_etf": "XLK", "earnings_date": "2021-11-03", "bmo_amc": "AMC", "gap": 0.121179, "zscore": 18.6841},
    {"pair_id": 113, "role": "signal", "ticker": "QCOM", "sector_etf": "XLK", "earnings_date": "2022-07-27", "bmo_amc": "AMC", "gap": -0.024012, "zscore": 6.9048},
    {"pair_id": 114, "role": "signal", "ticker": "QCOM", "sector_etf": "XLK", "earnings_date": "2022-11-02", "bmo_amc": "AMC", "gap": -0.074915, "zscore": 6.5667},
    {"pair_id": 115, "role": "signal", "ticker": "QCOM", "sector_etf": "XLK", "earnings_date": "2023-05-03", "bmo_amc": "AMC", "gap": -0.081203, "zscore": 10.5713},
    {"pair_id": 116, "role": "signal", "ticker": "QCOM", "sector_etf": "XLK", "earnings_date": "2023-08-02", "bmo_amc": "AMC", "gap": -0.099986, "zscore": 8.9663},
    {"pair_id": 117, "role": "signal", "ticker": "QCOM", "sector_etf": "XLK", "earnings_date": "2024-01-31", "bmo_amc": "AMC", "gap": -0.052815, "zscore": 7.0749},
    {"pair_id": 118, "role": "signal", "ticker": "QCOM", "sector_etf": "XLK", "earnings_date": "2024-11-06", "bmo_amc": "AMC", "gap": 0.041222, "zscore": 6.0433},
    {"pair_id": 119, "role": "signal", "ticker": "QCOM", "sector_etf": "XLK", "earnings_date": "2025-02-05", "bmo_amc": "AMC", "gap": -0.046677, "zscore": 5.2742},
    {"pair_id": 120, "role": "signal", "ticker": "QCOM", "sector_etf": "XLK", "earnings_date": "2025-07-30", "bmo_amc": "AMC", "gap": -0.038125, "zscore": 12.3111},
    {"pair_id": 121, "role": "signal", "ticker": "SBUX", "sector_etf": "XLY", "earnings_date": "2021-07-27", "bmo_amc": "AMC", "gap": -0.027919, "zscore": 5.6479},
    {"pair_id": 122, "role": "signal", "ticker": "SBUX", "sector_etf": "XLY", "earnings_date": "2021-10-28", "bmo_amc": "AMC", "gap": -0.051665, "zscore": 9.4657},
    {"pair_id": 123, "role": "signal", "ticker": "SBUX", "sector_etf": "XLY", "earnings_date": "2023-05-02", "bmo_amc": "AMC", "gap": -0.048144, "zscore": 12.3060},
    {"pair_id": 124, "role": "signal", "ticker": "SBUX", "sector_etf": "XLY", "earnings_date": "2023-08-01", "bmo_amc": "AMC", "gap": -0.007534, "zscore": 8.7049},
    {"pair_id": 125, "role": "signal", "ticker": "SBUX", "sector_etf": "XLY", "earnings_date": "2023-11-02", "bmo_amc": "BMO", "gap": 0.100323, "zscore": 7.9184},
    {"pair_id": 126, "role": "signal", "ticker": "SBUX", "sector_etf": "XLY", "earnings_date": "2024-01-30", "bmo_amc": "AMC", "gap": 0.043675, "zscore": 6.3045},
    {"pair_id": 127, "role": "signal", "ticker": "SBUX", "sector_etf": "XLY", "earnings_date": "2024-04-30", "bmo_amc": "AMC", "gap": -0.154527, "zscore": 26.7718},
    {"pair_id": 128, "role": "signal", "ticker": "SBUX", "sector_etf": "XLY", "earnings_date": "2025-01-28", "bmo_amc": "AMC", "gap": 0.022550, "zscore": 13.6492},
    {"pair_id": 129, "role": "signal", "ticker": "SBUX", "sector_etf": "XLY", "earnings_date": "2025-04-29", "bmo_amc": "AMC", "gap": -0.105295, "zscore": 5.5662},
    {"pair_id": 130, "role": "signal", "ticker": "SBUX", "sector_etf": "XLY", "earnings_date": "2025-07-29", "bmo_amc": "AMC", "gap": 0.051062, "zscore": 13.2358},
    {"pair_id": 131, "role": "signal", "ticker": "STZ", "sector_etf": "XLP", "earnings_date": "2023-01-05", "bmo_amc": "AMC", "gap": 0.009633, "zscore": 5.9029},
    {"pair_id": 132, "role": "signal", "ticker": "STZ", "sector_etf": "XLP", "earnings_date": "2024-01-05", "bmo_amc": "BMO", "gap": 0.008915, "zscore": 6.9317},
    {"pair_id": 133, "role": "signal", "ticker": "STZ", "sector_etf": "XLP", "earnings_date": "2024-04-11", "bmo_amc": "BMO", "gap": 0.022691, "zscore": 10.1959},
    {"pair_id": 134, "role": "signal", "ticker": "STZ", "sector_etf": "XLP", "earnings_date": "2025-01-10", "bmo_amc": "BMO", "gap": -0.076602, "zscore": 11.7801},
    {"pair_id": 135, "role": "signal", "ticker": "SYK", "sector_etf": "XLV", "earnings_date": "2023-01-31", "bmo_amc": "AMC", "gap": 0.060428, "zscore": 7.2622},
    {"pair_id": 136, "role": "signal", "ticker": "SYK", "sector_etf": "XLV", "earnings_date": "2024-01-30", "bmo_amc": "AMC", "gap": 0.068235, "zscore": 8.6168},
    {"pair_id": 137, "role": "signal", "ticker": "SYK", "sector_etf": "XLV", "earnings_date": "2024-04-30", "bmo_amc": "AMC", "gap": -0.008716, "zscore": 6.0101},
    {"pair_id": 138, "role": "signal", "ticker": "SYK", "sector_etf": "XLV", "earnings_date": "2024-07-30", "bmo_amc": "AMC", "gap": 0.000848, "zscore": 5.9146},
    {"pair_id": 139, "role": "signal", "ticker": "SYK", "sector_etf": "XLV", "earnings_date": "2025-01-28", "bmo_amc": "AMC", "gap": -0.000380, "zscore": 8.2860},
    {"pair_id": 140, "role": "signal", "ticker": "SYK", "sector_etf": "XLV", "earnings_date": "2025-07-31", "bmo_amc": "AMC", "gap": -0.053369, "zscore": 5.2274},
    {"pair_id": 141, "role": "signal", "ticker": "TSLA", "sector_etf": "XLY", "earnings_date": "2024-01-24", "bmo_amc": "AMC", "gap": -0.091277, "zscore": 7.5137},
    {"pair_id": 142, "role": "signal", "ticker": "TSLA", "sector_etf": "XLY", "earnings_date": "2024-04-23", "bmo_amc": "AMC", "gap": 0.118244, "zscore": 5.5972},
    {"pair_id": 143, "role": "signal", "ticker": "TTWO", "sector_etf": "XLC", "earnings_date": "2021-05-18", "bmo_amc": "AMC", "gap": 0.019547, "zscore": 8.3187},
    {"pair_id": 144, "role": "signal", "ticker": "TTWO", "sector_etf": "XLC", "earnings_date": "2022-11-07", "bmo_amc": "AMC", "gap": -0.165127, "zscore": 8.0837},
    {"pair_id": 145, "role": "signal", "ticker": "TTWO", "sector_etf": "XLC", "earnings_date": "2023-02-06", "bmo_amc": "AMC", "gap": 0.012614, "zscore": 8.0285},
    {"pair_id": 146, "role": "signal", "ticker": "TTWO", "sector_etf": "XLC", "earnings_date": "2023-05-17", "bmo_amc": "AMC", "gap": 0.101530, "zscore": 12.5688},
    {"pair_id": 147, "role": "signal", "ticker": "TTWO", "sector_etf": "XLC", "earnings_date": "2023-11-08", "bmo_amc": "AMC", "gap": 0.035334, "zscore": 27.4501},
    {"pair_id": 148, "role": "signal", "ticker": "TTWO", "sector_etf": "XLC", "earnings_date": "2024-05-16", "bmo_amc": "AMC", "gap": 0.037355, "zscore": 8.5275},
    {"pair_id": 149, "role": "signal", "ticker": "TTWO", "sector_etf": "XLC", "earnings_date": "2025-02-06", "bmo_amc": "AMC", "gap": 0.078344, "zscore": 9.4169},
    {"pair_id": 150, "role": "signal", "ticker": "UAL", "sector_etf": "XLI", "earnings_date": "2021-07-20", "bmo_amc": "AMC", "gap": 0.017124, "zscore": 5.5255},
    {"pair_id": 151, "role": "signal", "ticker": "UAL", "sector_etf": "XLI", "earnings_date": "2024-10-15", "bmo_amc": "AMC", "gap": 0.020858, "zscore": 7.2832},
    {"pair_id": 0, "role": "control", "ticker": "AAPL", "sector_etf": "XLK", "earnings_date": "2021-04-28", "bmo_amc": "AMC", "gap": 0.021404, "zscore": 1.3711},
    {"pair_id": 1, "role": "control", "ticker": "AAPL", "sector_etf": "XLK", "earnings_date": "2022-07-28", "bmo_amc": "AMC", "gap": 0.024421, "zscore": -0.2038},
    {"pair_id": 2, "role": "control", "ticker": "AAPL", "sector_etf": "XLK", "earnings_date": "2023-11-02", "bmo_amc": "AMC", "gap": -0.018931, "zscore": -0.0070},
    {"pair_id": 3, "role": "control", "ticker": "AAPL", "sector_etf": "XLK", "earnings_date": "2021-10-28", "bmo_amc": "AMC", "gap": -0.035696, "zscore": -0.2344},
    {"pair_id": 4, "role": "control", "ticker": "AAPL", "sector_etf": "XLK", "earnings_date": "2025-10-30", "bmo_amc": "AMC", "gap": 0.020388, "zscore": -0.2176},
    {"pair_id": 5, "role": "control", "ticker": "ABBV", "sector_etf": "XLV", "earnings_date": "2023-10-27", "bmo_amc": "BMO", "gap": -0.045294, "zscore": 1.7272},
    {"pair_id": 6, "role": "control", "ticker": "ADBE", "sector_etf": "XLK", "earnings_date": "2023-09-14", "bmo_amc": "AMC", "gap": -0.036988, "zscore": -0.0321},
    {"pair_id": 7, "role": "control", "ticker": "ADBE", "sector_etf": "XLK", "earnings_date": "2021-06-17", "bmo_amc": "AMC", "gap": 0.033178, "zscore": 1.2237},
    {"pair_id": 8, "role": "control", "ticker": "JBL", "sector_etf": "XLK", "earnings_date": "2022-09-27", "bmo_amc": "BMO", "gap": 0.040480, "zscore": -1.3966},
    {"pair_id": 9, "role": "control", "ticker": "ADBE", "sector_etf": "XLK", "earnings_date": "2022-06-16", "bmo_amc": "AMC", "gap": -0.044357, "zscore": -0.2294},
    {"pair_id": 11, "role": "control", "ticker": "ADBE", "sector_etf": "XLK", "earnings_date": "2023-06-15", "bmo_amc": "AMC", "gap": 0.054158, "zscore": 0.4812},
    {"pair_id": 20, "role": "control", "ticker": "AMZN", "sector_etf": "XLY", "earnings_date": "2021-04-29", "bmo_amc": "AMC", "gap": 0.015382, "zscore": 0.0805},
    {"pair_id": 21, "role": "control", "ticker": "AMZN", "sector_etf": "XLY", "earnings_date": "2025-05-01", "bmo_amc": "AMC", "gap": 0.006498, "zscore": -0.6621},
    {"pair_id": 22, "role": "control", "ticker": "AMZN", "sector_etf": "XLY", "earnings_date": "2022-04-28", "bmo_amc": "AMC", "gap": -0.107575, "zscore": 1.1722},
    {"pair_id": 23, "role": "control", "ticker": "AMZN", "sector_etf": "XLY", "earnings_date": "2025-02-06", "bmo_amc": "AMC", "gap": -0.026862, "zscore": -0.1188},
    {"pair_id": 24, "role": "control", "ticker": "AMZN", "sector_etf": "XLY", "earnings_date": "2022-02-03", "bmo_amc": "AMC", "gap": 0.113969, "zscore": 0.4142},
    {"pair_id": 29, "role": "control", "ticker": "BKR", "sector_etf": "XLE", "earnings_date": "2022-01-20", "bmo_amc": "BMO", "gap": 0.037698, "zscore": 1.7641},
    {"pair_id": 30, "role": "control", "ticker": "BKR", "sector_etf": "XLE", "earnings_date": "2022-04-20", "bmo_amc": "BMO", "gap": -0.021181, "zscore": -0.1870},
    {"pair_id": 31, "role": "control", "ticker": "BKR", "sector_etf": "XLE", "earnings_date": "2024-07-25", "bmo_amc": "AMC", "gap": 0.020585, "zscore": 0.6007},
    {"pair_id": 33, "role": "control", "ticker": "COHR", "sector_etf": "XLK", "earnings_date": "2025-08-13", "bmo_amc": "AMC", "gap": -0.224328, "zscore": 9.1640},
    {"pair_id": 34, "role": "control", "ticker": "COHR", "sector_etf": "XLK", "earnings_date": "2025-11-05", "bmo_amc": "AMC", "gap": 0.132472, "zscore": 1.4623},
    {"pair_id": 35, "role": "control", "ticker": "CTSH", "sector_etf": "XLK", "earnings_date": "2022-05-04", "bmo_amc": "AMC", "gap": -0.068815, "zscore": 1.8609},
    {"pair_id": 36, "role": "control", "ticker": "CTSH", "sector_etf": "XLK", "earnings_date": "2021-05-05", "bmo_amc": "AMC", "gap": -0.079695, "zscore": 3.9607},
    {"pair_id": 37, "role": "control", "ticker": "DELL", "sector_etf": "XLK", "earnings_date": "2021-11-23", "bmo_amc": "AMC", "gap": 0.012362, "zscore": 3.6620},
    {"pair_id": 38, "role": "control", "ticker": "DELL", "sector_etf": "XLK", "earnings_date": "2023-11-30", "bmo_amc": "AMC", "gap": -0.054302, "zscore": 1.6739},
    {"pair_id": 39, "role": "control", "ticker": "DVN", "sector_etf": "XLE", "earnings_date": "2025-08-05", "bmo_amc": "AMC", "gap": 0.021131, "zscore": 1.9732},
    {"pair_id": 40, "role": "control", "ticker": "GME", "sector_etf": "XLY", "earnings_date": "2025-06-10", "bmo_amc": "AMC", "gap": -0.038200, "zscore": 1.0466},
    {"pair_id": 41, "role": "control", "ticker": "GME", "sector_etf": "XLY", "earnings_date": "2024-03-26", "bmo_amc": "AMC", "gap": -0.172052, "zscore": 5.6112},
    {"pair_id": 42, "role": "control", "ticker": "GME", "sector_etf": "XLY", "earnings_date": "2025-03-25", "bmo_amc": "AMC", "gap": 0.127014, "zscore": 3.8682},
    {"pair_id": 43, "role": "control", "ticker": "GOOGL", "sector_etf": "XLC", "earnings_date": "2022-04-26", "bmo_amc": "AMC", "gap": -0.035870, "zscore": 3.0522},
    {"pair_id": 44, "role": "control", "ticker": "GOOGL", "sector_etf": "XLC", "earnings_date": "2022-02-01", "bmo_amc": "AMC", "gap": 0.094264, "zscore": 11.8902},
    {"pair_id": 45, "role": "control", "ticker": "GOOGL", "sector_etf": "XLC", "earnings_date": "2021-10-26", "bmo_amc": "AMC", "gap": 0.000692, "zscore": 4.6489},
    {"pair_id": 46, "role": "control", "ticker": "GOOGL", "sector_etf": "XLC", "earnings_date": "2024-07-23", "bmo_amc": "AMC", "gap": -0.046098, "zscore": 3.3545},
    {"pair_id": 47, "role": "control", "ticker": "GPN", "sector_etf": "XLI", "earnings_date": "2024-05-01", "bmo_amc": "BMO", "gap": -0.005472, "zscore": 3.7953},
    {"pair_id": 48, "role": "control", "ticker": "GPN", "sector_etf": "XLI", "earnings_date": "2022-10-31", "bmo_amc": "BMO", "gap": -0.010509, "zscore": 5.1783},
    {"pair_id": 49, "role": "control", "ticker": "GPN", "sector_etf": "XLI", "earnings_date": "2024-08-07", "bmo_amc": "BMO", "gap": 0.047756, "zscore": 5.3939},
    {"pair_id": 50, "role": "control", "ticker": "INTC", "sector_etf": "XLK", "earnings_date": "2021-07-22", "bmo_amc": "AMC", "gap": -0.024970, "zscore": 1.8905},
    {"pair_id": 51, "role": "control", "ticker": "INTC", "sector_etf": "XLK", "earnings_date": "2022-04-28", "bmo_amc": "AMC", "gap": -0.040297, "zscore": -0.1900},
    {"pair_id": 52, "role": "control", "ticker": "INTC", "sector_etf": "XLK", "earnings_date": "2023-07-27", "bmo_amc": "AMC", "gap": 0.061731, "zscore": 0.0222},
    {"pair_id": 53, "role": "control", "ticker": "INTC", "sector_etf": "XLK", "earnings_date": "2024-01-25", "bmo_amc": "AMC", "gap": -0.114710, "zscore": 0.2699},
    {"pair_id": 55, "role": "control", "ticker": "INTC", "sector_etf": "XLK", "earnings_date": "2025-01-30", "bmo_amc": "AMC", "gap": 0.004488, "zscore": -0.1689},
    {"pair_id": 56, "role": "control", "ticker": "LDOS", "sector_etf": "XLK", "earnings_date": "2021-08-03", "bmo_amc": "BMO", "gap": -0.029562, "zscore": 6.1823},
    {"pair_id": 57, "role": "control", "ticker": "LDOS", "sector_etf": "XLK", "earnings_date": "2023-10-31", "bmo_amc": "BMO", "gap": 0.039832, "zscore": 4.3477},
    {"pair_id": 59, "role": "control", "ticker": "LDOS", "sector_etf": "XLK", "earnings_date": "2024-02-13", "bmo_amc": "BMO", "gap": 0.043472, "zscore": 8.8394},
    {"pair_id": 63, "role": "control", "ticker": "MSFT", "sector_etf": "XLK", "earnings_date": "2021-04-27", "bmo_amc": "AMC", "gap": -0.022740, "zscore": 4.3854},
    {"pair_id": 64, "role": "control", "ticker": "MSFT", "sector_etf": "XLK", "earnings_date": "2025-04-30", "bmo_amc": "AMC", "gap": 0.086819, "zscore": 4.2485},
    {"pair_id": 69, "role": "control", "ticker": "MSFT", "sector_etf": "XLK", "earnings_date": "2024-04-25", "bmo_amc": "AMC", "gap": 0.032374, "zscore": -0.0680},
    {"pair_id": 75, "role": "control", "ticker": "NCLH", "sector_etf": "XLY", "earnings_date": "2021-11-03", "bmo_amc": "BMO", "gap": -0.018052, "zscore": 0.7526},
    {"pair_id": 76, "role": "control", "ticker": "NFLX", "sector_etf": "XLC", "earnings_date": "2025-04-17", "bmo_amc": "AMC", "gap": 0.011617, "zscore": 2.2383},
    {"pair_id": 77, "role": "control", "ticker": "NFLX", "sector_etf": "XLC", "earnings_date": "2022-01-20", "bmo_amc": "AMC", "gap": -0.238435, "zscore": 2.1480},
    {"pair_id": 80, "role": "control", "ticker": "NFLX", "sector_etf": "XLC", "earnings_date": "2023-01-19", "bmo_amc": "AMC", "gap": 0.064414, "zscore": 0.4721},
    {"pair_id": 89, "role": "control", "ticker": "NFLX", "sector_etf": "XLC", "earnings_date": "2024-04-18", "bmo_amc": "AMC", "gap": -0.072466, "zscore": 0.1998},
    {"pair_id": 92, "role": "control", "ticker": "NKE", "sector_etf": "XLY", "earnings_date": "2024-12-19", "bmo_amc": "AMC", "gap": -0.014896, "zscore": -0.4148},
    {"pair_id": 94, "role": "control", "ticker": "NKE", "sector_etf": "XLY", "earnings_date": "2025-12-18", "bmo_amc": "AMC", "gap": -0.103111, "zscore": 1.9245},
    {"pair_id": 97, "role": "control", "ticker": "NKE", "sector_etf": "XLY", "earnings_date": "2024-03-21", "bmo_amc": "AMC", "gap": -0.071639, "zscore": 0.2743},
    {"pair_id": 105, "role": "control", "ticker": "NVDA", "sector_etf": "XLK", "earnings_date": "2024-05-22", "bmo_amc": "AMC", "gap": 0.071897, "zscore": 4.8519},
    {"pair_id": 106, "role": "control", "ticker": "NVDA", "sector_etf": "XLK", "earnings_date": "2025-05-28", "bmo_amc": "AMC", "gap": 0.053720, "zscore": 1.5426},
    {"pair_id": 107, "role": "control", "ticker": "NVDA", "sector_etf": "XLK", "earnings_date": "2021-11-17", "bmo_amc": "AMC", "gap": 0.100884, "zscore": 3.7088},
    {"pair_id": 108, "role": "control", "ticker": "NVDA", "sector_etf": "XLK", "earnings_date": "2024-08-28", "bmo_amc": "AMC", "gap": -0.034421, "zscore": 3.4171},
    {"pair_id": 110, "role": "control", "ticker": "NVDA", "sector_etf": "XLK", "earnings_date": "2021-08-18", "bmo_amc": "AMC", "gap": 0.023565, "zscore": 0.9987},
    {"pair_id": 111, "role": "control", "ticker": "QCOM", "sector_etf": "XLK", "earnings_date": "2025-11-05", "bmo_amc": "AMC", "gap": -0.010741, "zscore": 1.9822},
    {"pair_id": 113, "role": "control", "ticker": "QCOM", "sector_etf": "XLK", "earnings_date": "2025-04-30", "bmo_amc": "AMC", "gap": -0.067353, "zscore": 1.1441},
    {"pair_id": 116, "role": "control", "ticker": "QCOM", "sector_etf": "XLK", "earnings_date": "2025-02-05", "bmo_amc": "AMC", "gap": -0.046677, "zscore": 5.3359},
    {"pair_id": 121, "role": "control", "ticker": "SBUX", "sector_etf": "XLY", "earnings_date": "2025-01-28", "bmo_amc": "AMC", "gap": 0.022550, "zscore": 14.6048},
    {"pair_id": 124, "role": "control", "ticker": "SBUX", "sector_etf": "XLY", "earnings_date": "2025-10-29", "bmo_amc": "AMC", "gap": -0.023318, "zscore": 2.4673},
    {"pair_id": 126, "role": "control", "ticker": "SBUX", "sector_etf": "XLY", "earnings_date": "2024-01-30", "bmo_amc": "AMC", "gap": 0.043675, "zscore": 6.5050},
    {"pair_id": 129, "role": "control", "ticker": "SBUX", "sector_etf": "XLY", "earnings_date": "2022-08-02", "bmo_amc": "AMC", "gap": 0.027105, "zscore": 2.8696},
    {"pair_id": 130, "role": "control", "ticker": "SBUX", "sector_etf": "XLY", "earnings_date": "2023-02-02", "bmo_amc": "AMC", "gap": -0.042771, "zscore": 0.1968},
    {"pair_id": 132, "role": "control", "ticker": "STZ", "sector_etf": "XLP", "earnings_date": "2025-01-10", "bmo_amc": "BMO", "gap": -0.076602, "zscore": 2.2258},
    {"pair_id": 133, "role": "control", "ticker": "STZ", "sector_etf": "XLP", "earnings_date": "2024-07-03", "bmo_amc": "BMO", "gap": 0.018633, "zscore": 4.4107},
    {"pair_id": 135, "role": "control", "ticker": "SYK", "sector_etf": "XLV", "earnings_date": "2023-01-31", "bmo_amc": "AMC", "gap": 0.060428, "zscore": 6.3502},
    {"pair_id": 136, "role": "control", "ticker": "SYK", "sector_etf": "XLV", "earnings_date": "2024-10-29", "bmo_amc": "AMC", "gap": 0.018436, "zscore": 3.7492},
    {"pair_id": 138, "role": "control", "ticker": "SYK", "sector_etf": "XLV", "earnings_date": "2023-08-03", "bmo_amc": "AMC", "gap": 0.029951, "zscore": -0.1086},
    {"pair_id": 139, "role": "control", "ticker": "SYK", "sector_etf": "XLV", "earnings_date": "2025-01-28", "bmo_amc": "AMC", "gap": -0.000380, "zscore": 8.5774},
    {"pair_id": 140, "role": "control", "ticker": "SYK", "sector_etf": "XLV", "earnings_date": "2025-07-31", "bmo_amc": "AMC", "gap": -0.053369, "zscore": 1.1568},
    {"pair_id": 142, "role": "control", "ticker": "TSLA", "sector_etf": "XLY", "earnings_date": "2023-07-19", "bmo_amc": "AMC", "gap": -0.040999, "zscore": 3.0909},
    {"pair_id": 143, "role": "control", "ticker": "TTWO", "sector_etf": "XLC", "earnings_date": "2021-11-03", "bmo_amc": "AMC", "gap": 0.025995, "zscore": 4.9477},
    {"pair_id": 144, "role": "control", "ticker": "TTWO", "sector_etf": "XLC", "earnings_date": "2022-05-16", "bmo_amc": "AMC", "gap": 0.085011, "zscore": 6.8559},
    {"pair_id": 145, "role": "control", "ticker": "TTWO", "sector_etf": "XLC", "earnings_date": "2022-08-08", "bmo_amc": "AMC", "gap": -0.035356, "zscore": 1.5147},
    {"pair_id": 146, "role": "control", "ticker": "TTWO", "sector_etf": "XLC", "earnings_date": "2021-08-02", "bmo_amc": "AMC", "gap": -0.060816, "zscore": 3.0641},
    {"pair_id": 147, "role": "control", "ticker": "TTWO", "sector_etf": "XLC", "earnings_date": "2024-11-06", "bmo_amc": "AMC", "gap": 0.043340, "zscore": 4.6833},
    {"pair_id": 149, "role": "control", "ticker": "TTWO", "sector_etf": "XLC", "earnings_date": "2025-02-06", "bmo_amc": "AMC", "gap": 0.078344, "zscore": 1.5252},
    {"pair_id": 150, "role": "control", "ticker": "UAL", "sector_etf": "XLI", "earnings_date": "2023-07-19", "bmo_amc": "AMC", "gap": 0.018621, "zscore": 2.8032},
    {"pair_id": 151, "role": "control", "ticker": "UAL", "sector_etf": "XLI", "earnings_date": "2024-07-17", "bmo_amc": "AMC", "gap": 0.020454, "zscore": 4.5959},
]


# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------
def day0_date(earnings_date: pd.Timestamp, bmo_amc: str) -> pd.Timestamp:
    """AMC -> next trading day; BMO -> the announcement day itself. Uses
    QuantBook's own daily history to find 'next trading day' rather than a
    weekday-only approximation."""
    if bmo_amc == "BMO":
        return earnings_date
    # AMC: need the next actual trading day. Pull a few days of SPY daily
    # bars as a market-calendar proxy (liquid, never halted).
    cal = qb.History(qb.AddEquity("SPY", Resolution.Daily).Symbol, earnings_date, earnings_date + timedelta(days=10), Resolution.Daily)
    if cal is None or cal.empty:
        return earnings_date + timedelta(days=1)   # weekend-naive fallback, logged via note downstream
    idx = pd.to_datetime(cal.index.get_level_values(-1) if isinstance(cal.index, pd.MultiIndex) else cal.index)
    after = sorted(d for d in idx if d.date() > earnings_date.date())
    return pd.Timestamp(after[0].date()) if after else earnings_date + timedelta(days=1)


def get_945_price(symbol, day0: pd.Timestamp, diagnostic=False):
    hist = qb.History(symbol, day0, day0 + timedelta(days=1), Resolution.Minute)
    if hist is None or hist.empty:
        return None, None
    times = hist.index.get_level_values(-1) if isinstance(hist.index, pd.MultiIndex) else hist.index
    times = pd.to_datetime(times)
    if diagnostic:
        print(f"    [diagnostic] first 3 raw minute-bar timestamps: {list(times[:3])}")
    target = dtime(9, 45)
    time_only = pd.Series([t.time() for t in times])
    mask = time_only >= target
    if not mask.any():
        return None, None
    pos = int(np.argmax(mask.to_numpy()))
    row = hist.iloc[pos]
    price = float(row["close"]) if "close" in row and pd.notna(row["close"]) else None
    return price, times[pos]


def nth_trading_day_close(symbol, day0: pd.Timestamp, n: int):
    """Close price N trading days after day0 (n=0 -> day0's own close)."""
    hist = qb.History(symbol, day0, day0 + timedelta(days=int(n * 1.6) + 15), Resolution.Daily)
    if hist is None or hist.empty:
        return None, None
    times = hist.index.get_level_values(-1) if isinstance(hist.index, pd.MultiIndex) else hist.index
    hist = hist.copy()
    hist.index = pd.to_datetime(times)
    hist = hist.sort_index()
    on_or_after = hist[hist.index.date >= day0.date()]
    if len(on_or_after) <= n:
        return None, None
    row = on_or_after.iloc[n]
    return float(row["close"]), on_or_after.index[n]


# ---------------------------------------------------------------------------
# MAIN LOOP
# ---------------------------------------------------------------------------
results = []

for i, ev in enumerate(EMBEDDED_SAMPLE):
    raw_ticker = ev["ticker"]
    qc_ticker = TICKER_OVERRIDES.get(raw_ticker, raw_ticker)
    etf = ev["sector_etf"]
    earnings_date = pd.Timestamp(ev["earnings_date"])
    bmo_amc = ev["bmo_amc"]

    print(f"\n[{i+1}/{len(EMBEDDED_SAMPLE)}] {raw_ticker} (pair {ev['pair_id']}, {ev['role']}) "
          f"earnings={earnings_date.date()} {bmo_amc}")

    row = {"pair_id": ev["pair_id"], "role": ev["role"], "ticker": raw_ticker, "sector_etf": etf,
           "earnings_date": ev["earnings_date"], "bmo_amc": bmo_amc, "gap": ev["gap"], "zscore": ev["zscore"],
           "note": ""}

    try:
        equity = qb.AddEquity(qc_ticker, Resolution.Minute)
        equity_symbol = equity.Symbol
        etf_equity = qb.AddEquity(etf, Resolution.Minute)
        etf_symbol = etf_equity.Symbol

        d0 = day0_date(earnings_date, bmo_amc)
        row["day0_date"] = d0.date().isoformat()

        stock_945, stock_945_ts = get_945_price(equity_symbol, d0, diagnostic=(i == 0))
        etf_945, etf_945_ts = get_945_price(etf_symbol, d0, diagnostic=(i == 0))
        row["stock_945_price"] = stock_945
        row["etf_945_price"] = etf_945
        row["stock_945_timestamp"] = str(stock_945_ts) if stock_945_ts is not None else None

        if stock_945 is None or etf_945 is None:
            row["note"] = "no 9:45am ET minute bar for stock or ETF on Day 0"
            results.append(row)
            continue

        for label, n in HORIZONS.items():
            stock_close, stock_close_date = nth_trading_day_close(equity_symbol, d0, n)
            etf_close, etf_close_date = nth_trading_day_close(etf_symbol, d0, n)
            row[f"stock_close_{label}"] = stock_close
            row[f"etf_close_{label}"] = etf_close
            row[f"{label}_date"] = stock_close_date.date().isoformat() if stock_close_date is not None else None

        results.append(row)
        print(f"  Day0={d0.date()}  stock_945={stock_945}  etf_945={etf_945}  "
              f"day5_stock={row.get('stock_close_day5')}  day5_etf={row.get('etf_close_day5')}")

    except Exception as e:
        row["note"] = f"exception: {e}"
        results.append(row)
        print(f"  EXCEPTION: {e}")


# ---------------------------------------------------------------------------
# C5 (and secondary-horizon) computation -- mechanical application of the
# LOCKED formula in C5_PostEarnings_PreRegistration.md section 4. No
# analysis (regression/bootstrap/LOTO/LOYO) happens here.
# ---------------------------------------------------------------------------
results_df = pd.DataFrame(results)


def compute_c(row, label):
    s945, sN = row.get("stock_945_price"), row.get(f"stock_close_{label}")
    e945, eN = row.get("etf_945_price"), row.get(f"etf_close_{label}")
    gap = row.get("gap")
    if any(v is None or pd.isna(v) for v in [s945, sN, e945, eN, gap]) or s945 == 0 or e945 == 0:
        return None
    stock_ret = (sN - s945) / s945
    etf_ret = (eN - e945) / e945
    return float(np.sign(gap) * (stock_ret - etf_ret))


for label in HORIZONS:
    results_df[f"C_{label}"] = results_df.apply(lambda r: compute_c(r, label), axis=1)

results_df.rename(columns={"C_day5": "C5"}, inplace=True)

print(f"\nTotal rows: {len(results_df)}")
usable = results_df[results_df["C5"].notna()]
print(f"Usable rows (C5 computed): {len(usable)} / {len(results_df)}")

display(results_df)

# To export for local regression/bootstrap/LOTO-LOYO analysis:
# results_df.to_csv("QC_C5_PostEarnings_RawResults.csv", index=False)

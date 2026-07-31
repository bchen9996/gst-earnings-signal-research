import urllib.request, urllib.parse, urllib.error, time, json
import pandas as pd

WIKI_API = "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/all-access/user/{article}/daily/{start}/{end}"

def probe(article: str, start: str, end: str, label: str):
    encoded = urllib.parse.quote(article.replace(" ", "_"), safe="")
    url = WIKI_API.format(article=encoded, start=start, end=end)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (research; GST project)"})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read()
            elapsed = time.time() - t0
            print(f"[{label}] {article!r} {start}-{end}: HTTP {resp.status}  elapsed={elapsed:.2f}s  "
                  f"bytes={len(body)}  Retry-After={resp.headers.get('Retry-After')}")
            try:
                data = json.loads(body)
                items = data.get("items", [])
                print(f"    -> {len(items)} daily items returned"
                      + (f", first={items[0]['timestamp']}, last={items[-1]['timestamp']}" if items else ""))
            except Exception as e:
                print(f"    -> body not parseable as expected JSON: {e}; first 200 bytes: {body[:200]!r}")
    except urllib.error.HTTPError as e:
        elapsed = time.time() - t0
        err_body = e.read()[:300]
        print(f"[{label}] {article!r} {start}-{end}: HTTPError {e.code}  elapsed={elapsed:.2f}s  "
              f"Retry-After={e.headers.get('Retry-After')}  body[:300]={err_body!r}")
    except Exception as e:
        elapsed = time.time() - t0
        print(f"[{label}] {article!r} {start}-{end}: EXCEPTION {type(e).__name__}: {e}  elapsed={elapsed:.2f}s")
    print()

print("=" * 100)
print("PART 1: exact ranges the real bisection attempted for AMZN (all in YYYYMMDD form used by the API)")
print("=" * 100)
ranges_amzn = [
    ("20251003", "20260730", "AMZN full 300d (attempt 1, depth 0)"),
    ("20251003", "20260302", "AMZN left half 150d (attempt 1, depth 1)"),
    ("20251003", "20251217", "AMZN left-left 75d (attempt 1, depth 2, never resolved before timeout)"),
    ("20251218", "20260302", "AMZN right-left 75d (never attempted before timeout)"),
    ("20260303", "20260730", "AMZN right half 150d (never attempted before timeout)"),
]
for start, end, label in ranges_amzn:
    probe("Amazon (company)", start, end, label)
    time.sleep(1.5)

print("=" * 100)
print("PART 2: known-good comparison ticker (AAPL / 'Apple Inc.') on the IDENTICAL date windows")
print("=" * 100)
for start, end, label in ranges_amzn:
    probe("Apple Inc.", start, end, label.replace("AMZN", "AAPL"))
    time.sleep(1.5)

print("=" * 100)
print("PART 3: progressively shorter AMZN ranges, all anchored at the same end date, to see whether")
print("one particular interval is pathological or whether slowness is uniform")
print("=" * 100)
today_end = "20260730"
for days_back, label in [(300, "300d"), (150, "150d"), (75, "75d"), (37, "37d (below MIN_BISECT_DAYS=45)"),
                          (20, "20d"), (7, "7d"), (1, "1d")]:
    start = (pd.Timestamp("2026-07-30") - pd.Timedelta(days=days_back)).strftime("%Y%m%d")
    probe("Amazon (company)", start, today_end, f"AMZN {label} ending today")
    time.sleep(1.5)

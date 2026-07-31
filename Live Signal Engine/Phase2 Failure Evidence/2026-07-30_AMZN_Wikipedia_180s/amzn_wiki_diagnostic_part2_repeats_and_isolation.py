import urllib.request, urllib.parse, urllib.error, time, json, datetime

WIKI_API = "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/all-access/user/{article}/daily/{start}/{end}"

def probe(article, start, end, label):
    encoded = urllib.parse.quote(article.replace(" ", "_"), safe="")
    url = WIKI_API.format(article=encoded, start=start, end=end)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (research; GST project)"})
    ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read()
            elapsed = time.time() - t0
            n_items = 0
            try:
                n_items = len(json.loads(body).get("items", []))
            except Exception:
                pass
            print(f"[{ts}] [{label}] {article!r} {start}-{end}: HTTP {resp.status}  elapsed={elapsed:.2f}s  "
                  f"bytes={len(body)}  Retry-After={resp.headers.get('Retry-After')}  items={n_items}")
    except urllib.error.HTTPError as e:
        elapsed = time.time() - t0
        err_body = e.read()[:200]
        print(f"[{ts}] [{label}] {article!r} {start}-{end}: HTTPError {e.code}  elapsed={elapsed:.2f}s  "
              f"Retry-After={e.headers.get('Retry-After')}  body[:200]={err_body!r}")
    except Exception as e:
        elapsed = time.time() - t0
        print(f"[{ts}] [{label}] {article!r} {start}-{end}: EXCEPTION {type(e).__name__}: {e}  elapsed={elapsed:.2f}s")

print("=" * 100)
print("PART 2: repeat the IDENTICAL full-range request 3x for AMZN, 3x for AAPL control, with timestamps")
print("=" * 100)
for i in range(3):
    probe("Amazon (company)", "20251003", "20260730", f"AMZN full-range trial {i+1}/3")
    time.sleep(3)
for i in range(3):
    probe("Apple Inc.", "20251003", "20260730", f"AAPL full-range trial {i+1}/3")
    time.sleep(3)

print()
print("=" * 100)
print("PART 3: range isolation -- full, first half, second half, then narrow only where failure occurs")
print("=" * 100)
probe("Amazon (company)", "20251003", "20260730", "AMZN full (300d)")
time.sleep(2)
probe("Amazon (company)", "20251003", "20260302", "AMZN first half (150d)")
time.sleep(2)
probe("Amazon (company)", "20260303", "20260730", "AMZN second half (150d)")
time.sleep(2)
probe("Amazon (company)", "20251003", "20251217", "AMZN Q1 quarter (75d)")
time.sleep(2)
probe("Amazon (company)", "20251218", "20260302", "AMZN Q2 quarter (75d)")
time.sleep(2)
probe("Amazon (company)", "20251218", "20260118", "AMZN Q2a (32d)")
time.sleep(2)
probe("Amazon (company)", "20260119", "20260302", "AMZN Q2b (43d)")
time.sleep(2)

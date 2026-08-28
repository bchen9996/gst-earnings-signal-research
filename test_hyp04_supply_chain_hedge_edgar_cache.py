#!/usr/bin/env python3
"""Tests for the on-disk EDGAR response cache -- HYP-04.

WHY THE CACHE EXISTS, and therefore what these tests have to protect:

The 2026-08-27 full-frame walk established that widening the corpus from
2026-only to 1996-2026 raised the extractor's false-positive rate WITH NO CODE
CHANGE -- eight fabricated counterparties, found over two measurement rounds.
The lesson was that gates must be re-measured against the whole corpus, not
spot-checked. But each such measurement costs ~1,250 live SEC requests, which
needs the repo owner's staged go-ahead, so in practice it does not get done
and recorded limitations stay open. The cache turns one authorized walk into
unlimited free re-measurement.

That only holds if a replay is EQUIVALENT to the live run. A cache that serves
subtly different bytes would let a gate be "measured" against a corpus that
never existed, which is worse than not measuring it -- it would produce a
confident number with nothing behind it. So the tests below are mostly about
non-equivalence:

  * a hit must reach no network AND must not inflate `requests_made`, which is
    a claim about load placed on a fair-access endpoint
  * a 404 must be REPLAYED as a 404, because the full-submission fallback
    branches on status and exists to recover the 2000-2001 filings; a replay
    that turned 404 into a miss would silently lose exactly those
  * the stored body must be RAW -- pre-strip_markup, pre-first_document --
    because those are the functions a re-measurement most needs to vary
  * a corrupt, truncated or version-mismatched entry must be a MISS, never a
    partial body handed to the parser as though it were a whole filing
  * neither a status-less transport error NOR a status in TRANSIENT_STATUSES
    may be cached, or a passing server hiccup becomes a permanent fact about
    the corpus. The 2026-08-28 walk proved this one in production: it cached
    two 503s, and this suite's own "definite status" control had used 500 --
    itself transient -- so the control was pinning the bug

Offline. `_get` is stubbed and the socket layer is blocked before any import.

Run directly: python test_hyp04_supply_chain_hedge_edgar_cache.py
"""
from __future__ import annotations

import gzip
import json
import socket
import sys
import tempfile
from pathlib import Path


class NetworkBlocked(RuntimeError):
    pass


def _no_net(*a, **k):
    raise NetworkBlocked("network access attempted during an offline test")


socket.socket.connect = _no_net
socket.socket.connect_ex = _no_net
socket.create_connection = _no_net
socket.getaddrinfo = _no_net

from hyp04_supply_chain_hedge.edgar_linkage import (  # noqa: E402
    CACHE_FORMAT_VERSION,
    CACHE_KIND_JSON,
    CACHE_KIND_TEXT,
    SOURCE_FULL_SUBMISSION,
    SOURCE_PRIMARY_DOCUMENT,
    EdgarClient,
    FilingCache,
    OfflineCacheMiss,
    extract_edges_from_text,
)

FAILURES: list[str] = []
SKIPS: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(("PASS: " if ok else "FAIL: ") + label
          + ("" if ok or not detail else f"   {detail}"))
    if not ok:
        FAILURES.append(label)


def skip(label: str, why: str) -> None:
    print(f"SKIP: {label}   ({why})")
    SKIPS.append(label)


CONTACT = "offline tester tester@realdomain.org"

# A filing body with real markup in it, so "the cache stores RAW" is testable
# rather than asserted. strip_markup must still have work to do on the way out.
# The denominator wording is the REAL one from McKesson's FY2000 10-K, taken
# from the walk artifact ("consolidated sales"), not a paraphrase. An earlier
# draft wrote "the Company's consolidated revenues" and produced zero edges --
# which turned out not to be a fixture typo but a genuine extractor gap, now
# recorded in HYP04_EXTRACTOR_POSSESSIVE_DENOMINATOR_FINDING_2026-08-27.md.
# This suite is about the CACHE, so it uses prose the extractor already
# handles; pinning the gap is that finding's job, not this file's.
RAW_FILING = (
    "<html><body><p>Sales to the Company's largest customer, "
    "Rite Aid Corporation, represented approximately 15% of consolidated "
    "sales.</p></body></html>"
)


class _Resp:
    def __init__(self, payload=None, text=None):
        self._payload = payload
        self.text = text

    def json(self):
        return self._payload


def _HTTPError(status):
    """A REAL requests.HTTPError carrying a status.

    Deliberately not a stand-in class. filing_text_with_source catches
    requests.HTTPError specifically -- correctly, since a bare Exception there
    would swallow bugs -- so a fake that raised its own type would never
    exercise the 404 fallback and this suite would be testing nothing. The
    first draft of this file made exactly that mistake.
    """
    import requests

    exc = requests.HTTPError(f"HTTP {status}")
    exc.response = type("_R", (), {"status_code": status})()
    return exc


class FakeClient(EdgarClient):
    """EdgarClient with the transport replaced. Counts what it was asked for."""

    def __init__(self, routes: dict, **kw):
        super().__init__(CONTACT, **kw)
        self.routes = routes
        self.urls: list[str] = []

    def _get(self, url: str, timeout: int = 30):
        self.urls.append(url)
        self.requests_made += 1
        for key in sorted(self.routes, key=len, reverse=True):
            if key in url:
                v = self.routes[key]
                if isinstance(v, int):          # a status code to raise
                    raise _HTTPError(v)
                if isinstance(v, dict):
                    return _Resp(payload=v)
                return _Resp(text=v)
        raise AssertionError(f"unexpected URL requested: {url}")


# ============ 1. no cache is byte-for-byte the old path ==================
def test_1_no_cache_changes_nothing() -> None:
    print("\n--- PART 1: a client with no cache ---")
    c = FakeClient({"company_tickers.json": {"0": {"ticker": "MCK",
                                                   "cik_str": 927653}}})
    check("1a. no cache attribute set means no caching", c.cache is None)
    check("1b. it resolves normally", c.cik_for("MCK") == "0000927653",
          str(c.cik_for("MCK")))
    # cik_for memoises the map, so the second call is free either way; what
    # matters is that exactly one transport call happened, as before.
    check("1c. and made exactly one transport call", len(c.urls) == 1,
          str(c.urls))


# ============ 2. a hit reaches no network and costs no request ===========
def test_2_a_hit_is_not_a_request() -> None:
    print("\n--- PART 2: hits ---")
    with tempfile.TemporaryDirectory() as td:
        cache = FilingCache(Path(td))
        routes = {"/Archives/": RAW_FILING}

        c1 = FakeClient(routes, cache=cache)
        t1 = c1.filing_text_with_source("927653", "0000927653-01-000010", "a.htm")
        check("2a. the live fetch works", t1[1] == SOURCE_PRIMARY_DOCUMENT,
              str(t1[1]))
        check("2b. and it was stored", cache.writes == 1, str(cache.stats()))

        c2 = FakeClient(routes, cache=cache)
        t2 = c2.filing_text_with_source("927653", "0000927653-01-000010", "a.htm")
        check("2c. the replay returns the same text", t2[0] == t1[0])
        check("2d. and the same source path", t2[1] == t1[1])
        check("2e. REACHING NO NETWORK", c2.urls == [], str(c2.urls))
        # The load claim. requests_made is what we tell the SEC we asked for.
        check("2f. a hit does not inflate requests_made", c2.requests_made == 0,
              str(c2.requests_made))


# ============ 3. the stored body is RAW ==================================
def test_3_the_cache_stores_what_the_transport_returned() -> None:
    """If the cache stored cleaned text, strip_markup could never be re-measured."""
    print("\n--- PART 3: raw, not parsed ---")
    with tempfile.TemporaryDirectory() as td:
        cache = FilingCache(Path(td))
        c = FakeClient({"/Archives/": RAW_FILING}, cache=cache)
        text, _ = c.filing_text_with_source("927653", "acc-1", "a.htm")

        stored = [f for f in Path(td).rglob("*.json.gz")]
        check("3a. exactly one entry was written", len(stored) == 1,
              str(stored))
        with gzip.open(stored[0], "rt", encoding="utf-8") as fh:
            rec = json.load(fh)
        check("3b. it is the RAW body, markup intact",
              "<html>" in rec["body"] and "<p>" in rec["body"],
              rec["body"][:60])
        check("3c. which is NOT what the caller received",
              "<html>" not in text, text[:60])
        check("3d. and the entry records its status", rec["status"] == 200,
              str(rec.get("status")))
        check("3e. and its format version",
              rec["v"] == CACHE_FORMAT_VERSION, str(rec.get("v")))


# ============ 4. a 404 must replay as a 404 ==============================
def test_4_negative_results_are_cached_and_replayed() -> None:
    """The fallback branches on status. A replayed miss would take the wrong one.

    This is the case that recovers the 2000-2001 filings: 10 of the 11
    unretrievable filings in the full-frame walk were 404s on the
    per-document URL. If a replay did not reproduce the 404, the
    full-submission fallback would not fire and the offline corpus would be
    missing precisely the oldest filings -- the ones the walk exists to reach.
    """
    print("\n--- PART 4: negative caching ---")
    with tempfile.TemporaryDirectory() as td:
        cache = FilingCache(Path(td))
        # Per-document URL 404s; the full-submission .txt answers.
        full = ("<DOCUMENT><TYPE>10-K" + RAW_FILING + "</DOCUMENT>"
                "<DOCUMENT><TYPE>EX-99 Special Obligor CVS </DOCUMENT>")
        routes = {"/Archives/edgar/data/927653/000092765301000010/a.htm": 404,
                  "/Archives/edgar/data/927653/0000927653-01-000010.txt": full}

        c1 = FakeClient(routes, cache=cache)
        t1, src1 = c1.filing_text_with_source(
            "927653", "0000927653-01-000010", "a.htm")
        check("4a. live: the fallback fired", src1 == SOURCE_FULL_SUBMISSION,
              str(src1))
        check("4b. and recovered the disclosure", "Rite Aid" in t1)
        check("4c. exhibits excluded", "Special Obligor" not in t1)

        c2 = FakeClient(routes, cache=cache)
        t2, src2 = c2.filing_text_with_source(
            "927653", "0000927653-01-000010", "a.htm")
        check("4d. REPLAY takes the same path", src2 == SOURCE_FULL_SUBMISSION,
              str(src2))
        check("4e. and yields identical text", t2 == t1)
        check("4f. reaching no network", c2.urls == [], str(c2.urls))


# ============ 5. offline mode ============================================
def test_5_offline_refuses_rather_than_reaching_out() -> None:
    print("\n--- PART 5: offline ---")
    with tempfile.TemporaryDirectory() as td:
        cache = FilingCache(Path(td))
        c = FakeClient({"/Archives/": RAW_FILING}, cache=cache, offline=True)
        try:
            c.filing_text_with_source("927653", "missing-acc", "a.htm")
            check("5a. an offline miss raises", False, "it returned instead")
        except OfflineCacheMiss:
            check("5a. an offline miss raises OfflineCacheMiss", True)
        except Exception as e:
            check("5a. an offline miss raises OfflineCacheMiss", False,
                  type(e).__name__)
        check("5b. and reached no network", c.urls == [], str(c.urls))

    # offline with nothing to read from is a construction error, not a run
    # that quietly behaves like a normal online client.
    try:
        FakeClient({}, offline=True)
        check("5c. offline without a cache is refused", False, "it constructed")
    except ValueError:
        check("5c. offline without a cache is refused at construction", True)

    # CONTROL: the same client, online, does fetch. Without this, 5a/5b would
    # pass for a client that is simply broken.
    with tempfile.TemporaryDirectory() as td:
        c2 = FakeClient({"/Archives/": RAW_FILING},
                        cache=FilingCache(Path(td)), offline=False)
        got, _ = c2.filing_text_with_source("927653", "acc", "a.htm")
        check("5d. CONTROL -- the same client online does fetch",
              "Rite Aid" in got and c2.urls != [], str(c2.urls))


# ============ 6. a damaged entry is a miss, never partial data ===========
def test_6_a_damaged_entry_is_a_miss() -> None:
    print("\n--- PART 6: damaged entries ---")
    with tempfile.TemporaryDirectory() as td:
        cache = FilingCache(Path(td))
        url = "https://www.sec.gov/Archives/x.htm"
        cache.put(url, CACHE_KIND_TEXT, 200, RAW_FILING)
        check("6a. stored", cache.get(url, CACHE_KIND_TEXT) is not None)

        # wrong kind -- a JSON reader must not be handed a text body
        check("6b. a kind mismatch is a miss",
              cache.get(url, CACHE_KIND_JSON) is None)

        # version bump
        f = cache._path(url)
        with gzip.open(f, "rt", encoding="utf-8") as fh:
            rec = json.load(fh)
        rec["v"] = CACHE_FORMAT_VERSION + 1
        with gzip.open(f, "wt", encoding="utf-8") as fh:
            json.dump(rec, fh)
        check("6c. a version mismatch is a miss",
              cache.get(url, CACHE_KIND_TEXT) is None)

        # truncation -- the realistic corruption, from an interrupted walk
        f.write_bytes(f.read_bytes()[:20])
        check("6d. a truncated entry is a miss, not a crash",
              cache.get(url, CACHE_KIND_TEXT) is None)

        # and a miss means the client falls through to the transport
        c = FakeClient({"/Archives/": RAW_FILING}, cache=cache)
        got, _ = c.filing_text_with_source("927653", "acc", "x.htm")
        check("6e. so the client refetches rather than serving nothing",
              "Rite Aid" in got)


def test_7_a_transport_error_without_a_status_is_not_cached() -> None:
    """A timeout says nothing about the filing. Caching it makes it permanent."""
    print("\n--- PART 7: what must NOT be stored ---")

    class Flaky(FakeClient):
        def _get(self, url: str, timeout: int = 30):
            self.urls.append(url)
            raise TimeoutError("connection timed out")

    with tempfile.TemporaryDirectory() as td:
        cache = FilingCache(Path(td))
        c = Flaky({}, cache=cache)
        try:
            c.filing_text_with_source("927653", "acc", "a.htm")
        except Exception:
            pass
        check("7a. nothing was written for a status-less failure",
              cache.writes == 0, str(cache.stats()))
        check("7b. and no file exists on disk",
              list(Path(td).rglob("*.json.gz")) == [], "an entry was created")

    # A TRANSIENT status is not definitive either, and this is the case that
    # was actually wrong. 503 is in TRANSIENT_STATUSES -- the module already
    # treats it as retryable -- so caching one contradicts that contract and
    # makes a passing server hiccup permanent for every future replay.
    #
    # Found in production, not in review: the 2026-08-28 full-frame walk hit
    # exactly two 503s and cached both. The original version of THIS test used
    # 500 as its "definite status" control, and 500 is itself transient, so the
    # control was pinning the bug instead of catching it.
    with tempfile.TemporaryDirectory() as td:
        cache = FilingCache(Path(td))
        c = FakeClient({"a.htm": 503, ".txt": 503}, cache=cache)
        try:
            c.filing_text_with_source("927653", "acc", "a.htm")
        except Exception:
            pass
        check("7c. a TRANSIENT 503 is NOT cached -- it stays retryable",
              cache.writes == 0, str(cache.stats()))
        check("7d. and leaves no entry on disk",
              list(Path(td).rglob("*.json.gz")) == [], "an entry was created")

    # CONTROL: a genuinely definitive status IS stored, so the checks above are
    # about WHICH statuses are definitive and not about the cache being inert
    # on every error path. 404 is the one that matters -- it drives the
    # full-submission fallback for the 2000-2001 filings.
    with tempfile.TemporaryDirectory() as td:
        cache = FilingCache(Path(td))
        c = FakeClient({"a.htm": 404, ".txt": 404}, cache=cache)
        try:
            c.filing_text_with_source("927653", "acc", "a.htm")
        except Exception:
            pass
        check("7e. CONTROL -- a DEFINITIVE 404 is stored",
              cache.writes >= 1, str(cache.stats()))


def test_8_readonly_serves_but_never_writes() -> None:
    print("\n--- PART 8: readonly ---")
    with tempfile.TemporaryDirectory() as td:
        warm = FilingCache(Path(td))
        c = FakeClient({"/Archives/": RAW_FILING}, cache=warm)
        c.filing_text_with_source("927653", "acc", "a.htm")
        n = len(list(Path(td).rglob("*.json.gz")))

        ro = FilingCache(Path(td), readonly=True)
        c2 = FakeClient({"/Archives/": RAW_FILING, "other": RAW_FILING},
                        cache=ro)
        got, _ = c2.filing_text_with_source("927653", "acc", "a.htm")
        check("8a. readonly still serves hits", "Rite Aid" in got
              and c2.urls == [], str(c2.urls))

        c3 = FakeClient({"/Archives/": RAW_FILING}, cache=ro)
        c3.filing_text_with_source("927653", "different-acc", "b.htm")
        check("8b. and a miss is fetched but NOT written",
              len(list(Path(td).rglob("*.json.gz"))) == n,
              "readonly wrote to disk")


def test_9_a_replay_produces_the_same_edges() -> None:
    """The claim the cache actually makes: replay == live, at the extractor.

    Every test above checks a mechanism. This one checks the thing those
    mechanisms exist to guarantee -- that measuring a gate against the cached
    corpus is measuring it against the real one.
    """
    print("\n--- PART 9: end-to-end equivalence ---")
    with tempfile.TemporaryDirectory() as td:
        cache = FilingCache(Path(td))
        routes = {"/Archives/": RAW_FILING}

        live_text, _ = FakeClient(routes, cache=cache).filing_text_with_source(
            "927653", "acc", "a.htm")
        replay_c = FakeClient(routes, cache=cache, offline=True)
        replay_text, _ = replay_c.filing_text_with_source("927653", "acc", "a.htm")

        live_edges, _ = extract_edges_from_text(
            live_text, ticker="MCK", cik="927653",
            filing_date="2001-06-01", accession="acc")
        replay_edges, _ = extract_edges_from_text(
            replay_text, ticker="MCK", cik="927653",
            filing_date="2001-06-01", accession="acc")

        live_names = sorted(e.named_counterparty for e in live_edges
                            if e.counterparty_is_named)
        replay_names = sorted(e.named_counterparty for e in replay_edges
                              if e.counterparty_is_named)
        check("9a. the live run found the counterparty",
              live_names == ["Rite Aid Corporation"], str(live_names))
        check("9b. the OFFLINE replay found exactly the same",
              replay_names == live_names, str(replay_names))
        check("9c. having reached no network at all",
              replay_c.urls == [] and replay_c.requests_made == 0,
              str(replay_c.urls))


def test_10_offline() -> None:
    try:
        socket.getaddrinfo("example.com", 443)
        check("10a. network blocked", False, "a lookup succeeded")
    except Exception as e:
        check("10a. network blocked", type(e).__name__ == "NetworkBlocked")


if __name__ == "__main__":
    test_1_no_cache_changes_nothing()
    test_2_a_hit_is_not_a_request()
    test_3_the_cache_stores_what_the_transport_returned()
    test_4_negative_results_are_cached_and_replayed()
    test_5_offline_refuses_rather_than_reaching_out()
    test_6_a_damaged_entry_is_a_miss()
    test_7_a_transport_error_without_a_status_is_not_cached()
    test_8_readonly_serves_but_never_writes()
    test_9_a_replay_produces_the_same_edges()
    test_10_offline()

    print()
    if SKIPS:
        print(f"{len(SKIPS)} SKIPPED (not counted as passes): {SKIPS}")
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("ALL HYP-04 EDGAR CACHE TESTS PASSED")
    sys.exit(0)

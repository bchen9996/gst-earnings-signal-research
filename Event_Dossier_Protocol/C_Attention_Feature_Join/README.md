# Layer C — Attention Feature Join

**Not populated, not scoped, not designed in this draft.** No GST, Wikipedia, IV, realized-volatility, price, or volume data has been fetched, inspected, or joined as part of creating this scaffold, per explicit instruction.

## Corrected capture-vs-reveal rule (2026-08-02)

Same correction as Layer B: the Phase 2 panel may continue collecting these features on its own independent schedule at all times — that collection is not gated on any single event's labeling status. What is gated is **reveal**: a Layer C feature value must not be shown to an event's Layer A labeler before that event's label is `human_frozen`, and a reviewer exposed early is disqualified from signing that event, same as for Layer B.

## Intended content (future work, under its own separately locked hypothesis protocol)

- GST attention-index values
- Wikipedia pageview values
- Implied volatility
- Realized volatility
- Price and volume features
- Other locked panel variables

## Relationship to the existing Phase 2 panel

The six locked research fields (`gst_zscore`, `wiki_zscore`, `implied_volatility`, `realized_vol`, `price`, `volume`) and their completion-gate contract already exist and are locked on the `phase2-wikipedia-reliability` branch (`GST_Phase2_DailyPanel.py`). The v0.1 confirmatory ticker universe (`../locked_universe_v0.1.json`) is copied verbatim from that same file's `TICKERS` constant. This layer is expected to **reuse** both, not redefine them — no new field or ticker-universe definitions are invented here.

## Hard gate

An event may only enter Layer C **reveal** after: (1) its Layer A label is `human_frozen`, and (2) its Layer B addendum has been revealed under the same rule. Layer C *capture* (the panel simply running) is unaffected and may happen at any time. `development_pilot` and `compromised` events are never eligible for Layer C reveal/join at all — they exist only to test protocol/tooling, never to feed a hypothesis test.

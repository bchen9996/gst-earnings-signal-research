# Mechanism B Validation — Complete

Three approaches tested:

1. **8-K filing frequency** (`edgar_8k_signal.py`, `mechanism_b_validation.csv`) —
   precision at or below the 25.4% base rate across most tested thresholds.
   Not viable.

2. **Price/volume anomaly** (`price_volume_signal.py`, `mechanism_b_validation.csv`) —
   some real signal (precision above base rate at moderate-to-high
   thresholds), but weaker than GST at every comparable recall level.

3. **Profile-filtered validation** (`option3_profile_filtered_validation.csv`) —
   filtered to the false-negative profile (smaller-cap, Consumer
   Cyclical/Industrials/Financial Services/Basic Materials/Energy, low
   prior-quarter z). Local base rate was only 27.5% vs 25.4% global — not
   meaningfully above threshold. Step 2 (price/volume precision/recall
   within the profile) was not run, per the pre-registered stopping
   condition (local base rate < 30%).

## Conclusion

Free-data Mechanism B is not viable with current infrastructure. Paid
data would be required to make progress: options flow (Unusual Whales),
analyst estimate dispersion (Finnhub/Bloomberg), or earnings transcript
NLP (Seeking Alpha/Refinitiv).

This is a data availability constraint, not a methodology failure.

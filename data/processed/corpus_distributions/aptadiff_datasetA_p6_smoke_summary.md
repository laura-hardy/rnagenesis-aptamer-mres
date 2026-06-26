# Corpus distribution summary

**Created (UTC):** 2026-06-26T05:18:00.644179+00:00

## Input

- Input path: `/Users/laura/Desktop/rnagenesis-aptamer-mres/data/raw/Aptadiff_datasetA/datasetA_IGFBP3_P6.csv`
- Sequence column: `seq`
- DNA-to-RNA conversion: `True` (`T -> U`)
- Exclusion policy: retain only sequences with alphabet `{A, U, C, G}` after conversion
- Weighting: each sequence counted once; `p6` not used

## Counts

- Rows read: 100
- Non-empty sequences: 100
- Retained valid sequences: 100
- Excluded empty sequences: 0
- Excluded invalid-alphabet sequences: 0
- Unique retained sequences: 100
- Duplicate retained sequences: 0
- Invalid examples recorded: 0

## Mononucleotide frequencies

- A: 0.085833
- U: 0.310833
- C: 0.089167
- G: 0.514167

## Length summary

- Min: 36.000000
- Max: 36.000000
- Mean: 36.000000
- Median: 36.000000
- Q05: 36.000000
- Q95: 36.000000

## GC content summary

- Min: 0.388889
- Max: 0.750000
- Mean: 0.603333
- Median: 0.625000
- Q05: 0.472222
- Q95: 0.695833

## MFE

- MFE computed: `False`

## Notes

This artifact is based on the preliminary Aptadiff Dataset A P6 subset. It is intended for poster Stage 1 null-model calibration and will later be replaced by distributions estimated from the full curated aptamer corpus.

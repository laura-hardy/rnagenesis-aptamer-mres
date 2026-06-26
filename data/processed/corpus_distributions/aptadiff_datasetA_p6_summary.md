# Corpus distribution summary

**Created (UTC):** 2026-06-26T05:40:45.952531+00:00

## Input

- Input path: `/Users/laura/Desktop/rnagenesis-aptamer-mres/data/raw/Aptadiff_datasetA/datasetA_IGFBP3_P6.csv`
- Sequence column: `seq`
- DNA-to-RNA conversion: `True` (`T -> U`)
- Exclusion policy: retain only sequences with alphabet `{A, U, C, G}` after conversion
- Weighting: each sequence counted once; `p6` not used

## Counts

- Rows read: 13803
- Non-empty sequences: 13803
- Retained valid sequences: 13802
- Excluded empty sequences: 0
- Excluded invalid-alphabet sequences: 1
- Unique retained sequences: 13802
- Duplicate retained sequences: 0
- Invalid examples recorded: 1

## Mononucleotide frequencies

- A: 0.086789
- U: 0.296700
- C: 0.083997
- G: 0.532513

## Length summary

- Min: 36.000000
- Max: 36.000000
- Mean: 36.000000
- Median: 36.000000
- Q05: 36.000000
- Q95: 36.000000

## GC content summary

- Min: 0.305556
- Max: 0.805556
- Mean: 0.616511
- Median: 0.638889
- Q05: 0.472222
- Q95: 0.722222

## MFE

- MFE computed: `False`

## Notes

This artifact is based on the preliminary Aptadiff Dataset A P6 subset. It is intended for poster Stage 1 null-model calibration and will later be replaced by distributions estimated from the full curated aptamer corpus.

## Invalid examples

- Row 13261: invalid=N original=`CGCATTTGGGTTGGTTTGGACTGGTTTTGCTGTNTG` converted=`CGCAUUUGGGUUGGUUUGGACUGGUUUUGCUGUNUG`

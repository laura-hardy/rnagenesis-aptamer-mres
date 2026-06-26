# Null model generation summary

**Created (UTC):** 2026-06-26T05:50:02.555124+00:00

## Inputs

- Source distribution JSON: `/Users/laura/Desktop/rnagenesis-aptamer-mres/data/processed/corpus_distributions/aptadiff_datasetA_p6.json`
- Sequences requested: 100
- Seed: 42
- NumPy version: 1.26.4

## Reference distributions used

- Base frequencies: A=0.086789, U=0.296700, C=0.083997, G=0.532513
- Length histogram: `{'36': 13802}`

## Generated outputs

- Sequences generated: 100
- Duplicate count: 0

### Generated length summary

- Min: 36.000000
- Max: 36.000000
- Mean: 36.000000
- Median: 36.000000
- Q05: 36.000000
- Q95: 36.000000

### Generated GC summary

- Min: 0.416667
- Max: 0.833333
- Mean: 0.614444
- Median: 0.611111
- Q05: 0.472222
- Q95: 0.750000

### Generated mononucleotide frequencies

- A: 0.084722
- U: 0.300833
- C: 0.084722
- G: 0.529722

## Notes

This null model is calibrated to the empirical Aptadiff A length and mononucleotide distributions only. It is not structure-aware and does not impose GC, MFE, motif, or homopolymer constraints. Duplicate sequences are intentionally retained at generation time; exact deduplication belongs in Stage 1 filtering.

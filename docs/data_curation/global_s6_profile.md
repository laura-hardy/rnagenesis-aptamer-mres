# Global S6 — pre-balancing corpus profile + CHECKPOINT-3 preparation

S6 profiles the frozen final S5 clustered corpus and stops for
supervisor review. It does not balance, apply a target cap, assign
FT/REF/EVAL, populate `partition`, drop rows, rewrite S4/S5, or start
S7.

```text
frozen final S5 corpus
  corpus_clustered_final.csv (1281 identities)
  clusters_final.tsv / cluster_summary_final.csv
  S5A membership + exact overlap provenance
        ->
aggregate profile + figures + CHECKPOINT-3 package
        ->
STOP. No modified corpus.
```

## Grain

The principal S6 grain is one S5 scientific identity = one exact
`(sequence_core, canonical_target_name)` relationship.

```text
records / identities = 1281
distinct sequence_core = 1144
final clusters         = 796
```

Donor `record_id` remains provenance and is not unique at this grain.

## Candidate cap analysis

The v1.4 plan requires S7 to apply `MAX_TARGET_FRACTION` at cluster
level, but it does not specify denominator, floor/ceiling, which whole
clusters are retained, multi-target cluster treatment, ordering, or
collateral removal of other-target identities. S6 therefore reports
diagnostic bounds only:

- nominal identity threshold = `floor(fraction * 1281)`;
- idealised record-wise capped size (not executable S7 output);
- cluster-union upper bound if every cluster touching an
  overrepresented target were removed.

C3-05 records the missing S7 rule. S6 does not invent a hidden
balancing algorithm.

## Bimodality

AptaDiff A/B do not enter this primary corpus. Length multimodality is
tested on the actual final S5 distinct-core lengths with a 1- vs
2-component Gaussian-mixture BIC comparison implemented in NumPy. A
lower BIC for two components is not mathematical proof of bimodality.

## Outputs

Ignored under `data/interim/deduplicated/`:

- `corpus_profile_report.md`
- `figure_pack_supervisor.md`
- `s6_profile/` machine-readable tables
- `s6_profile/source_length_regime_summary.csv`
- `figures/`
- `checkpoint3/checkpoint3_summary.md`
- `checkpoint3/checkpoint3_decisions.csv`
- `s6_profile_manifest.json`

The supervisor briefing is also written to
`docs/data_curation/corpus_profile_report_supervisor.md`.

Human decision fields in the CHECKPOINT-3 CSV are blank.

## Boundary

S6 does not create `corpus_final.csv`, does not populate `partition`,
and does not begin S7.

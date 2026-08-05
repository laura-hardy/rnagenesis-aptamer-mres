# Carbapenemase evaluation-reference resolution

## Purpose

This note records the final S0b resolution state for the carbapenemase
evaluation references used to construct leakage exclusions. It documents
authoritative machine-readable status without embedding aptamer sequences.

## Authoritative machine-readable source

The binding source for resolved evaluation-reference status is:

`data/raw/evaluation_references/carbapenemase_reference_additions_and_overrides.csv`

That CSV contains eight records: seven sequence-level records and one
dataset-level record. All eight records are resolved; none remain pending
sequence extraction.

## Supplementary evidence resolved

- Sabrowski Supplementary Table S2 resolved `NDM1-H14.2_43`.
- Shi Supporting Table S1 established that the KPC-2 KP sequence is XK10.
- Chen and Shi are therefore duplicate/application provenance for the XK10
  sequence family rather than independent selected aptamers.
- The pending-reference count is zero.

Supporting PDFs under `data/raw/evaluation_references/source_documents/` provide
the supplementary evidence used for that resolution. They are documentation
only and are not registered as sequence-table inputs.

## Leakage-set interpretation

- All seven D9 RNA clones are excluded.
- Positive, weak-binding, non-binding and methodological controls are excluded.
- DNA/RNA T/U equivalents are matched through a comparison representation.
- Full and core forms are retained where available.
- PRJNA830749 is dataset-level metadata and not a sequence row.
- 32 unique sequence exclusions were produced.
- Target aliases provide target-level protection in addition to sequence-level
  matching.

## Provenance note

The raw README under `data/raw/evaluation_references/` was prepared before the
supplementary extraction was completed and may retain historical “pending”
wording. The authoritative resolved status is the additions-and-overrides CSV,
the supplementary source documents and the generated S0b manifest.

## Remaining limitations

- The evaluation set includes DNA and RNA references with distinct roles.
- Duplicate provenance does not constitute independent selection evidence.
- S0 leakage controls do not themselves establish binding evidence for future
  corpus records.

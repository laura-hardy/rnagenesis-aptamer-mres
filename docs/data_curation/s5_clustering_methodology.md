# S5 clustering methodology

Thesis-methods note for leakage-safe S5 clustering. No biological
sequences. S4 and S5A scientific decisions are not reopened.

## Original plan

The v1.3 plan clustered the exact-deduplicated primary corpus at 90%
identity:

```text
mmseqs easy-cluster --min-seq-id 0.9 -c 0.8 --cov-mode 1 -s 7.5
```

It treated ENA `near_duplicate_family_id` as free clustering ground
truth: real multi-member families should not split, and materialised
singletons should stay singletons. If recall was poor, the authorised
fallback was `cd-hit-est -c 0.9 -n 8`.

The downstream purpose of `cluster_id` is leakage-safe balancing and
partitioning: related sequence families must not be split across FT /
REF / EVAL or later train/validation cuts.

## MMseqs S5C result

S5C clustered 1144 unique `sequence_core` values and broadcast
membership onto all 1281 scientific identities. It did not change S4
or S5A.

```text
MMseqs clusters          = 813
singleton clusters       = 651
multi-sequence clusters  = 162
largest cluster           = 36
1144 sequences → 813 clusters
```

Stable `S5C_` IDs are membership-derived SHA-256 values, independent
of native MMseqs labels. This frozen result is `sequence_cluster_id_mmseqs`.
S5C did not adjudicate ENA recall and did not run CD-HIT.

Of 16 retained multi-member S5 ENA families, 8 were contained in one
MMseqs cluster and 8 were split.

## S5D CD-HIT fallback

S5D kept the MMseqs candidate unchanged and ran the prespecified
fallback:

```text
cd-hit-est -c 0.9 -n 8 -T 1 -d 0
```

CD-HIT produced 791 clusters and contained 11/16 families. It joined
reverse-complement pairs that MMseqs left split, using default both-strand
search and shorter-sequence identity, not global 90% Levenshtein.

CD-HIT still split five families. Independently, several families are
disconnected under the project's global-Levenshtein 0.90 definition
because the source classifier includes reverse complements and
truncation/substring edges. No parameter was retuned. CD-HIT is not
selected for v1 final clustering.

## Audit of ENA family construction

Repository evidence is `scripts/data_preparation/ena_review_rules.py`
(`assign_near_duplicate_families`, `classify_sequence_relationship`).
Families were **not** built at a 90% MMseqs/CD-HIT identity threshold.

1. Comparison is only within `(experiment_group_id, target_key)`.
   Different experiments or targets were never compared.
2. Pairwise edges form union-find connected components. Transitivity
   is used. Families are not all-pairs identity sets.
3. Edge classes include exact duplicate, reverse complement, equal-length
   Hamming ≈95%, substring/truncation (≥50% length ratio), and relative
   edit ≤0.08.
4. Differing lengths are permitted.
5. Multi-member components receive `ndfam_*` IDs. Source-blank
   singletons are materialised as `ena_singleton_{review_unit_id}`.
   Blank means “no multi-member family under that algorithm”, not
   “unknown” and not “globally sequence-isolated”.

## Contradiction identified

The previous S5D decision was:

```text
NO-GO — GROUND-TRUTH / 90%-RULE CONTRADICTION
```

That decision is historically correct **if** ENA families are required
to be both (a) wholly contained and (b) a complete positive-and-negative
global 90%-identity reference. Those two requirements cannot hold together:

- an ENA singleton is not proof of global isolation;
- different family IDs may be ≥90% similar once compared corpus-wide;
- some valid ENA families are intrinsically incompatible with a global
  90% same-strand identity / coverage rule (reverse orientation,
  truncation, family transitivity).

Neither prespecified tool can satisfy the old joint rule without
forbidden parameter changes.

## Final positive-must-link interpretation

S5E resolves the contradiction by changing the **interpretation**, not
the MMseqs parameters and not the scientific identity table.

ENA real multi-member family IDs are **positive must-link constraints**.
They are not:

- the definition of sequence identity;
- negative/cannot-link constraints;
- proof that different family IDs must occupy different clusters.

Therefore:

- different ENA family IDs may merge under corpus-wide MMseqs similarity;
- materialised singleton IDs may cluster with other sequences;
- cross-family MMseqs clusters are not validation failures merely because
  family IDs differ.

Required validation is positive recall only: every retained multi-member
ENA family with ≥2 S5 sequence cores must occupy one final cluster.

## Why this is safer for leakage prevention

Balancing and partitioning must not split near-duplicate or
experimentally related sequences. The safest grouping is the
connected component over:

```text
MMseqs similarity-cluster membership
UNION
trusted source-family must-links
```

This keeps every corpus-wide 90%-similarity group together **and** every
known retained ENA experimental family together, including reverse
orientation, truncation, and transitive family edges that MMseqs
cannot represent. Scientific `(sequence, target)` identities are not
merged or removed. Multi-target sequences remain multiple identities and
share one leakage-safe cluster.

## Why singleton / cross-family IDs cannot serve as negative ground truth

Family construction never compared different source buckets. A
materialised singleton therefore cannot be used as a cannot-link
against the rest of the corpus. Cross-family MMseqs joins can be
genuine ≥90% similarities that the original within-bucket grouping
never tested. Reporting those joins is descriptive, not a failure.

## Why MMseqs is retained as the base rather than CD-HIT

MMseqs is the planned corpus-wide 90%-identity sequence clustering
method, with frozen parameters and a validated RNA/U preflight. CD-HIT
was a diagnostic fallback after apparent poor ENA recall. It did not
remove the semantic contradiction, it is a different identity/coverage
definition, and promoting it would replace the authorised sequence-similarity
grouping rather than adding the missing family must-links. S5E therefore
unions MMseqs components; it does not rerun MMseqs and does not use
CD-HIT clusters as the base.

Final `cluster_id` is membership-derived from the unioned component.
Un-unioned finals keep the frozen MMseqs `S5C_` identity. The MMseqs
candidate files remain frozen and unread-write.

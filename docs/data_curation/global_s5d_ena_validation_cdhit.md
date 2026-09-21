# Global S5D — ENA cluster validation + CD-HIT fallback

**Status (2026-09-17):** S5D's NO-GO for treating ENA families as complete 90%
ground truth remains historically correct. S5E supersedes the
*interpretation* of that result: ENA families are positive must-links, not
negative ground truth. MMseqs remains the base method. CD-HIT is not
selected. See `global_s5e_final_clustering.md` and
`s5_clustering_methodology.md`.

S5D keeps the frozen MMseqs S5C candidate unchanged, audits how ENA
`near_duplicate_family_id` was built, characterises the 16-family
recall failure, and runs the plan-authorised CD-HIT fallback. It does
not change the 90% identity threshold, tune clustering parameters,
merge or split families by hand, begin S6/S7, or overwrite S5A/S5C
artefacts.

```text
frozen S5A corpus_dedup.csv (1281 identities, 1144 cores)
frozen S5C MMseqs candidate (813 clusters)
        ->
ENA family-methodology audit (read-only)
MMseqs failure characterisation + pairwise diagnostics
cd-hit-est -c 0.9 -n 8 -T 1 -d 0
        ->
same ENA validation
method comparison
        ->
NO-GO for final S5 clustering
(ground-truth / 90%-rule contradiction)
```

## Decision

S5D **execution succeeded**. A **final clustering method is not
accepted**.

```text
decision = NO-GO — GROUND-TRUTH / 90%-RULE CONTRADICTION
case     = D
```

CD-HIT improved family containment from 8/16 to 11/16 but still
splits five families. Independently, six of the 16 families are
disconnected under global Levenshtein identity at 0.90, because the
ENA source classifier groups reverse complements, truncations, and
substrings. Those families cannot be recovered by a 90% same-strand
global-identity rule without violating that rule. No `*_final`
artefacts or overlap report were written.

## Integrity

HEAD and `origin/main` remain `bdc1df1b170eaac37a909a701e07c62377acfffd`
on `main`. `git ls-files data` is empty. Recalculated S4, S5A, and S5C
candidate hashes matched the freeze. `corpus_dedup.csv` was not
overwritten.

## ENA family-methodology audit

Repository evidence for `near_duplicate_family_id` is in
`scripts/data_preparation/ena_review_rules.py`
(`assign_near_duplicate_families`, `classify_sequence_relationship`)
and `scripts/data_preparation/README_ena_review.md`. Families were
**not** built at a 90% MMseqs/CD-HIT identity threshold.

Construction, from that code:

1. Only concrete A/C/G/U sequences participate.
2. Comparison is **within** `(experiment_group_id, target_key)` only.
   Target identity contributes; sequences from different experiments
   or targets are never compared.
3. Pairwise edges are union-find **connected components** (transitivity
   is used).
4. Pairwise relationship classes:
   - exact duplicate;
   - reverse complement;
   - equal-length Hamming ≤ `max(2, ceil(0.05 × L))` (about 95% identity);
   - substring/truncation when the shorter sequence is ≥15 nt, is
     contained in the longer sequence, and is ≥50% of the longer
     length;
   - otherwise edit / max length ≤ 0.08.
5. Multi-member components receive `ndfam_` + SHA-1 prefix IDs.
   Singletons are left blank at source; S1 materialises
   `ena_singleton_{review_unit_id}` with size 1. Blank therefore means
   “no multi-member family under that algorithm”, not “unknown”.
6. `near_duplicate_family_size` is the component member count.
   Differing lengths are allowed (truncation/substring/extension).
7. Sequences are not merged; family IDs are provenance for later
   validation.

The governing plan still treats these labels as the S5 validation
reference. They are sequence-similarity families, but they are
**incompatible with a 90% same-strand global-identity clustering
rule** because they deliberately include reverse complements,
truncations down to 50% length ratio, 8% relative edit, and
transitivity.

S5 membership `experiment_group_id` is blank for all 237 ENA rows, so
live family reports cannot recover the original experiment-group
bucket from that table. Canonical targets are present. Families were
not regenerated.

## MMseqs candidate (frozen)

```text
unique sequence_core input = 1144
MMseqs clusters            = 813
singleton clusters         = 651
multi-sequence clusters    = 162
largest cluster            = 36
scientific identities      = 1281
```

Parameters unchanged: `--min-seq-id 0.9 -c 0.8 --cov-mode 1 -s 7.5 --threads 1`.

### Sixteen-family containment

```text
families total                 = 16
families wholly contained      = 8
family containment rate        = 0.50
contained-family cores         = 59
split-family cores             = 82
total cores in the 16 families = 141
```

Verified, not hardcoded. One additional declared multi-member family
has only one S5 member (out-of-S5/E5 members are not counted as an S5
split).

### Split / contained families (sequence-safe)

MMseqs splits (8):

| Family | Cores | Partition | Lengths | Targets | ≥90% Levenshtein | Source classifier |
|---|---:|---|---|---|---|---|
| `ndfam_015c802be3` | 2 | 2 → 1+1 | 38 equal | PAP | disconnected | reverse complement |
| `ndfam_0593c5e896` | 2 | 2 → 1+1 | 31 equal | PAP | disconnected | reverse complement |
| `ndfam_18e0fe415b` | 2 | 2 → 1+1 | 23–37 | RF1 | disconnected | internal substring |
| `ndfam_24ea338bac` | 6 | 6 → 5+1 | 40 equal | NGF | connected, not all-pairs | Hamming variants |
| `ndfam_34079d351d` | 11 | 11 → 4+2+2+1+1+1 | 44–46 | NGF | all-pairs ≥0.90 | Hamming / small edit |
| `ndfam_94e9c2a26b` | 11 | 11 → 6+4+1 | 39–40 | NGF | connected, not all-pairs | Hamming / small edit |
| `ndfam_e51f65c5e5` | 46 | 46 → 33+5+3+2+1+1+1 | 40–42 | NGF | connected, not all-pairs | Hamming + substring |
| `ndfam_e86042d956` | 2 | 2 → 1+1 | 37 equal | PAP | disconnected | reverse complement |

MMseqs contained (8): `ndfam_1ed5e36a9d` (9), `ndfam_2efe30c22f` (2),
`ndfam_4d17f922d8` (3), `ndfam_ba567934ca` (3), `ndfam_e09d7c30e2` (2),
`ndfam_e94829466b` (2), `ndfam_f73502061c` (7), `ndfam_fa8cf96e7e` (31).

Two contained families (`ndfam_1ed5e36a9d`, `ndfam_fa8cf96e7e`) are
still disconnected at 0.90 global Levenshtein because they include
prefix/suffix truncation. MMseqs local alignment / coverage can join
them without satisfying global 90% identity.

### Causes of splitting, where alignments exist

Pairwise MMseqs search used `easy-search --search-type 3 --prefilter-mode 2`
on the 16-family cores only. It is diagnostic, not a clustering
algorithm.

- Reverse-complement families: global Levenshtein (same strand) is
  far below 0.90; exhaustive MMseqs pairwise can still report high
  local identity. MMseqs clustering did not join them. CD-HIT-EST
  default `-r 1` does both strands and did join them.
- Truncation/substring families: source definition allows ≥50%
  length ratio; global identity is then below 0.90. Coverage
  (`cov-mode 1`, 0.8) also rejects some joins.
- `ndfam_34079d351d` is all-pairs ≥0.90 under global Levenshtein
  but MMseqs still split it (coverage / greedy representative
  behaviour).
- `ndfam_e51f65c5e5` and Hamming series are connected at 0.90 but
  not all-pairs; greedy clustering plus coverage splits the chain.

### Singleton-family separation (96 materialised singletons)

ENA-internal grain, not whole-corpus grain:

```text
isolated from every other ENA core                         = 83
cluster with another materialised singleton                = 10
cluster with a real multi-member ENA family                =  2
cluster only with non-ENA sequences                        =  1
ENA-internal conflicts                                     = 12
of those, documented target-scope (source never compared)  =  1
```

Non-ENA neighbours are not an ENA-internal failure. Eleven of the
twelve ENA-internal co-clusterings have the same canonical target in
S5 membership and could not be attributed to experiment-group
scoping because that field is blank at S5 membership grain. They
may be genuine ≥90% similarities the original within-bucket grouping
missed, or core-trim changes; they were not used to retune clustering.

### Cross-family merges (MMseqs)

```text
clusters containing >1 ENA family                         = 8
clusters combining distinct real ENA families             = 5
clusters mixing real families + materialised singletons   = 2
clusters mixing multiple materialised singletons          = 3
```

## CD-HIT environment / U handling

```text
installation = Homebrew tap brewsci/bio, formula cd-hit 4.8.1_2
path         = /opt/homebrew/bin/cd-hit-est
version      = CD-HIT 4.8.1 (built on Feb 28 2019)
```

Native A/C/G/U preflight: identical U sequences clustered,
near-identical U sequences clustered, U vs T clustered, mixed T/U
clustered, distant sequence separate. **Comparison-only U→T was not
used.** Authoritative `sequence_core` FASTA is byte-identical to the
S5C freeze.

Documented identity semantics from installed help:

> global sequence identity = number of identical bases in alignment
> divided by the full length of the shorter sequence

Default CD-HIT-EST also does `+/+` and `+/-` alignments (`-r 1`).
That flag was not added or removed; the plan command was tested as
written, plus execution-only `-T 1` and `-d 0`.

## CD-HIT command

```text
/opt/homebrew/bin/cd-hit-est \
  -i data/interim/deduplicated/s5d_cdhit/sequence_clustering_input.fasta \
  -o data/interim/deduplicated/s5d_cdhit/cdhit_output.fasta \
  -c 0.9 -n 8 -T 1 -d 0
```

`-T 1` is single-thread determinism. `-d 0` keeps full `S5SEQ_*`
identifiers in `.clstr`. No `-aS`, `-aL`, alternate word size,
length cutoff, or identity other than 0.9.

## CD-HIT cluster results

```text
input unique cores                 = 1144
clusters                           = 791
singleton clusters                 = 612
multi-sequence clusters            = 179
largest cluster                    = 44
scientific identities              = 1281
missing cluster_id                 = 0
unique scientific_identity_id      = 1281
all cores assigned exactly once    = yes
shared cores (118) share cluster   = yes
scientific representatives         = 791 (one per cluster)
```

Sizes: 1=612, 2=116, 3=44, 4=9, 5=5, 6=1, 7=1, 9=1, 41=1, 44=1.
Two identical runs: identical membership, stable `S5C_` IDs, and
representative assignment. No scientific identity was removed.

## CD-HIT ENA validation (same 16 families)

```text
families wholly contained      = 11
family containment rate        = 0.6875
contained-family cores         = 60 / 141
split-family cores             = 81
```

Still split (5): `ndfam_24ea338bac` (6 → 3+1+1+1),
`ndfam_34079d351d` (11 → 9+2; all-pairs ≥0.90),
`ndfam_94e9c2a26b` (11 → 3+3+2+2+1),
`ndfam_e51f65c5e5` (46 → 44+1+1),
`ndfam_f73502061c` (7 → 5+2; MMseqs had contained this family).

CD-HIT newly contained the three reverse-complement pairs and the
RF1 substring pair, using strand and shorter-sequence identity, not
global 90% Levenshtein.

Singletons (96): isolated 77; with another singleton 13; with a real
family 2; only with non-ENA 4; ENA-internal conflicts 15.

Cross-family clusters: 10 (4 combining distinct real families).

## Method comparison

| Metric | MMseqs | CD-HIT |
|---|---:|---:|
| total clusters | 813 | 791 |
| singleton clusters | 651 | 612 |
| multi-sequence clusters | 162 | 179 |
| largest cluster | 36 | 44 |
| 16 ENA families wholly contained | 8 | 11 |
| ENA family containment rate | 0.50 | 0.6875 |
| member-weighted contained-family cores | 59/141 | 60/141 |
| materialised ENA singleton ENA-internal separation | 0.875 | 0.844 |
| clusters combining distinct ENA families | 8 | 10 |
| all 1144 cores assigned | yes | yes |
| deterministic rerun | yes | yes |

## Final clustering decision

**`NO-GO — GROUND-TRUTH / 90%-RULE CONTRADICTION`**

The plan requires both (a) 90% identity clustering and (b) ENA
families wholly contained. Six of the 16 S5 multi-member families
are disconnected at 0.90 under the project's global-Levenshtein
definition because the source classifier uses reverse complements
and truncation/substring edges. Neither prespecified tool can
satisfy both rules at once without parameter changes, which S5D
refuses. CD-HIT was still run as the documented fallback experiment
and is not promoted.

No third clustering algorithm was invented. MMseqs was not selected
because it ran first.

## Final outputs

None. No `clusters_final.tsv`, `corpus_clustered_final.csv`,
`cluster_summary_final.csv`, `s5_final_clustering_manifest.json`, or
`overlap_report.md`.

Ignored CD-HIT candidate outputs live under
`data/interim/deduplicated/s5d_cdhit/`. S5C MMseqs files are
unchanged.

## Tests / determinism

```text
S5D synthetic tests = 21 passed
S5C regression      = 24 passed
S5A regression      = 21 passed
S5B regression      = 17 passed
total               = 83 passed
CD-HIT live rerun   = identical membership, stable IDs, representatives
```

## Boundary

- S4 / S5A science unchanged
- MMseqs candidate preserved
- no threshold tuning
- no manual family merges/splits
- no scientific identities removed
- no balancing, S6, FT/REF/EVAL, or train/val split
- no commit / push
- no data tracked

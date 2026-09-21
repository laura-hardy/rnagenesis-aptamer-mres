# CHECKPOINT-3 supervisor decisions — 2026-09-21

## Status and authority

CHECKPOINT-3 supervisor consultation is complete. This decision record is
the authority for finalisation work after the frozen S6 pre-balancing profile.
It records decisions only: it does not alter S4/S5/S6 outputs, corpus
membership, clusters, or partitions. S7 has **not** yet run.

### Inputs mapped by this record

- `docs/data_curation/corpus_profile_report_supervisor.md` — supervisor
  briefing, especially the decision table, C3-01 to C3-05, sequence profile,
  clustering notes, and next steps.
- `docs/data_curation/rna_aptamer_corpus_curation_plan.md` — v1.4 plan,
  especially §§1.1, 2.3, 2.6, 2.8, 8, 15, and 18.
- `Corpus curation and splitting decisions 21.docx` — written advice from
  Amin and Ian, followed by the combined decisions.

The briefing's baseline is 1,281 scientific identities, 1,144 sequence
cores, 796 leakage-safe clusters, and 411 canonical protein targets. The
decisions below supersede the plan's deferred CHECKPOINT-3 placeholders where
they conflict, including the previous default `MAX_TARGET_FRACTION = 0.05`.

## Decision summary

| ID | Final combined decision | Implementation status |
| --- | --- | --- |
| C3-01 | Cap each target at **3%** of the post-cap identity denominator. | Approved; not applied. |
| C3-02 | No additional target-family balancing. Use target representation, evidence level, sequence-length regime, and source to make FT/REF/EVAL broadly comparable; use known family labels only as a secondary check. | Approved; not applied. |
| C3-03 | Retain E2–E4; keep E5 excluded for finalisation. Quantify the E5 parked population and the consequences of inclusion in the S7 report. | Approved; not applied. |
| C3-04 | Retain the protein-only primary corpus; keep non-protein records parked. | Approved; not applied. |
| C3-05 | Apply Amin's deterministic whole-cluster removal rule, stated operationally below. | Approved; not applied. |

## C3-01 — maximum target share

**Report finding/context.** The briefing's C3-01 table presents 2%, 3%, 5%
and 10% options. NGF is 131/1,281 identities (10.23%); it is the only target
above 3%, while the next-largest target is 34 identities (2.65%). At 3%, the
idealised record-wise diagnostic has a nominal threshold of 38 identities and
93 excess identities. These figures are decision support, not executable S7
results, because whole clusters must be retained or removed.

**Amin's advice.** Use a 5% maximum target share: reduce NGF's clear
over-representation without unnecessarily removing data from smaller targets;
do not use 2%, and implement any cap at cluster level.

**Ian's advice.** Restrict the 10%-share target to 3% or just above the rest
of the observed distribution; he also highlighted the 89- and 19-sequence
clusters.

**Final combined decision.** The combined response says to follow Ian as the
biological-domain expert. The final cap is therefore **3%**, not 5%. This
records the apparent tension explicitly: the source wording offers “3% or
just above” the rest of the distribution, but the combined instruction to
follow Ian is operationalised as the stated 3% option. Do not silently revert
to Amin's 5% recommendation. Any later departure from 3% requires a new,
explicit recorded decision.

## C3-02 — balancing and split stratification

**Report finding/context.** The planned family-stratified split is weak:
1,097/1,281 identities (85.64%) and 351/411 targets have
`target_family = unknown`. The briefing therefore identifies this as a
decision constraint, not a minor metadata caveat. It also reports two
sequence-length regimes centred near 39 and 77 nt.

**Amin's advice.** Do not add target-family balancing. When assigning intact
clusters to FT/REF/EVAL, keep target representation, evidence level,
sequence-length regime, and source broadly comparable. Treat known family
labels as a secondary check, not a hard stratification variable.

**Ian's advice.** Ignore target-family splitting for now; revisit it in the
future.

**Final combined decision.** No additional target-family balancing. Implement
Amin's stated comparability checks, with known target-family labels secondary
only. Preserve the two observed sequence-length regimes both when assigning
splits and when constructing null/reference distributions; do not approximate
the corpus by one unimodal length distribution. The report notes that the
length structure is partly source-associated, so source should be monitored
alongside length.

## C3-03 — evidence threshold and E5

**Report finding/context.** The retained corpus contains E2 803 (62.69%), E3
247 (19.28%), E4 231 (18.03%), and E5 0. The briefing states that E5 is
parked, has not been simulated for inclusion, and that the 796-cluster corpus
is above the plan's `<500`-cluster contingency for relaxing the threshold.
The plan defines E5 as a database/deposit target annotation without a
traceable assay.

**Amin's advice.** Retain the E2–E4 threshold and keep E5 excluded: there is
no compelling corpus-size reason to weaken the evidence standard.

**Ian's advice.** Quantify how many E5 records exist, explain what E5 means,
and report what inclusion would mean; for now he is content to keep E5
excluded.

**Final combined decision.** Keep E5 excluded for finalisation. The current
primary corpus has zero E5 identities. The S4 routing summary records 521
`park_evidence_e5` relationship records outside the primary corpus. Before or
with S7 reporting, quantify the eligible E5 population at the appropriate
record/relationship and post-dedup identity/cluster grains, and state the
effect that admission would have on corpus composition, evidence mix, and
split units. This is a required diagnostic, not authorisation to include E5.

## C3-04 — biological scope

**Report finding/context.** The briefing reports a protein-only primary
corpus. Adding separately parked non-protein records would change the
biological target mix and the thesis transfer framing.

**Amin's advice.** Keep the primary corpus protein-only, aligned with the
thesis scope and downstream protein target; leave non-protein records parked.

**Ian's advice.** Keep protein targets and do not add small molecules to the
RNA sequence clusters.

**Final combined decision.** Retain the protein-only primary corpus and keep
non-protein records parked.

## C3-05 — deterministic, whole-cluster cap implementation

**Report finding/context.** The briefing requires a cluster-level cap but
previously left the denominator, ranking, ties, mixed-target handling, and
collateral-removal treatment unspecified. Clusters are leakage-safe units;
the largest contains 89 identities and the next-largest contains 19, both
targeting NGF. The report states that post-cap size cannot be inferred from
record-wise simulations.

**Amin's advice.** Use the deterministic whole-cluster removal rule below.

**Ian's advice.** No independent preference; defer the rule to Amin.

**Final combined decision — required operational rule.** For every
overrepresented target:

1. Calculate the cap against the **post-cap final identity denominator**.
2. Never split a cluster.
3. Consider target-pure clusters first. Rank them by the number of identities
   belonging to the overrepresented target, descending.
4. Use mixed-target clusters only if target-pure removals are insufficient.
   Among feasible mixed-target removals, choose the option with the least
   collateral removal of identities belonging to other targets.
5. Break remaining ties by stable `cluster_id`.
6. After every cluster removal, recompute the final denominator and all target
   percentages. Continue until the 3% cap is satisfied.

The S7 implementation and report must make the exact removal trace auditable:
the current denominator, affected target counts and percentages, selected
cluster, target-purity/collateral rationale, and updated values after each
removal. It must not use a record-wise removal shortcut.

## Additional finalisation constraints

### Partition order and independence

- Freeze REF and EVAL before making fine-tuning or hyperparameter decisions.
- Create the train/validation split only within FT, at cluster level, after
  the FT/REF/EVAL assignment.
- Do not move clusters between partitions later to benefit fine-tuning or
  hyperparameter results. Any legitimate correction must be documented as a
  new split revision.

### Length and reference distributions

- Preserve the two observed sequence-length regimes in split construction.
- Preserve them when building null/reference distributions. Do not use a
  single unimodal length approximation.
- Record any source-associated length structure and the resulting treatment in
  the relevant split/reference-distribution documentation.

### Publication, redistribution, and leakage audit

- Do not publish sequence data from the corpus on GitHub or elsewhere
  publicly. This includes curated sequences, raw source sequences, sequence
  derivatives, and sequence-containing split artefacts.
- Public materials may contain aggregate statistics, provenance information,
  and reconstruction procedures only, subject to the existing data-handling
  policy.
- Add a pre-publication GitHub leakage audit to the curation/closure workflow.
  Before the repository is made public, audit tracked history and current
  tracked files for sequence data and other restricted data; document the
  result and remediation before publication.

## Required next work and boundary

The next implementation stage may apply the approved 3% cap using the C3-05
rule, validate the resulting post-cap corpus, assign intact clusters to
FT/REF/EVAL under C3-02, freeze REF/EVAL, and then create the FT-only
train/validation split. It must also produce the required E5 inclusion-impact
diagnostic while keeping E5 excluded.

This record does **not** authorise changes to S4/S5/S6 scientific outputs,
re-clustering, E5 inclusion, non-protein inclusion, public release of sequence
data, committing, or pushing.


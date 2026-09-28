# Planned Evaluation — Supervisor Review Request

**Project:** Prediction-Guided Generative Design of RNA Aptamers for AMR Diagnostics (MRes, Year 2)
**Prepared for:** Prof. Amin Beheshti
**Prepared by:** Laura Hardy
**Date:** 25 September 2026
**Source documents:** `aptarank_full_mres_thesis_evaluation_plan.md` (v2.3), `fine-tuning-implementation-plan.md` (rev. 25 Sep 2026), `rna_aptamer_corpus_curation_plan.md`, `docs/log.md`

---

## 1. What I am asking for

I am aiming to finish fine-tuning and generation by 2 October, which leaves roughly one week to execute the final evaluation and then the rest of October to write up before submission on 1 November. The evaluation plan is written and frozen, but it has not been executed, and this is the last point at which its scope can still be changed cheaply.

I would like your recommendation on four things:

1. **Scope.** Is this the right amount of evaluation for an MRes this close to submission — too much, too little, or the wrong balance between parts?
2. **Scientific defensibility.** Does the design support the claims I intend to make, and are the controls and uncertainty treatment adequate?
3. **Linkage to the methodological contribution.** Does the evaluation actually test what I am claiming to contribute, or does it test something adjacent to it?
4. **Feasibility.** Given the prerequisites and the rest of the October workload, can this be executed in the window available?

Sections 2 to 6 give the context needed to answer those without further background from me. Section 7 sets out the specific decisions where I would most value a recommendation.

---

## 2. The problem, in one page

An aptamer is a short single-stranded nucleic acid that folds into a three-dimensional shape and binds a protein target, functioning much like an antibody but synthesised chemically. They are conventionally discovered by SELEX, an iterative wet-lab selection process. The application motivating this thesis is diagnostics for antimicrobial resistance: detecting carbapenemase enzymes (KPC-2, NDM-1, OXA-48) that render last-line antibiotics ineffective.

The machine-learning problem has an awkward shape. There is no dataset of RNA aptamers against these targets at training scale — a handful of published references exist, and they are reserved for evaluation. So the model cannot learn a target-conditioned distribution `p(sequence | NDM-1)`. What it can learn is a *domain* prior: what experimentally supported RNA aptamers look like in general, across many protein targets. Target specificity then has to come from a separate downstream step that scores and ranks candidates against a particular protein structure.

That division produces the two methodological contributions the thesis rests on:

**(a) A leakage-controlled curated corpus and a small-data domain adaptation of a released RNA foundation model.** I built a corpus of experimentally supported RNA aptamer–protein pairs from multiple primary sources, partitioned it at *cluster* level into four functionally disjoint roles, and used it to adapt RNAGenesis — a latent-diffusion RNA generative model — from a generic RNA prior toward an aptamer-domain prior.

**(b) AptaRank, a two-tier computational prioritisation framework** for ranking generated candidates, which is the accepted ICDM 2026 demonstration paper and serves as the downstream application layer here.

The honest limit, which is stated as a claim boundary throughout the plans: the generator cannot be shown to have learned carbapenemase binding, and no result in this thesis constitutes evidence of binding, affinity, selectivity or biological activity. The strongest permitted generator-level conclusion is distributional — that adaptation moved generated sequences toward characteristics of held-out real aptamers while preserving validity, novelty and diversity.

---

## 3. What has been built and frozen

### 3.1 The corpus and its four roles

Curation ran as a gated pipeline (extraction, normalisation, constant-region trimming, per-source filtering, target normalisation, deduplication, MMseqs2 clustering at 90% identity, profiling, balancing, partition), with a supervisor checkpoint at the profiling stage. Inclusion required experimental evidence at level E2–E4 (a reported affinity constant, a named binding assay, or a published selection clone); bare database annotations (E5) are cleaned but parked. Modelling uses the trimmed random region (`sequence_core`), not the full construct, so the model does not learn T7 promoter and primer motifs as though they were binding motifs. Per-target share is capped at 3% by whole-cluster removal so no single well-studied target dominates. All carbapenemase and NDM-1 reference sequences were routed to a leakage exclusion set and never enter the corpus.

The current release closed on 25 September 2026 (commit `10aac629`) with 1,170 scientific identities, 1,031 unique sequence cores and 790 clusters, partitioned as:

| Role | Identities | Clusters | Unique cores | Targets | Permitted use |
|---|---:|---:|---:|---:|---|
| TRAIN | 726 | 569 | 669 | 320 | Fitting the generator only |
| VALIDATION | 132 | 63 | 95 | 100 | Checkpoint and development decisions only |
| REF | 131 | 79 | 113 | 97 | AptaRank calibration only |
| EVAL | 181 | 79 | 154 | 111 | One final held-out assessment only |

Partitioning at cluster level means near-duplicate SELEX families cannot straddle a boundary. Cross-role cluster leakage and core leakage are both zero. Each role file is hash-pinned, and the training loader fails closed if given a file with an unexpected hash or a role not authorised for fitting. EVAL is additionally kept physically off the training machine until the final milestone.

The point of the four-way split is that it removes a circularity that would otherwise make every result meaningless: if the same sequences fine-tuned the generator, calibrated the ranking tool's reference distributions, *and* served as positive controls, the fine-tuned generator would score well by construction and the positive control would pass trivially.

### 3.2 The adaptation

The released RNAGenesis autoencoder stack stays entirely frozen — encoder, Q-Former, latent projection and ProGen2-small decoder. Only the latent diffusion denoiser (a 24-layer transformer operating on a 32 × 160 latent, epsilon-prediction, ~7.4 GB) is trainable, initialised from the *generic* released diffusion checkpoint rather than the authors' already aptamer-adapted one.

The reasoning is small-data transfer learning: with 669 distinct training sequences, relearning a sequence representation or decoder is not viable, and holding the autoencoder fixed preserves the latent coordinate system the released diffusion model already operates in. Parameter-efficient alternatives (LoRA, partial unfreezing, Q-Former or decoder adaptation, target-conditioned diffusion) are deferred to the PhD — their absence is deliberate scope control, not a missing baseline.

The training regime is deliberately conservative for the data size: AdamW, learning rate 3e-5 (one permitted bounded fallback to 1e-5 if the pilot shows immediate overfitting), effective batch 32, 21 optimizer updates per epoch, maximum 5 epochs (105 updates), cosine schedule with 10% warmup, checkpoint every epoch, three independent training seeds targeted. Checkpoint selection uses a *fixed-draw* validation denoising loss — the timesteps and noise tensors are generated once and hashed, so differences between checkpoints are not Monte Carlo noise. There is no hyperparameter sweep.

### 3.3 The four generation conditions

| ID | Condition | Role in the argument |
|---|---|---|
| **D1** | MRes curated-aptamer diffusion-adapted RNAGenesis | The adapted model under test |
| **B1** | Generic released RNAGenesis | Primary controlled baseline — the *only* difference from D1 is my fine-tuning |
| **B2** | TRAIN-matched empirical i.i.d. RNA null | Non-neural floor: lengths and nucleotide frequencies matched to TRAIN, no learned structure |
| **B0** | Authors' released aptamer-adapted checkpoint | External comparator only; its existing 30,080-sequence pool used a 37-nt sampling regime, so it is not length-comparable |

**B1 versus D1 is the primary controlled comparison.** B2 bounds the bottom. B0 is reported separately and only with length-normalised or length-stratified metrics. Naming is fixed across code, figures and thesis text specifically so B0 is never described as "unadapted" — it has already been fine-tuned by its authors, and an earlier version of this project did briefly mislabel it that way.

Each condition is generated at 30,000 raw attempts, with attempted, parsed, valid and unique counts all retained separately so validity and duplicate rates have honest denominators. My current implementation generates 30,000 attempts *per training seed*, which for a three-seed D1 means 90,000 D1 attempts against 30,000 each for B1 and B2. Section 7.4 raises whether that is the right choice.

### 3.4 AptaRank

Tier 1 is a target-agnostic intrinsic-quality score with five components — normalised minimum free energy, ensemble defect, mean positional entropy (all favoured low), and stem fraction and GC fraction (two-sided around the REF median) — combined as an equally weighted mean of empirical-CDF percentiles fitted on REF. Each candidate also gets its own null: 99 dinucleotide-preserving shuffles of itself, with a pass at p ≤ 0.05. This composition-preserving per-candidate test is the stronger of the two nulls in the design.

Tier 2 is target-aware but explicitly not docking. An expert asserts the binding mode (pocket, detected with fpocket, or surface patch, measured with freeSASA), and the tool scores geometric compatibility between the candidate's predicted footprint and that site, reported as a percentile against a bank of shuffled controls in weak/moderate/strong bands. Tier 1 ranks; Tier 2 annotates. There is no composite Tier 1 + Tier 2 score, and no learned binding predictor anywhere in the pipeline.

---

## 4. How the modelling work is staged

The fine-tuning implementation plan divides all modelling work into eleven gated milestones. Each has defined inputs, required outputs and tests, a human review gate, and an explicit list of things that must *not* happen yet. The gates are the mechanism that keeps the data roles honest: M0 through M8 may touch only TRAIN and VALIDATION, REF stays sealed until M9B, and EVAL stays sealed until M10. I am including this because the later sections refer to these milestone numbers.

| Milestone | Purpose | Status today |
|---|---|---|
| **M0** | Verify the data, software, model and environment boundary: role hashes, model asset manifests, exact trainable-parameter count, environment and patch verification, proof REF and EVAL are absent from the training machine | **In progress** |
| **M1** | Reproduce known-working released inference so code integration is shown not to alter generation behaviour | **In progress** |
| **M2** | Verify the B0 comparator and the provenance of its existing 30,080-sequence pool | Not started |
| **M3** | Prove the frozen corpus enters the model without transformation or leakage: exact sequence counts, strict A/C/G/U assertion, no TRAIN/VALIDATION overlap, upstream random splitting disabled | Not started |
| **M4** | Freeze baselines and the validation protocol *before* any training: harden the B2 null generator and regenerate its pool, solve how requested length maps to actual output length for B1, fix the validation noise draws, the checkpoint-selection rule and the generated-sample guardrails | Not started |
| **M5** | Software smoke tests on synthetic data: frozen-parameter assertions, one forward and backward pass, save/reload/resume, peak memory and feasible microbatch | Not started |
| **M6** | Small real-data pilot to test the small-data regime, with one permitted bounded learning-rate repair | Not started |
| **M7** | Final D1 training across the three seeds, checkpoint selection by fixed-draw validation loss | Not started |
| **M8** | Full B1 and D1 generation and the development-time generator comparison against VALIDATION | Not started |
| **M9A** | **Generator freeze** — checkpoints, seed policy, generation settings, cleaning code, pools and the generator-evaluation code and metric list all immutable | Not started |
| **M9B / M9C** | AptaRank calibration on REF, then the end-to-end freeze of every analytical decision | Evaluation Day 1 |
| **M10** | The single final held-out assessment against EVAL | Evaluation Days 2–5 |

M9A is the boundary between modelling and evaluation, and it is the prerequisite the evaluation week assumes. It is substantially more than "training finished": it also requires the full generation pools to exist with manifests, **and** the generator-evaluation analysis code to be implemented, tested and frozen. That last item is a distinct stage of the pipeline that does not yet exist, and Section 5.2 describes it.

---

## 5. The planned evaluation

### 5.1 The freeze-and-unlock spine

Everything else depends on this. Rather than looking at EVAL and then deciding how to analyse it, every analytical choice is frozen first and EVAL is unlocked once. M9C in particular freezes the scoring equations, directions, weights, bands, target-screening algorithm and its time box, sample and shortlist sizes, and the statistical procedures — including a `generator_eval_metric_spec` table that names, for every metric, its exact statistic, its denominator, and which direction counts as "closer to EVAL".

This is the pre-registration analogue, and it is what makes a weak or null result reportable rather than embarrassing. After unlock, no metric may be added, no threshold adjusted, no seed chosen, and no pool regenerated.

### 5.2 A pipeline stage still to be built: the generator-evaluation suite

The evaluation as planned has a software prerequisite that I want to make explicit rather than leave implied, because it affects the timing judgement. The evaluation plan lists a frozen generator-evaluation suite among its prerequisites and among its ten completion blockers, and forbids building it during the evaluation week — the week's time is budgeted for running analyses, not writing them. **This code has not been written yet.** It is separate from the RNAGenesis training code, and it is the last substantial piece of software the project needs.

It has to take the frozen generation pools plus the held-out EVAL cores and produce, reproducibly and from hash-pinned inputs:

- output accounting per condition — attempted, parsed, valid A/C/G/U, unique valid, duplicate and invalid counts, with the metric-specific denominator for each downstream statistic;
- memorisation and novelty diagnostics — exact TRAIN overlap, normalised edit distance to the nearest TRAIN sequence, maximum identity to TRAIN;
- sequence distribution comparisons against EVAL — length, nucleotide fractions, GC, mono- and dinucleotide frequencies;
- structural and thermodynamic comparisons using pinned ViennaRNA — normalised MFE and paired fraction;
- diversity and mode-collapse summaries — sequence clustering at the project threshold, cluster count, singleton fraction, largest-cluster share, Shannon diversity and effective cluster count;
- seed-level summaries and the seed-aware bootstrap that preserves training- and generation-seed blocks;
- optionally, a frozen-representation distribution distance such as embedding MMD, which the plan already marks non-blocking if it would require new implementation.

It also has to be validated against synthetic fixtures before EVAL is ever touched, and it has to emit the `generator_eval_metric_spec` table described above so that each metric's direction is fixed before any result is seen.

The functionality is not research-novel and much of it is straightforward, but it is the code path that carries my primary held-out result — the one thing AptaRank explicitly cannot substitute for — so it needs to be correct and frozen before M9A rather than written in a hurry alongside the analysis. Realistically it competes for the same days as the 2 October block described in Section 6, which already carries fine-tuning, generation and thesis writing.

### 5.3 The evidence chain

**(1) Generator-level EVAL — the held-out test of the fine-tuning claim.** The frozen B1, B2 and D1 pools are compared against the 154 held-out EVAL cores using only pre-declared metrics, each labelled in advance as a *closeness* measure (distance to EVAL), a *guardrail* (validity, novelty, memorisation) or a descriptive *outcome*. Crucially, there is no aggregate "generator quality" score — each metric is reported individually, and if the directional metrics disagree the result is reported as *mixed*.

**(2) AptaRank Tier 1 on EVAL.** All valid unique EVAL cores, each paired with one exact-length uniform-random RNA control, uploaded blinded in one run with group and pair labels held outside the scoring engine. Outputs: full score distributions, paired real-minus-control differences, AUROC as a descriptive effect size against this synthetic null, shuffle-pass rates for both groups, and cluster-bootstrap confidence intervals (10,000 replicates, resampling whole sequence clusters with their paired controls).

**(3) AptaRank Tier 2 on EVAL.** A capped, score-blind cognate-versus-mismatch panel: does the score rank a sequence's known target above pre-specified mismatched proteins of the same binding mode? Targets are ordered by a cheap metadata count, then structurally screened in that fixed order inside a bounded time box, stopping at four valid same-mode targets (giving K=3 mismatches each), with a hard ceiling of six targets and 30 cognate relations. Metrics are per-relation concordance, cognate rank, strict top-1, and cognate-minus-median-mismatch, with cluster bootstrap intervals and an explicit target-concentration diagnostic.

**(4) Cross-tier.** Spearman correlation between the two tiers, interpreted strictly as *redundancy* — a low correlation means the tiers measure different things, which is the intended architecture, not a failure.

**(5) Downstream pipeline.** 200 candidates per condition through Tier 1 (B1/B2/D1 in one blinded 600-candidate upload; B0 separately), then the top 30 per condition through Tier 2 against each valid carbapenemase configuration — roughly 90 candidates per target job.

**(6) Final D1 shortlists** for each valid target, labelled as computationally prioritised candidates for future experimental validation, retaining full provenance per candidate.

**(7) Optional NDM-1 context.** A purely descriptive nucleotide-level comparison of the top-50 Tier-1-ranked D1 candidates against three independently verified published NDM-1 ssDNA aptamer references held outside all four corpus roles. Lowest priority; explicitly not validation.

Stages 1 and 5 are complementary, not interchangeable: stage 1 is the held-out evidence for fine-tuning, and AptaRank scores cannot substitute for it.

### 5.4 The five-day evaluation week

| Day | Critical path |
|---|---|
| 1 | Preflight; REF Tier 1 recalibration; Tier 2 scoring-basis decision (half-day cap); freeze everything; M9B/M9C records |
| 2 | EVAL unlock; blinded Tier 1 UI run; generator-vs-EVAL analysis launched locally in parallel; bounded Tier 2 target screen |
| 3 | Tier 2 EVAL runs; finalise generator, Tier 1, Tier 2 and cross-tier results |
| 4 | Generated-candidate Tier 1 for all conditions; freeze shortlists |
| 5 | Top-30 Tier 2 per target; final D1 shortlists; tables, figures, clean rerun, archive |

The plan names ten completion blockers and treats everything else as optional extensions that may only start once those ten are secure. A weak, null or mixed result counts as complete; a missing analysis does not.

### 5.5 What is deliberately excluded

No wet-lab work, no docking or molecular dynamics, no target-conditioned generation, no second fine-tuning strategy, no hyperparameter sweep, no B0 regeneration, no new representation model, and no expansion of the reference set. These are recorded as PhD extensions rather than gaps.

---

## 6. Planned timeline

These are the checkpoint dates I am working to. Several fall on weekends because they are targets for work to be *complete by*, not working days.

| By | Deliverables |
|---|---|
| **Fri 2 Oct** | Fine-tuning (M0–M8) and the 30,000-sequence generation pools complete; thesis methods chapter drafted; corrections applied to thesis chapters 1 and 2 |
| **Mon 5 Oct onward** | ICDM camera-ready evaluation work — 1 day of evaluation plus 0.5 days updating the paper. This runs under its own separate one-day workflow and is not covered by this document |
| **Sun 11 Oct** | All thesis evaluation work complete |
| **Mon 12 Oct** | ICDM poster prepared (0.5–1 day) |
| **Sun 18 Oct** | Results and conclusion chapters drafted |
| **Sat 31 Oct** | Final comments and revisions applied; abstract, acknowledgements and remaining sections added; administrative requirements completed, including co-author signatures on the publications form and AptaIndex data permissions |
| **Sun 1 Nov** | Submission |

### 6.1 Why the 2 October date is an aim rather than a forecast

I am aiming for 2 October because the rest of the schedule depends on it, not because I can predict it. I have not done fine-tuning before, so I do not have a reliable sense of how long M0 through M8 actually take. The block spans nine gated milestones on a shared GPU server, and today I am working through M0 and M1. Several remaining items have genuinely unknown duration: the encoder reconstruction still needs runtime verification, M4 has to resolve empirically how the released model's requested sequence length maps to actual cleaned output length before B1 can be length-matched, and the generator-evaluation suite in Section 5.2 has yet to be written. The same block also carries the methods chapter draft and corrections to chapters 1 and 2.

### 6.2 The arithmetic of the evaluation window

The evaluation plan is scoped as five working days. Against the checkpoints above, the days actually available between the end of fine-tuning and the 11 October target are:

| Date | Availability |
|---|---|
| Mon 5 Oct | ICDM camera-ready evaluation — unavailable |
| Tue 6 Oct | 0.5 day on the ICDM paper update; 0.5 day available |
| Wed 7 – Fri 9 Oct | 3 full days |
| Sat 10 – Sun 11 Oct | Weekend, if worked |

That is about 3.5 working days, or 5.5 including the weekend, against a plan that needs 5 — with no slack, and only if 2 October holds exactly. It also means the ICDM camera-ready work sits immediately before evaluation Day 1, which is the day that freezes every analytical decision for the whole week.

This is the part of the schedule I am least confident about, and it is the substance of question 7.5.

---

## 7. The decisions I would like a recommendation on

### 7.1 Scope — is this too much, too little, or misbalanced?

The evaluation currently carries four distinct evaluations (generator-level, Tier 1, Tier 2, downstream application) plus calibration, shortlists and archiving. My own view is that the generator-level EVAL is non-negotiable because it is the only held-out test of the fine-tuning contribution, and that if something has to go, the order I would cut is: the NDM-1 reference comparison first, then B0's Tier 1 panel, then reducing the Tier 2 panel from four targets to a smaller explicitly illustrative one. Does that priority order match yours, and would you rather I cut pre-emptively to protect the write-up than discover mid-week that I need to?

The opposite worry: at four targets and K=3, Tier 2 has very few independent clusters, so its confidence intervals may be wide or not estimable. Is a result that is honest but underpowered worth the share of the window the UI work costs, or is that effort better spent deepening the generator-level analysis, which is cheap to compute and more directly tied to my contribution?

### 7.2 Defensibility — five specific points

**Training scale versus claim.** 669 sequences and 105 optimizer updates is a very small adaptation. I think that is precisely why the claim is restricted to distributional shift with validity, novelty and memorisation guardrails, and why B2 is included as a floor. Does that framing hold up, or would an examiner expect a stronger demonstration than "the distribution moved"?

**Seeds.** Three training seeds are targeted but not guaranteed by GPU availability. With one seed, the plan requires me to state that uncertainty excludes training-run variability. Is one seed plus that explicit caveat acceptable for an MRes, or is it worth protecting three seeds even at the cost of scope elsewhere?

**Reporting "mixed".** Closeness to EVAL is a set of per-metric directional comparisons with no composite score, so a plausible outcome is that some metrics move toward EVAL and others do not, reported as mixed. I believe refusing to build a composite is the scientifically correct choice. Is a mixed headline result defensible in a results chapter, or does it read as an absent finding?

**The Tier 1 null.** The paired control is uniform-random RNA, which is a weak floor, and AUROC against it is reported as a descriptive effect size rather than classification performance. The stronger null is the per-candidate dinucleotide-preserving shuffle. Is that pairing sufficient, or should I add a dinucleotide-preserving shuffled *condition* to the comparison (currently listed as optional)?

**A live risk on Day 1.** Tier 2's percentile bands depend on a server-side control bank whose provenance may not be fully recoverable within the half-day audit cap. If it is not, the plan falls back to raw same-mode scores and the band and joint-region results disappear from the thesis. Would you rather I pre-commit to the raw-score branch now and design the write-up around it, rather than leave a scientific reporting decision sitting on Day 1?

### 7.3 Linkage — does this test my contribution?

My claimed contributions are the leakage-controlled corpus, the small-data adaptation, and the prioritisation framework. The generator-level EVAL tests the adaptation. AptaRank's Tier 1 and Tier 2 EVAL test the prioritisation framework. But **nothing isolates the corpus design itself** — there is no ablation comparing my curated corpus against an uncurated or less strictly partitioned one, so its contribution is argued from construction and audit rather than demonstrated by a result. I excluded that arm as scope control. Is that defensible as-is, or is it the gap an examiner would push on hardest? A cheap partial answer would be a chemistry or evidence-level subgroup analysis, currently listed as optional.

Related: is unconditional domain adaptation plus downstream ranking a sufficiently strong end-to-end story, given that nothing in the pipeline is conditioned on the actual targets?

### 7.4 One open design decision: generation volume per seed

My implementation currently generates 30,000 raw attempts per training seed, so a three-seed D1 yields 90,000 attempts while B1 and B2 yield 30,000 each. The evaluation plan's wording ("30,000 raw attempts per new condition") reads as pooled across seeds — roughly 10,000 per seed — and I need to settle this before M9A because it affects three things: generation runtime on the shared GPU ahead of the 2 October aim, whether D1 and B1 are matched on pool size for the distributional comparisons, and how much within-seed data the seed-aware bootstrap has to work with. Per-seed pools give cleaner seed-level estimates at triple the generation cost; pooling keeps the conditions symmetric and cheaper. Which would you prefer?

### 7.5 Feasibility — the prerequisite stack and the window

Two things compound here. The evaluation week assumes M9A is complete before Day 1, which as Section 4 notes means trained checkpoints *and* full generation pools *and* the frozen analysis suite of Section 5.2 that has not been written. And as Section 6.2 shows, the window between the ICDM camera-ready work and the 11 October target is about 3.5 working days, or 5.5 if I work the weekend, against a five-day plan.

I would rather agree a contingency with you now than improvise one mid-week. The options I can see:

1. **Cut evaluation scope now** to what genuinely fits 3.5–4 days, using the priority order in 7.1, and keep 11 October.
2. **Let evaluation run past 11 October** into the 12–18 October window, accepting that the results and conclusion chapters get less drafting time before the 18 October checkpoint, on the basis that 31 October still holds revision capacity.
3. **Protect 11 October by reducing the experiment** — one training seed and pooled generation — which also eases the 2 October block.
4. **Move the evaluation window later** and treat 18 October as a structurally complete draft with placeholders for late numbers.

Which would you recommend? And is there a point in the next week — after M4 or M6, say — at which you would want me to make that call rather than wait and see whether 2 October holds?

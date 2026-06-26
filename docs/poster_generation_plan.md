I’ve read the methods, null-model design, filtering/ranking plan, and Cursor audit. The main implementation plan should stay narrow: **poster-ready Stage 1 preliminary results**, not the full five-level pipeline. The full methodology is broader, but for this sprint we should produce a defensible Stage 1 comparison between **unadapted RNAGenesis** and an **Aptadiff-A-calibrated null model**.

The key alignment points are:

The null model should sample sequence lengths from the empirical corpus length distribution and sample bases independently from global corpus-derived nucleotide frequencies, with no positional, structural, GC, or motif constraints. This matches your null-model design. 

The full MRes methodology frames Aim 3 as a modular filtering/ranking framework using sequence validity, uniqueness, novelty, GC content, MFE, secondary-structure similarity, and target-relevant criteria, but the poster sprint should focus only on the first hard-filtering stage plus summary plots. 

The audit found that Stage 1 hard filtering already exists and has already been run on the unadapted RNAGenesis 30k pool, but the null model, empirical-distribution JSON, plotting script, and poster captions are still missing. 

## Proposed overall plan

### Phase 0 — Create a clean poster branch

Start from synced `main`.

```bash
git switch main
git pull origin main
git switch -c poster-stage1-preliminary-results
```

This branch should contain the poster sprint code only: distribution estimation, null generation, Stage 1 config updates if needed, plotting, and documentation.

---

## Phase 1 — Estimate empirical reference distributions from Aptadiff Dataset A

**Goal:** Convert Aptadiff Dataset A into a reusable reference-distribution artifact.

Input:

```text
data/raw/Aptadiff_datasetA/datasetA_IGFBP3_P6.csv
```

The audit says this file has `seq` and `p6` columns, uses DNA alphabet with `T`, contains 13,803 sequences, fixed length 36, and one sequence with `N`. 

Implementation target:

```text
scripts/estimate_corpus_distributions.py
```

Output:

```text
data/processed/corpus_distributions/aptadiff_datasetA_p6.json
data/processed/corpus_distributions/aptadiff_datasetA_p6_summary.md
```

The script should:

1. Read the `seq` column.
2. Convert DNA to RNA using `T → U`.
3. Drop or exclude sequences containing characters outside `{A,U,C,G}`.
4. Record how many sequences were read, retained, and excluded.
5. Compute:

   * mononucleotide frequencies: `A`, `U`, `C`, `G`
   * length distribution
   * GC content distribution
   * summary statistics for length and GC
6. Optionally compute ViennaRNA MFE and normalised MFE for the reference corpus, if runtime is acceptable.
7. Save everything to JSON so that later you can replace Aptadiff A with the full curated corpus without changing downstream code.

Important design decision: **do not weight by `p6` yet** unless you deliberately want the null model to reflect read abundance rather than unique sequence composition. For this poster sprint, I would use each unique sequence once. It is simpler and easier to explain.

---

## Phase 2 — Generate a poster-specific Stage 1 config from the reference distributions

**Goal:** Keep Stage 1 thresholds modular and empirically grounded.

Current audit finding: `configs/stage1_hard_filter_default.json` has only the homopolymer filter active; length, GC, MFE, and near-dedup thresholds are currently `null`. 

Implementation target:

```text
scripts/make_stage1_config_from_distributions.py
```

Output:

```text
configs/stage1_hard_filter_aptadiffA_poster.json
```

This config should probably set:

| Filter                             | Poster setting                                                |
| ---------------------------------- | ------------------------------------------------------------- |
| RNA alphabet validity              | active                                                        |
| leading `11` stripping             | active, because RNAGenesis raw outputs include decoder prefix |
| length bounds                      | from Aptadiff empirical distribution                          |
| exact deduplication                | active                                                        |
| homopolymer run threshold          | fail at run length `>= 5`                                     |
| GC content band                    | Aptadiff 5th–95th percentiles                                 |
| normalised MFE threshold           | optional; only if reference MFE distribution is computed      |
| near-dedup against training corpus | defer unless time allows                                      |

Because Aptadiff A and cleaned RNAGenesis are both length 36, the length threshold may become exactly 36. That is fine, but we should explicitly document that this is a property of this preliminary subset, not a general rule for the final curated corpus.

For the poster, I would **not** enable near-dedup yet. It introduces extra dependencies and interpretation complexity. We can mention it as planned for later stages.

---

## Phase 3 — Finish null model generation

**Goal:** Generate 30,000 null model sequences using the empirical Aptadiff-A distributions.

The null-model design says the model should sample lengths from the empirical length distribution and sample each nucleotide independently from global corpus-derived frequencies. GC should not be directly constrained; it should emerge from the base frequencies. 

Current audit finding: `scripts/null_model.py` is only a stub, has no CLI or file I/O, and currently mishandles Aptadiff DNA input unless `T→U` conversion is added. 

Implementation target:

```text
scripts/generate_null_sequences.py
```

Inputs:

```text
data/processed/corpus_distributions/aptadiff_datasetA_p6.json
```

Outputs:

```text
results/null_model_30k/null_sequences.txt
results/null_model_30k/null_sequences.fasta
results/null_model_30k/null_generation_metadata.json
```

The script should:

1. Load the distribution JSON.
2. Sample 30,000 lengths from the empirical length histogram.
3. Sample bases independently using the corpus mononucleotide frequencies.
4. Use a fixed random seed, probably `42`.
5. Write one-sequence-per-line `.txt`, because the Stage 1 CLI already accepts that format.
6. Also write FASTA with IDs like:

```text
>null_model_000001
AUGC...
```

7. Save metadata:

   * source distribution JSON
   * seed
   * number generated
   * base frequencies used
   * length histogram used
   * NumPy version

For this dataset, all generated null sequences will likely be length 36, because Aptadiff A is fixed length 36. That is actually useful because it makes the null directly comparable to the cleaned RNAGenesis baseline.

---

## Phase 4 — Run Stage 1 on null and, if necessary, rerun Stage 1 on RNAGenesis

**Goal:** Produce comparable Stage 1 outputs for both conditions.

Existing RNAGenesis Stage 1 output:

```text
results/aim3_stage1_unadapted_30k/
```

The audit says this already exists and processed 30,080 unadapted RNAGenesis sequences, with 13,136 passing under the current default config. 

New null Stage 1 output:

```text
results/aim3_stage1_null_30k/
```

Run commands, eventually:

```bash
python scripts/run_stage1_hard_filter.py \
  --input-glob "results/null_model_30k/null_sequences.txt" \
  --condition null_model_30k \
  --output-dir results/aim3_stage1_null_30k \
  --config configs/stage1_hard_filter_aptadiffA_poster.json
```

Then rerun RNAGenesis with the same poster config, so both conditions are filtered identically:

```bash
python scripts/run_stage1_hard_filter.py \
  --input-glob "results/phase4_1_unadapted_rnagenesis_30k/raw/*.txt" \
  --condition unadapted_rnagenesis_30k \
  --output-dir results/aim3_stage1_unadapted_30k_poster_config \
  --config configs/stage1_hard_filter_aptadiffA_poster.json
```

I recommend rerunning RNAGenesis under the poster config rather than comparing the null run to the older default-config run. Otherwise the comparison may be subtly inconsistent.

---

## Phase 5 — Create poster plotting script

**Goal:** Generate the two core poster figures.

Implementation target:

```text
scripts/plot_stage1_poster_results.py
```

Inputs:

```text
results/aim3_stage1_unadapted_30k_poster_config/stage1_summary.json
results/aim3_stage1_null_30k/stage1_summary.json
results/aim3_stage1_unadapted_30k_poster_config/stage1_all_sequences.csv
results/aim3_stage1_null_30k/stage1_all_sequences.csv
```

Outputs:

```text
results/aim3_poster_figures/stage1_pass_rate_plot.png
results/aim3_poster_figures/stage1_pass_rate_plot.pdf
results/aim3_poster_figures/gc_content_distribution_plot.png
results/aim3_poster_figures/gc_content_distribution_plot.pdf
```

Figure 1: **Stage 1 pass rate plot**

Show:

| Condition                | Generated |   Passed |   Failed | Pass rate |
| ------------------------ | --------: | -------: | -------: | --------: |
| Unadapted RNAGenesis     |    30,080 | computed | computed |  computed |
| Aptadiff-calibrated null |    30,000 | computed | computed |  computed |

Useful variant: stacked pass/fail bar chart, with pass-rate labels.

Figure 2: **GC content distribution plot**

Show the GC distribution of:

1. unadapted RNAGenesis sequences
2. null model sequences
3. optional: Aptadiff A reference distribution

I strongly recommend including the Aptadiff reference distribution as a third curve or histogram if the plot remains readable. It makes the calibration story much clearer: “the null was generated from this reference distribution; RNAGenesis is compared against both.”

---

## Phase 6 — Generate one example ViennaRNA structure

**Goal:** Produce one simple, poster-friendly example structure.

Implementation target:

```text
scripts/export_example_structure.py
```

Input:

```text
results/aim3_stage1_unadapted_30k_poster_config/stage1_passed_sequences.csv
```

Output:

```text
results/aim3_poster_figures/example_rnagenesis_structure.txt
results/aim3_poster_figures/example_rnagenesis_structure.md
results/aim3_poster_figures/example_rnagenesis_structure.png
```

For the poster, the minimal acceptable structure artifact is:

```text
Sequence:
AUGC...

Dot-bracket:
..((...))...

MFE:
-12.3 kcal/mol
```

A nice figure could simply show the sequence, dot-bracket structure, and MFE in a clean monospaced panel. I would not spend time trying to make a perfect circular RNA diagram unless the basic results are already done.

Selection rule:

Pick a **passed RNAGenesis sequence** with:

1. valid RNA alphabet
2. no homopolymer failure
3. GC content near the Aptadiff mean
4. reasonably negative normalised MFE
5. visually non-trivial dot-bracket structure

This keeps the example representative rather than cherry-picked purely for visual appeal.

---

## Phase 7 — Write poster captions and interpretation

**Goal:** Produce a short markdown file with captions and a defensible interpretation.

Implementation target:

```text
docs/poster_stage1_preliminary_results.md
```

Contents:

1. Methods paragraph:

   * Aptadiff Dataset A used as preliminary reference subset.
   * DNA sequences converted to RNA using `T→U`.
   * Invalid sequences excluded.
   * Empirical base and length distributions estimated.
   * Null model generated by independent base sampling from corpus frequencies and empirical length sampling.
   * Stage 1 filters applied identically to null and unadapted RNAGenesis.

2. Caption for pass-rate plot.

3. Caption for GC distribution plot.

4. Caption for example structure.

5. Interpretation:

   * What the null model controls for.
   * Whether RNAGenesis differs from composition-matched chance.
   * Whether Stage 1 filtering removes a meaningful fraction.
   * Caveat: this is preliminary and based on Aptadiff A only, not the final curated training corpus.

The methods document already frames success computationally: a reproducible workflow, model comparison against random/null baselines, and transparent filtering/ranking outputs. 

---

## Phase 8 — Final validation and commit

Before committing:

```bash
python -m pytest tests/test_stage1_hard_filter.py -q
git status
git diff --stat
```

Also run a smoke test of the new scripts using a small count:

```bash
python scripts/generate_null_sequences.py \
  --distributions-json data/processed/corpus_distributions/aptadiff_datasetA_p6.json \
  --n-sequences 100 \
  --seed 42 \
  --output-dir results/null_model_smoke_test
```

Then Stage 1 smoke test:

```bash
python scripts/run_stage1_hard_filter.py \
  --input-glob "results/null_model_smoke_test/null_sequences.txt" \
  --condition null_model_smoke_test \
  --output-dir results/aim3_stage1_null_smoke_test \
  --config configs/stage1_hard_filter_aptadiffA_poster.json
```

Commit code/config/docs, but not raw data:

```bash
git add scripts/ src/ configs/ docs/ data/processed/ results/aim3_poster_figures/
git status
git commit -m "Add poster Stage 1 null model and plotting workflow"
```

We should be careful about committing large result CSVs. My preference:

**Commit:**

* scripts
* config
* distribution JSON
* small markdown summaries
* final poster figures
* captions/interpretation doc

**Do not commit unless needed:**

* full 30k null sequence file
* full per-sequence Stage 1 CSVs
* large intermediate outputs

---

## Proposed implementation order for Cursor prompts

I would split implementation into six Cursor prompts:

1. **Create branch and inspect current tree.**
2. **Implement `estimate_corpus_distributions.py`.**
3. **Implement `generate_null_sequences.py`.**
4. **Implement `make_stage1_config_from_distributions.py` or update config manually from distribution JSON.**
5. **Run Stage 1 on null and rerun RNAGenesis with the same poster config.**
6. **Implement plotting, structure export, and captions markdown.**

The first actual coding prompt should be for **Phase 1 only**. We should not ask Cursor to implement everything in one go; it will almost certainly create tangled code.

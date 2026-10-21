# Supervisor table pack: RNAGenesis generator evaluation

**Status:** sequence-free presentation tables for the closed M10 evaluation.  
**Source:** `docs/m10_generator_evaluation_results.md` and the frozen public
`m10_sequence_free_report.json` (SHA-256
`20e8daf7b2decb92299a9c0274273fd764db94c63c46e603c204cc7b0f09547f`).  
**Interpretive report:** [generator evaluation supervisor briefing](generator_evaluation_report_supervisor.md).

These tables reproduce reviewed aggregates. They do not recompute metrics or
contain sequence strings.

## Table 1. Generator conditions


| Condition | Generator                                                  | Frozen role                              | Key limitation                                                                                      |
| --------- | ---------------------------------------------------------- | ---------------------------------------- | --------------------------------------------------------------------------------------------------- |
| B1        | Released generic RNAGenesis diffusion model                | Primary unadapted neural baseline for D1 | One checkpoint identity; block results are technical controls, not independent training replicates. |
| D1        | Generic model fine-tuned on 669 unique TRAIN aptamer cores | Aptamer-domain adaptation intervention   | Only training seeds 43 and 44; each seed is coupled to one technical block.                         |
| B2        | TRAIN-matched empirical i.i.d. RNA sampler, seed 42        | Non-neural low-order null                | One empirical-null seed; no learned higher-order sequence model.                                    |
| B0        | Historical released aptamer-adapted RNAGenesis             | External descriptive comparator          | Fixed 36-nt cleaned output and less controlled external-training provenance.                        |




## Table 2. Output accounting


| Condition | Raw attempts | Successfully parsed | Valid canonical RNA | Unique valid | Invalid | Duplicate excess | Unique fraction |
| --------- | ------------ | ------------------- | ------------------- | ------------ | ------- | ---------------- | --------------- |
| B0        | 30,080       | 30,080              | 30,080              | 30,080       | 0       | 0                | 1.000000        |
| B1        | 30,000       | 30,000              | 30,000              | 29,983       | 0       | 17               | 0.999433        |
| B2        | 30,000       | 30,000              | 30,000              | 30,000       | 0       | 0                | 1.000000        |
| D1        | 30,000       | 30,000              | 30,000              | 30,000       | 0       | 0                | 1.000000        |




## Table 3. Frozen EVAL closeness metrics

Lower is closer. B0 is shown only as an external panel.


| Condition              | Median nearest-EVAL normalized edit distance | Nucleotide TV | Dinucleotide TV |
| ---------------------- | -------------------------------------------- | ------------- | --------------- |
| B0                     | 0.450980                                     | 0.322060      | 0.449365        |
| B1                     | 0.467532                                     | 0.055273      | 0.082193        |
| B2                     | 0.463415                                     | 0.011854      | 0.051472        |
| D1, equal-seed mixture | 0.464789                                     | 0.020335      | 0.058307        |


Need to add stats - are these differences significant.

## Table 4. Primary B1–D1 effects


| Metric                                       | B1           | D1 equal-seed | D1 − B1       | Frozen relation |
| -------------------------------------------- | ------------ | ------------- | ------------- | --------------- |
| Median nearest-EVAL normalized edit distance | 0.4675324675 | 0.4647887324  | −0.0027437351 | D1 closer       |
| Nucleotide TV                                | 0.0552730398 | 0.0203348433  | −0.0349381964 | D1 closer       |
| Dinucleotide TV                              | 0.0821925665 | 0.0583066320  | −0.0238859345 | D1 closer       |




## Table 5. Matched technical blocks


| Block | D1 training seed | Rows per condition | Metric                            | B1           | D1           | D1 − B1       |
| ----- | ---------------- | ------------------ | --------------------------------- | ------------ | ------------ | ------------- |
| A     | 43               | 15,000             | Median nearest-EVAL edit distance | 0.4675324675 | 0.4666666667 | −0.0008658009 |
| A     | 43               | 15,000             | Nucleotide TV                     | 0.0542943594 | 0.0233687329 | −0.0309256265 |
| A     | 43               | 15,000             | Dinucleotide TV                   | 0.0816967819 | 0.0624284933 | −0.0192682886 |
| B     | 44               | 15,000             | Median nearest-EVAL edit distance | 0.4675324675 | 0.4634146341 | −0.0041178334 |
| B     | 44               | 15,000             | Nucleotide TV                     | 0.0562517297 | 0.0173009538 | −0.0389507759 |
| B     | 44               | 15,000             | Dinucleotide TV                   | 0.0826883559 | 0.0561476439 | −0.0265407120 |




## Table 6. Observed D1 two-seed ranges

These are observed ranges, not confidence intervals.


| Descriptor                        | Minimum      | Maximum      |
| --------------------------------- | ------------ | ------------ |
| Median nearest-EVAL edit distance | 0.4634146341 | 0.4666666667 |
| Nucleotide TV                     | 0.0173009538 | 0.0233687329 |
| Dinucleotide TV                   | 0.0561476439 | 0.0624284933 |
| Exact requested-length rate       | 0.9574       | 0.9756       |
| Median MFE (kcal/mol)             | −8.9000      | −8.6000      |
| Median MFE per nucleotide         | −0.178571    | −0.171698    |
| Median paired fraction            | 0.467533     | 0.469136     |




## Table 7. Predicted folding medians


| Condition | MFE (kcal/mol) | MFE per nucleotide | Paired fraction |
| --------- | -------------- | ------------------ | --------------- |
| EVAL      | −11.8000       | −0.226786          | 0.505263        |
| B0        | −3.5000        | −0.097222          | 0.388889        |
| B1        | −8.3000        | −0.160526          | 0.472727        |
| B2        | −10.2000       | −0.198750          | 0.493827        |
| D1        | −8.7000        | −0.175000          | 0.467532        |




## Table 8. Length adherence


| Condition | Exact-length hits | Attempt denominator | Exact-hit rate | Shortfall attempts | Interpretation                                 |
| --------- | ----------------- | ------------------- | -------------- | ------------------ | ---------------------------------------------- |
| B0        | not applicable    | 30,080              | not applicable | not applicable     | Source records no biological requested length. |
| B1        | 28,967            | 30,000              | 0.965567       | 1,033              | Matched schedule with D1.                      |
| B2        | 30,000            | 30,000              | 1.000000       | 0                  | Empirical-null construction.                   |
| D1        | 28,995            | 30,000              | 0.966500       | 1,005              | Matched schedule with B1.                      |




## Table 9. Frozen TRAIN relationship


| Condition | Exact TRAIN overlap | Median nearest-TRAIN normalized edit distance |
| --------- | ------------------- | --------------------------------------------- |
| B0        | 0                   | 0.416667                                      |
| B1        | 0                   | 0.444444                                      |
| B2        | 0                   | 0.441176                                      |
| D1        | 0                   | 0.440000                                      |




## Table 10. EVAL and production provenance


| Item                                      | Frozen value                                                       |
| ----------------------------------------- | ------------------------------------------------------------------ |
| EVAL identities / unique cores / clusters | 181 / 154 / 79                                                     |
| EVAL short / long cores                   | 89 / 65                                                            |
| EVAL SHA-256                              | `ff4b36535052981c240dfa0571acd9cf00a386c80d9487a5994d1597f3386015` |
| Governing M10 plan v3.4                   | `1f3a73bc294a75c527e11f074c6d3265786c8e7e70d41eacf3ea83d3cf512941` |
| Frozen metric specification               | `2b0679b999235cc838298563448b01ef73f5fdd5132c5ddd3d9944f301f5c824` |
| Production runner                         | `02735f84f264b3b0cfe7f9b5d2ab704846bb5840f9235707197e2999f9152c77` |
| Sequence-free report                      | `20e8daf7b2decb92299a9c0274273fd764db94c63c46e603c204cc7b0f09547f` |
| Run manifest                              | `5d828d918ff8d79e66d65181584175c87d125f69f59b76b2e3a48e78395803d0` |
| Protected evidence                        | `9ba39df6e9c24196d35958613f373f92bac6bf720acde6a07e3880d9d6dc42ee` |
| M10 closure commit                        | `9a843c9d7ef8b0c4cdcbb37e9c8bbb0f6a68c79b`                         |




## Table-use boundary

The displayed precision is sufficient for review and presentation. Use the
full-precision values in `docs/m10_generator_evaluation_results.md` or the frozen
public report for downstream calculation. Do not treat rounded differences as
new metrics, significance tests, or confidence estimates.
# Generator evaluation supervisor figures

These figures accompany
`docs/fine_tuning/generator_evaluation_report_supervisor.md`.

| Figure | Content |
| --- | --- |
| `figure_1_eval_closeness` | B1, D1, and B2 on the three frozen sequence-level EVAL closeness metrics. |
| `figure_2_matched_block_deltas` | Signed D1-minus-B1 differences for the pooled comparison and matched blocks A and B. |
| `figure_3_structure_medians` | Raw median MFE, MFE per nucleotide, and paired fraction for EVAL and all four conditions. |
| `figure_4_output_guardrails` | Canonical validity, exact uniqueness, and requested-length adherence. |

Each figure is supplied as PNG for Markdown/presentation use and SVG for scalable
editing. Plotted values are reproduced in
`docs/fine_tuning/generator_evaluation_supervisor_tables.md`.

The values come from the frozen sequence-free production report, SHA-256
`20e8daf7b2decb92299a9c0274273fd764db94c63c46e603c204cc7b0f09547f`,
and the reviewed M10 result note. No protected sequence-bearing evidence was
opened or recalculated for these figures.

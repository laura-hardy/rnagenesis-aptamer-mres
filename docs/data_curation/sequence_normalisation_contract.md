# Sequence normalisation contract

Shared behavioural contract for canonical corpus sequence fields. This document
defines what the shared code must do. It does not contain source aptamer
sequences.

Australian/British spelling is used throughout (“normalisation”).

## Purpose and stage boundary

- **S1** preserves source records and source sequences **verbatim**. Source
  adapters must not apply independent cleaning or alphabet policies.
- The shared normalisation code is applied from **S2** onward.
- `sequence_raw` is never overwritten. It remains the immutable source string.
- `sequence_full` is the cleaned complete oligonucleotide after display cleaning
  and molecule-aware alphabet normalisation, including any documented constant
  or flanking regions that remain part of the construct.
- `sequence_core` is the documented or confidently inferred variable/core
  region. Without an approved trim, `sequence_core` equals `sequence_full`.
- No source adapter may implement an independent normalisation policy. All
  adapters must call the shared functions (or an approved thin wrapper that
  does not diverge from this contract).

## Conservative molecule handling

- An **explicit experimental molecule type** takes precedence over alphabet
  alone.
- A **U-only** sequence supports RNA classification when molecule type is
  otherwise unknown.
- A **T-only** sequence does **not** by itself distinguish ssDNA from RNA
  printed using a DNA alphabet; molecule type remains unknown unless
  independently established.
- **T→U** conversion is allowed only when the molecule is independently
  established as RNA.
- Genuine DNA aptamers retain **T**.
- Mixed **T/U** is a review condition and is not silently repaired.
- Unknown molecule type remains **unknown** rather than being forced to RNA
  solely because a DNA alphabet is present.

Supported molecule-type labels for the shared API include: `RNA`, `ssDNA`,
`DNA`, and `unknown`.

## Display-only cleaning

Deterministic removal of display-only artefacts is allowed:

- leading and trailing whitespace;
- internal whitespace used only for display;
- recognised 5′ and 3′ terminal labels (including Unicode prime variants);
- display hyphens or configured separator characters;
- case differences (normalise to uppercase).

Surrounding quotation marks that clearly wrap the complete value may be
removed. Textual null tokens (empty string, `NA`, `N/A`, `NULL`, `NONE`, and a
lone hyphen) are treated as missing.

Display cleaning must **not** remove biological characters merely because they
are unexpected. Unexpected characters are retained in the cleaned string and
flagged for QC.

## Constant and flanking regions

- Known promoters, primers and fixed regions may be **detected**.
- Detection does **not** automatically imply trimming.
- Trimming requires either source documentation or a high-confidence
  group-level inference that has been explicitly approved.
- Both `sequence_full` and `sequence_core` must be retained after any applied
  trim.
- Every applied trim must record the exact reason, side, number of bases and
  confidence.
- Uncertain trim proposals are routed to review (`trim_requires_review` or an
  equivalent proposal status).
- Source-specific primer sequences belong in source configuration or extraction
  metadata, not hard-coded in generic functions.

Constant-region inference is a **group-level technical aid**, not proof that a
region is biologically nonfunctional. Proposals must never be applied without an
explicit approved trim plan and an exact prefix or suffix match.

## Length policy

- Accepted `sequence_core` length for the training corpus is **20–100 nt**.
- Length is evaluated **only after** core determination.
- Out-of-range sequences receive QC decisions later rather than being silently
  truncated.
- `sequence_full` may be longer than 100 nt when it contains documented fixed
  regions.

## Alphabet and validation policy

Alphabet categories after display cleaning:

| Category     | Meaning |
|--------------|---------|
| `missing`    | Empty or textual-null input |
| `RNA`        | Only A/C/G/U |
| `DNA_T`      | Only A/C/G/T |
| `mixed_T_U`  | Contains both T and U but is otherwise nucleotide-like |
| `ambiguous`  | Canonical bases plus supported IUPAC ambiguity codes |
| `invalid`    | Any other character present |

Supported ambiguity codes must be **retained and flagged**, not silently
discarded. Invalid sequences must not be “fixed” by dropping characters.

## Determinism and provenance

- All shared functions must be **deterministic**.
- Input records are **immutable**; functions must not mutate caller-owned
  mappings or strings in place.
- Transformations must be **auditable**: every applied change is recorded in
  ordered transformation and QC-flag lists without dumping sequences to
  stdout/stderr.

# NDM-1 5ZGX pocket-target preparation

This directory freezes the target-only preparation used to configure AptaRank
for NDM-1. It selects one fpocket cavity using independent structural evidence;
it does not read aptamer sequences, use candidate scores, perform docking, or
predict binding.

## Frozen biological decision

- Target: wild-type NDM-1, PDB `5ZGX`, chain `A`.
- Binding mode: AptaRank `pocket`, interpreted as the shallow catalytic groove.
- Primary pocket anchors: author-numbered residues `H120, H122, D124, H189,
  C208, H250`.
- Tie-break coverage residues: `L65, M67, F70, V73, W93, Q123, K211, G219,
  N220`.
- A valid cavity must overlap at least one residue from each zinc subsite.
- There is no fallback to fpocket's highest-scoring unrelated cavity.

The anchors select a geometrical cavity; they are not asserted RNA-contact
residues. The RNA reference literature does not provide an experimentally
mapped NDM-1 epitope.

## Reproduce from a clean checkout

Run from this directory:

```bash
conda env create --file environment.yml
conda activate ndm1-target-preparation
curl --fail --location --silent --show-error \
  https://files.rcsb.org/download/5ZGX.pdb --output 5ZGX.pdb
python prepare_ndm1_target.py \
  --raw-pdb 5ZGX.pdb \
  --fpocket-bin "$(command -v fpocket)" \
  --output-dir artifacts/ndm1_5zgx_fpocket4
python -m unittest -v test_prepare_ndm1_target.py
```

The output directory must not already exist. This prevents a rerun from
silently overwriting the frozen artifacts. Use a new output directory for any
intentional replication.

To compare an independent replication with the frozen run:

```bash
python verify_replication.py \
  artifacts/ndm1_5zgx_fpocket4 \
  artifacts/ndm1_5zgx_fpocket4_replication
```

## Coordinate policy

The unmodified RCSB file is retained and hashed. Alternate atom locations are
resolved deterministically by occupancy, with ties preferring a blank location
and then `A`. Two derived structures are produced:

1. `5ZGX_A_biological_master.pdb` contains chain-A protein atoms, the two Zn
   ions and the deposited bridging hydroxide. Ethylene glycol (`EDO`) and
ordinary crystallographic water (`HOH`) are removed.
2. `5ZGX_A_fpocket_input.pdb` contains chain-A protein atoms only. This matches
   the AptaRank target file's `strip_hetatm: true` policy and prevents the
   active-site EDO molecule from being treated as NDM-1 geometry.

The protein-only calculation retains the deposited metal-bound protein
conformation but does not model metal-mediated RNA contacts. This is a stated
limitation rather than an unrecorded preprocessing choice.

## fpocket measurement and selection

fpocket 4.0 is run once on the protein-only target, with its paper-aligned
default of 300 Monte Carlo volume iterations stated explicitly. For every detected cavity,
the workflow records fpocket score, volume, lining residues, alpha-sphere
count, principal-axis extents and equivalent-sphere diameter. Following the
AptaRank paper workflow, the characteristic dimension is

`2 * largest singular value / sqrt(number of alpha spheres)`.

fpocket's `Volume` value is a stochastic Monte Carlo estimate and can differ
slightly on an independent replication. It is descriptive and is used only for
the equivalent-sphere cross-check. Reproduction is assessed from the selected
pocket number, lining-residue set, alpha-sphere set and characteristic
dimension; neither volume nor fpocket score participates in pocket selection.

The selected pocket maximises overlap with the six primary anchors. A tie is
resolved by overlap with the nine extended groove residues; an unresolved tie
fails closed. Candidate data are never consulted.

## Files used for AptaRank

- `artifacts/ndm1_5zgx_fpocket4/aptarank_target_5zgx.txt`: uploadable target
  configuration.
- `artifacts/ndm1_5zgx_fpocket4/target_configuration.json`: full preparation,
  rule, software, result and SHA-256 provenance.
- `artifacts/ndm1_5zgx_fpocket4/results/pocket_inventory.csv`: all detected
  pockets, including the selected flag and residue overlaps.
- `artifacts/ndm1_5zgx_fpocket4/results/selected_pocket.json`: the frozen
  target-level geometry.
- `artifacts/ndm1_5zgx_fpocket4/results/run_report.md`: concise human-readable
  result and interpretation boundary.
- `artifacts/ndm1_5zgx_fpocket4/MANIFEST.sha256`: checksums for every frozen
  artifact other than the manifest itself.

Before a biological AptaRank run, confirm that the deployed provenance reports
PDB `5ZGX`, chain `A`, pocket mode, fpocket `4.0`, the same six target-site
residue numbers, and the same selected pocket measurements. Stop rather than
substituting another pocket if those values disagree.

## Interpretation boundary

This configuration tests whether an RNA candidate's estimated accessible-loop
extent is geometrically compatible with one static representation of the
NDM-1 catalytic groove. It does not establish binding, affinity, competitive
inhibition, selectivity, an RNA contact map, or a complete RNA-protein pose.

## Structural sources

- RCSB PDB 5ZGX: <https://www.rcsb.org/structure/5ZGX>
- Zhang et al. (2018), active-site conformational fluctuations:
  <https://doi.org/10.1128/AAC.01579-18>
- King et al. (2013), substrate recognition and catalytic mechanism:
  <https://doi.org/10.1371/journal.pone.0047249>
- Kim et al. (2011), molecular basis of NDM-1:
  <https://doi.org/10.1371/journal.pone.0024621>
- Le Guilloux et al. (2009), fpocket:
  <https://doi.org/10.1186/1471-2105-10-168>

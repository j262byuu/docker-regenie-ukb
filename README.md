# regenie-ukb

REGENIE v4.1 (MKL build) + PLINK 2.0 (AVX2) in a single Ubuntu 22.04 container, packaged for UK Biobank-scale GWAS workflows on LSF and SLURM clusters.

## What's inside

| Tool | Version | Build |
|------|---------|-------|
| [REGENIE](https://github.com/rgcgithub/regenie) | v4.1 | Official pre-compiled MKL static binary (`regenie_v4.1.gz_x86_64_Linux_mkl`) |
<!-- AUTOGEN:PLINK-ROW:START -->
| [PLINK 2.0](https://www.cog-genomics.org/plink/2.0/) | alpha 7 (2026-08-18) | Linux AVX2 |
<!-- AUTOGEN:PLINK-ROW:END -->
| Base OS | Ubuntu 22.04 | x86_64 |

Compressed image size: ~55 MB.

## Why this image

- **MKL-optimized REGENIE.** The Intel MKL build is the recommended option for whole-genome regression on UKB-scale data — substantially faster than the default static build, particularly for Step 1.
- **plink2 bundled in.** Pre-imputation QC, LD pruning, variant filtering, and BGEN/PGEN conversion typically live in the same job as REGENIE. Shipping them together avoids the usual two-image / module-load dance on HPC.
- **Locale fix baked in.** The official MKL binary calls into Boost.Locale and aborts on minimal Ubuntu images with:
  ```
  locale::facet::_S_create_c_locale name not valid
  ```
  This image installs `locales` and generates `en_US.UTF-8` so that doesn't happen. (If you've hit this error elsewhere — that's why.)
- **HPC-friendly.** Designed to be pulled and converted to Apptainer/Singularity for LSF or SLURM. No entrypoint magic, no baked-in user IDs, no surprises when bind-mounting scratch.

## Quick start

### Docker

```bash
docker pull j262byuu/regenie-ukb:v4.1-mkl
docker run --rm -v $PWD:/work -w /work j262byuu/regenie-ukb:v4.1-mkl \
  regenie --version
```

### Apptainer / Singularity (LSF / SLURM)

```bash
apptainer pull regenie-ukb.sif docker://j262byuu/regenie-ukb:v4.1-mkl

apptainer exec --bind /scratch:/scratch regenie-ukb.sif regenie --help
apptainer exec --bind /scratch:/scratch regenie-ukb.sif plink2 --version
```

### Typical UKB GWAS pattern

```bash
# Step 1 — null model on an LD-pruned variant set
apptainer exec regenie-ukb.sif regenie \
  --step 1 \
  --bed   ukb_pruned \
  --phenoFile pheno.tsv \
  --bsize 1000 \
  --threads 16 \
  --lowmem --lowmem-prefix /scratch/regenie_tmp \
  --out   step1_out

# Step 2 — per-chromosome association on imputed BGEN
apptainer exec regenie-ukb.sif regenie \
  --step 2 \
  --bgen   ukb_imp_chr${CHR}.bgen \
  --sample ukb_imp.sample \
  --ref-first \
  --pred   step1_out_pred.list \
  --bsize  400 \
  --threads 8 \
  --minINFO 0.4 \
  --out    step2_chr${CHR}
```

Adjust `--bsize`, `--threads`, and `--lowmem-prefix` to match your node's memory and scratch layout.

## Requirements

- **x86_64 CPU with AVX2.** The plink2 binary is the AVX2 build and will refuse to run on pre-Haswell hardware (`This plink2 build requires a processor which supports AVX2/Haswell instructions`). REGENIE MKL itself is x86_64 only.
- Standard container runtime — no `--privileged`, no special capabilities, no GPU.

## Build provenance

- Built from upstream pre-compiled binaries rather than from source. This preserves the exact MKL build the REGENIE team ships and tests, and the exact plink2 binary published on the cog-genomics S3 bucket:
  <!-- AUTOGEN:PLINK-URL:START -->`plink2-assets/alpha7/plink2_linux_avx2_20260818.zip`<!-- AUTOGEN:PLINK-URL:END -->
- Minimal runtime layer: `libgomp1`, `libcurl4`, `locales`, plus `wget` / `unzip` / `ca-certificates` for the build stage.

## How this image stays current

A weekly GitHub Actions workflow ([`auto-build.yml`](.github/workflows/auto-build.yml))
checks upstream for a newer plink2 build and, when it finds one, bumps the
Dockerfile, rebuilds, smoke-tests, and pushes both tags automatically.

Two notes for anyone reading or reusing that workflow:

- **Detection reads the S3 bucket listing, not `plink2_linux_avx2_latest.zip`.**
  That `latest` alias exists and returns HTTP 200, but upstream is not keeping it
  current — on 2026-08-22 it still served the 2026-04-25 build while the newest
  was 2026-08-18. Depending on it would pin this image to a stale plink2
  indefinitely, without producing a single error. The workflow instead lists the
  bucket, takes the highest `alphaN/` channel, then the highest `YYYYMMDD` inside
  it. Channel is compared before date because upstream publishes to several alpha
  lines on the same day.
- **The `plink2 --version` smoke test runs in CI, not in the Dockerfile.**
  The bundled plink2 is the AVX2 build and refuses to start on pre-Haswell
  hardware, so a `RUN plink2 --version` layer would make this image unbuildable on
  older machines. GitHub's runners have AVX2, so the check runs there against the
  built image, and a failure blocks the push.

REGENIE upgrades are **not** automated — a new REGENIE release changes the tag
naming scheme, so the workflow only opens an issue when one appears.

## Tags

<!-- AUTOGEN:TAGS:START -->
- `v4.1-mkl` — moving tag, always the latest build. **Currently:** REGENIE v4.1 (MKL) + plink2 alpha 7 (2026-08-18).
- `v4.1-mkl-plink20260818` — immutable pin of the same build. Use this one for reproducible pipelines.
<!-- AUTOGEN:TAGS:END -->

Naming pattern: `<regenie-version>-mkl` for the moving tag, `<regenie-version>-mkl-plink<YYYYMMDD>` for immutable pins.

### Changelog

<!-- AUTOGEN:CHANGELOG:START -->
- **2026-08-22** — plink2 bumped from alpha 6 (2026-02-28) to alpha 7 (2026-08-18). REGENIE unchanged at v4.1. Note that `v4.1-mkl` was overwritten in place; the earlier alpha 6 build is no longer available under any tag.
<!-- AUTOGEN:CHANGELOG:END -->

## Caveats

- **x86_64 only.** No ARM64 / Apple Silicon variant. The MKL build cannot be rebuilt for ARM.
- **Personal-use image.** Maintained on a best-effort basis, not affiliated with the REGENIE or PLINK developers. Please cite the original tools — not this image — in any publications:
  - REGENIE: Mbatchou et al. (2021), *Nature Genetics* 53:1097–1103.
  - PLINK 2.0: Chang et al. (2015), *GigaScience* 4:7.

## License

Built from upstream binaries:
- REGENIE — MIT License
- PLINK 2.0 — GPL v3

Dockerfile and packaging: MIT.

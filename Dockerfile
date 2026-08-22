# =============================================================================
# Dockerfile — REGENIE v4.1 (MKL) + plink2 for UKB GWAS
#
# plink2 version is bumped automatically by .github/workflows/auto-build.yml.
# To build by hand:
#   docker build -t j262byuu/regenie-ukb:v4.1-mkl \
#                -t j262byuu/regenie-ukb:v4.1-mkl-plink20260818 .
#   docker push j262byuu/regenie-ukb:v4.1-mkl
#   docker push j262byuu/regenie-ukb:v4.1-mkl-plink20260818
# =============================================================================

FROM ubuntu:22.04

ARG DEBIAN_FRONTEND=noninteractive
ARG REGENIE_VERSION=v4.1
ARG PLINK2_CHANNEL=alpha7
ARG PLINK2_VERSION=20260818

# ---- minimal runtime deps ------------------------------------------------
# libcurl4 — needed because REGENIE MKL binary links against it.
# libgomp1 — OpenMP threading.
# locales  — REQUIRED: without this, REGENIE aborts with
#   "locale::facet::_S_create_c_locale name not valid"
#   because some Boost component tries to initialize a UTF-8 locale.
RUN apt-get update && apt-get install -y --no-install-recommends \
      wget ca-certificates \
      unzip \
      libgomp1 \
      libcurl4 \
      locales \
    && rm -rf /var/lib/apt/lists/* \
    && sed -i '/en_US.UTF-8/s/^# //g' /etc/locale.gen \
    && locale-gen

ENV LANG=en_US.UTF-8 \
    LANGUAGE=en_US:en \
    LC_ALL=en_US.UTF-8

# ---- REGENIE v4.1 MKL (official pre-compiled static binary) --------------
RUN cd /tmp && \
    wget -q https://github.com/rgcgithub/regenie/releases/download/${REGENIE_VERSION}/regenie_${REGENIE_VERSION}.gz_x86_64_Linux_mkl.zip && \
    unzip regenie_${REGENIE_VERSION}.gz_x86_64_Linux_mkl.zip && \
    mv regenie_${REGENIE_VERSION}.gz_x86_64_Linux_mkl /usr/local/bin/regenie && \
    chmod +x /usr/local/bin/regenie && \
    rm -rf /tmp/*

# ---- plink2 (latest AVX2 build: alpha7.4, 18 Aug 2026) -------------------
RUN cd /tmp && \
    wget -q https://s3.amazonaws.com/plink2-assets/${PLINK2_CHANNEL}/plink2_linux_avx2_${PLINK2_VERSION}.zip && \
    unzip plink2_linux_avx2_${PLINK2_VERSION}.zip && \
    mv plink2 /usr/local/bin/plink2 && \
    chmod +x /usr/local/bin/plink2 && \
    rm -rf /tmp/*

# ---- Sanity check --------------------------------------------------------
RUN regenie --version
# plink2 is deliberately NOT checked here. It is the AVX2 build and refuses to
# start on pre-Haswell CPUs, so a `RUN plink2 --version` layer would make this
# image unbuildable on any such machine. The check runs in CI instead — see
# .github/workflows/auto-build.yml, which executes it against the built image on
# an AVX2-capable runner and blocks the push if it fails.

# ---- Runtime -------------------------------------------------------------
WORKDIR /home
CMD ["/bin/bash"]

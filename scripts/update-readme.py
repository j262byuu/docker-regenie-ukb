#!/usr/bin/env python3
"""Rewrite the version-dependent parts of README.md after a plink2 bump.

README.md is the single documentation source: GitHub renders it as the repo
front page, and the release workflow pushes the same file to the Docker Hub
repository description. So it has to stay both human-editable and
machine-updatable.

Rather than regex over prose — which works right up until someone rewords a
sentence and the pattern silently stops matching — the version-dependent spans
are fenced with `<!-- AUTOGEN:<NAME>:START/END -->` markers. This script only
ever touches text between markers; everything outside is hand-written and safe
to edit freely. A missing marker is a hard error, not a silent no-op.

Idempotent: running twice with the same arguments produces no diff.
"""

import argparse
import datetime
import re
import sys

README = "README.md"


def die(msg):
    print(f"update-readme: {msg}", file=sys.stderr)
    sys.exit(1)


def replace_block(text, name, new_body):
    """Swap the contents between AUTOGEN:<name>:START/END markers."""
    start = f"<!-- AUTOGEN:{name}:START -->"
    end = f"<!-- AUTOGEN:{name}:END -->"
    pattern = re.compile(
        re.escape(start) + r"(.*?)" + re.escape(end), re.DOTALL
    )
    if not pattern.search(text):
        die(f"marker block AUTOGEN:{name} not found in {README} — "
            f"was the block removed or renamed by a hand edit?")
    return pattern.sub(lambda _: f"{start}{new_body}{end}", text, count=1)


def block_body(text, name):
    start = f"<!-- AUTOGEN:{name}:START -->"
    end = f"<!-- AUTOGEN:{name}:END -->"
    m = re.search(re.escape(start) + r"(.*?)" + re.escape(end), text, re.DOTALL)
    return m.group(1) if m else ""


def human_channel(channel, label=None):
    """alpha7 -> 'alpha 7', or the exact 'alpha 7.4' when we know the minor.

    The S3 key only carries the major channel, so detection alone cannot tell
    alpha 7.4 from alpha 7.1. The binary can: `plink2 --version` prints
    "PLINK v2.0.0-a.7.4LM AVX2 Intel (18 Aug 2026)". The workflow already runs
    that as a smoke test, so it passes the parsed minor in via --channel-label
    rather than scraping the hand-maintained cog-genomics HTML page for it.
    """
    if label:
        if not re.match(r"^alpha \d+(\.\d+)*$", label):
            die(f"--channel-label must look like 'alpha 7.4', got {label!r}")
        return label
    m = re.match(r"^alpha(\d+)$", channel)
    if not m:
        die(f"unexpected channel format: {channel!r}")
    return f"alpha {m.group(1)}"


def read_base_image():
    """Base OS label from the Dockerfile's FROM line, so the table cannot drift."""
    try:
        with open("Dockerfile", encoding="utf-8") as fh:
            for line in fh:
                m = re.match(r"^FROM\s+([^\s:]+):(\S+)", line)
                if m:
                    return f"{m.group(1).capitalize()} {m.group(2)}"
    except OSError as exc:
        die(f"cannot read Dockerfile for the base image: {exc}")
    die("no FROM <image>:<tag> line found in Dockerfile")


def iso_date(yyyymmdd):
    return f"{yyyymmdd[:4]}-{yyyymmdd[4:6]}-{yyyymmdd[6:]}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--channel", required=True, help="e.g. alpha7")
    ap.add_argument("--version", required=True, help="e.g. 20260818")
    ap.add_argument("--prev-channel", help="previous channel, for the changelog entry")
    ap.add_argument("--prev-version", help="previous version, for the changelog entry")
    ap.add_argument("--regenie", default="v4.1", help="REGENIE version in the image tags")
    ap.add_argument("--today", help="override today's date (YYYY-MM-DD), for testing")
    ap.add_argument("--channel-label", help="exact upstream label, e.g. 'alpha 7.4', parsed from plink2 --version")
    ap.add_argument("--platform", default="plink2_linux_avx2_")
    args = ap.parse_args()

    if not re.match(r"^\d{8}$", args.version):
        die(f"--version must be YYYYMMDD, got {args.version!r}")

    text = open(README, encoding="utf-8").read()
    chan_h = human_channel(args.channel, args.channel_label)
    date_h = iso_date(args.version)
    regenie = args.regenie
    pin_tag = f"{regenie}-mkl-plink{args.version}"

    # --- version table ---
    # The whole table is regenerated, not just the plink row. A marker comment
    # sitting between two table rows terminates the table in GitHub-flavored
    # Markdown, so the markers have to live outside it. (Docker Hub's renderer
    # tolerated it; GitHub's does not.)
    base_os = read_base_image()
    text = replace_block(text, "VERSIONS", (
        "\n| Tool | Version | Build |\n"
        "|------|---------|-------|\n"
        f"| [REGENIE](https://github.com/rgcgithub/regenie) | {regenie} | "
        f"Official pre-compiled MKL static binary "
        f"(`regenie_{regenie}.gz_x86_64_Linux_mkl`) |\n"
        f"| [PLINK 2.0](https://www.cog-genomics.org/plink/2.0/) "
        f"| {chan_h} ({date_h}) | Linux AVX2 |\n"
        f"| Base OS | {base_os} | x86_64 |\n"
    ))

    # --- build provenance path ---
    text = replace_block(text, "PLINK-URL", (
        f"`plink2-assets/{args.channel}/{args.platform}{args.version}.zip`"
    ))

    # --- tags ---
    text = replace_block(text, "TAGS", (
        f"\n- `{regenie}-mkl` — moving tag, always the latest build. "
        f"**Currently:** REGENIE {regenie} (MKL) + plink2 {chan_h} ({date_h}).\n"
        f"- `{pin_tag}` — immutable pin of the same build. "
        f"Use this one for reproducible pipelines.\n"
    ))

    # --- changelog ---
    if args.prev_channel and args.prev_version:
        today = args.today or datetime.date.today().isoformat()
        prev_h = f"{human_channel(args.prev_channel)} ({iso_date(args.prev_version)})"
        entry = (
            f"- **{today}** — plink2 bumped from {prev_h} to {chan_h} ({date_h}). "
            f"REGENIE unchanged at {regenie}. `{regenie}-mkl` now points at this build; "
            f"the previous build remains available as an immutable pin."
        )
        existing = block_body(text, "CHANGELOG")
        # Idempotency: an identical entry means this bump was already recorded.
        if entry not in existing:
            text = replace_block(text, "CHANGELOG", f"\n{entry}\n{existing.strip()}\n")

    open(README, "w", encoding="utf-8").write(text)
    print(f"update-readme: README.md now describes plink2 {chan_h} ({date_h})")


if __name__ == "__main__":
    main()

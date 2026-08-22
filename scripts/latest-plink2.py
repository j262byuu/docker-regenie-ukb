#!/usr/bin/env python3
"""Resolve the newest plink2 Linux AVX2 build published on the upstream S3 bucket.

plink2 is not a GitHub project: there is no release API, no tag list, no feed.
The binaries live in a public S3 bucket that permits anonymous ListBucket, so
that listing is the authoritative source.

Two things about that bucket are easy to get wrong, and both fail *silently*:

  1. `plink2-assets/plink2_linux_avx2_latest.zip` exists and returns 200, which
     makes it look like the obvious shortcut. It is stale — as of 2026-08-22 it
     still served the 2026-04-25 build (ETag 71851d54…, 7601125 bytes) while the
     real newest build was 2026-08-18 (ETag d7ce8657…, 7567334 bytes). Upstream
     is not maintaining that alias. Using it would quietly pin the image to a
     months-old plink2 forever, with no error anywhere. Never use it.

  2. Picking the largest date across the whole bucket selects the wrong channel.
     Upstream publishes to several alpha lines on the same day: both
     alpha6/plink2_linux_avx2_20260818.zip and alpha7/plink2_linux_avx2_20260818.zip
     exist. Channel must be compared before date.

So: list the channel prefixes, take the highest alpha number, then take the
highest date inside that channel.

Prints KEY=value lines on stdout, suitable for `>> "$GITHUB_OUTPUT"`.

Exits non-zero on any failure to resolve a version. It deliberately never falls
back to "assume the current version is still newest" — that would make a broken
detector indistinguishable from "no new release", which is exactly how a weekly
cron job dies without anyone noticing.
"""

import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

S3_BASE = os.environ.get("PLINK2_S3_BASE", "https://s3.amazonaws.com/plink2-assets/")
PLATFORM = os.environ.get("PLINK2_PLATFORM", "plink2_linux_avx2_")
NS = "{http://s3.amazonaws.com/doc/2006-03-01/}"
TIMEOUT = 30

CHANNEL_RE = re.compile(r"^alpha(\d+)/$")
BUILD_RE = re.compile(r"^alpha\d+/" + re.escape(PLATFORM) + r"(\d{8})\.zip$")


def die(msg):
    print(f"latest-plink2: {msg}", file=sys.stderr)
    sys.exit(1)


def fetch_xml(query):
    url = f"{S3_BASE}?{query}"
    try:
        with urllib.request.urlopen(url, timeout=TIMEOUT) as resp:
            if resp.status != 200:
                die(f"HTTP {resp.status} from {url}")
            body = resp.read()
    except urllib.error.URLError as exc:
        die(f"cannot reach {url}: {exc}")
    except OSError as exc:
        die(f"cannot reach {url}: {exc}")
    try:
        return ET.fromstring(body)
    except ET.ParseError as exc:
        die(f"malformed XML from {url}: {exc}")


def newest_channel():
    """Highest alphaN/ prefix in the bucket."""
    root = fetch_xml("list-type=2&delimiter=/")
    channels = []
    for cp in root.findall(f"{NS}CommonPrefixes"):
        prefix = cp.findtext(f"{NS}Prefix") or ""
        m = CHANNEL_RE.match(prefix)
        if m:
            channels.append((int(m.group(1)), prefix.rstrip("/")))
    if not channels:
        die(f"no alphaN/ channel prefixes found under {S3_BASE} — bucket layout changed?")
    return max(channels)[1]


def newest_build(channel):
    """Highest YYYYMMDD build for our platform inside one channel.

    Paginates defensively. A single channel's listing fits in one page today,
    but a truncated response silently returning a stale max would be the same
    class of failure this script exists to avoid.
    """
    dates = []
    token = ""
    while True:
        query = f"list-type=2&prefix={channel}/{PLATFORM}"
        if token:
            query += f"&continuation-token={urllib.parse.quote(token, safe='')}"
        root = fetch_xml(query)
        for contents in root.findall(f"{NS}Contents"):
            key = contents.findtext(f"{NS}Key") or ""
            m = BUILD_RE.match(key)
            if m:
                dates.append(m.group(1))
        if (root.findtext(f"{NS}IsTruncated") or "false").lower() != "true":
            break
        token = root.findtext(f"{NS}NextContinuationToken") or ""
        if not token:
            die(f"{channel}: listing truncated but no continuation token returned")
    if not dates:
        die(f"no {PLATFORM}YYYYMMDD.zip builds found in {channel}/")
    return max(dates)


def main():
    channel = newest_channel()
    version = newest_build(channel)
    url = f"{S3_BASE}{channel}/{PLATFORM}{version}.zip"
    human = f"{version[:4]}-{version[4:6]}-{version[6:]}"
    for line in (
        f"channel={channel}",
        f"version={version}",
        f"date={human}",
        f"url={url}",
    ):
        print(line)


if __name__ == "__main__":
    main()

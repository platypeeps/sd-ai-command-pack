#!/usr/bin/env bash
# Installs the pinned opencode on a CI runner and puts it on PATH for the
# steps after the one that calls this. Both jobs in `tests.yml` that run the
# suite call it, so the version and its checksum live here once (sd:1557).
#
# `tests/test_sd_review_opencode.py::TheEscapeIsClosedLive` is the only
# check that the sd:1375 config-merge escape is closed against opencode
# itself; without the binary it skips, and the `Fail on skipped tests` step
# turns that skip into a red run. The config-load half the test measures is
# offline -- opencode logs its `loading path=<checkout>/opencode.json` line
# during config discovery, before it resolves a provider -- and the run is
# bounded and killed after bootstrap, so no model credential is needed on the
# runner (measured credential-free: the marker is emitted, then the run ends
# on a model-not-found error inside the timeout, and no MCP server starts).
#
# Pinned to the exact version `bin/sd_opencode.py` and the test docstring
# were measured against; npm `latest` is already past it, so an unpinned
# install would run a confinement boundary test against an unmeasured build.
# The version is interpolated into the URL and the assertion.
#
# This fetches the linux-x64 binary straight from npm's immutable
# per-version registry tarball and checks it against the sha256 of the
# artifact npm publishes. It is deliberately not `npm install -g
# opencode-ai@...`: that form installs outside a lockfile, which the `zizmor`
# gate reports as `adhoc-packages` (a real surfaced finding, not a
# persona-gated one, so it cannot be recorded in check-zizmor-personas.py).
# A checksummed download is the `--require-hashes` equivalent for a tool with
# no lockfile, and it needs no Node toolchain.
#
# linux-x64 only, so this is correct for `ubuntu-latest` jobs alone; a macOS
# leg would need its own artifact and checksum.
#
# To bump: change OPENCODE_VERSION, then recompute the checksum from the
# authentic artifact and cross-check it against that version's published
# sha512 integrity (a mismatch means the artifact changed, not a normal bump):
#   V=<new-version>
#   curl -fsSL "https://registry.npmjs.org/opencode-linux-x64/-/opencode-linux-x64-$V.tgz" | sha256sum
#   curl -s https://registry.npmjs.org/opencode-linux-x64 \
#     | python3 -c "import sys,json;print(json.load(sys.stdin)['versions']['$V']['dist']['integrity'])"
# The sha256 line goes in OPENCODE_SHA256; the integrity line is the base64
# sha512 the first was verified equal to when this pin was set.
#
# `$GITHUB_PATH` puts the binary on PATH for later steps; the assertion here
# calls it by path, because `$GITHUB_PATH` only takes effect in later steps,
# and fails loudly if the extracted binary is ever not the pinned one -- a
# different check from the checksum, which verifies the artifact, not what
# landed on PATH.
set -euo pipefail

OPENCODE_VERSION="1.18.30"
OPENCODE_SHA256="aa31a7e68ce5c73cba302c6a4f31c2e308398db125e49d3dbea32f61862fe6de"

url="https://registry.npmjs.org/opencode-linux-x64/-/opencode-linux-x64-${OPENCODE_VERSION}.tgz"
curl -fsSL "$url" -o "$RUNNER_TEMP/opencode.tgz"
echo "$OPENCODE_SHA256  $RUNNER_TEMP/opencode.tgz" | sha256sum -c -
tar -xzf "$RUNNER_TEMP/opencode.tgz" -C "$RUNNER_TEMP"
install -Dm755 "$RUNNER_TEMP/package/bin/opencode" "$RUNNER_TEMP/opencode-bin/opencode"
echo "$RUNNER_TEMP/opencode-bin" >> "$GITHUB_PATH"
test "$("$RUNNER_TEMP/opencode-bin/opencode" --version)" = "$OPENCODE_VERSION"

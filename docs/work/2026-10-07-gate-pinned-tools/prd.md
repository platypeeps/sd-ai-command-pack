---
title: Offload gate runs pinned copies of the drifting tools, so hub and satellite bind the same bytes
created: 2026-10-07
branch: feat/gate-pinned-tools-2936
item: sd:2936
---
# PRD — gate pinned tools

## Problem

An opted-in repository (`repo.satellite_gate = accept`) merges on a
satellite's gate pass only when the satellite's offload view equals the
hub's. The view binds the bytes of each tool in `OFFLOAD_TOOLS`, and
`offload_differences` refuses on any difference.

Two machines rarely hold the same bytes for a tool the operator installs:

- PR #296 refused at `cargo-nextest`. Each machine had built 0.9.146 with
  `cargo install`, and two builds of one release differ. Both machines now
  run the official release binary, sha256
  `7a558b157d164ab4fb6cb1a48cbac5a57b7b8ad99f5d3492eb6eda64faf91df0`, by hand.
- Homebrew upgrades `node`, `npm`, `uv` and `bash` on each machine on its
  own weekly schedule. Between the two upgrades every satellite pass refuses.
- `sh`, `cc`, `c++`, `clang`, and on the hub `make` and `git`, come from
  macOS and the Command Line Tools (CLT). The `/usr/bin` shims are the same
  bytes for every CLT version, so a compiler difference does not refuse, and
  a refusal on a system tool names nothing the operator can act on.

## Goal

The operator chose option (b) on 2026-10-07: the gate runs its own pinned
copies, installed from a pin list (tool, version, source URL, sha256), so the
hub and the satellite bind identical bytes.

## Requirements

1. The pack holds one pin list. Each entry names a tool, its version, its
   platform, an official release archive URL and the archive's sha256.
2. `sd gate tools install` installs every pin for this machine's platform
   that is missing, checks the sha256 before it unpacks, and never changes
   an installed copy. `sd gate tools status` reports each pin.
3. In an opted-in repository every gate's `PATH` starts with the pinned
   copies. A gate whose pinned copy is missing refuses before reuse or a run,
   and the refusal names the tool, the folder and `sd gate tools install`.
4. A gate in a repository that did not opt in changes nothing.
5. A tool that cannot be pinned keeps resolving on `PATH`. A refusal on it
   names how each side found it: the resolved file, and for a macOS or CLT
   tool the macOS version and build and the CLT version.
6. A macOS or CLT tool binds the CLT or Xcode version beside its bytes, so a
   CLT difference refuses on `cc`. The macOS version is named, not bound.
7. In an opted-in repository `git` and `make` resolve to the CLT copies,
   whatever the caller's `PATH` puts first.
8. The contract with sd:2937 (machine-setup installs nightly and reports
   drift) is written in design.md, "Contract with machine-setup".

## Non-goals

- Pinning `bash` or `python3`, or a release archive of `git` or `make` (design.md, "Per-tool sources").
- Removing old pinned copies.
- Installing from the gate itself: the gate never downloads.

## Acceptance

- New tests fail with each guarded behaviour removed; each quotes its line.
- `sd gate check --base main` passes; branch coverage of the changed
  modules does not drop.

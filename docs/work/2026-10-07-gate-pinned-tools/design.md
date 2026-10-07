# Design — gate pinned tools

## The pin list

`PINS` in `bin/sd_gate_tools.py` is the one pin list. It is a pack file, so
`pack_bin` and `gate_inputs` hash it: a hub and a satellite at one pack
revision read one list, and two lists refuse as `satellite_pack_mismatch`
first. Each entry is a dict:

| Field | Meaning |
|---|---|
| `tool` | the name of the release, such as `node` |
| `version` | the release version |
| `platform` | `<sys.platform>-<platform.machine()>`, such as `darwin-arm64`; other platforms ignore the entry |
| `url` | an official release archive, `.tar.gz` |
| `sha256` | the archive's sha256, from the project's published checksum where it publishes one |
| `bin` | the folder inside the archive that holds the executables, `.` for its top |
| `provides` | the executable names the gate binds, each in `OFFLOAD_TOOLS` |

A pin bump is a pack pull request that edits one entry.

## Where the copies live

A copy lives in `<cache>/pinned-tools/<tool>-<version>-<sha256[:12]>/`, the
archive unpacked. `<cache>` is `sd_gate_cache.cache_root`:
`$SD_GATE_CACHE_DIR`, else `${XDG_CACHE_HOME:-$HOME/.cache}/sd/gate`. The
folder name holds the archive digest, so a new pin is a new folder, and an
installed folder never changes. The gate cache's pruning removes only
`*/cargo-target.*` folders, so it never reaches these.

`install` reads an `https` URL, or a `file` URL in tests, and refuses any other scheme.
It downloads to a temporary file in `pinned-tools/`, checks the
sha256, unpacks into a temporary folder with the `data` filter, checks that
each `provides` name is an executable file under `bin`, and renames the
folder into place. A rename onto a folder another install finished first
keeps that folder. A failure leaves no folder at the final name.

## The gate

`offload_pins`, which sets every opted-in check's environment, puts each
platform pin's `<folder>/<bin>` first on `PATH`, in `PINS` order. It drops
those entries from the rest of `PATH` first, so a second pinning changes
nothing. The view, the local binding and the check resolve every name on
that `PATH`, so they bind and run the pinned copy.

`from_receipts` refuses before reuse or a run when a pinned copy is missing,
as it does for `pinned_subcommands`:

    the gate's pinned uv 0.12.22 is not installed at <folder>: run `sd gate tools install`

A gate in `whole` mode (the repository did not opt in) gets no pinned `PATH`
and never refuses on a missing copy.

`cargo_subcommands` skips a name a platform pin provides. Otherwise the
caller's `cargo-nextest`, copied into `CARGO_SUBCOMMANDS` and put before
`PATH` by `subcommand_path`, would shadow the pinned one.

## Per-tool sources

| Tool | Source | Pinned | Why |
|---|---|---|---|
| `cargo-nextest` 0.9.146 | GitHub release `cargo-nextest-0.9.146-universal-apple-darwin.tar.gz` | yes | the official binary is the PR #296 sha256 `7a558b15…` |
| `node` 26.10.0, with its `npm` | nodejs.org `node-v26.10.0-darwin-arm64.tar.gz`, sha256 from `SHASUMS256.txt` | yes | self-contained; `npm` is the archive's `npm-cli.js`, which runs the `node` beside it on `PATH` |
| `uv` 0.12.22 | GitHub release `uv-aarch64-apple-darwin.tar.gz`, sha256 from its `.sha256` file | yes | one static binary |
| `bash` | none | no | no official macOS binary; the Homebrew bottle loads `readline`, `ncurses` and `gettext` from `/opt/homebrew/opt`, so a copy is not self-contained; a source build is not byte-stable (the PR #296 failure) |
| `git` | none | no | the Homebrew bottle loads `pcre2` and `gettext`; the hub runs the CLT `/usr/bin/git` |
| `make` | none | no | the hub runs the CLT `/usr/bin/make` (GNU Make 3.81); Homebrew installs GNU make as `gmake` |
| `python3` | none | no | the view binds `sys.executable`, the interpreter that runs `sd-check`, not a `PATH` name the gate can redirect |
| `sh`, `cc`, `c++`, `clang` | macOS and CLT | no | system files; bound with the macOS and CLT version below |
| `cargo`, `rustc` | rustup proxies | no | the tree's `rust-toolchain.toml` picks the toolchain; `-vV` is bound (sd:2881) |

Two Homebrew installs of one bottle version at one prefix are the same
bytes, so an unpinned Homebrew tool refuses only while the two machines
run different versions. The refusal names both resolved files, which carry
the Cellar version; the remedy is `brew upgrade <tool>` on the older one.

## Unpinned tools in a refusal

`view_tool` writes a `resolution` for every bound name, not only for
`cargo` and `rustc`:

- a `VERSIONED_TOOLS` name keeps its release line, or `path` (sd:2881);
- a file in the system volume (`/bin`, `/sbin`, `/usr/bin`, `/usr/sbin`)
  writes its resolved path and `system_version`;
- any other writes its resolved path, with the `HOME` prefix as `~`.

`system_version` is `macOS <version> (<build>)` and the developer tools that
`xcrun` runs: `CLT <version>` from `pkgutil` when the developer folder is the
CLT, else `Xcode <version> (<build>)` from the app's `version.plist`.
`DEVELOPER_DIR` in the gate's environment chooses the folder before
`xcode-select -p`. A system tool's digest binds that line beside its bytes,
as a `VERSIONED_TOOLS` name binds `-vV`. One process asks once per
developer folder. It runs `sw_vers`, `xcode-select` and `pkgutil` by absolute path,
so a gate's short `PATH` cannot turn one part into `unknown`.

A refusal then reads, for example:

    offload view part tools at cc (satellite via /usr/bin/cc; macOS 27.0.1 (26A434); CLT 27.0.0.0.1788430756,
    hub via /usr/bin/cc; macOS 27.0.1 (26A434); CLT 27.1.0.0.1790000000)

`resolution` is never compared; only `tools` refuses.

## Contract with machine-setup (sd:2937)

1. Pin list: `PINS` in the pack's `bin/sd_gate_tools.py`; read it as JSON with `sd gate tools status --json`.
2. Format: one object per pin for this platform: `tool`, `version`, `platform`, `url`, `sha256`, `bin`, `provides`, `folder`, `installed`.
3. Install nightly: `sd gate tools install`; exit 0 when every pin is installed, 1 naming each failure; idempotent, network only for a missing pin.
4. Copies: `<cache>/pinned-tools/<tool>-<version>-<sha256[:12]>/`, `<cache>` = `$SD_GATE_CACHE_DIR` or `${XDG_CACHE_HOME:-$HOME/.cache}/sd/gate`.
5. Run it with the `SD_GATE_CACHE_DIR` and `XDG_CACHE_HOME` the gate's callers have, or it installs where no gate looks.
6. Never write inside a copy; the gate binds its bytes. The pack never deletes one; machine-setup may delete a folder no pin names once it is a day old.
7. The gate puts `<folder>/<bin>` first on `PATH` in an opted-in repository and refuses with `run sd gate tools install` while one is missing.
8. Drift report: compare both machines' `status --json`; unpinned tools are compared by the gate's own refusal, which names each side.

## How the run and the bindings could part

| Way the tool the check runs can differ from the one bound | Guard | Test |
|---|---|---|
| The check runs the caller's tool while the view binds the pinned one, or the other way | `offload_pins` sets the check's `PATH`, and the view and binding resolve on it | `test_the_check_runs_the_pinned_copy_and_the_row_binds_it` |
| A pinned copy is missing, so the name falls through to the caller's `PATH` | `from_receipts` refuses before reuse or a run | `test_a_missing_pinned_copy_refuses_the_gate_with_the_install_command` |
| The caller's `cargo-nextest` in `CARGO_SUBCOMMANDS` shadows the pinned one | `cargo_subcommands` skips a name a pin provides | `test_a_pinned_name_is_not_copied_from_the_caller` |
| Pinning twice moves `PATH` | `offload_pins` drops the pinned entries before it prepends them | `test_pinning_twice_changes_nothing` |
| An archive other than the pinned one is installed | `install` checks the sha256 before it unpacks | `test_a_wrong_digest_installs_nothing` |
| A half-unpacked archive is read as installed | unpack into a temporary folder, rename into place | `test_an_archive_without_a_provided_name_installs_nothing` |
| An install changes a copy a gate is running | an installed folder is never written; a new pin is a new folder | `test_an_installed_copy_is_left_alone` |
| Two CLT versions run two compilers behind one shim | a system tool binds `system_version` | `test_a_system_tool_binds_the_system_version` |
| A repository that did not opt in | `whole` mode: no pinned `PATH`, no refusal | `test_a_gate_that_did_not_opt_in_gets_no_pinned_path` |

## Residual risk

- A pinned copy changed in place by hand: the view binds the bytes, so the
  two machines refuse, but neither gate says the copy is damaged.
- `bash`, `git`, `make` and `python3` still drift with Homebrew and macOS;
  the refusal names the versions.

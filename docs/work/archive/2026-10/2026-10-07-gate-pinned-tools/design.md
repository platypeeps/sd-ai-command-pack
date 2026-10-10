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
nothing. Next comes the gate's link folder (`clt_links`, below), so `git` and
`make` resolve to the Command Line Tools copies. The view, the local binding and the check resolve every name on
that `PATH`, so they bind and run the pinned copy.

`from_receipts` refuses before reuse or a run when a pinned copy is missing,
as it does for `pinned_subcommands`:

    the gate's pinned uv 0.12.23 is not installed at <folder>: run `sd gate tools install`

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
| `uv` 0.12.23 | GitHub release `uv-aarch64-apple-darwin.tar.gz`, sha256 from its `.sha256` file | yes | one static binary, the version Homebrew runs on both machines; the archive also holds `uvx` |
| `bash` | none | no | no official macOS binary; the Homebrew bottle loads `readline`, `ncurses` and `gettext` from `/opt/homebrew/opt`, so a copy is not self-contained; a source build is not byte-stable (the PR #296 failure) |
| `git` | CLT `/usr/bin/git`, through the gate's link | no archive | the Homebrew bottle loads `pcre2` and `gettext`; the CLT copy is on every Mac with a compiler |
| `make` | CLT `/usr/bin/make`, through the gate's link | no archive | GNU Make 3.81 from the CLT; Homebrew installs GNU make as `gmake` |
| `python3` | none | no | the view binds `sys.executable`, the interpreter that runs `sd-check`, not a `PATH` name the gate can redirect |
| `sh`, `cc`, `c++`, `clang` | macOS and CLT | no | system files; bound with the CLT version below |
| `cargo`, `rustc` | rustup proxies | no | the tree's `rust-toolchain.toml` picks the toolchain; the proxy's bytes and `-vV` are bound (sd:2881, decision log) |

Two Homebrew installs of one bottle version at one prefix are the same
bytes, so an unpinned Homebrew tool refuses only while the two machines
run different versions. The refusal names both resolved files, which carry
the Cellar version; the remedy is `brew upgrade <tool>` on the older one.

## Unpinned tools in a refusal

`view_tool` writes a `resolution` for every bound name, not only for
`cargo` and `rustc`:

- a `VERSIONED_TOOLS` name writes its release line, or `path`, then `at` and its resolved file (sd:2881);
- a file in the system volume (`/bin`, `/sbin`, `/usr/bin`, `/usr/sbin`)
  writes its resolved path and `system_version`;
- any other writes its resolved path, with the `HOME` prefix as `~`.

`system_version` is `macOS <version> (<build>)` and `developer_tools`, the
developer tools that `xcrun` runs: `CLT <version>` from `pkgutil` when the
developer folder is the CLT, else `Xcode <version> (<build>)` from the app's
`version.plist`.
`DEVELOPER_DIR` in the gate's environment chooses the folder before
`xcode-select -p`; it may name `Xcode.app` itself, as `xcode-select -s` takes it. A system tool's digest binds `developer_tools` beside its bytes,
as a `VERSIONED_TOOLS` name binds `-vV`; the macOS part is named, not bound. One process asks once per
developer folder. It runs `sw_vers`, `xcode-select` and `pkgutil` by absolute path,
so a gate's short `PATH` cannot turn one part into `unknown`.

A refusal then reads, for example:

    offload view part tools at cc (satellite via /usr/bin/cc; macOS 27.0.1 (26A434); CLT 27.0.0.0.1788430756,
    hub via /usr/bin/cc; macOS 27.0.1 (26A434); CLT 27.1.0.0.1790000000)

## The CLT link folder

`clt_links` keeps `<cache>/clt-links/` with one link per `CLT_TOOLS` name,
`git -> /usr/bin/git` and `make -> /usr/bin/make`. `offload_pins` makes or
mends it on every opted-in gate and puts it on `PATH` after the pinned
folders. A link that names another file is replaced by a rename, so a gate
reading it sees one link or the other. The view resolves `git` to the link,
whose real file is in `/usr/bin`, so it binds the CLT bytes and
`developer_tools`. A folder that cannot be written leaves both names to
`PATH`; the view binds what they resolve to, so a difference still refuses.

`resolution` is never compared; only `tools` refuses.

## Contract with machine-setup (sd:2937)

1. Pin list: `PINS` in the pack's `bin/sd_gate_tools.py`; read it as JSON with `sd gate tools status --json`. Pinned: `cargo-nextest` 0.9.146, `node` 26.10.0 with `npm`, `uv` 0.12.23.
2. Format: one object per pin for this platform: `tool`, `version`, `platform`, `url`, `sha256`, `bin`, `provides`, `folder`, `installed`.
3. Install nightly: `sd gate tools install`; exit 0 when every pin is installed, 1 naming each failure; idempotent, network only for a missing pin.
4. Copies: `<cache>/pinned-tools/<tool>-<version>-<sha256[:12]>/`, `<cache>` = `$SD_GATE_CACHE_DIR` or `${XDG_CACHE_HOME:-$HOME/.cache}/sd/gate`.
5. Run it with the `SD_GATE_CACHE_DIR` and `XDG_CACHE_HOME` the gate's callers have, or it installs where no gate looks.
6. Never write inside a copy; the gate binds its bytes. The pack never deletes one; machine-setup may delete a folder no pin names once it is a day old.
7. The gate puts `<folder>/<bin>` first on `PATH` in an opted-in repository and refuses with `run sd gate tools install` while one is missing.
8. Drift report: compare both machines' `status --json`; unpinned tools are compared by the gate's own refusal, which names each side.
9. The gate owns `<cache>/clt-links/` and writes it itself; `install` and `status` do not list it, and machine-setup neither writes nor deletes it.

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
| Two CLT versions run two compilers behind one shim | a system tool binds `developer_tools` | `test_a_system_tool_binds_the_developer_tools` |
| Two macOS point releases refuse a gate that runs one CLT | `macos_version` is named, not bound | `test_a_system_tool_names_the_macos_version_but_does_not_bind_it` |
| One machine's Homebrew `git` or `make` leads `PATH` | the gate's CLT links lead it | `test_git_and_make_bind_the_clt_copy_whatever_path_comes_first` |
| A link left naming another file | `clt_links` replaces it | `test_a_link_to_another_file_is_mended` |
| A pinned folder also holds another bound name, such as `cargo` | `install` refuses that archive | `test_an_archive_that_also_holds_another_bound_name_installs_nothing` |
| A repository that did not opt in | `whole` mode: no pinned `PATH`, no refusal | `test_a_gate_that_did_not_opt_in_gets_no_pinned_path` |

## Residual risk

- A pinned copy changed in place by hand: the view binds the bytes, so the
  two machines refuse, but neither gate says the copy is damaged.
- `bash` and `python3` still drift with Homebrew and macOS; the refusal
  names the versions. `git` and `make` drift with the CLT, which binds.
- The `/usr/bin` shims of two macOS releases may differ in bytes: they then
  refuse though the CLT matches, and the refusal names both macOS versions.
- A pinned folder also puts the names it does not bind on `PATH`: `uvx`, and
  `npx` and `corepack` beside `node`. Each comes from the pinned archive, so
  both machines run one release, but no view binds it.
- `cargo` and `rustc` refuse while two machines run different rustup
  installs, though `-vV` matches (decision log).

## Decision log

| Date | Decision | Reasons |
|---|---|---|
| 2026-10-07 | A system file binds the CLT or Xcode version, not the macOS version; the refusal names both | Lead ruling. The CLT version picks the compiler behind the `/usr/bin` shims. The macOS version picks neither, and the shim bytes are bound anyway, so binding it only refused gates a point release apart. |
| 2026-10-07 | `git` and `make` run the CLT copy through the gate's own link folder, bound with the CLT version | #296 refused at `git`: Homebrew's copy led one machine's `PATH`. No release archive of either is self-contained. A link folder chooses two names; putting `/usr/bin` first would also choose `bash` and `python3`. |
| 2026-10-07 | `uv` pin 0.12.23 | Both machines run Homebrew `uv` 0.12.23. The sha256 `50487ae5…` is from the release's `.sha256` file and matches the downloaded archive. |
| 2026-10-07 | The `cargo-nextest` folder holds only `cargo-nextest`, and `install` refuses an archive whose `bin` holds a bound name it does not pin | `tar tzvf` of the 0.9.146 archive lists one file. So a pinned folder first on `PATH` never brings a `cargo` ahead of the machine's own, and `~/.cargo/bin` need not lead `PATH`. The guard keeps that true for a later pin. |
| 2026-10-07 | `cargo` and `rustc` keep binding the proxy's bytes beside `-vV`; the resolution adds the resolved file | Homebrew's `rustup` `cargo` is a script that sets `RUSTUP_OVERRIDE_UNIX_FALLBACK_SETTINGS` before it runs the toolchain, and `-vV` does not show such a wrapper (sd:2881, `test_another_wrapper_refuses_though_it_runs_the_same_toolchain`). Dropping the bytes would pass a wrapper that changes what runs. The cost is a refusal while the two machines install rustup differently; the refusal now names both files, such as `~/.cargo/bin/cargo` and `/opt/homebrew/Cellar/rustup/1.29.1/bin/cargo`, and the remedy is one rustup install on both. |

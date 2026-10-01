# Optional deterministic-check receipts

Read this before explicitly recording or reusing local check evidence.
Default checking and review do not enable reuse.
Local receipts do not replace required CI or completed independent review coverage.

## Eligibility and declaration

The checkout must be clean and committed, without staged, unstaged, or untracked changes.
Track `.github/sd-check-reuse.json` in that checkout.
The declaration requires exactly these keys and values:

```json
{
  "schema_version": 1,
  "complete": true,
  "network": "none",
  "dependencies": ["src", "tests", "pyproject.toml"],
  "tools": ["python3"],
  "environment": ["TEST_WORKERS"]
}
```

This example shows the schema, not an approved dependency inventory for this repository.
Two optional keys, `secret_name_exceptions` and `build_outputs`, may join them; the next section describes them.
Audit the actual command before asserting `complete: true`.
Each list contains unique, nonempty strings.
Use existing repository-relative files or directories as dependency roots.
Declared directories are fingerprinted recursively.
Explicitly declared dependencies may include ignored or local files; undeclared ignored inputs are not covered.
Declared roots cannot be absolute or contain `..`.
Dependency roots and descendants reject `.git` and secret-looking names before fingerprinting.
List a source file whose name only looks secret, such as `src/token.rs`, in `secret_name_exceptions`.
Each exception is an exact repository-relative path to a tracked regular file inside a declared root.
Patterns, directories, untracked or ignored files, and unused entries make the declaration unsupported.
Every other secret-looking name stays rejected.

Declare each ignored folder the check builds, such as `target`, in `build_outputs`.
Map it to the variable that redirects the build, such as `"target": "CARGO_TARGET_DIR"`, or to `null`.
A recorded run gets a fresh, empty temporary folder in that variable, removed after the run.
The operator's own folder is never deleted, moved, hashed, or reused.
For an output mapped to `null`, recording refuses while the folder exists.
A build output cannot hold a tracked file or overlap a dependency root or exception.
Its variable cannot be a declared or base variable, or a secret-looking name.
Symlinks and nonregular dependency entries are unsupported.
Name checks do not prove that file contents contain no credentials.
Do not declare secret material.

List every additional executable the check invokes under `tools`.
Detected command executables also contribute to the binding.
Recording runs with only `PATH`, `HOME`, `LANG`, `LC_ALL`, `TMPDIR`, and declared environment variables.
Declared names must be valid variable identifiers.
Names containing `KEY`, `TOKEN`, `SECRET`, `PASSWORD`, `CREDENTIAL`, `COOKIE`, or `AUTH` are rejected, ignoring case.
The binding fingerprints the declared variables only; their values are not stored in the binding.
`PATH`, `HOME`, `LANG`, `LC_ALL`, and `TMPDIR` are not fingerprinted unless the declaration lists them.
The tools and toolchains that `PATH` selects are bound by path and bytes instead.
The receipt includes typed check output; do not run a command that prints secrets.

This declaration is an operator assertion, not enforced hermeticity or OS read confinement.
Never enable reuse when the command reads undeclared ignored files, environment, or external dependencies, or requires network access.
Unknown dependency completeness disables reuse.
Do not enable it for this pack's network-dependent full gate.

## Record and reuse

Run `sd-check --record-receipt --json` for an eligible full check.
Use `--database PATH` only with receipt recording when selecting an explicitly provisioned database.
Otherwise the operator's default database applies.
`--only` and `--dry-run` cannot record a receipt.

Recording invalidates the previous pass before starting the check.
Only complete success with identical before-and-after bindings produces a reusable checkpoint.
Failed, partial, interrupted, or changed-input runs leave no reusable pass.
Concurrent checkpoint changes refuse through revision checks.
Report `receipt_error` separately from the underlying check results.

Use `sd-review --reuse-check` for per-run opt-in.
Shipping prepare and standalone review accept the same `--reuse-check` flag.
Use the same explicit database selection when the receipt was stored outside the default database.
A missing, stale, malformed, or foreign receipt causes the normal deterministic check to run.
Legacy runner receipts always rerun because they lack complete identity evidence.

## Identity boundaries

Bindings include canonical checkout, HEAD, tree, full check invocation, detected commands, and detection source.
They also include checker implementation, relevant policy/configuration, runtime/tool identity, declared dependency bytes, and declared environment identity.
When `rustup` is on the controlled `PATH`, each tool that `rustup which` names binds its whole toolchain directory by content.
A toolchain name or version alone never binds it.
Reuse rechecks the binding before accepting the saved result.
Changing any bound input invalidates reuse.
The same Git tree alone is insufficient.

Supported structure does not prove that the declared inputs describe an arbitrary command completely.
When evidence cannot establish eligibility, run the check instead of weakening the declaration.

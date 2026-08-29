# Implementation Plan

1. Update the template shell parser and merge gate with exact-head evidence.
2. Add missing, stale, matching, and malformed-head regression cases.
3. Align source skills, adapters, and documentation with the new command form.
4. Bump the patch version and changelog, then regenerate all derived surfaces.
5. Run `make sync`, focused tests, candidate validation, and `make check`.
6. Commit, push the feature branch, and open an upstream pull request with the
   required tooling/generated scope declaration.

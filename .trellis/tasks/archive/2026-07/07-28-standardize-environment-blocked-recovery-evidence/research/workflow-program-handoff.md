# Handoff: environment-blocked + idempotent-retry scenarios for 07-22

Inbound scenario set produced by
`07-28-standardize-environment-blocked-recovery-evidence` for the coupled
lifecycle matrix owned by `07-22-validate-sd-workflow-program-integration`.

Package 11 owns the production behavior and the focused fixtures below; 07-22
consumes these rows into its S-scenario matrix and cites the named test as the
evidence location. Per 07-22 design, the integration task references — it does
not reimplement — this child's behavior. Owner task for every row:
`07-28-standardize-environment-blocked-recovery-evidence`. Run any test with
`PYTHONPATH="templates/scripts:tests:." .venv/bin/python -m unittest <module>`.

## Environment-blocked emission (per boundary / owning operation)

| ID | Boundary | Owning operation | mutationState | Evidence test (module::name) | Expected observed result |
|----|----------|------------------|---------------|------------------------------|--------------------------|
| EB01 | tool-cache | toolchain cache setup (shared lib) | none | test_script_lib::test_cache_env_main_json_failure_emits_validated_fragment | `--json` failure emits one validated `environment_blocked` fragment; plaintext path unchanged |
| EB02 | tool-cache | toolchain cache setup, retry advertised | none | test_script_lib::test_cache_setup_blocked_evidence_is_retryable_tool_cache | `retryable: true` only with a known mutation state |
| EB03 | user-state | work-loop private state dir create | none | test_work_loop::test_ensure_private_directory_classifies_mkdir_block_as_user_state | mkdir refusal classified `user-state`, not a repo defect |
| EB04 | user-state | work-loop CLI state write | none | test_work_loop::test_cli_state_write_block_emits_environment_fragment | CLI emits the fragment; prior exit/fail-closed behavior retained |
| EB05 | git-metadata | record-session / finish-work recorder | partial-recoverable | test_record_session::test_record_session_wrapper_emits_git_metadata_block_under_json | recorder `--json` emits a `git-metadata` block at its checkpoint |
| EB06 | git-metadata + kb-target | housekeeping fetch/prune, branch delete, KB refresh | mixed | test_housekeeping_result::test_environment_boundary_anomalies_attach_structured_blocks | only environment codes attach blocks; each is `validate_environment_blocked_evidence`-clean, no `://` in diagnostic |
| EB07 | kb-target | update-spec-kb refresh | partial-recoverable | test_update_spec_kb::test_update_spec_kb_refresh_block_emits_kb_target_fragment | refresh block names `kb-target` / `kb-refresh`; plaintext path omits the fragment |
| EB08 | kb-target | update-spec-kb inspect (read path) | none | test_update_spec_kb::test_update_spec_kb_inspect_block_emits_none_mutation_fragment | read-path block reports `mutationState: none` |

## Idempotent-retry (retry resumes without duplicating work)

| ID | Owning operation | Evidence test (module::name) | Expected observed result |
|----|------------------|------------------------------|--------------------------|
| IR01 | update-spec-kb refresh | test_update_spec_kb::test_update_spec_kb_refresh_block_is_retryable_via_idempotent_reconcile | two runs produce an identical `.obsidian-kb` tree hash; no duplicated entries |
| IR02 | record-session recorder | test_record_session::test_record_session_wrapper_reuses_uncommitted_retry_entry | retry reuses the uncommitted entry rather than appending a second journal entry |
| IR03 | record-session recorder (untracked) | test_record_session::test_record_session_wrapper_reuses_untracked_workspace_retry_entry | retry over an untracked workspace reuses the same entry |
| IR04 | work-loop cache remediation | test_work_loop::test_run_git_does_not_duplicate_cache_setup_remediation | repeated cache-setup failure does not duplicate the remediation |
| IR05 | work-loop verified advance | test_work_loop::test_verified_live_advance_is_idempotent_and_unverified_advance_is_red | a verified advance is idempotent; an unverified advance stays red |

## Cross-command contract invariants (shared composer / validator)

| ID | Invariant | Evidence test (module::name) |
|----|-----------|------------------------------|
| IC01 | Every supported boundary composes | test_script_lib::test_environment_evidence_builds_every_boundary |
| IC02 | Unknown boundary / mutation state rejected (no guessing) | test_script_lib::test_environment_evidence_rejects_unknown_boundary_and_state |
| IC03 | Retry requires a known, provable mutation state | test_script_lib::test_environment_evidence_retry_requires_known_mutation_state |
| IC04 | Diagnostic redacted and size-bounded | test_script_lib::test_environment_evidence_redacts_and_bounds_diagnostic |
| IC05 | `recoveryAction` argv is bounded data, malformed rejected | test_script_lib::test_environment_evidence_recovery_action_argv_is_bounded_data, ::test_environment_evidence_recovery_action_rejects_malformed |
| IC06 | Validator drops unknown fields, rejects bad fragments | test_script_lib::test_environment_evidence_validator_rejects_and_drops_unknown |

## Fail-safe / no authority expansion

| ID | Property | Evidence test (module::name) |
|----|----------|------------------------------|
| FS01 | A block is additive and never changes `outcome` | test_housekeeping_result::test_environment_block_is_additive_and_does_not_alter_outcome |
| FS02 | Policy anomalies emit no block (no over-classification into the contract) | test_housekeeping_result::test_policy_anomalies_emit_no_environment_block |

## Notes for the integration owner

- The `managed-payload` boundary is a reserved enum value in this release; no
  owner emits it yet, so 07-22 needs no managed-payload row until a producer
  lands.
- No row above authorizes a merge, branch deletion, archive, force operation,
  or broad cleanup; that invariant is the R6 skill-render contract documented in
  `sd-help/references/environment-blocked-recovery.md`.

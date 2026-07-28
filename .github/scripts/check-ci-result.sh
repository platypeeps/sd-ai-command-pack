#!/usr/bin/env bash

set -euo pipefail

if [ "$#" -ne 8 ]; then
  printf '%s\n' "usage: check-ci-result.sh <event> <scope-result> <mode> <unittest> <lint> <security> <release-payload> <main-push-scope>" >&2
  exit 2
fi

event_name="$1"
scope_result="$2"
scope_mode="$3"
unittest_result="$4"
lint_result="$5"
security_result="$6"
release_payload_result="$7"
main_push_scope_result="$8"

printf '%s\n' \
  "event=$event_name ci_scope=$scope_result mode=$scope_mode unittest=$unittest_result lint=$lint_result security=$security_result release_payload_gate=$release_payload_result main_push_scope=$main_push_scope_result"

case "$event_name" in
  pull_request|push)
    ;;
  *)
    printf '%s\n' "CI Result received an unsupported event." >&2
    exit 1
    ;;
esac

if [ "$scope_result" != "success" ]; then
  printf '%s\n' "The CI scope lane did not succeed." >&2
  exit 1
fi

case "$scope_mode" in
  full)
    if [ "$unittest_result" != "success" ] || [ "$lint_result" != "success" ] || [ "$security_result" != "success" ]; then
      printf '%s\n' "A required full-CI lane did not succeed." >&2
      exit 1
    fi
    if [ "$event_name" = "pull_request" ]; then
      if [ "$release_payload_result" != "success" ] || [ "$main_push_scope_result" != "skipped" ]; then
        printf '%s\n' "The pull-request full-CI lane combination is inconsistent." >&2
        exit 1
      fi
    elif [ "$release_payload_result" != "skipped" ] || [ "$main_push_scope_result" != "success" ]; then
      printf '%s\n' "The main-push full-CI lane combination is inconsistent." >&2
      exit 1
    fi
    ;;
  bookkeeping)
    if [ "$unittest_result" != "skipped" ] || [ "$lint_result" != "skipped" ] || [ "$security_result" != "skipped" ] || [ "$release_payload_result" != "skipped" ]; then
      printf '%s\n' "Bookkeeping CI requires every expensive lane to be skipped." >&2
      exit 1
    fi
    if [ "$event_name" = "pull_request" ]; then
      if [ "$main_push_scope_result" != "skipped" ]; then
        printf '%s\n' "The pull-request bookkeeping lane combination is inconsistent." >&2
        exit 1
      fi
    elif [ "$main_push_scope_result" != "success" ]; then
      printf '%s\n' "The main-push bookkeeping lane requires the direct-push scope backstop." >&2
      exit 1
    fi
    ;;
  *)
    printf '%s\n' "CI Result received an unrecognized scope mode." >&2
    exit 1
    ;;
esac

printf '%s\n' "CI Result accepted the $scope_mode mode lane combination."

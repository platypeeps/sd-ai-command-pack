#!/bin/sh
# A fake of the system checkout's adversarial-gate.sh for the dashboard's
# tests (sd:6044): `run` and `deep` only. It renders a one-line lens with each
# --set KEY=VALUE in place of {KEY}, then runs the `codex` on PATH, or
# $CLAUDE_BIN in the checkout, with the argv the real gate gives them.
set -eu

die() { echo "adversarial-gate: $*" >&2; exit 1; }

lens() {
  case "$1" in
    task)   echo 'The document is a work item. Read `{INPUT_PATH}` and `{DESIGN_PATH}`.' ;;
    brief)  echo 'The document is a brief. Read `{INPUT_PATH}`.' ;;
    repo)   echo 'The document is a whole repository, `{REPO_NAME}`, the checkout you are in.' ;;
    change) echo 'The document is a proposed change. Run `git diff {BASE}...{HEAD}`; read `{INPUT_PATH}`.' ;;
    deep)   echo 'The document is a whole repository, `{REPO_NAME}`. **Use at most {AGENTS} areas.**' ;;
    source) echo 'A fetch that failed is not evidence. Read `{INPUT_PATH}`.' ;;
    *) die "no such lens: $1" ;;
  esac
}

verb="${1:-}"
[ "$verb" = run ] || [ "$verb" = deep ] || die "the fake gate runs only run and deep, not '$verb'"
shift
name="" sets="" repo="" out="" model="" effort=""
while [ $# -gt 0 ]; do
  case "$1" in
    --lens) name="$2" ;;
    --set) sets="$sets
$2" ;;
    --repo) repo="$2" ;;
    --out) out="$2" ;;
    --model) model="$2" ;;
    --effort) effort="$2" ;;
    --timeout) ;;
    *) die "$verb: unexpected argument '$1'" ;;
  esac
  shift 2
done
prompt=$(lens "$name" | GATE_SETS="$sets" awk '
  BEGIN { n = split(ENVIRON["GATE_SETS"], lines, "\n")
          for (i = 1; i <= n; i++) if ((eq = index(lines[i], "=")) > 0) {
            k[++m] = "{" substr(lines[i], 1, eq - 1) "}"; v[m] = substr(lines[i], eq + 1) } }
  { for (i = 1; i <= m; i++) while ((p = index($0, k[i])) > 0)
      $0 = substr($0, 1, p - 1) v[i] substr($0, p + length(k[i]))
    print }')
if [ "$verb" = run ]; then
  echo "# adversarial gate: read-only sandbox, $repo -> $out" >&2
  printf '%s\n' "$prompt" | codex exec -m "$model" -c "model_reasoning_effort=$effort" -s read-only -C "$repo" -o "$out" -
else
  tools="Read,Grep,Glob,Agent"
  cd "$repo"
  printf '%s\n' "$prompt" | "$CLAUDE_BIN" -p --tools "$tools" --allowedTools "$tools" --effort "$effort" \
    --model "$model" > "$out"
fi

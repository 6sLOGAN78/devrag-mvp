#!/usr/bin/env bash
# Gate: go.mod must not require a newer Go than the installed toolchain, and the toolchain
# must not be downloaded implicitly (R-57).
set -euo pipefail

root="."
while [ $# -gt 0 ]; do
  case "$1" in
    --root) root="$2"; shift 2 ;;
    *) shift ;;
  esac
done

gomod="$root/go.mod"
if [ ! -f "$gomod" ]; then
  echo "skipped: no go.mod"
  exit 0
fi
if ! command -v go >/dev/null 2>&1; then
  echo "FAIL: go.mod exists but no go toolchain is installed"
  exit 1
fi

directive=$(awk '$1 == "go" { print $2; exit }' "$gomod")
if [ -z "$directive" ]; then
  echo "FAIL: go.mod has no go directive"
  exit 1
fi
if grep -qE '^toolchain ' "$gomod"; then
  echo "FAIL: go.mod pins a toolchain line, which would trigger a download"
  exit 1
fi
installed=$(go version | awk '{ sub(/^go/, "", $3); print $3 }')

# Compare dotted versions: pad a bare 1.25 to 1.25.0.
norm() { awk -F. '{ printf "%d.%d.%d", $1, $2, ($3 == "" ? 0 : $3) }' <<<"$1"; }
need=$(norm "$directive")
have=$(norm "$installed")
newest=$(printf '%s\n%s\n' "$need" "$have" | sort -V | tail -n1)
if [ "$newest" != "$have" ]; then
  echo "FAIL: go.mod requires go $directive but the installed toolchain is $installed"
  exit 1
fi
echo "go toolchain OK: go.mod $directive, installed $installed"

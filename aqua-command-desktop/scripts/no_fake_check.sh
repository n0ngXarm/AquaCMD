#!/usr/bin/env bash
set -euo pipefail
root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
roots=()
for name in src server collector desktop/f1_api desktop/f1_api_view.py desktop/f3_api desktop/f3_api_view.py desktop/f3_projection.py; do
    if [[ -d "$root/$name" || -f "$root/$name" ]]; then roots+=("$root/$name"); fi
done
if [[ ${#roots[@]} -eq 0 ]]; then
    printf '%s\n' 'no_fake_check: ERROR (no production source directories)' >&2
    exit 2
fi
pattern='mock|fake|faker|Math[.]random|random[.](random|randint|uniform|choice)'
failed=0
for directory in "${roots[@]}"; do
    set +e
    grep -RInEi --binary-files=without-match --exclude-dir=__pycache__ \
        --include='*.py' --include='*.js' --include='*.mjs' --include='*.ts' \
        --include='*.tsx' --include='*.jsx' --include='*.json' --include='*.sql' \
        --include='*.html' --include='*.css' \
        "$pattern" "$directory"
    code=$?
    set -e
    case "$code" in
        0) failed=1 ;;
        1) ;;
        *) printf 'no_fake_check: ERROR (grep exit %s)\n' "$code" >&2; exit "$code" ;;
    esac
done
if [[ $failed -ne 0 ]]; then
    printf '%s\n' 'no_fake_check: FAIL (forbidden tokens shown above)' >&2
    exit 1
fi
printf '%s\n' 'no_fake_check: PASS'

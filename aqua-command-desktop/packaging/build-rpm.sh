#!/bin/sh
set -eu
aqua_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
aqua_build=${1:?Usage: build-rpm.sh /absolute/build-directory}
aqua_spec="$aqua_root/packaging/aqua-command-desktop.spec"
if [ -z "${SOURCE_DATE_EPOCH:-}" ]; then
    SOURCE_DATE_EPOCH=$(git -C "$aqua_root" log -1 --format=%ct 2>/dev/null || stat -c %Y "$aqua_spec")
fi
case "$SOURCE_DATE_EPOCH" in
    ''|*[!0-9]*) echo 'SOURCE_DATE_EPOCH must be a nonnegative integer' >&2; exit 2 ;;
esac
export SOURCE_DATE_EPOCH
mkdir -p "$aqua_build/tmp" "$aqua_build/SOURCES" "$aqua_build/SPECS" "$aqua_build/RPMS" "$aqua_build/SRPMS" "$aqua_build/BUILD" "$aqua_build/BUILDROOT"
aqua_build=$(CDPATH= cd -- "$aqua_build" && pwd)
tar --sort=name --mtime="@$SOURCE_DATE_EPOCH" --owner=0 --group=0 --numeric-owner \
    --exclude=.git --exclude=__pycache__ --exclude='*.pyc' --exclude='*.rpm' \
    --exclude=build --exclude=local-data --exclude=node_modules \
    --exclude=tests --exclude='*test*.py' --exclude='*.test.js' --exclude='*.test.mjs' \
    --exclude='*.db*' --exclude='*.sqlite*' --exclude='*.tmp' --exclude='.env*' \
    --exclude='*.pem' --exclude='*.key' --exclude='*.pfx' --exclude='*.p12' \
    --transform='s,^,aqua-command-desktop-0.9.0/,' -czf "$aqua_build/SOURCES/aqua-command-desktop-0.9.0.tar.gz" \
    -C "$aqua_root" LICENSE README.md VERIFICATION.md backend collector config desktop docs packaging src
# Review the exact source archive before rpmbuild consumes it. This guard also
# works when rebuilding from an extracted source archive without a Git checkout.
mkdir -p "$aqua_build/privacy-input"
tar -xzf "$aqua_build/SOURCES/aqua-command-desktop-0.9.0.tar.gz" -C "$aqua_build/privacy-input"
python3 "$aqua_root/packaging/privacy_preflight.py" \
    --directory "$aqua_build/privacy-input/aqua-command-desktop-0.9.0"
cp "$aqua_spec" "$aqua_build/SPECS/"
rpmbuild --define "_topdir $aqua_build" --define "_tmppath $aqua_build/tmp" \
    --define "_buildhost aquacmd-build" --define "source_date_epoch_from_changelog 0" \
    --define "use_source_date_epoch_as_buildtime 1" --define "clamp_mtime_to_source_date_epoch 1" -bb "$aqua_build/SPECS/aqua-command-desktop.spec"

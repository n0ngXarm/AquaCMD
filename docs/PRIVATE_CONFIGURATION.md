# Private configuration and rollback

## Desktop catalogs and mappings

Catalog selection uses `AQUACMD_CATALOG_PATH` when explicitly supplied, even if
that file is missing. Otherwise it checks the existing desktop private config
directory's `catalog/Export all.txt`, then legacy `~/Downloads/Export all.txt`.
There is no repository catalog fallback; no catalog is copied into a public
build. A missing catalog opens an empty workspace.

The existing desktop config directory is unchanged. Its
`opcua_tag_mapping.json` precedes the empty factory template under `config/`.
Existing private files, SQLite databases, exact Tag spelling, NodeIds, namespace
URIs and import/export formats are unchanged. This work does not rename private
Tags, rewrite existing mappings, or migrate database contents.

## Separate CLI credentials

`python3 main.py setup` accepts credentials only through terminal secure input.
Blank credential input keeps the configured value. Unavailable secure input
fails before reading a piped credential or changing configuration.

The write target is `AQUACMD_ENV_FILE`, or
`${XDG_CONFIG_HOME:-~/.config}/aqua-command/pwa.env`. Profiles inside the source
tree, symlink paths and files owned by another user are rejected. On Linux the
private directory is mode 0700; profile and backup files are mode 0600. Windows
CLI writes fail closed until owner-only ACL handling is separately verified.

Load precedence is process environment, selected private profile, then a legacy
repository `.env` only when no private profile or explicit selection exists.
An explicit missing profile never loads a different profile. Legacy input is
read-only. Setup preserves unknown keys and creates an exact owner-only
`pwa.env.bak` before replacing the private profile. Credentials belong in these
files, never CLI arguments, logs, Git, packages, or evidence bundles.

Writes use a same-directory temporary file, file fsync, atomic rename, and
directory fsync. A pre-rename failure keeps the old profile intact. If rename
succeeds but directory sync fails, setup exits nonzero and explicitly reports
uncertain durability; do not treat that result as an unchanged file. These are
filesystem fault tests, not proof of power-loss recovery.

## Rollback

Stop the CLI first. Copy the selected `.env.bak` to a new owner-only temporary
file in the same private directory, then atomically replace the private profile.
Retain mode 0600 and directory mode 0700. Alternatively remove only the newly
created private profile after preserving it privately; the untouched legacy
configuration becomes eligible on next start unless an explicit path remains.
Do not paste credential contents into a shell command or report.

Source rollback uses the previous local branch/commit; this remediation has not
installed over the operator's existing application. Existing desktop mappings,
databases and legacy catalog files need no rollback because they were not
modified. Never restore quarantined private assets into a public checkout.

## Distribution guard and remaining gates

The pre-commit hook checks staged blobs, including files whose working-tree
copies were changed afterward. Token shapes, private key headers, personal home
paths, runtime/artifact filenames and populated factory mappings are rejected.
Unrecognized binary data is rejected; five bundled public fonts require exact
reviewed SHA-256 hashes. `AQUACMD_PRIVATE_CATALOG` or `--private-catalog` enables
additional exact private Tag comparison without storing that catalog. The build
guard checks the exact extracted source archive before rpmbuild.

Hooks are local opt-in and can be bypassed; separate release review remains
required. Current-source scans do not clear existing Git ancestry, identify
every possible secret, or prove exposed credentials were revoked. Rotation is
PENDING_OWNER_ACTION. No branch with historical private blobs is approved for
public push by this change.

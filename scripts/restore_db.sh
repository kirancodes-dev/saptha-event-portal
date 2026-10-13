#!/usr/bin/env bash
# Restore a backup made by scripts/backup_db.sh into an EMPTY database (UPG-21).
# See docs/DEPLOY.md, "Restore drill".
#
#   scripts/restore_db.sh <s3://... | gs://... | local file> <target postgresql:// URL>
#
# It refuses a target that already has tables, so it can't overwrite a live
# database by mistake. Restore into a new database, check it, then point the
# app's DATABASE_URL at it. Uses S3_ENDPOINT_URL / AWS_* like the backup.
set -euo pipefail

src="${1:?usage: restore_db.sh <dump: s3://, gs:// or a file> <target DATABASE_URL>}"
target="${2:?usage: restore_db.sh <dump> <target DATABASE_URL>}"

tables="$(psql "$target" -Atc "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public'")"
if [ "$tables" != "0" ]; then
  echo "The target database already has $tables table(s). Restore into an empty database." >&2
  exit 3
fi

workdir="$(mktemp -d)"
trap 'rm -rf "$workdir"' EXIT
dump="$workdir/restore.dump"
case "$src" in
  s3://*)
    if [ -n "${S3_ENDPOINT_URL:-}" ]; then aws --endpoint-url "$S3_ENDPOINT_URL" s3 cp "$src" "$dump" --only-show-errors
    else aws s3 cp "$src" "$dump" --only-show-errors; fi ;;
  gs://*) gcloud storage cp "$src" "$dump" --quiet ;;
  *) cp "$src" "$dump" ;;
esac

pg_restore --no-owner --no-privileges --exit-on-error --dbname="$target" "$dump"
echo "Restored. Row counts per table:"
psql "$target" -Atc "SELECT relname || ': ' || n_live_tup FROM pg_stat_user_tables ORDER BY relname"
echo "Run 'ANALYZE;' for exact counts, then 'alembic current' to see the schema revision."

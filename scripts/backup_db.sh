#!/usr/bin/env bash
# Daily PostgreSQL backup to a private bucket (UPG-21). See docs/DEPLOY.md, "Backups".
#
#   DATABASE_URL           the database to dump (postgresql://...)
#   BACKUP_BUCKET          s3://bucket/prefix or gs://bucket/prefix (a PRIVATE bucket)
#   BACKUP_RETENTION_DAYS  delete dumps older than this many days (default 30)
#   S3_ENDPOINT_URL        for an S3-compatible service such as Supabase Storage
#   AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY / AWS_DEFAULT_REGION   for s3://
#   (gs:// uses the gcloud credentials of whoever runs it)
#
# Needs pg_dump of the server's major version or newer, and the aws or gcloud CLI.
# The dump holds every record of every person: it never touches the repository,
# and the local copy is deleted when the script ends.
set -euo pipefail

: "${DATABASE_URL:?DATABASE_URL is not set}"
: "${BACKUP_BUCKET:?BACKUP_BUCKET is not set (s3://... or gs://...)}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-30}"
BUCKET="${BACKUP_BUCKET%/}"

workdir="$(mktemp -d)"
trap 'rm -rf "$workdir"' EXIT
name="saptha-$(date -u +%Y%m%dT%H%M%SZ).dump"
dump="$workdir/$name"

echo "Dumping the database..."
pg_dump --format=custom --no-owner --no-privileges --file="$dump" "$DATABASE_URL"
pg_restore --list "$dump" > /dev/null   # fails if the dump is unreadable
echo "Dump ok: $(du -h "$dump" | cut -f1)"

aws_s3() {
  if [ -n "${S3_ENDPOINT_URL:-}" ]; then aws --endpoint-url "$S3_ENDPOINT_URL" s3 "$@"; else aws s3 "$@"; fi
}

case "$BUCKET" in
  s3://*)
    aws_s3 cp "$dump" "$BUCKET/$name" --only-show-errors
    listing="$(aws_s3 ls "$BUCKET/" | awk '{print $4}')"
    delete() { aws_s3 rm "$BUCKET/$1" --only-show-errors; }
    ;;
  gs://*)
    gcloud storage cp "$dump" "$BUCKET/$name" --quiet
    listing="$(gcloud storage ls "$BUCKET/" | sed 's#.*/##')"
    delete() { gcloud storage rm "$BUCKET/$1" --quiet; }
    ;;
  *)
    echo "BACKUP_BUCKET must start with s3:// or gs://" >&2; exit 2 ;;
esac
echo "Uploaded $BUCKET/$name"

# Retention: dump names carry their UTC date, so compare names, not file times.
cutoff="saptha-$(date -u -d "-$RETENTION_DAYS days" +%Y%m%d 2>/dev/null || date -u -v-"$RETENTION_DAYS"d +%Y%m%d)"
removed=0
for old in $listing; do
  case "$old" in saptha-*.dump) ;; *) continue ;; esac
  if [[ "$old" < "$cutoff" ]]; then delete "$old"; removed=$((removed + 1)); fi
done
echo "Removed $removed dump(s) older than $RETENTION_DAYS days."

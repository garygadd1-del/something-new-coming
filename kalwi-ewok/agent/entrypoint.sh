#!/bin/sh
# One stub task, then exit. No listeners and no background work.
set -eu

if [ "$#" -ne 0 ]; then
  echo "kalwi-ewok: arguments are not accepted" >&2
  exit 2
fi

uid=$(id -u)
if [ "$uid" = "0" ]; then
  echo "kalwi-ewok: refusing to run as root" >&2
  exit 2
fi

role="${KALWI_ROLE:?KALWI_ROLE is required}"
task="${KALWI_TASK:-stub}"
gpu="${KALWI_GPU:-off}"
prod="${KALWI_PROD_DEPLOY:-0}"
money="${KALWI_MONEY_SENDS:-0}"
secrets="${KALWI_SECRETS:-none}"

if [ "$gpu" != "off" ]; then
  echo "kalwi-ewok: refusing KALWI_GPU=$gpu" >&2
  exit 2
fi

if [ "$prod" != "0" ] || [ "$money" != "0" ] || [ "$secrets" != "none" ]; then
  echo "kalwi-ewok: hard gate refused prod, money, or secrets" >&2
  exit 2
fi

if [ "$task" != "stub" ]; then
  echo "kalwi-ewok: only the stub task is available" >&2
  exit 2
fi

case "$role" in
  kalwi-render|kalwi-ledger|kalwi-scout) ;;
  *)
    echo "kalwi-ewok: unknown role $role" >&2
    exit 2
    ;;
esac

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
if [ -d "$script_dir/skills/hooks" ]; then
  hook_root="$script_dir/skills/hooks"
elif [ -d "$script_dir/../skills/hooks" ]; then
  hook_root=$(CDPATH= cd -- "$script_dir/../skills/hooks" && pwd)
else
  echo "kalwi-ewok: baked skill hooks are missing" >&2
  exit 2
fi

echo "kalwi-ewok: spawn role=$role task=$task gpu=off"
hook_dir="$hook_root/$role"
found=0
for hook in "$hook_dir"/*.sh; do
  if [ -f "$hook" ]; then
    found=1
    echo "kalwi-ewok: hook $hook"
    /bin/sh "$hook"
  fi
done
if [ "$found" -ne 1 ]; then
  echo "kalwi-ewok: no stub hook for $role" >&2
  exit 2
fi

echo "kalwi-ewok: die-clean role=$role"
exit 0

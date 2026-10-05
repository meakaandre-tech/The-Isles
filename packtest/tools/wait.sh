#!/bin/bash
# usage: wait.sh [max-seconds] [out-dir] -> waits for the pack-test run of HEAD, then unpacks the ci-logs branch into out-dir
cd "$(dirname "$0")/../.."
sha=$(git rev-parse --short=7 HEAD); end=$(( $(date +%s) + ${1:-560} )); o=${2:-/tmp/isles263/out}
while :; do
  st=$(gh api "repos/meakaandre-tech/The-Isles/actions/runs?per_page=5" --jq "[.workflow_runs[] | select(.head_branch==\"pack-test\")][0] | \"\(.status) \(.conclusion) \(.head_sha[0:7])\"")
  case "$st" in completed*$sha) break;; esac
  if [ $(date +%s) -ge $end ]; then   # still running: show the snapshot the run pushed
    echo "still running: $st"; git fetch -q origin ci-logs && { rm -rf $o; mkdir -p $o; git archive FETCH_HEAD | tar -x -C $o; cat $o/commit.txt; grep '^\[' $o/run.txt | tail -${3:-12}; }
    exit 1
  fi
  sleep 20
done
echo "$st"
git fetch -q origin ci-logs
[ "$(git show FETCH_HEAD:commit.txt | cut -c1-7)" = "$sha" ] || echo "WARNING: logs are for another commit"
rm -rf $o; mkdir -p $o; git archive FETCH_HEAD | tar -x -C $o
ls $o | tr '\n' ' '; echo; grep '^\[' $o/run.txt

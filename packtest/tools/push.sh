#!/bin/bash
# usage: push.sh "message" [paths...] -> commit (everything, or only the paths) on pack-test and push
cd "$(dirname "$0")/../.."
msg=$1; shift
if [ $# -gt 0 ]; then git add -A -- "$@"; else git add -A; fi
git commit -q --allow-empty -m "$msg

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01GKaUgBKxTjJi7CdM5RT2V2"
git push -q origin pack-test 2>&1 | grep -v "^remote:" | tail -1
git rev-parse --short=7 HEAD

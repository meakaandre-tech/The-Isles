#!/bin/bash
# On the machine of whoever has the providers without a public download (see vendor-recv.sh):
#   vendor-send.sh [minutes, default 30]
# Watches the ci-key-<job> branches; for every new public key it encrypts the packs of vendor/ that have no URL in
# layout/providers.json for that key and pushes them to ci-vendor-<job>. When the time is up the ci-vendor-* and
# ci-key-* branches are deleted. Only ciphertext for a key that died with its job is ever pushed.
cd "$(dirname "$0")/../.."; root=$PWD
files=$(python3 - <<'P'
import sys; sys.path.insert(0, 'tools'); import providers
print(' '.join(providers.find(k, m).name for k, m in providers.manifest().items() if not m.get('url') and providers.find(k, m)))
P
)
[ -z "$files" ] && { echo "nothing to send in vendor/"; exit 1; }
T=$(mktemp -d); end=$(( $(date +%s) + 60 * ${1:-30} )); touch $T/served
echo "sending: $files"
while [ $(date +%s) -lt $end ]; do
  for part in vanilla pack perf nether dh-vanilla dh-pack dh-perf dh-nether; do
    sha=$(git ls-remote origin "refs/heads/ci-key-$part" | cut -f1)
    [ -z "$sha" ] && continue; grep -q "$sha" $T/served && continue
    git fetch -q origin "ci-key-$part" || continue
    rm -rf $T/w; mkdir -p $T/w && cd $T/w
    git -C $root show FETCH_HEAD:pub.pem > pub.pem; git -C $root show FETCH_HEAD:fingerprint.txt > for.txt
    openssl rand -hex 32 > key
    tar -c -C $root/vendor $files | openssl enc -aes-256-ctr -pbkdf2 -pass file:key -out blob.enc
    openssl pkeyutl -encrypt -pubin -inkey pub.pem -pkeyopt rsa_padding_mode:oaep -in key -out key.enc
    rm -f key pub.pem
    git init -q -b v && git add -A && git -c user.name=the-isles -c user.email=the-isles@users.noreply.github.com commit -q -m "encrypted for one pack test job (see packtest/tools/vendor-recv.sh)" \
      && git push -q -f "$(git -C $root remote get-url origin)" "v:ci-vendor-$part" && { echo "$sha" >> $T/served; echo "[$(date +%H:%M:%S)] sent to $part ($(cat for.txt))"; }
    cd $root
  done
  sleep 8
done
for part in vanilla pack perf nether dh-vanilla dh-pack dh-perf dh-nether; do git push -q origin --delete "ci-vendor-$part" "ci-key-$part" 2>/dev/null; done
rm -rf $T; echo "done, branches deleted"

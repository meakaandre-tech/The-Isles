#!/bin/bash
# On the runner: asks for the providers that have no public download (layout/providers.json, "url": null).
#   vendor-recv.sh <job> <wanted provider ids, comma separated>
# They may not be redistributed, so they are neither in the repository nor behind a URL, and this sandbox cannot set
# repository secrets. Instead the job makes an RSA key pair that only lives in its memory, pushes the public half to the
# branch ci-key-<job> and waits (VENDOR_WAIT seconds, default 240) for the branch ci-vendor-<job>: the packs encrypted
# for exactly that key by packtest/tools/vendor-send.sh, run by whoever has the packs. Nobody else can read that branch's
# content, and after the job nobody can at all. When nothing arrives the job goes on without those providers.
part=$1; want=$2; root=$PWD
need=$(python3 - "$want" <<'P'
import sys; sys.path.insert(0, 'tools'); import providers
print(' '.join(k for k, m in providers.manifest().items() if k in sys.argv[1].split(',') and not m.get('url') and not providers.find(k, m)))
P
)
[ -z "$need" ] && { echo "vendor: nothing to ask for"; exit 0; }
[ -z "$PUSH_URL" ] && { echo "vendor: no PUSH_URL, cannot ask for: $need"; exit 0; }
K=$(mktemp -d); cd $K
openssl genrsa -out priv.pem 3072 2>/dev/null && openssl rsa -in priv.pem -pubout -out pub.pem 2>/dev/null
fp=$(sha256sum pub.pem | cut -c1-24)
mkdir ask && cp pub.pem ask/ && echo "$need" > ask/want.txt && echo "$fp" > ask/fingerprint.txt && echo "${GITHUB_SHA} ${GITHUB_RUN_ID}" > ask/run.txt
(cd ask && git init -q -b ci-key-$part && git config user.name "github-actions" && git config user.email "actions@users.noreply.github.com" \
  && git add -A && git commit -q -m "public key of a pack test job (see packtest/tools/vendor-recv.sh)" && git push -q -f "$PUSH_URL" "HEAD:ci-key-$part")
echo "vendor: asked for '$need' with key $fp, waiting ${VENDOR_WAIT:-240}s"
end=$(( $(date +%s) + ${VENDOR_WAIT:-240} )); got=
mkdir got && cd got && git init -q
while [ $(date +%s) -lt $end ]; do
  if git fetch -q --depth 1 "$PUSH_URL" "ci-vendor-$part" 2>/dev/null && [ "$(git show FETCH_HEAD:for.txt 2>/dev/null)" = "$fp" ]; then
    git show FETCH_HEAD:key.enc > ../key.enc; git show FETCH_HEAD:blob.enc > ../blob.enc
    openssl pkeyutl -decrypt -inkey ../priv.pem -pkeyopt rsa_padding_mode:oaep -in ../key.enc -out ../key \
      && mkdir -p $root/vendor && openssl enc -d -aes-256-ctr -pbkdf2 -pass file:../key -in ../blob.enc | tar -x -C $root/vendor && got=1
    break
  fi
  sleep 10
done
cd $root; rm -rf $K
[ -n "$got" ] && echo "vendor: received $(ls vendor | tr '\n' ' ')" || echo "vendor: nothing received, going on without: $need"

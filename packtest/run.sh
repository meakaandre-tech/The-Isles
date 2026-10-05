#!/bin/bash
# The Isles pack test. Run from the repository root on a GitHub runner (see .github/workflows/pack-test.yml).
# Files next to this script steer it:
#   phases        words, any of: vanilla (Fabric API + The Isles only), baseline (same without The Isles: vanilla
#                 generator, timing only), pack (every mod of mods.tsv + The Isles, real client, restart)
#   mods.tsv      url <tab> file name of every mod of the pack
#   exclude.txt   regexes of mod file names to leave out (to bisect)
#   gen.py        writes the probe data pack and the console command files from layout/islands.json
#   script.txt    client script of the pack phase (cmd/key/keydown/keyup/type/sleep/shot/move/click/rclick/waitlog)
set +e
root=$PWD; P=$root/packtest; out=/tmp/ci; W=/tmp/work
mkdir -p $out $W; exec > >(tee $out/run.txt) 2>&1
ts() { echo "[$(date +%H:%M:%S)] $*"; }
# progress: every 3 minutes the logs so far are pushed to the ci-logs branch (the workflow pushes the final state)
snapshot() {
  for d in $W/*/; do n=$(basename $d); [ -f $d/server.log ] && cp $d/server.log $out/server-$n.log; [ -f $d/server2.log ] && cp $d/server2.log $out/server2-$n.log; done 2>/dev/null
  echo "${GITHUB_SHA} (running, $(date +%H:%M:%S))" > $out/commit.txt
  rm -rf /tmp/ci-snap && cp -r $out /tmp/ci-snap && cd /tmp/ci-snap && git init -q -b ci-logs && git config user.name "github-actions" \
    && git config user.email "actions@users.noreply.github.com" && git add -A && git commit -q -m "Pack test for ${GITHUB_SHA} (in progress)" \
    && git push -q -f "$PUSH_URL" ci-logs
}
if [ -n "$PUSH_URL" ]; then (while sleep 180; do (snapshot) >/dev/null 2>&1; done) & SNAP=$!; fi
phases=$(cat $P/phases 2>/dev/null || echo "vanilla")
has() { echo " $phases " | grep -q " $1 "; }
nproc; free -m | head -2
ZIP=/tmp/the-isles-tested.zip
[ -f $ZIP ] || (cd $root/datapack && zip -q -r -X $ZIP .)
python3 $P/gen.py $W/gen || ts "gen.py FAILED"
cp $W/gen/gen.json $out/ 2>/dev/null
MC=26.3; LOADER=0.19.5
VD=$(cat $P/view-distance 2>/dev/null || echo 8)

# ---- mods
mkdir -p $W/mods
while IFS=$'\t' read -r url name; do
  [ -z "$url" ] && continue
  if [ -f $P/exclude.txt ] && echo "$name" | grep -qE -f <(grep -v '^\s*$' $P/exclude.txt); then echo "excluded: $name"; continue; fi
  has pack || case "$name" in fabric-api*) ;; *) continue;; esac
  for try in 1 2 3; do curl -fsSL -o "$W/mods/$name" "$url" && break; sleep 5; done
  [ -s "$W/mods/$name" ] || echo "DOWNLOAD FAILED: $name"
done < $P/mods.tsv
(cd $W/mods && sha1sum *.jar) > $out/mods.txt
ts "mods: $(ls $W/mods | wc -l)"
inst=$(curl -fsSL https://meta.fabricmc.net/v2/versions/installer | python3 -c "import json,sys; print(json.load(sys.stdin)[0]['version'])")
curl -fsSL -o $W/server.jar "https://meta.fabricmc.net/v2/versions/loader/$MC/$LOADER/$inst/server/jar"
ls -l $W/server.jar

# ---- client project warm-up in the background while the servers run
if has pack && [ ! -f $P/server-only ]; then
  (sudo apt-get update -q >/dev/null 2>&1; sudo apt-get install -y -q xvfb xdotool imagemagick libgl1-mesa-dri libglx-mesa0 libegl1 libegl-mesa0 libgles2 mesa-utils >/dev/null 2>&1; echo apt-done) > $out/apt.txt 2>&1 &
  C=$P/client
  mkdir -p $C/run/mods && cp $W/mods/*.jar $C/run/mods/
  # key bindings as legacy numbers: the 26.3 options datafixer fails on names and the client then never joins
  printf 'pauseOnLostFocus:false\nonboardAccessibility:false\ntutorialStep:none\nnarrator:0\nrenderDistance:'$VD'\nsimulationDistance:6\nguiScale:2\nmaxFps:30\nsoundCategory_master:0.0\n' > $C/run/options.txt
  [ -f $P/client-options.txt ] && cat $P/client-options.txt >> $C/run/options.txt
  [ -d $P/client-config ] && cp -r $P/client-config/. $C/run/
  (cd $C && chmod +x gradlew && ./gradlew downloadAssets --no-daemon -Dorg.gradle.console=plain > $out/client-prep.log 2>&1; echo "EXIT $?" >> $out/client-prep.log) &
fi

SX=${SERVER_XMX:-5G}
start_server() { # $1 = log file (in the current directory)
  rm -f in.fifo; mkfifo in.fifo
  (java -Xmx$SX -jar server.jar --nogui < in.fifo > $1 2>&1; echo "EXIT $?" >> $1) &
  exec 3> in.fifo
  local t0=$(date +%s)
  for i in $(seq 1 360); do
    if grep -q 'Done (' $1 || grep -q '^EXIT' $1; then break; fi
    [ $((i % 12)) = 0 ] && cp $1 $out/ 2>/dev/null
    if [ $((i % 6)) = 0 ] && [ $i -gt 24 ]; then   # slow start: what is the server thread doing
      pid=$(pgrep -f 'server.jar' | head -1)
      [ -n "$pid" ] && { echo "=== $(date +%H:%M:%S) $PWD/$1"; jstack $pid 2>/dev/null | awk 'BEGIN{RS="";FS="\n"} /"Server thread"/ {for(k=1;k<=NF&&k<=28;k++) print $k; print ""}'; } >> $out/slow-start-stacks.txt
    fi
    sleep 5
  done
  ts "server start took $(( $(date +%s) - t0 ))s: $(grep -o 'Done (.*' $1 | head -1)"
}
stop_server() { echo "stop" >&3; for i in $(seq 1 120); do grep -q '^EXIT' $1 && break; sleep 2; done; exec 3>&-; }
feed() { # $1 = command file, $2 = server log
  [ -f "$1" ] || return
  local before=1 line rest t pc re t0 ok
  while read -r line; do
    grep -q '^EXIT' $2 && { ts "server gone, feed aborted at: $line"; break; }
    case "$line" in
      "#sleep "*) sleep "${line#\#sleep }";;
      "#poll "*)   # "#poll N command ## regex": sends the command every 3 s until the log shows the regex (at most N seconds)
        rest=${line#\#poll }; t=${rest%% *}; rest=${rest#* }; pc=${rest%% \#\# *}; re=${rest##* \#\# }
        before=$(( $(wc -l < $2) + 1 )); t0=$(date +%s); ok=TIMEOUT
        while [ $(( $(date +%s) - t0 )) -lt $t ]; do
          echo "$pc" >&3; sleep 1
          sed -n "${before},\$p" $2 | grep -qE "$re" && { ok=ok; break; }
          sleep 2
        done
        ts "poll $ok after $(( $(date +%s) - t0 ))s: $re"
        if [ $ok = TIMEOUT ] && [ ! -f $out/timeout-stacks.txt ]; then   # first timeout: what are the server's threads doing
          pid=$(pgrep -f 'server.jar' | head -1); [ -n "$pid" ] && jstack $pid > $out/timeout-stacks.txt 2>&1
        fi;;
      "#wait "*)   # "#wait N ## regex": waits until the log shows the regex after the previous command
        rest=${line#\#wait }; t=${rest%% *}; re=${rest##* \#\# }; t0=$(date +%s); ok=TIMEOUT
        while [ $(( $(date +%s) - t0 )) -lt $t ]; do
          sed -n "${before},\$p" $2 | grep -qE "$re" && { ok=ok; break; }; sleep 1
        done
        [ $ok = ok ] || ts "wait TIMEOUT after ${t}s: $re";;
      ""|"#"*) ;;
      *) before=$(( $(wc -l < $2) + 1 )); echo "$line" >&3; sleep 0.12;;
    esac
  done < "$1"
}
finish_feed() { # $1 = log: waits until the console has caught up
  echo "say CHECK commands done" >&3
  for i in $(seq 1 360); do grep -q 'CHECK commands done' $1 && break; grep -q '^EXIT' $1 && break; sleep 2; done
}
props() { # $1 = level-name
  echo "eula=true" > eula.txt
  printf 'level-seed=20261004\nlevel-name='$1'\nwhite-list=false\nenforce-whitelist=false\nonline-mode=false\nmax-tick-time=-1\nview-distance='$VD'\nsimulation-distance=6\ngamemode=creative\ndifficulty=normal\nspawn-protection=0\npause-when-empty-seconds=-1\nsync-chunk-writes=false\n' > server.properties
}
simple_phase() { # $1 = name, $2 = with The Isles (1/0): Fabric API only
  local name=$1 dir=$W/$1
  CUR=$dir
  mkdir -p $dir/mods $dir/world/datapacks && cd $dir
  cp $W/server.jar . && cp "$W"/mods/fabric-api*.jar mods/
  [ "$2" = 1 ] && cp $ZIP world/datapacks/the-isles.zip
  cp -r $W/gen/probes world/datapacks/packtest-probes
  props world
  ts "$name: server start"
  start_server server.log
  if grep -q 'Done (' server.log; then
    feed $W/gen/commands-$name.txt server.log; finish_feed server.log
    ts "$name: commands done"
    stop_server server.log
  fi
  exec 3>&-
  cp server.log $out/server-$name.log
  cp -r crash-reports $out/crash-reports-$name 2>/dev/null
  python3 $P/tools/nbt.py world/level.dat > $out/level-$name.txt 2>&1
  du -sh world > $out/world-size-$name.txt 2>&1; find world -maxdepth 3 | head -80 >> $out/world-size-$name.txt
  ts "$name: stopped"
}

has vanilla && simple_phase vanilla 1
has baseline && simple_phase baseline 0
if has bisect; then for f in $W/gen/commands-bisect-*.txt; do n=$(basename $f .txt); simple_phase ${n#commands-} 1; done; fi
has pack && source $P/pack-phase.sh

cd $root
python3 $P/tools/report.py $out > $out/report.txt 2>&1
head -60 $out/report.txt
[ -n "$SNAP" ] && kill $SNAP 2>/dev/null
ts "end"

# Sourced by run.sh (phase "nether"): Fabric API + The Isles (phase word "nethermods": every mod of mods.tsv and
# datapack-mods as well), Nether probes on the console, then a real client in two layers and through four portals.
# Phase word "netherperf": first the variants of packtest/nether-perf.txt, each on a fresh world: seconds for 64 chunks
# and for 9 chunks somewhere else (what a first trip through a portal has to wait for), heap, a thread-dump profile,
# block counts of two layers. "nperfonly": only those.
ntime() { # $1 = tag, $2 = forceload command, $3 = "execute if loaded ..." test: seconds until the region is loaded (checked 5 times a second)
  local t0=$(date +%s.%N) i
  echo "$2" >&3
  for i in $(seq 1 6000); do
    echo "$3 run say NLOADED $1" >&3; sleep 0.2
    grep -q "NLOADED $1" server.log && break
    grep -q '^EXIT' server.log && break
  done
  NT=$(python3 -c "import time; print(round(time.time() - $t0, 1))")
}
nheap() { # heap in use after a full collection, MB
  local pid=$(pgrep -f 'server.jar' | head -1) u
  jcmd $pid GC.run >/dev/null 2>&1; sleep 2
  u=$(jcmd $pid GC.heap_info 2>/dev/null | grep -oE 'used [0-9]+K' | head -1 | grep -oE '[0-9]+'); NH=$(( ${u:-0} / 1024 ))
}
nperf_phase() { # $1 = name, rest: "-pack" (the vanilla Nether) or settings of tools/build_nether.py
  local name=nperf$(has nethermods && echo m)-$1 pack=1 pid before dir; shift; dir=$W/$name
  [ "$1" = "-pack" ] && { pack=0; shift; }
  cd $root
  env ISLES_PROVIDERS=none "$@" python3 tools/build_pack.py 2>&1 | grep -i nether > $out/build-$name.txt
  rm -f $W/$name.zip; (cd $root/datapack && zip -q -r -X $W/$name.zip .)
  mkdir -p $W/gen-$name; env "$@" NPERF_PACK=$pack python3 $P/gen_nether.py $W/gen-$name > /dev/null 2>&1
  mkdir -p $dir/mods $dir/world/datapacks && cd $dir
  cp $W/server.jar .
  if has nethermods; then cp $W/mods/*.jar mods/; [ $pack = 1 ] && cp $ZIP_MODS world/datapacks/the-isles-mods.zip; else cp "$W"/mods/fabric-api*.jar mods/; fi
  [ -f $W/packtest-debug.jar ] && cp $W/packtest-debug.jar mods/
  [ $pack = 1 ] && cp $W/$name.zip world/datapacks/the-isles.zip
  cp -r $W/gen/probes world/datapacks/packtest-probes
  props world
  start_server server.log
  if grep -q 'Done (' server.log; then
    feed $W/gen-$name/commands-nether-perf-head.txt server.log; sleep 10
    nheap; before=$NH
    pid=$(pgrep -f 'server.jar' | head -1); touch $dir/profiling
    (while [ -f $dir/profiling ]; do jstack $pid 2>/dev/null; sleep 1; done > $W/$name-stacks.raw) &
    ntime gen64 "execute in minecraft:the_nether run forceload add 0 0 127 127" "execute in minecraft:the_nether if loaded 0 0 0 if loaded 127 0 127"; gen=$NT
    rm -f $dir/profiling; sleep 1.5
    python3 $P/tools/stacks.py $W/$name-stacks.raw > $out/${name}-stacks.txt 2>&1
    nheap
    jcmd $pid GC.class_histogram 2>/dev/null > $W/$name-histo.txt; (head -22 $W/$name-histo.txt; tail -1 $W/$name-histo.txt) > $out/$name-histo.txt
    NL=$(( $(tail -1 $W/$name-histo.txt | awk '{print $3}') / 1048576 ))
    ntime portal9 "execute in minecraft:the_nether run forceload add 4000 4000 4047 4047" "execute in minecraft:the_nether if loaded 4000 0 4000 if loaded 4047 0 4047"
    ts "NPERF $name gen64 $gen s  portal9 $NT s  heap $before -> $NH MB, live objects $NL MB  ($*)"
    feed $W/gen-$name/commands-nether-perf.txt server.log; finish_feed server.log
    stop_server server.log
  else
    ts "NPERF $name the server did not start"
  fi
  exec 3>&-
  cp server.log $out/server-$name.log
  cd $root
}
if has netherperf && [ -f $P/nether-perf.txt ]; then
  while read -r pname pvars; do case "$pname" in ""|"#"*) ;; *) nperf_phase "$pname" $pvars < /dev/null;; esac; done < $P/nether-perf.txt
  cd $root && ISLES_PROVIDERS=none python3 tools/build_pack.py > /dev/null
fi
if ! has nperfonly; then
dir=$W/nether; CUR=$dir
mkdir -p $dir/mods $dir/world/datapacks && cd $dir
cp $W/server.jar .
if has nethermods; then cp $W/mods/*.jar mods/; cp $ZIP_MODS world/datapacks/the-isles-mods.zip; else cp "$W"/mods/fabric-api*.jar mods/; fi
[ -f $W/packtest-debug.jar ] && cp $W/packtest-debug.jar mods/
cp $ZIP world/datapacks/the-isles.zip
cp -r $W/gen/probes world/datapacks/packtest-probes
props world
C=$P/client
n=0
nshot() { n=$((n+1)); import -window root $out/nether-$(printf '%02d' $n).png; }
nscript() { # $1 = script file (cmd/sleep/shot)
  local kind arg
  while read -r kind arg; do
    case "$kind" in
      cmd) echo "$arg" >&3; sleep 0.15;;
      sleep) sleep "$arg";;
      shot) nshot;;
    esac
    pgrep -f KnotClient >/dev/null || { ts "client gone, script aborted at: $kind $arg"; break; }
    grep -q '^EXIT' $dir/server.log && { ts "server gone, script aborted at: $kind $arg"; break; }
  done < "$1"
}
ts "nether: server start with $(ls mods | wc -l) mods"
start_server server.log
if grep -q 'Done (' server.log; then
  # a poor man's profiler for the generation: 120 thread dumps, a second apart, top frames of the busy worker threads counted
  (for i in $(seq 1 120); do sleep 1; pid=$(pgrep -f 'server.jar' | head -1); [ -n "$pid" ] && jstack $pid 2>/dev/null; done > $W/nether-stacks.raw
   python3 $P/tools/stacks.py $W/nether-stacks.raw > $out/nether-stacks.txt 2>&1) &
  feed $W/gen/commands-nether.txt server.log; finish_feed server.log
  ts "nether: commands done"; cp server.log $out/server-nether.log
  if [ ! -f $P/server-only ] && ! grep -q '^EXIT' server.log; then
    for i in $(seq 1 180); do grep -q '^EXIT' $out/client-prep.log && grep -q apt-done $out/apt.txt && break; sleep 5; done
    ts "nether: client start"
    cd $C
    export LIBGL_ALWAYS_SOFTWARE=1 DISPLAY=:99 SDL_VIDEO_FORCE_EGL=1
    pgrep Xvfb >/dev/null || { Xvfb :99 -screen 0 1280x720x24 >/dev/null 2>&1 & sleep 2; }
    (env -u CI timeout ${CLIENT_TIMEOUT:-3000} ./gradlew runClient --no-daemon -Dorg.gradle.console=plain --args="--quickPlayMultiplayer localhost --username packtest --width 1280 --height 720" > nether-gradle.log 2>&1; echo "EXIT $?" >> nether-gradle.log) &
    for i in $(seq 1 240); do
      if grep -q 'joined the game' $dir/server.log || grep -q '^EXIT' nether-gradle.log; then break; fi
      sleep 5
    done
    if grep -q 'joined the game' $dir/server.log; then
      ts "nether: client joined"; sleep ${JOIN_SETTLE:-40}
      xdotool mousemove 640 360
      nscript $W/gen/script-nether.txt
    else
      ts "nether: client did not join"; nshot
    fi
    ts "nether: client script done"
    pkill -f KnotClient; sleep 6
    tail -c 300000 $C/nether-gradle.log > $out/nether-gradle.log
    cp $C/run/logs/latest.log $out/client-nether.log 2>/dev/null
    cp -r $C/run/crash-reports $out/client-crash-reports-nether 2>/dev/null
    cd $dir
  fi
  stop_server server.log
fi
exec 3>&-
cp server.log $out/server-nether.log
cp -r crash-reports $out/crash-reports-nether 2>/dev/null
du -sh world world/dimensions/minecraft/the_nether world/DIM-1 > $out/world-size-nether.txt 2>&1
cd $root
ts "nether: stopped"
fi

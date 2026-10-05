# Sourced by run.sh (phase "nether"): Fabric API + The Isles (phase word "nethermods": every mod of mods.tsv and
# datapack-mods as well), Nether probes on the console, then a real client in two layers and through four portals.
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

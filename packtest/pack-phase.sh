# Sourced by run.sh: the whole mod pack with The Isles, a real client, then a restart on the saved world.
dir=$W/pack; CUR=$dir
mkdir -p $dir/mods $dir/world/datapacks && cd $dir
cp $W/server.jar . && cp $W/mods/*.jar mods/
[ -f $P/debug ] && [ -f $W/packtest-debug.jar ] && cp $W/packtest-debug.jar mods/
cp $ZIP world/datapacks/the-isles.zip
cp -r $W/gen/probes world/datapacks/packtest-probes
props world
[ -d $P/server-config ] && cp -r $P/server-config/. .
C=$P/client
n=0
shot() { n=$((n+1)); import -window root $out/${pfx}$(printf '%02d' $n).png; }
run_script() { # $1 = script file
  local kind arg t re
  while read -r kind arg; do
    case "$kind" in
      cmd) echo "$arg" >&3;;
      key) xdotool key "$arg";;
      keydown) xdotool keydown "$arg";;
      keyup) xdotool keyup "$arg";;
      type) xdotool type --delay 40 "$arg";;
      sleep) sleep "$arg";;
      shot) shot;;
      move) xdotool mousemove $arg;;
      click) xdotool mousemove $arg; sleep 0.3; xdotool click 1; sleep 0.4;;
      rclick) xdotool mousemove $arg; sleep 0.3; xdotool click 3; sleep 0.4;;
      mdown) xdotool mousedown $arg;;
      mup) xdotool mouseup $arg;;
    esac
    pgrep -f KnotClient >/dev/null || { ts "client gone, script aborted at: $kind $arg"; break; }
    grep -q '^EXIT' $dir/server.log && { ts "server gone, script aborted at: $kind $arg"; break; }
  done < "$1"
}
start_client() { # $1 = gradle log
  cd $C
  export LIBGL_ALWAYS_SOFTWARE=1 DISPLAY=:99
  # Minecraft 26.3 (SDL3) asks for an sRGB-capable framebuffer; Xvfb's GLX visuals have none, EGL does
  export SDL_VIDEO_FORCE_EGL=1
  pgrep Xvfb >/dev/null || { Xvfb :99 -screen 0 1280x720x24 >/dev/null 2>&1 & sleep 2; }
  (glxinfo -B; eglinfo -B 2>/dev/null | head -40) > $out/gfx.txt 2>&1
  (env -u CI timeout ${CLIENT_TIMEOUT:-4200} ./gradlew runClient --no-daemon -Dorg.gradle.console=plain --args="--quickPlayMultiplayer localhost --username packtest --width 1280 --height 720" > $1 2>&1; echo "EXIT $?" >> $1) &
}
stop_client() { # $1 = suffix, $2 = gradle log
  pkill -f KnotClient; sleep 6
  tail -c 400000 $C/$2 > $out/$2
  cp $C/run/logs/latest.log $out/client$1.log 2>/dev/null
  cp -r $C/run/crash-reports $out/client-crash-reports 2>/dev/null
}

ts "pack: server start"
start_server server.log
if grep -q 'Done (' server.log; then
  feed $W/gen/commands-pack.txt server.log; finish_feed server.log
  ts "pack: commands done"; cp server.log $out/server-pack.log
  if [ ! -f $P/server-only ] && ! grep -q '^EXIT' server.log; then
    for i in $(seq 1 180); do grep -q '^EXIT' $out/client-prep.log && grep -q apt-done $out/apt.txt && break; sleep 5; done
    ts "pack: client start"
    start_client client-gradle.log
    for i in $(seq 1 240); do
      if grep -q 'joined the game' $dir/server.log || grep -q '^EXIT' client-gradle.log; then break; fi
      sleep 5
    done
    pfx=client-
    if grep -q 'joined the game' $dir/server.log; then
      ts "pack: client joined"
      sleep ${JOIN_SETTLE:-40}
      xdotool mousemove 640 360
      run_script $W/gen/script-pack.txt
    else
      ts "pack: client did not join"; shot
    fi
    ts "pack: client script done"
    stop_client "" client-gradle.log
    cd $dir
  fi
  stop_server server.log
fi
exec 3>&-
cp server.log $out/server-pack.log
ts "pack: server stopped"
if grep -q 'Done (' server.log; then
  start_server server2.log
  if grep -q 'Done (' server2.log; then
    feed $W/gen/commands-pack-restart.txt server2.log; finish_feed server2.log
    sleep 5; stop_server server2.log
  fi
  exec 3>&-
  cp server2.log $out/server2-pack.log
  ts "pack: restart done"
fi
cp -r crash-reports $out/crash-reports-pack 2>/dev/null
ls -la config > $out/server-config-list.txt 2>/dev/null
python3 $P/tools/nbt.py world/level.dat > $out/level-pack.txt 2>&1
du -sh world > $out/world-size-pack.txt 2>&1
cd $root

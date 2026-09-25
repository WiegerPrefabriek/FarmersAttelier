#!/bin/zsh
# Farmers Atelier Customer Service stoppen.
#
# Zoekt wie er op de poort luistert in plaats van op de procesnaam te matchen: de Python
# uit de .venv meldt zich onder het pad van de systeem-Python, dus op naam zoeken werkt niet.
# Voor de zekerheid wordt gecontroleerd dat het echt run.py van dit project is.
POORT="${POORT:-8800}"

PID="$(lsof -ti "tcp:$POORT" -sTCP:LISTEN 2>/dev/null | head -1)"
if [[ -z "$PID" ]]; then
  echo "Draaide niet (niemand luistert op poort $POORT)."
  sleep 1; exit 0
fi

if ! ps -o command= -p "$PID" | grep -q "run\.py"; then
  echo "Op poort $POORT draait iets anders dan Farmers Atelier:"
  ps -o pid,command -p "$PID"
  echo "Voor de zekerheid niets gestopt."
  sleep 3; exit 1
fi

kill "$PID" 2>/dev/null
for i in {1..10}; do
  sleep 0.5
  kill -0 "$PID" 2>/dev/null || break
done
kill -0 "$PID" 2>/dev/null && kill -9 "$PID" 2>/dev/null

if lsof -ti "tcp:$POORT" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "Stoppen mislukt; poort $POORT is nog bezet."
else
  echo "Gestopt."
fi
sleep 1

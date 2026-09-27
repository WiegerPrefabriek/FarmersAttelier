#!/bin/zsh
# Farmers Atelier Customer Service starten.
# Dubbelklikken op dit bestand (of op de kopie op het Bureaublad) start de server en
# opent de browser. Draait hij al, dan wordt alleen de browser geopend.
#
# De server draait los van dit venster: je mag de Terminal daarna gewoon sluiten.
# Stoppen: "Farmers Atelier stoppen.command", of in de Terminal: pkill -f FARMERS-ATELIER
#
# Let op: gebruik http://localhost:<poort>/ en niet http://127.0.0.1:<poort>/.
# Chrome op deze Mac komt op het IP-adres niet binnen (de tab valt terug naar
# newtab), op de naam localhost wel. De server luistert op allebei.
cd "$HOME/Desktop/FARMERS-ATELIER" || { echo "Map ~/Desktop/FARMERS-ATELIER niet gevonden."; exit 1; }

POORT="${POORT:-8800}"
LOG="logs/server.log"
mkdir -p logs

if curl -sS -m 2 -o /dev/null "http://127.0.0.1:$POORT/" 2>/dev/null; then
  echo "Draait al op poort $POORT."
else
  if [[ ! -x ./.venv/bin/python ]]; then
    echo "De Python-omgeving ontbreekt. Eenmalig aanmaken:"
    echo "  cd ~/Desktop/FARMERS-ATELIER && python3 -m venv .venv && ./.venv/bin/pip install -r requirements.txt"
    exit 1
  fi
  echo "Starten op poort $POORT…"
  POORT="$POORT" nohup ./.venv/bin/python run.py >> "$LOG" 2>&1 &
  disown
  for i in {1..15}; do
    sleep 1
    curl -sS -m 2 -o /dev/null "http://127.0.0.1:$POORT/" 2>/dev/null && break
  done
fi

if curl -sS -m 2 -o /dev/null "http://127.0.0.1:$POORT/" 2>/dev/null; then
  open "http://localhost:$POORT/"
  echo "Open: http://localhost:$POORT/   (dit venster mag dicht)"
else
  echo "Starten mislukt. De laatste regels uit $LOG:"
  tail -20 "$LOG"
fi

#!/bin/bash
# install_cron.sh — Installa il cron job giornaliero (Linux/Mac)
# Uso: bash install_cron.sh [orario]
# Esempio: bash install_cron.sh 08:00

HOUR=${1:-08}
MINUTE=${2:-00}

# Se viene passato HH:MM separa
if [[ "$1" == *":"* ]]; then
    HOUR=$(echo "$1" | cut -d: -f1)
    MINUTE=$(echo "$1" | cut -d: -f2)
fi

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON=$(which python3 || which python)
LOG_FILE="$PROJECT_DIR/logs/cron.log"

CRON_CMD="$MINUTE $HOUR * * * cd $PROJECT_DIR && $PYTHON main.py --run-now >> $LOG_FILE 2>&1"

echo "📅 Installazione cron job:"
echo "   Orario: ogni giorno alle $HOUR:$MINUTE"
echo "   Comando: $CRON_CMD"
echo ""

# Aggiunge alla crontab senza duplicati
(crontab -l 2>/dev/null | grep -v "real_estate_monitor"; echo "$CRON_CMD") | crontab -

if [ $? -eq 0 ]; then
    echo "✅ Cron job installato con successo!"
    echo ""
    echo "   Verifica con: crontab -l"
    echo "   Rimuovi con:  crontab -e (cancella la riga)"
else
    echo "❌ Errore installazione cron job"
fi

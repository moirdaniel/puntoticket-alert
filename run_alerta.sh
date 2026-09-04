#!/usr/bin/env sh
cd "$(dirname "$0")" || exit 1
python3 ticket_alert.py --gui --interval 60

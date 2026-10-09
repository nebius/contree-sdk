#!/bin/bash
set -euo pipefail
mkdir -p /logs/verifier
if [ "$(cat /app/greeting.txt)" = "$GREETING" ]; then
    echo 1 > /logs/verifier/reward.txt
else
    echo 0 > /logs/verifier/reward.txt
fi

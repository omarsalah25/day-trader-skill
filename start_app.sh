#!/usr/bin/env bash
# Launch script for Day Trader 24/7 Autonomous App & Dashboard

PORT=${1:-8080}
echo "=========================================================="
echo " Starting Day Trader 24/7 Autonomous Market Terminal..."
echo " Dashboard URL: http://localhost:${PORT}"
echo " Press Ctrl+C to stop the server."
echo "=========================================================="

python3 app/server.py --port "${PORT}"

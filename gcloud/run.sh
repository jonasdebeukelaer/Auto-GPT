#!/bin/bash
set -e

echo "Running crypto-gpt..."

echo ""
echo "Load secrets..."
cp .env.base .env
cat ./mnt2/secrets.env >> .env

echo ""
echo "Start dummy server..."
python dummy_server.py 8080 &

echo ""
echo "Start application..."
python -m autogpt --ai-settings mnt1/ai-settings.yaml --skip-news --continuous

echo ""
echo "Stopped gracefully!"

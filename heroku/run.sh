#!/bin/bash
set -e

echo "Running trader script..."

echo "$AI_SETTINGS" > ai_settings.yaml
python -m autogpt --ai-settings ai_settings.yaml --skip-news --continuous

echo "Trader script finished!"

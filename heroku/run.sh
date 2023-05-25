#!/bin/bash
set -e

echo "Running trader script..."

echo "$AI_SETTINGS" > ai_settings.yaml
python -m autogpt --ai-settings ai_settings.yaml --gpt3only --skip-news --debug --continuous

echo "Script finished!"

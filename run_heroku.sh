#!/bin/bash
set -e

echo "$AI_SETTINGS" > ai_settings.yaml
python -m autogpt --ai-settings ai_settings.yaml --gpt3only --skip-news --debug --continuous

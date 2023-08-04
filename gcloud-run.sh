#!/bin/bash

echo "Running crypto-gpt..."

echo ""
echo "setup gcloud"
gcloud auth login


echo ""
echo "Exporting secrets to env vars..."
# load secrets to env
while IFS= read -r line
do
  echo "loading secret: $line" | cut -d '=' -f 1
  export "${line?}"
done < ./secrets.env
echo "All secrets exported!"
echo ""

python -m autogpt --ai-settings ai_settings.yaml --skip-news --continuous

echo "Stopped gracefully!"

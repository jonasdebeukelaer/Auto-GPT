#!/bin/bash
set -e

PROJECT_ID="crypto-gpt-69"
REGION="europe-west1"
SERVICE_NAME="crypto-gpt"

# Check if the user is logged in
if [[ $(gcloud auth list --filter=status:ACTIVE --format="value(account)") == "" ]]; then
    echo "You are not logged in to gcloud. Please run 'gcloud auth login' and try again."
    exit 1
fi

gcloud config set project $PROJECT_ID
gcloud config set run/region $REGION

# Submit a new build to Cloud Build
# TODO: make async and make finish trigger the deploy
gcloud builds submit --config cloudbuild.yaml .

# Deploy the image to Cloud Run
gcloud run deploy $SERVICE_NAME \
  --image "eu.gcr.io/$PROJECT_ID/$SERVICE_NAME" \
  --region $REGION \
  --platform managed \
  --no-allow-unauthenticated \
  --cpu 1 \
  --memory 2Gi \
  --update-secrets=/app/ai-settings.yaml=crypto-gpt-ai-settings:1 \
  --update-secrets=/app/secrets.env=crypto-gpt-env-secrets:1

echo "Deployment completed successfully."

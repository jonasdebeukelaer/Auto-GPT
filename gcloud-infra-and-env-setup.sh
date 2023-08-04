#!/bin/bash
set -e

PROJECT_ID="crypto-gpt-69"
REGION="europe-west1"
PROJECT_NUMBER=$(gcloud projects describe "${PROJECT_ID}" --format 'value(projectNumber)')
SERVICE_ACCOUNT="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"

AI_SETTINGS_SECRETS_NAME="crypto-gpt-ai-settings"
ENV_VAR_SECRETS_NAME="crypto-gpt-env-secrets"

# Check if the user is logged in
if [[ $(gcloud auth list --filter=status:ACTIVE --format="value(account)") == "" ]]; then
    echo "You are not logged in to gcloud. Please run 'gcloud auth login' and try again."
    exit 1
fi

gcloud config set project $PROJECT_ID
gcloud config set run/region $REGION

# allow google cloud run access to secrets
gcloud secrets add-iam-policy-binding ${AI_SETTINGS_SECRETS_NAME} \
  --member "serviceAccount:${SERVICE_ACCOUNT}" \
  --role roles/secretmanager.secretAccessor

# allow google cloud run access to ai settings
gcloud secrets add-iam-policy-binding ${ENV_VAR_SECRETS_NAME} \
  --member "serviceAccount:${SERVICE_ACCOUNT}" \
  --role roles/secretmanager.secretAccessor

# deploy minio instance
MINIO_PASSWORD=$(gcloud secrets versions access 1 --secret="crypto-gpt-minio-password")
gcloud run deploy minio \
  --image bitnami/minio:2023.7.18 \
  --region "$REGION" \
  --platform managed \
  --allow-unauthenticated \
  --port 9000 \
  --cpu 1 \
  --memory 2Gi \
  --set-env-vars "MINIO_ROOT_USER=crypto-gpt-user,MINIO_ROOT_PASSWORD=${MINIO_PASSWORD}"

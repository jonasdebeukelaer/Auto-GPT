#!/bin/bash
set -e

PROJECT_ID="crypto-gpt-69"
REGION="europe-west1"

# Check if the user is logged in
if [[ $(gcloud auth list --filter=status:ACTIVE --format="value(account)") == "" ]]; then
    echo "You are not logged in to gcloud. Please run 'gcloud auth login' and try again."
    exit 1
fi

gcloud config set project $PROJECT_ID

# Submit a new build to Cloud Build
gcloud builds submit --config cloudbuild.yaml . --async --region $REGION

echo "Deployment completed successfully."

#!/bin/bash
# Script to create Kubernetes secret from environment variables
# This keeps secrets out of git while making deployment easy

set -e

# Check if .env file exists
if [ ! -f "deployments/.env" ]; then
    echo "Error: deployments/.env file not found!"
    echo "Please copy deployments/.env.example to deployments/.env and fill in your values"
    exit 1
fi

# Load environment variables from .env file
export $(grep -v '^#' deployments/.env | xargs)

# Validate required variables
if [ -z "$LLM_URL" ] || [ -z "$LLM_API_KEY" ] || [ -z "$LLM_MODEL" ]; then
    echo "Error: Missing required environment variables"
    echo "Please ensure LLM_URL, LLM_API_KEY, and LLM_MODEL are set in deployments/.env"
    exit 1
fi

echo "Creating Kubernetes secret from environment variables..."

# Create or update the secret
kubectl create secret generic game-env \
    --from-literal=LLM_URL="$LLM_URL" \
    --from-literal=LLM_API_KEY="$LLM_API_KEY" \
    --from-literal=LLM_MODEL="$LLM_MODEL" \
    --dry-run=client -o yaml | kubectl apply -f -

echo "Secret 'game-env' created/updated successfully!"
echo ""
echo "The secret contains:"
echo "  - LLM_URL: $LLM_URL"
echo "  - LLM_API_KEY: [hidden]"
echo "  - LLM_MODEL: $LLM_MODEL"


#!/bin/sh
set -e

# Default to "debug" if the first argument is not provided
TAG=${1:-"debug"}
IMAGE_NAME="bagl3y/esphome-tesla-ble-bridge"
FULL_IMAGE_NAME="${IMAGE_NAME}:${TAG}"

echo "Building and pushing image: ${FULL_IMAGE_NAME}"

# Build the image
docker build -t "${FULL_IMAGE_NAME}" .

# Push the image
docker push "${FULL_IMAGE_NAME}"

echo "Successfully pushed ${FULL_IMAGE_NAME}" 
#!/bin/sh
set -e

# Default to "debug" if the first argument is not provided
TAG=${1:-"debug"}
IMAGE_NAME="bagl3y/esphome-tesla-ble-bridge"
FULL_IMAGE_NAME="${IMAGE_NAME}:${TAG}"
PLATFORMS="linux/amd64,linux/arm64"

echo "Building and pushing multi-arch image: ${FULL_IMAGE_NAME}"
echo "Target platforms: ${PLATFORMS}"

# Use docker buildx to build for multiple platforms
docker buildx build \
  --platform "${PLATFORMS}" \
  --tag "${FULL_IMAGE_NAME}" \
  --push \
  .

echo "Successfully pushed multi-arch image ${FULL_IMAGE_NAME} for platforms ${PLATFORMS}" 
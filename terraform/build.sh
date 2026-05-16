#!/usr/bin/env bash
# Build the Lambda deployment package.
# Run this before 'tofu plan' or 'tofu apply'.
# Called automatically by Terraform when source files change.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BUILD_DIR="${SCRIPT_DIR}/.lambda_build"
ZIP_FILE="${SCRIPT_DIR}/.lambda.zip"
HANDLERS="${SCRIPT_DIR}/../src/handlers"

echo "Building Lambda package..."
rm -rf "${BUILD_DIR}"
mkdir -p "${BUILD_DIR}"

pip3 install \
  -r "${HANDLERS}/requirements.txt" \
  -t "${BUILD_DIR}" \
  --quiet \
  --no-cache-dir

# Strip packages provided by the Lambda Python 3.12 runtime to minimise package size
rm -rf \
  "${BUILD_DIR}"/boto3* \
  "${BUILD_DIR}"/botocore* \
  "${BUILD_DIR}"/s3transfer* \
  "${BUILD_DIR}"/jmespath* \
  "${BUILD_DIR}"/urllib3* \
  "${BUILD_DIR}"/six* \
  "${BUILD_DIR}"/python_dateutil* \
  "${BUILD_DIR}"/dateutil

# Install Twilio only when enabled — it adds ~29 MB to the package
if [ "${TWILIO_ENABLED:-false}" = "true" ]; then
  echo "Installing Twilio SDK (TWILIO_ENABLED=true)..."
  pip3 install "twilio>=9.0" -t "${BUILD_DIR}" --quiet --no-cache-dir
fi

cp "${HANDLERS}/app.py" "${BUILD_DIR}/"

cd "${BUILD_DIR}"
zip -r "${ZIP_FILE}" . -q
echo "Built ${ZIP_FILE} ($(du -sh "${ZIP_FILE}" | cut -f1))"

#!/bin/bash

# Build script to package Lambda code for distribution
# This creates a zip file that should be uploaded to S3 bucket: <account-id>-quip-s3-sync-lambda

set -e

# Activate virtual environment if it exists
if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
fi

echo "Building Lambda code package..."

# Create a temporary directory for the build
BUILD_DIR="lambda_build"
rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR"

# Copy Lambda source code
echo "Copying Lambda source code..."
cp -r src/* "$BUILD_DIR/"

# Install dependencies
echo "Installing Python dependencies..."
pip install -r src/requirements.txt -t "$BUILD_DIR"

# Remove unnecessary files
echo "Cleaning up unnecessary files..."
find "$BUILD_DIR" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find "$BUILD_DIR" -type f -name "*.pyc" -delete
find "$BUILD_DIR" -type f -name "*.pyo" -delete
find "$BUILD_DIR" -type d -name "*.dist-info" -exec rm -rf {} + 2>/dev/null || true
find "$BUILD_DIR" -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true

# Create the zip file
echo "Creating zip file..."
cd "$BUILD_DIR"
zip -r ../quip-sync-lambda.zip .
cd ..

# Clean up build directory
rm -rf "$BUILD_DIR"

echo ""
echo "✅ Lambda code package created: quip-sync-lambda.zip"
echo ""
echo "Next steps:"
echo "1. Create S3 bucket (if not exists): aws s3 mb s3://<account-id>-quip-s3-sync-lambda"
echo "2. Upload to S3: aws s3 cp quip-sync-lambda.zip s3://<account-id>-quip-s3-sync-lambda/"
echo "3. Users can then deploy via CloudFormation"

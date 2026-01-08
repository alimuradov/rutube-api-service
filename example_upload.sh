#!/bin/bash
# Example upload script for Rutube
# This script demonstrates how to upload a video with various options

# Exit on error
set -e

echo "=================================================="
echo "Rutube Video Upload Example"
echo "=================================================="
echo ""

# Check if cookie file exists
COOKIE_FILE="${RUTUBE_COOKIES:-cookies.txt}"

if [ ! -f "$COOKIE_FILE" ]; then
    echo "ERROR: Cookie file not found: $COOKIE_FILE"
    echo ""
    echo "Please export cookies from studio.rutube.ru:"
    echo "  1. Install 'Get cookies.txt LOCALLY' browser extension"
    echo "  2. Go to https://studio.rutube.ru and login"
    echo "  3. Click extension → 'Get cookies.txt LOCALLY' → 'Current Site'"
    echo "  4. Save as cookies.txt in project folder"
    echo ""
    echo "Or set RUTUBE_COOKIES environment variable:"
    echo "  export RUTUBE_COOKIES=/path/to/cookies.txt"
    echo ""
    exit 1
fi

# Video file path
VIDEO_FILE=".local/Медитация_Адвента_Неделя_2__Иисус_—_полностью_Бог_и_полностью_человек.mp4"

# Check if video file exists
if [ ! -f "$VIDEO_FILE" ]; then
    echo "ERROR: Video file not found: $VIDEO_FILE"
    exit 1
fi

echo "Video file: $VIDEO_FILE"
echo "Cookie file: $COOKIE_FILE"
echo ""

# Uncomment to test with dry run first
# echo "Running in DRY RUN mode..."
# python3 rutube.py \
#     "$VIDEO_FILE" \
#     "Test Video Title" \
#     --description "This is a test upload" \
#     --category 63 \
#     --cookies "$COOKIE_FILE" \
#     --dry-run

# Actual upload (remove the exit below to enable)
echo "WARNING: This will perform an actual upload to Rutube!"
echo "Press Ctrl+C within 5 seconds to cancel..."
sleep 5

echo ""
echo "Starting upload..."
echo ""

# Upload the video
python3 rutube.py \
    "$VIDEO_FILE" \
    "Размышления над Адвентом. Неделя 2: Иисус – полностью Бог и полностью человек" \
    --description "Медитация на тему Адвента" \
    --category 63 \
    --cookies "$COOKIE_FILE"

echo ""
echo "=================================================="
echo "Upload complete!"
echo "=================================================="

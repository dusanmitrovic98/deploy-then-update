#!/usr/bin/env bash
set -e  # Exit on errors

echo "---> Installing dependencies"
pip install -r requirements.txt

echo "---> Pulling latest code"
git pull origin main
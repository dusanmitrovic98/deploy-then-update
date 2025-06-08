#!/usr/bin/env bash

# Exit on error
set -o errexit

# Install Python dependencies
pip install -r requirements.txt

# Initialize the repository if needed
if [ ! -d ".git" ]; then
    git init
    git remote add origin $REPO_URL
fi

# Fetch the latest code
git fetch origin $BRANCH

# Reset to the latest commit
git reset --hard origin/$BRANCH
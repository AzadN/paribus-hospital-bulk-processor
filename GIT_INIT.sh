#!/bin/bash
# Run these commands locally to create a GitHub-ready repo with meaningful commits.

git init
git add .
git commit -m "chore: initial scaffold for Paribus bulk hospital processor"
git branch -M main
# Create a remote repo on GitHub and replace URL below:
# git remote add origin git@github.com:YOUR_USERNAME/paribus-bulk.git
# git push -u origin main

# Optional: add a second commit with tests and docs
git add tests README.md DEPLOYMENT.md
git commit -m "test: add pytest test and deployment docs"

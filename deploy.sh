#!/bin/bash
set -e # Exit with nonzero exit code if anything fails

SOURCE_BRANCH="master"
TARGET_BRANCH="gh-pages"

build_normal()
{
    echo "Running ~The Build~"
    # Save some useful information
    REPO=`git config remote.origin.url`
    SSH_REPO=${REPO/https:\/\/github.com\//git@github.com:}
    SHA=`git rev-parse --verify HEAD`

    # Clone the existing gh-pages for this repo into out/
    # Create a new empty branch if gh-pages doesn't exist yet (should only happen on first deply)
    git clone $REPO out
    cd out
    git checkout $TARGET_BRANCH || git checkout --orphan $TARGET_BRANCH
    cd ..

    # Clean out existing contents of build
    rm -rf out/build/* || exit 0

    # Ensure needed directories are present
    mkdir -p out/data
    mkdir -p out/static

    # Run our compile script
    python app.py
}

# Pull requests and commits to other branches shouldn't try to deploy, just build to verify
if [ "$TRAVIS_PULL_REQUEST" != "false" -o "$TRAVIS_BRANCH" != "$SOURCE_BRANCH" ]; then
    build_normal
    exit 0
fi

# run normal build
build_normal

# prepare to push to remote
# copy over README.md and .gitignore
cp .gitignore out/.gitignore
cp README.md out/README.md

# Move our output from build onto our gh-pages branch root
cd out/build
cp -r * ..
cd ..

git config user.name "Travis CI"
git config user.email "duskdragon@gmail.com"

# If there are no changes to the compiled out (e.g. this is a non-website update) then just bail.
if [[ -z `git diff --exit-code` ]]; then
    echo "No changes to pages on this push; exiting."
    exit 0
fi

# Commit the "changes", i.e. the new version.
# The delta will show diffs between new and old versions.
git add -A
git commit -m "Deploy to GitHub Pages: ${SHA}"

# Get the deploy key by using Travis's stored variables to decrypt deploy_key.enc
ENCRYPTED_KEY_VAR="encrypted_${ENCRYPTION_LABEL}_key"
ENCRYPTED_IV_VAR="encrypted_${ENCRYPTION_LABEL}_iv"
ENCRYPTED_KEY=${!ENCRYPTED_KEY_VAR}
ENCRYPTED_IV=${!ENCRYPTED_IV_VAR}
openssl aes-256-cbc -K $ENCRYPTED_KEY -iv $ENCRYPTED_IV -in deploy_key.enc -out deploy_key -d
chmod 600 deploy_key
eval `ssh-agent -s`
ssh-add deploy_key

# Now that we're all set up, we can push.
git push $SSH_REPO $TARGET_BRANCH

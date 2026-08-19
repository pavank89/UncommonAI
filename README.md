# uncommonAI — GitHub Autopilot V3

Phone-first automation for the uncommonAI YouTube channel.

## Important

This repository is public. **Never commit secrets.**

The workflow expects these GitHub Actions secrets:

- `OPENAI_API_KEY`
- `YOUTUBE_CLIENT_SECRET_JSON`

The first version of the cloud workflow uses GitHub-hosted `ubuntu-latest`.
GitHub currently says standard runners are free for public repositories.

## What this V3 does

Research → strategy → script → editorial gate → AI narration → AI visuals →
FFmpeg assembly → thumbnail → Shorts → final approval → YouTube upload.

## Reality about "free"

GitHub Actions can provide the compute layer at no charge for this public
repository. AI model APIs can still charge for usage. This package does not
promise zero AI/API cost.

## YouTube OAuth

Do not put your Google password in GitHub.

Create a Google OAuth Desktop client and store the complete downloaded JSON
contents as the GitHub Actions secret `YOUTUBE_CLIENT_SECRET_JSON`.

The first cloud run may require an interactive OAuth consent step. A fully
headless YouTube upload requires completing OAuth once and securely persisting
the resulting refresh token. The next iteration should store that token as a
GitHub secret rather than committing it.

## Recommended first test

Run the workflow in **research** mode first. Do not attempt automatic
publishing until OAuth has been completed and tested.


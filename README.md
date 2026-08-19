# uncommonAI — Autopilot V4

This version is **phone-first** and uses GitHub Issues as the approval console.

## How it works

1. Weekly GitHub Action collects AI/tech signals and opens an approval issue.
2. You comment `APPROVE` from your phone.
3. GitHub runs the AI production package.
4. It creates a final-approval issue and uploads the package as an artifact.
5. You review it and comment `PUBLISH`.
6. YouTube publishing remains locked until the one-time OAuth refresh token is configured.

## Free vs paid

**Free infrastructure:** GitHub Actions + RSS research + GitHub Issues/artifacts.

**Potentially paid:** AI model API calls for script/voice/images. This package does
not pretend those APIs are free.

## Secrets

Add only these as GitHub Actions secrets:

- `OPENAI_API_KEY` — needed for production.
- Later: `YOUTUBE_TOKEN_JSON` — only after the YouTube OAuth setup is completed.

Never put secrets in this repository.

## Important

The V4 workflow intentionally does NOT publish automatically yet. This prevents
a broken OAuth setup from wasting a production run or exposing credentials.

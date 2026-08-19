# Android phone setup

1. Open the `UncommonAI` repository.
2. Upload the files/folders in this package, preserving:
   `.github/workflows/uncommonai.yml`
3. In GitHub open:
   Settings → Secrets and variables → Actions → New repository secret
4. Add:
   `OPENAI_API_KEY`
5. Add:
   `YOUTUBE_CLIENT_SECRET_JSON`
   using the entire contents of your Google OAuth desktop-client JSON.
6. Open the Actions tab.
7. Select `UncommonAI Autopilot`.
8. Tap `Run workflow`.
9. Start with `research`.

Do not paste secrets into issues, README files, source files, or chat.

NOTE:
YouTube OAuth is the one part that needs an initial authorization flow.
The workflow should not publish until that authorization has been completed
and a refresh token is securely available.

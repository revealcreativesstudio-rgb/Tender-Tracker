# Tender Tracker (free version)

Every morning at 06:00 Nairobi time this project reads the Government Advertising Agency (GAA)
"All Tenders" page, reads each new notice to find the eligibility (Women, Youth, PWD, Open) and
closing time, and updates the dashboard.

## Setup (about 15 minutes, best done on a computer)

1. Sign in to GitHub. Click **+** (top right) > **New repository**.
   Name it `tender-tracker`, choose **Public**, then **Create repository**.
   (Free GitHub accounts can only host the dashboard from a public repository.
   The repository holds public tender information only. Your applications and
   contracts stay in your own browser.)
2. On the new repository page click **uploading an existing file**. Unzip this folder first,
   then drag in `scanner.py`, `requirements.txt`, `README.md` and the whole `docs` folder.
   Click **Commit changes**.
3. Add the schedule file. Click **Add file > Create new file**. In the name box type exactly
   `.github/workflows/scan.yml` (typing the slashes creates the folders). Open the
   `scan.yml` file from this folder, copy everything, paste it in, then **Commit changes**.
4. **Settings > Pages**. Under Build and deployment, set Source to **GitHub Actions**.
5. **Settings > Actions > General**. Under Workflow permissions choose
   **Read and write permissions**, then **Save**.
6. Open the **Actions** tab, click **Daily tender scan**, then **Run workflow**.
   Wait about 2 to 3 minutes for a green tick.
7. Your site address is `https://YOUR-USERNAME.github.io/tender-tracker/`.
   Open it, and add it to your phone's home screen.

From then on it updates itself every morning. To refresh sooner, repeat step 6.

## If something goes wrong
- Red cross in the Actions tab: click the failed run, copy the error text and send it to Claude.
- Banner on the dashboard says "Problem reading: GAA": the GAA page changed or was down.
  The dashboard keeps showing the earlier results until the next successful scan.

## Known limits
- Only the GAA source is connected so far. e-GP, PPIP, school sites and free web search are next.
- Tenders with no closing date written on the GAA page are skipped.
- Scanned (picture-only) PDF notices cannot be read, so their eligibility shows "see notice".
- Closing time defaults to 10:00 a.m. when the notice does not state it (tagged "Closing time not stated").

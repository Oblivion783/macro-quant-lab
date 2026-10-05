# Setup on Windows

About 35 minutes in total. Part A is one click in the browser; Part B is on your personal laptop. Use personal accounts only.

## Part A · GitHub settings (browser, 10 minutes)

Open https://github.com/Oblivion783/macro-quant-lab and go to **Settings**.

1. **Pages → Build and deployment → Source**: choose **GitHub Actions**. That is the only required click: the site goes live at https://oblivion783.github.io/macro-quant-lab/ on the next weekday run (05:47 IST), with the audio feed at `/podcast.xml`.
2. Optional, **Secrets and variables → Actions → Secrets → New repository secret**: `GEMINI_API_KEY`, a free key from https://aistudio.google.com/apikey made with your personal Google account. With it, the AI writes the brief's narrative (every number checked against the data); without it, the template writer is used.
3. Already done: the daily job runs every weekday at 05:47 IST and publishes the brief, charts, archive, README summary and audio. GitHub sometimes starts scheduled jobs late or skips them, so backup slots at 06:23 and 08:13 IST run it only if the 05:47 run did not happen. GitHub emails you only when a run fails; the morning email comes from the separate 06:37 Claude brief. The first run on 4 Oct 2026 stored 55 series, all passing the quality checks, and decoded the last four Fed statements. **Actions → Daily Macro Desk → Run workflow** runs it on demand. To pause publishing, add the repository variable `PUBLISH_ENABLED` = `false`.

## Part B · Your laptop (PowerShell, 30 minutes)

Open **PowerShell** (Start → type "PowerShell").

### 1. Install Python, Git and VS Code
```powershell
winget install -e --id Python.Python.3.12
winget install -e --id Git.Git
winget install -e --id Microsoft.VisualStudioCode
```
Close PowerShell and open it again so the new commands are found.

### 2. Tell Git who you are
Use GitHub's private no-reply address (GitHub → Settings → Emails → "Keep my email addresses private" shows it).
```powershell
git config --global user.name "Aditya Kumar"
git config --global user.email "ID+Oblivion783@users.noreply.github.com"
```

### 3. Get the code
```powershell
cd $HOME\Documents
git clone https://github.com/Oblivion783/macro-quant-lab.git
cd macro-quant-lab
```

### 4. Create the Python environment
```powershell
py -3.12 -m venv .venv
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned   # once per laptop; answer Y
.\.venv\Scripts\Activate.ps1                           # the prompt now starts with (.venv)
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 5. Check everything works
```powershell
python -m unittest discover -s tests -t .
```
You should see `OK` after about 40 tests.

### 6. Turn on the commit check
```powershell
pre-commit install
```
Every `git commit` now runs a quick check for sensitive wording (the patterns in config/compliance.yaml) before the commit goes through.

### 7. Run the pipeline yourself
```powershell
git pull                                   # get the data the daily job committed
python scripts/run_daily.py --offline      # rebuild the snapshot from stored data
python scripts/run_daily.py --offline --publish   # also builds the pages and charts locally
```
Open `docs\index.md` and `docs\assets\charts\` to see the output. To preview the whole site: `mkdocs serve`, then open http://127.0.0.1:8000.

### 8. SQL practice (DuckDB)
```powershell
python -m mql.store --duckdb
python scripts/sql.py notebooks\sql_practice.sql
```

### 9. The dashboard
```powershell
pip install -r app\requirements.txt
streamlit run app\streamlit_app.py
```
In November, publish it free on Streamlit Community Cloud: https://share.streamlit.io → **Create app** → repository `Oblivion783/macro-quant-lab`, branch `main`, file `app/streamlit_app.py`.

## Everyday loop

```powershell
cd $HOME\Documents\macro-quant-lab
.\.venv\Scripts\Activate.ps1
git pull
# ...edit in VS Code:  code .
git add -A
git commit -m "Say what you changed"
git push
```

## Using Claude while you build

- Open the folder in VS Code (`code .`). When something breaks, paste the full error and the file into Claude.
- `CLAUDE.md` at the repo root explains the project's structure and rules, so Claude Code (if you use it) follows them.
- Never paste anything from work into any AI tool for this project.

## Once Pages is on

- Site: https://oblivion783.github.io/macro-quant-lab/
- Audio brief: add https://oblivion783.github.io/macro-quant-lab/podcast.xml in your podcast app (Pocket Casts or AntennaPod: add by URL; Apple Podcasts: Library → ⋯ → Follow a Show by URL).

## Troubleshooting

| Problem | Fix |
|---|---|
| `Activate.ps1 cannot be loaded` | Run the `Set-ExecutionPolicy` line in step 4. |
| `python` opens the Microsoft Store | Use `py` instead, or turn off the app execution aliases in Windows Settings → Apps → Advanced app settings. |
| A series fails in the quality report | Usually a temporary source outage; it retries tomorrow. If it persists, check its code at the source and edit `config/series.yaml`. |
| Yahoo returns HTTP 429 | Rate-limited; run again later. The daily job tolerates it. |
| `git push` rejected | `git pull --rebase`, then push again (the daily job commits every morning). |
| Compliance gate blocks a commit | It names the file and line. Remove the term; never weaken the gate to get a commit through. |

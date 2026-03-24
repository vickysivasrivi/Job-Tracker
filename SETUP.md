# DevOps Job Hunt — GitHub Actions Setup

Runs every morning at 8am on GitHub's servers.  
Your laptop can be **completely off**.

---

## Step 1 — Create a private GitHub repository

1. Go to [github.com](https://github.com) → **+** → **New repository**
2. Name: `devops-job-automation`
3. Set to **Private** (keeps your resume safe)
4. Click **Create repository**

---

## Step 2 — Upload these files

Drag and drop into the repo (or use GitHub Desktop):

```
.github/workflows/daily_jobs.yml
scripts/daily_automation.py
scripts/build_ats_resume.py
SETUP.md
```

---

## Step 3 — Add Secrets (your private info)

**Settings → Secrets and variables → Actions → New repository secret**

| Secret name | What to put |
|---|---|
| `ANTHROPIC_KEY` | Your key from console.anthropic.com (sk-ant-api03-...) |
| `EMAIL_FROM` | Your Gmail (e.g. you@gmail.com) |
| `EMAIL_PASSWORD` | **Gmail App Password** — see below |
| `EMAIL_TO` | Where to send the digest (can be same email) |
| `YOUR_RESUME` | Paste your entire CV text here |
| `APIFY_TOKEN` | Optional — from apify.com → Settings → Integrations |

**Variables tab** (same page, different tab):

| Variable | Value |
|---|---|
| `JOB_TITLE` | `DevOps Engineer` |
| `JOB_LOCATION` | `Ireland` |
| `MIN_SCORE` | `60` |
| `TOP_N` | `5` |

---

## Step 4 — Get a Gmail App Password

> You **cannot** use your normal Gmail password. Google blocks it.

1. Go to [myaccount.google.com/security](https://myaccount.google.com/security)
2. Enable **2-Step Verification** (required)
3. Go to [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)
4. Select **Mail** → Generate
5. Copy the 16-character code → paste as `EMAIL_PASSWORD` secret

---

## Step 5 — Test it now (laptop on)

1. Go to your repo → **Actions** tab
2. Click **Daily DevOps Job Hunt** → **Run workflow** → **Run workflow**
3. Watch the logs in real time
4. Check your email in 2–3 minutes

---

## Step 6 — It now runs automatically

Every day at 9am Irish time, GitHub runs the script.  
Laptop off → no problem.  
Check **Actions** tab any time to see run history and logs.

---

## Updating your resume

Go to: **Settings → Secrets → YOUR_RESUME → Update**  
The next morning run uses the new version automatically.

---

## NodeFlair Score Tips (how to get 80+)

When you upload the PDF to NodeFlair:
1. **Paste the job description** into NodeFlair's job description box  
   A generic check without a job description always scores low (30–50)  
   With a matching job description you should get 70–90+
2. The PDF has correct format: single column, no tables, standard headers
3. Keywords from the job are emphasised in each section


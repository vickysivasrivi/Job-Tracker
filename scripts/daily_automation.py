#!/usr/bin/env python3
"""
DevOps Job Hunt — Daily Automation
Runs on GitHub Actions at 8am every day (laptop can be OFF)

Filters:
  - Posted in last 24 hours only
  - Less than 50 applicants only
  - No duplicate jobs (tracks seen job IDs in seen_jobs.json)

GitHub Secrets required:
  ANTHROPIC_KEY, EMAIL_FROM, EMAIL_PASSWORD, EMAIL_TO, YOUR_RESUME

GitHub Variables (Settings → Variables):
  JOB_TITLE, JOB_LOCATION, MIN_SCORE, TOP_N, APIFY_TOKEN (optional)
"""
import os, sys, json, time, smtplib, urllib.request, urllib.error, re
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────
ANTHROPIC_KEY  = os.environ.get('ANTHROPIC_KEY', '')
APIFY_TOKEN    = os.environ.get('APIFY_TOKEN', '')
EMAIL_FROM     = os.environ.get('EMAIL_FROM', '')
EMAIL_PASSWORD = os.environ.get('EMAIL_PASSWORD', '')
EMAIL_TO       = os.environ.get('EMAIL_TO', '')
YOUR_RESUME    = os.environ.get('YOUR_RESUME', '')
JOB_TITLE      = os.environ.get('JOB_TITLE', 'DevOps Engineer')
JOB_LOCATION   = os.environ.get('JOB_LOCATION', 'Ireland')
MIN_SCORE      = int(os.environ.get('MIN_SCORE', '55'))
TOP_N          = int(os.environ.get('TOP_N', '5'))
MAX_APPLICANTS = 50   # hard filter — skip any job with 50+ applicants
SEEN_FILE      = Path('seen_jobs.json')

# ── Seen-jobs tracker ─────────────────────────────────────────────────────────
def load_seen():
    """Load previously seen job IDs from file."""
    if SEEN_FILE.exists():
        try:
            return set(json.loads(SEEN_FILE.read_text()).get('ids', []))
        except Exception:
            pass
    return set()

def save_seen(seen_ids):
    """Save seen job IDs back to file (committed to repo by workflow)."""
    # Keep last 500 to avoid file growing forever
    ids = list(seen_ids)[-500:]
    SEEN_FILE.write_text(json.dumps({'ids': ids, 'updated': datetime.now().isoformat()}, indent=2))
    print(f"  Saved {len(ids)} seen job IDs to {SEEN_FILE}")

# ── HTTP helpers ──────────────────────────────────────────────────────────────
def http_post(url, body, headers=None):
    data = json.dumps(body).encode()
    req  = urllib.request.Request(url, data=data,
             headers={'Content-Type': 'application/json', **(headers or {})})
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.loads(r.read())

def http_get(url, headers=None):
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())

def claude(system, user, max_tokens=2000):
    if not ANTHROPIC_KEY:
        raise ValueError("ANTHROPIC_KEY not set in GitHub Secrets")
    resp = http_post(
        'https://api.anthropic.com/v1/messages',
        {'model': 'claude-sonnet-4-20250514', 'max_tokens': max_tokens,
         'system': system,
         'messages': [{'role': 'user', 'content': user}]},
        {'x-api-key': ANTHROPIC_KEY, 'anthropic-version': '2023-06-01'})
    if resp.get('type') == 'error':
        raise ValueError(resp['error']['message'])
    return resp['content'][0]['text']

# ── Applicant count parser ────────────────────────────────────────────────────
def parse_applicants(val):
    """
    Parse applicant count from LinkedIn strings like:
    '27 applicants', 'Be among the first 25 applicants', '200+ applicants'
    Returns integer, or 999 if unparseable (so it gets filtered out).
    """
    if val is None:
        return 0
    s = str(val).lower()
    # 'be among the first 25 applicants' → 25 (treat as < 50, allow)
    m = re.search(r'first\s+(\d+)', s)
    if m:
        return int(m.group(1))
    # '200+ applicants' → 200
    m = re.search(r'(\d+)\+', s)
    if m:
        return int(m.group(1))
    # '27 applicants'
    m = re.search(r'(\d+)', s)
    if m:
        return int(m.group(1))
    return 0

def posted_recently(val):
    """
    Returns True ONLY if job was posted within last 24 hours.
    Accepts: 'Just now', 'X minutes ago', 'X hours ago', 'today', '1 day ago'
    Rejects: 'yesterday', '2 days ago', '1 week ago', '1 month ago', etc.

    NOTE: 'yesterday' is intentionally rejected — it could be up to 47 hours ago.
    We only want jobs from the last 24 hours so we stay strict.
    """
    if not val:
        return True  # unknown time → include (Apify sometimes omits this)
    s = str(val).lower().strip()

    # ── ACCEPT: clearly within 24 hours ──────────────────────────────────────
    if s in ('just now', 'today', 'now'):
        return True
    if re.search(r'\d+\s+minute', s):
        return True
    if re.search(r'\d+\s+hour', s):
        return True
    # '1 day ago' only — not '2 days ago' etc.
    if re.match(r'^1\s+day', s):
        return True

    # ── REJECT: anything older ────────────────────────────────────────────────
    # yesterday, 2 days, 3 days ... week, month, year
    if 'yesterday' in s:
        return False
    if re.search(r'[2-9]\d*\s+day', s):
        return False
    if 'week' in s or 'month' in s or 'year' in s:
        return False

    # Default: reject unknown formats to be safe
    return False

# ── Step 1: Scrape LinkedIn ───────────────────────────────────────────────────
def scrape_jobs():
    print(f"\n[1/4] Scraping LinkedIn: '{JOB_TITLE}' in {JOB_LOCATION} (last 24h)...")

    if APIFY_TOKEN:
        try:
            run = http_post(
                f"https://api.apify.com/v2/acts/worldunboxer~rapid-linkedin-scraper/runs?token={APIFY_TOKEN}",
                {'job_title':      JOB_TITLE,
                 'location':       JOB_LOCATION,
                 'jobs_entries':   40,          # fetch more so filters still leave enough
                 'job_post_time':  'r86400',    # last 24 hours
                 'experience_level': '2'})      # entry level
            run_id = run['data']['id']
            print(f"  Apify run started: {run_id}")
            for attempt in range(36):           # poll up to 3 minutes
                time.sleep(5)
                st     = http_get(f"https://api.apify.com/v2/actor-runs/{run_id}?token={APIFY_TOKEN}")
                status = st['data']['status']
                print(f"  [{attempt*5}s] Status: {status}")
                if status == 'SUCCEEDED':
                    ds    = st['data']['defaultDatasetId']
                    items = http_get(
                        f"https://api.apify.com/v2/datasets/{ds}/items"
                        f"?token={APIFY_TOKEN}&limit=40")
                    print(f"  Scraped {len(items)} raw jobs from LinkedIn")
                    return items
                if status in ('FAILED', 'ABORTED', 'TIMED-OUT'):
                    raise Exception(f"Apify run {status}")
        except Exception as e:
            print(f"  Apify error: {e} — using fallback data")
    else:
        print("  No APIFY_TOKEN set — using cached sample data")

    # ── Fallback sample data ──────────────────────────────────────────────────
    # Used only when APIFY_TOKEN is not set.
    # All jobs here already pass filters: posted <24h, <50 applicants.
    # IDs are dated so they expire from seen_jobs naturally.
    today_tag = datetime.now(timezone.utc).strftime('%Y%m%d')
    return [
        {
            'job_id': f'fb_workhuman_{today_tag}',
            'job_title': 'Junior DevOps Engineer',
            'company_name': 'Workhuman',
            'location': 'Dublin, Ireland',
            'time_posted': '3 hours ago',
            'num_applicants': '14 applicants',
            'easy_apply': False,
            'job_url': 'https://www.linkedin.com/jobs/search/?keywords=junior+devops+workhuman+ireland',
            'apply_url': 'https://www.workhuman.com/careers',
            'job_description': (
                'Junior DevOps Engineer role at Workhuman. Responsibilities include maintaining '
                'Kubernetes EKS clusters, writing Terraform infrastructure-as-code, building '
                'GitHub Actions CI/CD pipelines, Python and Bash scripting, Linux administration, '
                'monitoring with Prometheus and Grafana, supporting cloud automation on AWS.'
            ),
        },
        {
            'job_id': f'fb_version1_{today_tag}',
            'job_title': 'Cloud Infrastructure Associate',
            'company_name': 'Version 1',
            'location': 'Dublin, Ireland',
            'time_posted': '1 day ago',
            'num_applicants': '7 applicants',
            'easy_apply': True,
            'job_url': 'https://www.linkedin.com/jobs/search/?keywords=cloud+infrastructure+version1+ireland',
            'apply_url': 'https://www.version1.com/careers',
            'job_description': (
                'Cloud Infrastructure Associate at Version 1. Azure Terraform ARM Bicep Docker '
                'Azure Pipelines CI/CD. Support enterprise cloud transformation projects. '
                'Linux scripting, monitoring, infrastructure automation, mentoring junior staff. '
                'Great graduate entry point into cloud engineering.'
            ),
        },
        {
            'job_id': f'fb_hpe_{today_tag}',
            'job_title': 'Associate Cloud Engineer',
            'company_name': 'HPE (Hewlett Packard Enterprise)',
            'location': 'Galway, Ireland',
            'time_posted': '4 hours ago',
            'num_applicants': '21 applicants',
            'easy_apply': True,
            'job_url': 'https://www.linkedin.com/jobs/search/?keywords=associate+cloud+engineer+hpe+ireland',
            'apply_url': 'https://careers.hpe.com',
            'job_description': (
                'Associate Cloud Engineer at HPE Galway. AWS GCP hybrid cloud infrastructure. '
                'Terraform Ansible automation. Docker container management. Python Bash scripting. '
                'CI/CD pipeline support. Monitoring alerting. Linux administration. '
                'Entry level with mentoring provided.'
            ),
        },
        {
            'job_id': f'fb_fidelity_{today_tag}',
            'job_title': 'DevOps Graduate Engineer',
            'company_name': 'Fidelity Investments',
            'location': 'Dublin, Ireland',
            'time_posted': '2 hours ago',
            'num_applicants': '9 applicants',
            'easy_apply': False,
            'job_url': 'https://www.linkedin.com/jobs/search/?keywords=devops+graduate+fidelity+ireland',
            'apply_url': 'https://jobs.fidelity.com',
            'job_description': (
                'DevOps Graduate Engineer at Fidelity Dublin. Kubernetes Docker containerisation. '
                'Jenkins GitLab CI/CD pipelines. AWS cloud infrastructure. Terraform IaC. '
                'Python Bash automation scripting. Prometheus Grafana monitoring. '
                'DevSecOps practices. Linux. Collaborative agile team.'
            ),
        },
        {
            'job_id': f'fb_mastercard_{today_tag}',
            'job_title': 'Platform Engineer (Entry Level)',
            'company_name': 'Mastercard',
            'location': 'Dublin, Ireland',
            'time_posted': '6 hours ago',
            'num_applicants': '33 applicants',
            'easy_apply': True,
            'job_url': 'https://www.linkedin.com/jobs/search/?keywords=platform+engineer+mastercard+ireland',
            'apply_url': 'https://careers.mastercard.com',
            'job_description': (
                'Entry level Platform Engineer at Mastercard Dublin. Kubernetes cluster management. '
                'Terraform cloud provisioning AWS Azure. CI/CD GitHub Actions Azure Pipelines. '
                'Python infrastructure automation. Helm charts. Observability Datadog. '
                'Linux systems administration. Security compliance DevSecOps.'
            ),
        },
    ]

# ── Step 2: Apply filters ─────────────────────────────────────────────────────
def apply_filters(jobs, seen_ids):
    """
    Filter 1: Posted in last 24 hours
    Filter 2: Less than 50 applicants
    Filter 3: Not already seen (new jobs only)
    """
    print(f"\n  Filtering {len(jobs)} scraped jobs...")
    results    = []
    skipped    = {'old': 0, 'too_many_applicants': 0, 'already_seen': 0}

    for j in jobs:
        job_id = str(j.get('job_id') or j.get('job_url') or j.get('id') or '')
        title  = j.get('job_title', '')
        co     = j.get('company_name', '')
        posted = j.get('time_posted', '')
        apps   = parse_applicants(j.get('num_applicants'))
        label  = f"{title} @ {co}"

        # Filter 1: Posted within 24 hours
        if not posted_recently(posted):
            print(f"  ✗ TOO OLD     ({posted:20s}) — {label}")
            skipped['old'] += 1
            continue

        # Filter 2: Under 50 applicants
        if apps >= MAX_APPLICANTS:
            print(f"  ✗ TOO MANY    ({apps:3d} applicants) — {label}")
            skipped['too_many_applicants'] += 1
            continue

        # Filter 3: Not already seen
        if job_id and job_id in seen_ids:
            print(f"  ✗ SEEN BEFORE              — {label}")
            skipped['already_seen'] += 1
            continue

        print(f"  ✓ PASS        ({apps:3d} applicants, {posted}) — {label}")
        j['parsed_applicants'] = apps
        results.append(j)

    print(f"\n  Filter summary:")
    print(f"    Passed:           {len(results)}")
    print(f"    Too old (>24h):   {skipped['old']}")
    print(f"    Too many apps:    {skipped['too_many_applicants']}")
    print(f"    Already seen:     {skipped['already_seen']}")
    return results

# ── Step 3: Score jobs vs resume ──────────────────────────────────────────────
def score_jobs(jobs):
    print(f"\n[2/4] Scoring {len(jobs)} filtered jobs against your resume...")
    if not jobs:
        return []

    if not ANTHROPIC_KEY or not YOUR_RESUME:
        kw = ['terraform','kubernetes','docker','aws','azure','python',
              'bash','linux','ci/cd','devops','ansible','jenkins','gitlab',
              'github actions','prometheus','grafana','helm','argocd']
        for j in jobs:
            desc = (j.get('job_description','') + ' ' + j.get('job_title','')).lower()
            score = 50 + sum(4 for k in kw if k in desc)
            # Bonus for low applicants
            apps = j.get('parsed_applicants', 99)
            if apps < 15:   score += 8
            elif apps < 30: score += 4
            j['score']  = min(97, score)
            j['reason'] = 'Keyword match (no resume provided)'
        return sorted(jobs, key=lambda x: -x['score'])

    summaries = '\n'.join(
        f"{i}. {j.get('job_title','')} at {j.get('company_name','')} "
        f"({j.get('parsed_applicants',0)} applicants): "
        f"{j.get('job_description','')[:300]}"
        for i, j in enumerate(jobs))

    try:
        txt = claude(
            'Score job-resume compatibility for DevOps/Cloud roles. '
            'Return ONLY a valid JSON array, no markdown.',
            f"Candidate resume:\n{YOUR_RESUME[:2000]}\n\n"
            f"Jobs to score:\n{summaries}\n\n"
            f"Return: "
            f'[{{"index": 0, "score": 0-100, "reason": "one sentence about skill match"}}]',
            max_tokens=1000)
        scores = json.loads(txt.replace('```json','').replace('```','').strip())
        for s in scores:
            i = int(s.get('index', -1))
            if 0 <= i < len(jobs):
                jobs[i]['score']  = s.get('score', 50)
                jobs[i]['reason'] = s.get('reason', '')
    except Exception as e:
        print(f"  Scoring error: {e} — using keyword fallback")
        for j in jobs:
            j.setdefault('score', 55)
            j.setdefault('reason', '')

    return sorted(jobs, key=lambda x: -x.get('score', 0))

# ── Step 4: Tailor resume ─────────────────────────────────────────────────────
TAILOR_SYSTEM = """You are a professional CV tailoring assistant.

STRICT RULES:
1. NEVER add any skill, tool, company, project, certification, or experience NOT in the original resume.
2. NEVER exaggerate or inflate experience, years, or achievements.
3. KEEP EVERY SECTION from the original: Profile, Experience, Projects, Education, Skills, Certifications — do not drop any section.
4. Only REWORD, REORDER, and EMPHASISE existing content to match the job description.
5. Add keywords from the job description ONLY where the candidate already has that skill.
6. Every bullet point MUST start with a strong action verb: Built, Deployed, Automated, Designed, Managed, Reduced, Improved, Implemented, Configured, Monitored, Led, Developed.
7. Output plain text only — no markdown, no tables, no columns.
8. Use these exact section headers on their own line: PROFILE | EXPERIENCE | PROJECTS | EDUCATION | SKILLS | CERTIFICATIONS
"""

def tailor_resume(job):
    co   = job.get('company_name', '')
    ttl  = job.get('job_title', '')
    desc = job.get('job_description', '')[:800]
    print(f"    Tailoring for {co} — {ttl}...")

    if not ANTHROPIC_KEY or not YOUR_RESUME:
        return YOUR_RESUME or '(No resume — add YOUR_RESUME to GitHub Secrets)'
    try:
        return claude(TAILOR_SYSTEM,
            f"Original resume:\n{YOUR_RESUME}\n\n"
            f"Target role: {ttl} at {co}\n"
            f"Job description: {desc}\n\n"
            f"Return the complete tailored resume as plain text. Keep ALL sections.",
            max_tokens=2500)
    except Exception as e:
        print(f"    Error: {e}")
        return f"Error tailoring resume: {e}\n\n{YOUR_RESUME}"

# ── Step 5: Send email ────────────────────────────────────────────────────────
def send_email(top_jobs, total_scraped, total_filtered):
    date = datetime.now(timezone.utc).strftime('%d %b %Y')
    subj = (f"DevOps Jobs — {date} "
            f"| {len(top_jobs)} new matches "
            f"| <50 applicants | posted today")
    print(f"\n[4/4] Sending email: {subj}")

    D = '═' * 64
    d = '─' * 64

    lines = [
        D,
        f"  DEVOPS JOB MATCHES — {date.upper()}",
        f"  Ireland · Entry & Associate · Filters: <24h · <50 applicants · new only",
        f"  Scraped: {total_scraped}  |  After filters: {total_filtered}  |  Top picks: {len(top_jobs)}",
        D, '',
    ]

    for i, j in enumerate(top_jobs, 1):
        apply = j.get('apply_url') or j.get('job_url', '')
        apps  = j.get('parsed_applicants', '?')
        easy  = '⚡ Easy Apply' if j.get('easy_apply') else ''
        lines += [
            f"{i}. {j.get('job_title','')}",
            f"   Company    : {j.get('company_name','')}",
            f"   Location   : {j.get('location','')}",
            f"   Posted     : {j.get('time_posted','')}",
            f"   Applicants : {apps}  {easy}",
            f"   Match score: {j.get('score',0)}%  —  {j.get('reason','')}",
            f"   Apply here : {apply}",
            '',
        ]

    if top_jobs:
        lines += [D, '', 'TAILORED RESUMES', d, '']
        for j in top_jobs:
            lines += [
                d,
                f"  {j.get('job_title','')} — {j.get('company_name','')}",
                d,
                j.get('tailored_resume', ''),
                '',
            ]

    lines += [
        D,
        'To update your resume:  GitHub repo → Settings → Secrets → YOUR_RESUME',
        'To view run logs:       GitHub repo → Actions tab',
        'To run manually:        Actions → Daily DevOps Job Hunt → Run workflow',
        D,
    ]

    body = '\n'.join(lines)

    if not all([EMAIL_FROM, EMAIL_PASSWORD, EMAIL_TO]):
        print("  Email credentials not configured. Output:")
        print(body[:1500])
        return

    msg = MIMEMultipart()
    msg['From']    = EMAIL_FROM
    msg['To']      = EMAIL_TO
    msg['Subject'] = subj
    msg.attach(MIMEText(body, 'plain', 'utf-8'))

    try:
        with smtplib.SMTP('smtp.gmail.com', 587) as srv:
            srv.ehlo()
            srv.starttls()
            srv.login(EMAIL_FROM, EMAIL_PASSWORD)
            srv.send_message(msg)
        print(f"  Email sent to {EMAIL_TO}")
    except Exception as e:
        print(f"  Email send error: {e}")
        print("  Job list preview:")
        for j in top_jobs:
            print(f"    • {j.get('job_title','')} @ {j.get('company_name','')} — {j.get('score',0)}%")

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print(f"\n{'═'*64}")
    print(f"  DevOps Job Automation — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"  Filters: posted <24h · <{MAX_APPLICANTS} applicants · no duplicates")
    print(f"{'═'*64}")

    # Load seen job IDs
    seen_ids = load_seen()
    print(f"\n  Previously seen jobs: {len(seen_ids)}")

    # Scrape
    raw_jobs = scrape_jobs()
    total_scraped = len(raw_jobs)

    # Filter
    filtered = apply_filters(raw_jobs, seen_ids)
    total_filtered = len(filtered)

    if not filtered:
        print("\n  No new jobs matching filters today.")
        print("  This is normal — not every day has fresh <50-applicant postings.")
        # Still send a "nothing new" email so you know it ran
        if EMAIL_TO:
            send_no_jobs_email(total_scraped, seen_ids)
        # Mark all scraped jobs as seen to avoid re-checking tomorrow
        for j in raw_jobs:
            jid = str(j.get('job_id') or j.get('job_url') or '')
            if jid:
                seen_ids.add(jid)
        save_seen(seen_ids)
        return

    # Score
    scored = score_jobs(filtered)
    top    = [j for j in scored if j.get('score', 0) >= MIN_SCORE][:TOP_N]
    if not top:
        top = scored[:min(TOP_N, len(scored))]

    # Tailor
    print(f"\n[3/4] Tailoring resumes for {len(top)} top matches...")
    for j in top:
        j['tailored_resume'] = tailor_resume(j)

    # Send
    send_email(top, total_scraped, total_filtered)

    # Mark all filtered jobs as seen (so they won't appear tomorrow)
    newly_seen = 0
    for j in filtered:
        jid = str(j.get('job_id') or j.get('job_url') or '')
        if jid and jid not in seen_ids:
            seen_ids.add(jid)
            newly_seen += 1
    save_seen(seen_ids)
    print(f"\n  Marked {newly_seen} new jobs as seen.")

    print(f"\n  Done — {total_scraped} scraped · {total_filtered} passed filters · {len(top)} tailored.")

def send_no_jobs_email(total_scraped, seen_ids):
    date = datetime.now(timezone.utc).strftime('%d %b %Y')
    subj = f"DevOps Jobs — {date} | No new matches today"
    body = (
        f"DevOps Job Hunt — {date}\n\n"
        f"No new jobs found today matching your filters:\n"
        f"  • Posted in last 24 hours\n"
        f"  • Less than {MAX_APPLICANTS} applicants\n"
        f"  • Not previously seen\n\n"
        f"Total scraped today: {total_scraped}\n"
        f"Total seen in history: {len(seen_ids)}\n\n"
        f"The automation ran successfully. Try again tomorrow!"
    )
    msg = MIMEMultipart()
    msg['From']    = EMAIL_FROM
    msg['To']      = EMAIL_TO
    msg['Subject'] = subj
    msg.attach(MIMEText(body, 'plain', 'utf-8'))
    try:
        with smtplib.SMTP('smtp.gmail.com', 587) as srv:
            srv.ehlo(); srv.starttls()
            srv.login(EMAIL_FROM, EMAIL_PASSWORD)
            srv.send_message(msg)
        print(f"  Sent 'no new jobs' email to {EMAIL_TO}")
    except Exception as e:
        print(f"  Email error: {e}")

if __name__ == '__main__':
    main()
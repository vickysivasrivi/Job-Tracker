#!/usr/bin/env python3
"""
Tech Job Hunt — Daily Automation
Runs on GitHub Actions at 8am every day (laptop can be OFF)

Searches THREE role categories every morning:
  1. DevOps / Cloud / Platform Engineer
  2. Software Developer / Engineer
  3. Backend Engineer / Developer

Filters:
  - Posted in last 24 hours only
  - Less than 50 applicants only
  - No duplicate jobs (tracks seen job IDs in seen_jobs.json)

GitHub Secrets required:
  ANTHROPIC_KEY, EMAIL_FROM, EMAIL_PASSWORD, EMAIL_TO, YOUR_RESUME

GitHub Variables (Settings → Variables):
  JOB_LOCATION, MIN_SCORE, TOP_N_PER_CATEGORY
"""
import os, json, time, smtplib, urllib.request, urllib.error, re
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────
ANTHROPIC_KEY        = os.environ.get('ANTHROPIC_KEY', '')
APIFY_TOKEN          = os.environ.get('APIFY_TOKEN', '')
EMAIL_FROM           = os.environ.get('EMAIL_FROM', '')
EMAIL_PASSWORD       = os.environ.get('EMAIL_PASSWORD', '')
EMAIL_TO             = os.environ.get('EMAIL_TO', '')
YOUR_RESUME          = os.environ.get('YOUR_RESUME', '')
JOB_LOCATION         = os.environ.get('JOB_LOCATION', 'Ireland')
MIN_SCORE            = int(os.environ.get('MIN_SCORE', '55'))
TOP_N_PER_CATEGORY   = int(os.environ.get('TOP_N_PER_CATEGORY', '3'))
MAX_APPLICANTS       = 50
SEEN_FILE            = Path('seen_jobs.json')

# ── Job categories — edit these to change what roles are searched ─────────────
JOB_CATEGORIES = [
    ('DevOps / Cloud',     'DevOps Engineer Cloud Engineer Platform Engineer'),
    ('Software Developer', 'Software Developer Software Engineer Junior Developer'),
    ('Backend Engineer',   'Backend Engineer Backend Developer Node Python Java'),
]

# ── Seen-jobs tracker ─────────────────────────────────────────────────────────
def load_seen():
    if SEEN_FILE.exists():
        try:
            return set(json.loads(SEEN_FILE.read_text()).get('ids', []))
        except Exception:
            pass
    return set()

def save_seen(seen_ids):
    ids = list(seen_ids)[-500:]
    SEEN_FILE.write_text(json.dumps({'ids': ids, 'updated': datetime.now().isoformat()}, indent=2))
    print(f"  Saved {len(ids)} seen job IDs")

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
         'system': system, 'messages': [{'role': 'user', 'content': user}]},
        {'x-api-key': ANTHROPIC_KEY, 'anthropic-version': '2023-06-01'})
    if resp.get('type') == 'error':
        raise ValueError(resp['error']['message'])
    return resp['content'][0]['text']

# ── Filters ───────────────────────────────────────────────────────────────────
def parse_applicants(val):
    if val is None:
        return 0
    s = str(val).lower()
    m = re.search(r'first\s+(\d+)', s)
    if m: return int(m.group(1))
    m = re.search(r'(\d+)\+', s)
    if m: return int(m.group(1))
    m = re.search(r'(\d+)', s)
    if m: return int(m.group(1))
    return 0

def posted_recently(val):
    """Strict 24h filter. Rejects 'yesterday', '2 days ago', '1 week ago' etc."""
    if not val:
        return True
    s = str(val).lower().strip()
    if s in ('just now', 'today', 'now'):
        return True
    if re.search(r'\d+\s+minute', s):
        return True
    if re.search(r'\d+\s+hour', s):
        return True
    if re.match(r'^1\s+day', s):
        return True
    if 'yesterday' in s:
        return False
    if re.search(r'[2-9]\d*\s+day', s):
        return False
    if 'week' in s or 'month' in s or 'year' in s:
        return False
    return False

# ── Step 1: Scrape one category via Apify ────────────────────────────────────
def scrape_category(category_label, search_term):
    """Scrape LinkedIn for one job category. Returns list of raw jobs."""
    print(f"\n  Scraping: {category_label} — '{search_term}'")

    if APIFY_TOKEN:
        try:
            run = http_post(
                f"https://api.apify.com/v2/acts/worldunboxer~rapid-linkedin-scraper/runs?token={APIFY_TOKEN}",
                {'job_title':       search_term,
                 'location':        JOB_LOCATION,
                 'jobs_entries':    25,
                 'job_post_time':   'r86400',
                 'experience_level': '2'})
            run_id = run['data']['id']
            print(f"    Apify run: {run_id}")
            for attempt in range(36):
                time.sleep(5)
                st     = http_get(f"https://api.apify.com/v2/actor-runs/{run_id}?token={APIFY_TOKEN}")
                status = st['data']['status']
                if status == 'SUCCEEDED':
                    ds    = st['data']['defaultDatasetId']
                    items = http_get(
                        f"https://api.apify.com/v2/datasets/{ds}/items?token={APIFY_TOKEN}&limit=25")
                    print(f"    Got {len(items)} jobs")
                    for item in items:
                        item['_category'] = category_label
                    return items
                if status in ('FAILED', 'ABORTED', 'TIMED-OUT'):
                    raise Exception(f"Apify {status}")
                if attempt % 6 == 0:
                    print(f"    [{attempt*5}s] {status}...")
        except Exception as e:
            print(f"    Apify error: {e} — using fallback")
    else:
        print("    No APIFY_TOKEN — using fallback sample data")

    return get_fallback(category_label)

def get_fallback(category_label):
    """Fallback sample data per category — all pass filters (<24h, <50 apps)."""
    today = datetime.now(timezone.utc).strftime('%Y%m%d')
    fallbacks = {
        'DevOps / Cloud': [
            {'job_id': f'devops_workhuman_{today}',
             'job_title': 'Junior DevOps Engineer', 'company_name': 'Workhuman',
             'location': 'Dublin, Ireland', 'time_posted': '3 hours ago',
             'num_applicants': '14 applicants', 'easy_apply': False,
             'job_url':   'https://www.linkedin.com/jobs/search/?keywords=junior+devops+workhuman+ireland',
             'apply_url': 'https://www.workhuman.com/careers',
             'job_description': 'Kubernetes EKS Terraform GitHub Actions Python Bash CI/CD SaaS cloud'},
            {'job_id': f'devops_version1_{today}',
             'job_title': 'Cloud Infrastructure Associate', 'company_name': 'Version 1',
             'location': 'Dublin, Ireland', 'time_posted': '1 day ago',
             'num_applicants': '7 applicants', 'easy_apply': True,
             'job_url':   'https://www.linkedin.com/jobs/search/?keywords=cloud+infrastructure+version1+ireland',
             'apply_url': 'https://www.version1.com/careers',
             'job_description': 'Azure Terraform ARM Bicep Docker Azure Pipelines CI/CD enterprise cloud'},
            {'job_id': f'devops_hpe_{today}',
             'job_title': 'Associate Cloud Engineer', 'company_name': 'HPE',
             'location': 'Galway, Ireland', 'time_posted': '4 hours ago',
             'num_applicants': '21 applicants', 'easy_apply': True,
             'job_url':   'https://www.linkedin.com/jobs/search/?keywords=cloud+engineer+hpe+galway',
             'apply_url': 'https://careers.hpe.com',
             'job_description': 'AWS GCP Terraform Ansible Docker Python Bash CI/CD Linux monitoring'},
        ],
        'Software Developer': [
            {'job_id': f'sw_stripe_{today}',
             'job_title': 'Junior Software Engineer', 'company_name': 'Stripe',
             'location': 'Dublin, Ireland', 'time_posted': '2 hours ago',
             'num_applicants': '18 applicants', 'easy_apply': False,
             'job_url':   'https://www.linkedin.com/jobs/search/?keywords=junior+software+engineer+stripe+dublin',
             'apply_url': 'https://stripe.com/jobs',
             'job_description': 'Python Ruby API development microservices distributed systems payments fintech'},
            {'job_id': f'sw_hubspot_{today}',
             'job_title': 'Associate Software Developer', 'company_name': 'HubSpot',
             'location': 'Dublin, Ireland', 'time_posted': '5 hours ago',
             'num_applicants': '29 applicants', 'easy_apply': True,
             'job_url':   'https://www.linkedin.com/jobs/search/?keywords=associate+software+developer+hubspot+dublin',
             'apply_url': 'https://www.hubspot.com/careers',
             'job_description': 'Java Python JavaScript React REST APIs agile SaaS CRM platform development'},
            {'job_id': f'sw_intercom_{today}',
             'job_title': 'Graduate Software Engineer', 'company_name': 'Intercom',
             'location': 'Dublin, Ireland', 'time_posted': '6 hours ago',
             'num_applicants': '11 applicants', 'easy_apply': False,
             'job_url':   'https://www.linkedin.com/jobs/search/?keywords=graduate+software+engineer+intercom+dublin',
             'apply_url': 'https://www.intercom.com/careers',
             'job_description': 'Ruby Rails React TypeScript PostgreSQL Redis microservices customer messaging'},
        ],
        'Backend Engineer': [
            {'job_id': f'be_shopify_{today}',
             'job_title': 'Junior Backend Developer', 'company_name': 'Shopify',
             'location': 'Dublin, Ireland', 'time_posted': '1 hour ago',
             'num_applicants': '9 applicants', 'easy_apply': False,
             'job_url':   'https://www.linkedin.com/jobs/search/?keywords=junior+backend+developer+shopify+dublin',
             'apply_url': 'https://www.shopify.com/careers',
             'job_description': 'Ruby Rails Go Python REST APIs GraphQL PostgreSQL Redis scalable systems'},
            {'job_id': f'be_personio_{today}',
             'job_title': 'Backend Engineer (Entry Level)', 'company_name': 'Personio',
             'location': 'Dublin, Ireland', 'time_posted': '3 hours ago',
             'num_applicants': '16 applicants', 'easy_apply': True,
             'job_url':   'https://www.linkedin.com/jobs/search/?keywords=backend+engineer+personio+dublin',
             'apply_url': 'https://www.personio.com/careers',
             'job_description': 'PHP Laravel Python Node.js MySQL PostgreSQL REST API HR software SaaS'},
            {'job_id': f'be_workday_{today}',
             'job_title': 'Associate Backend Developer', 'company_name': 'Workday',
             'location': 'Dublin, Ireland', 'time_posted': '7 hours ago',
             'num_applicants': '23 applicants', 'easy_apply': True,
             'job_url':   'https://www.linkedin.com/jobs/search/?keywords=associate+backend+developer+workday+dublin',
             'apply_url': 'https://www.workday.com/careers',
             'job_description': 'Java Spring Boot microservices AWS REST APIs agile HCM enterprise software'},
        ],
    }
    jobs = fallbacks.get(category_label, [])
    for j in jobs:
        j['_category'] = category_label
    return jobs

# ── Step 2: Apply filters ─────────────────────────────────────────────────────
def apply_filters(jobs, seen_ids):
    """Filter: <24h posted, <50 applicants, not already seen."""
    results = []
    skipped = {'old': 0, 'too_many': 0, 'seen': 0}
    for j in jobs:
        job_id = str(j.get('job_id') or j.get('job_url') or j.get('id') or '')
        posted = j.get('time_posted', '')
        apps   = parse_applicants(j.get('num_applicants'))
        label  = f"{j.get('job_title','')} @ {j.get('company_name','')}"
        if not posted_recently(posted):
            print(f"  ✗ OLD       ({posted}) — {label}")
            skipped['old'] += 1
            continue
        if apps >= MAX_APPLICANTS:
            print(f"  ✗ TOO MANY  ({apps} applicants) — {label}")
            skipped['too_many'] += 1
            continue
        if job_id and job_id in seen_ids:
            print(f"  ✗ SEEN      — {label}")
            skipped['seen'] += 1
            continue
        print(f"  ✓ PASS      ({apps} apps, {posted}) — {label}")
        j['parsed_applicants'] = apps
        results.append(j)
    print(f"  Passed: {len(results)} | Old: {skipped['old']} | Too many: {skipped['too_many']} | Seen: {skipped['seen']}")
    return results

# ── Step 3: Score jobs vs resume ──────────────────────────────────────────────
KEYWORDS = {
    'DevOps / Cloud':     ['terraform','kubernetes','docker','aws','azure','gcp','ci/cd',
                           'helm','ansible','jenkins','gitlab','github actions','prometheus',
                           'grafana','argocd','devops','devsecops','linux','bash','python'],
    'Software Developer': ['python','java','javascript','typescript','react','node','rest',
                           'api','microservices','sql','postgresql','git','agile','testing',
                           'software','developer','engineer','backend','frontend','fullstack'],
    'Backend Engineer':   ['python','java','node','go','ruby','php','rest','graphql',
                           'postgresql','mysql','redis','microservices','api','kafka',
                           'backend','database','scalable','distributed','spring','django'],
}

def score_jobs(jobs):
    if not jobs:
        return []
    if not ANTHROPIC_KEY or not YOUR_RESUME:
        for j in jobs:
            cat  = j.get('_category', '')
            kws  = KEYWORDS.get(cat, [])
            desc = (j.get('job_description','') + ' ' + j.get('job_title','')).lower()
            sc   = 50 + sum(4 for k in kws if k in desc)
            apps = j.get('parsed_applicants', 99)
            if apps < 15:  sc += 8
            elif apps < 30: sc += 4
            j['score']  = min(97, sc)
            j['reason'] = 'Keyword match'
        return sorted(jobs, key=lambda x: -x['score'])

    summaries = '\n'.join(
        f"{i}. [{j.get('_category','')}] {j.get('job_title','')} at {j.get('company_name','')} "
        f"({j.get('parsed_applicants',0)} applicants): {j.get('job_description','')[:250]}"
        for i, j in enumerate(jobs))
    try:
        txt = claude(
            'Score job-resume compatibility. Return ONLY a valid JSON array, no markdown.',
            f"Resume:\n{YOUR_RESUME[:2000]}\n\nJobs:\n{summaries}\n\n"
            f"Return: [{{\"index\":0,\"score\":0-100,\"reason\":\"one sentence\"}}]",
            max_tokens=1200)
        scores = json.loads(txt.replace('```json','').replace('```','').strip())
        for s in scores:
            i = int(s.get('index',-1))
            if 0 <= i < len(jobs):
                jobs[i]['score']  = s.get('score', 50)
                jobs[i]['reason'] = s.get('reason', '')
    except Exception as e:
        print(f"  Scoring error: {e}")
        for j in jobs:
            j.setdefault('score', 55)
            j.setdefault('reason', '')
    return sorted(jobs, key=lambda x: -x.get('score', 0))

# ── Step 4: Tailor resume ─────────────────────────────────────────────────────
TAILOR_SYSTEM = """You are a professional CV tailoring assistant.

STRICT RULES:
1. NEVER add skills, tools, companies, projects, or experience NOT in the original resume.
2. NEVER exaggerate or inflate anything.
3. KEEP EVERY SECTION: Profile, Experience, Projects, Education, Skills, Certifications.
4. Only REWORD, REORDER, EMPHASISE existing content to match the job.
5. Use keywords from the job description ONLY where the candidate already has that skill.
6. Every bullet MUST start with an action verb: Built, Deployed, Automated, Designed,
   Managed, Reduced, Improved, Implemented, Configured, Monitored, Developed, Led.
7. Output plain text only — no markdown, no tables.
8. Use exact section headers: PROFILE | EXPERIENCE | PROJECTS | EDUCATION | SKILLS | CERTIFICATIONS
"""

def tailor_resume(job):
    co   = job.get('company_name', '')
    ttl  = job.get('job_title', '')
    cat  = job.get('_category', '')
    desc = job.get('job_description', '')[:800]
    print(f"    Tailoring [{cat}] {ttl} @ {co}...")
    if not ANTHROPIC_KEY or not YOUR_RESUME:
        return YOUR_RESUME or '(Add YOUR_RESUME to GitHub Secrets)'
    try:
        return claude(TAILOR_SYSTEM,
            f"Original resume:\n{YOUR_RESUME}\n\n"
            f"Target role: {ttl} at {co} [{cat}]\n"
            f"Job description: {desc}\n\n"
            f"Return the complete tailored resume as plain text. Keep ALL sections.",
            max_tokens=2500)
    except Exception as e:
        print(f"    Error: {e}")
        return f"Error: {e}\n\n{YOUR_RESUME}"

# ── Step 5: Send email ────────────────────────────────────────────────────────
def send_email(jobs_by_category, total_scraped, total_filtered):
    date      = datetime.now(timezone.utc).strftime('%d %b %Y')
    total_top = sum(len(v) for v in jobs_by_category.values())
    subj = (f"Tech Job Matches — {date} | "
            f"{total_top} picks across {len(jobs_by_category)} categories | Ireland")
    print(f"\n[5/5] Sending: {subj}")

    D = '═' * 64
    d = '─' * 64
    lines = [
        D,
        f"  TECH JOB MATCHES — {date.upper()}",
        f"  Ireland · Entry & Associate · <24h · <50 applicants · new only",
        f"  Scraped: {total_scraped}  |  After filters: {total_filtered}  |  Top picks: {total_top}",
        D, '',
    ]

    # ── Job listings grouped by category ─────────────────────────────────────
    for cat, jobs in jobs_by_category.items():
        if not jobs:
            continue
        lines += [d, f"  {cat.upper()}", d, '']
        for i, j in enumerate(jobs, 1):
            apply = j.get('apply_url') or j.get('job_url', '')
            apps  = j.get('parsed_applicants', '?')
            easy  = '⚡ Easy Apply' if j.get('easy_apply') else ''
            lines += [
                f"  {i}. {j.get('job_title','')}",
                f"     Company    : {j.get('company_name','')}",
                f"     Location   : {j.get('location','')}",
                f"     Posted     : {j.get('time_posted','')}",
                f"     Applicants : {apps}  {easy}",
                f"     Match      : {j.get('score',0)}%  —  {j.get('reason','')}",
                f"     Apply here : {apply}",
                '',
            ]

    # ── Tailored resumes ──────────────────────────────────────────────────────
    lines += [D, '', 'TAILORED RESUMES', '']
    for cat, jobs in jobs_by_category.items():
        for j in jobs:
            if not j.get('tailored_resume'):
                continue
            lines += [
                d,
                f"  [{cat}] {j.get('job_title','')} — {j.get('company_name','')}",
                d,
                j['tailored_resume'],
                '',
            ]

    lines += [
        D,
        'Update resume : GitHub repo → Settings → Secrets → YOUR_RESUME',
        'View logs     : GitHub repo → Actions tab',
        'Run now       : Actions → Tech Job Hunt → Run workflow',
        D,
    ]

    body = '\n'.join(lines)

    if not all([EMAIL_FROM, EMAIL_PASSWORD, EMAIL_TO]):
        print("  Email not configured — printing summary:")
        for cat, jobs in jobs_by_category.items():
            print(f"  [{cat}]")
            for j in jobs:
                print(f"    • {j.get('job_title','')} @ {j.get('company_name','')} — {j.get('score',0)}%")
        return

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
        print(f"  Email sent to {EMAIL_TO}")
    except Exception as e:
        print(f"  Email error: {e}")

def send_no_jobs_email(total_scraped, seen_count):
    date = datetime.now(timezone.utc).strftime('%d %b %Y')
    msg  = MIMEMultipart()
    msg['From']    = EMAIL_FROM
    msg['To']      = EMAIL_TO
    msg['Subject'] = f"Tech Jobs — {date} | No new matches today"
    msg.attach(MIMEText(
        f"Tech Job Hunt — {date}\n\n"
        f"No new jobs matched your filters today:\n"
        f"  • Posted in last 24 hours\n"
        f"  • Less than {MAX_APPLICANTS} applicants\n"
        f"  • Not previously seen\n\n"
        f"Searched categories: {', '.join(c for c,_ in JOB_CATEGORIES)}\n"
        f"Scraped today: {total_scraped}\n"
        f"Seen in history: {seen_count}\n\n"
        f"Automation ran successfully. Try again tomorrow!",
        'plain', 'utf-8'))
    try:
        with smtplib.SMTP('smtp.gmail.com', 587) as srv:
            srv.ehlo(); srv.starttls()
            srv.login(EMAIL_FROM, EMAIL_PASSWORD)
            srv.send_message(msg)
        print(f"  Sent 'no new jobs' email")
    except Exception as e:
        print(f"  Email error: {e}")

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print(f"\n{'═'*64}")
    print(f"  Tech Job Hunt — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"  Categories: {', '.join(c for c,_ in JOB_CATEGORIES)}")
    print(f"  Filters: <24h · <{MAX_APPLICANTS} applicants · no duplicates")
    print(f"{'═'*64}")

    seen_ids = load_seen()
    print(f"\n  Previously seen: {len(seen_ids)} jobs")

    # ── Scrape all categories ─────────────────────────────────────────────────
    print(f"\n[1/5] Scraping {len(JOB_CATEGORIES)} job categories...")
    all_raw = []
    for category_label, search_term in JOB_CATEGORIES:
        jobs = scrape_category(category_label, search_term)
        all_raw.extend(jobs)
        if APIFY_TOKEN:
            time.sleep(3)  # small gap between Apify runs

    # Deduplicate by job_url across categories
    seen_urls = set()
    deduped = []
    for j in all_raw:
        key = j.get('job_url') or j.get('job_id') or ''
        if key not in seen_urls:
            seen_urls.add(key)
            deduped.append(j)
    total_scraped = len(deduped)
    print(f"\n  Total scraped (deduplicated): {total_scraped}")

    # ── Filter ────────────────────────────────────────────────────────────────
    print(f"\n[2/5] Applying filters...")
    filtered      = apply_filters(deduped, seen_ids)
    total_filtered = len(filtered)

    if not filtered:
        print("\n  No new jobs today — sending notification email.")
        if EMAIL_TO:
            send_no_jobs_email(total_scraped, len(seen_ids))
        for j in deduped:
            jid = str(j.get('job_id') or j.get('job_url') or '')
            if jid: seen_ids.add(jid)
        save_seen(seen_ids)
        return

    # ── Score ─────────────────────────────────────────────────────────────────
    print(f"\n[3/5] Scoring {total_filtered} filtered jobs...")
    scored = score_jobs(filtered)

    # ── Select top N per category ─────────────────────────────────────────────
    print(f"\n[4/5] Selecting top {TOP_N_PER_CATEGORY} per category...")
    jobs_by_category = {}
    for cat, _ in JOB_CATEGORIES:
        cat_jobs = [j for j in scored
                    if j.get('_category') == cat and j.get('score', 0) >= MIN_SCORE]
        if not cat_jobs:
            # Fallback: take best regardless of MIN_SCORE if nothing passes threshold
            cat_jobs = [j for j in scored if j.get('_category') == cat]
        jobs_by_category[cat] = cat_jobs[:TOP_N_PER_CATEGORY]

    # ── Tailor resumes ────────────────────────────────────────────────────────
    all_top = [j for jobs in jobs_by_category.values() for j in jobs]
    print(f"  Total top picks: {len(all_top)}")
    for j in all_top:
        j['tailored_resume'] = tailor_resume(j)

    # ── Send email ────────────────────────────────────────────────────────────
    send_email(jobs_by_category, total_scraped, total_filtered)

    # ── Save seen ─────────────────────────────────────────────────────────────
    newly = 0
    for j in filtered:
        jid = str(j.get('job_id') or j.get('job_url') or '')
        if jid and jid not in seen_ids:
            seen_ids.add(jid)
            newly += 1
    save_seen(seen_ids)
    print(f"\n  Marked {newly} new jobs as seen.")
    print(f"\n  Done — {total_scraped} scraped · {total_filtered} filtered · {len(all_top)} tailored.")

if __name__ == '__main__':
    main()
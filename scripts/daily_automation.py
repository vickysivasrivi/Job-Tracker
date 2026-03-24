#!/usr/bin/env python3
"""
DevOps Job Hunt — Daily Automation
Runs on GitHub Actions at 8am every day (laptop can be OFF)

Secrets required in GitHub repo Settings → Secrets → Actions:
  ANTHROPIC_KEY, EMAIL_FROM, EMAIL_PASSWORD, EMAIL_TO,
  YOUR_RESUME, JOB_TITLE, JOB_LOCATION, APIFY_TOKEN (optional)
"""
import os, sys, json, time, smtplib, urllib.request, urllib.error, textwrap
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

# ── Config ────────────────────────────────────────────────────────────────────
ANTHROPIC_KEY  = os.environ.get('ANTHROPIC_KEY', '')
APIFY_TOKEN    = os.environ.get('APIFY_TOKEN', '')
EMAIL_FROM     = os.environ.get('EMAIL_FROM', '')
EMAIL_PASSWORD = os.environ.get('EMAIL_PASSWORD', '')
EMAIL_TO       = os.environ.get('EMAIL_TO', '')
YOUR_RESUME    = os.environ.get('YOUR_RESUME', '')
JOB_TITLE      = os.environ.get('JOB_TITLE', 'DevOps Engineer')
JOB_LOCATION   = os.environ.get('JOB_LOCATION', 'Ireland')
MIN_SCORE      = int(os.environ.get('MIN_SCORE', '60'))
TOP_N          = int(os.environ.get('TOP_N', '5'))

# ── HTTP helpers ──────────────────────────────────────────────────────────────
def post(url, body, headers=None):
    data = json.dumps(body).encode()
    req  = urllib.request.Request(url, data=data,
             headers={'Content-Type': 'application/json', **(headers or {})})
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.loads(r.read())

def get(url, headers=None):
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())

def claude(system, user, max_tokens=2000):
    if not ANTHROPIC_KEY:
        raise ValueError("No ANTHROPIC_KEY set")
    resp = post('https://api.anthropic.com/v1/messages',
        {'model': 'claude-sonnet-4-20250514', 'max_tokens': max_tokens,
         'system': system, 'messages': [{'role': 'user', 'content': user}]},
        {'x-api-key': ANTHROPIC_KEY, 'anthropic-version': '2023-06-01'})
    if resp.get('type') == 'error':
        raise ValueError(resp['error']['message'])
    return resp['content'][0]['text']

# ── Step 1: Scrape LinkedIn via Apify ────────────────────────────────────────
def scrape_jobs():
    print(f"[1/4] Scraping LinkedIn: '{JOB_TITLE}' in {JOB_LOCATION}...")
    if APIFY_TOKEN:
        try:
            run = post(
                f"https://api.apify.com/v2/acts/worldunboxer~rapid-linkedin-scraper/runs?token={APIFY_TOKEN}",
                {'job_title': JOB_TITLE, 'location': JOB_LOCATION,
                 'jobs_entries': 25, 'job_post_time': 'r86400', 'experience_level': '2'})
            run_id = run['data']['id']
            print(f"  Apify run: {run_id}")
            for _ in range(30):
                time.sleep(5)
                st = get(f"https://api.apify.com/v2/actor-runs/{run_id}?token={APIFY_TOKEN}")
                status = st['data']['status']
                if status == 'SUCCEEDED':
                    ds = st['data']['defaultDatasetId']
                    items = get(f"https://api.apify.com/v2/datasets/{ds}/items?token={APIFY_TOKEN}&limit=25")
                    print(f"  Got {len(items)} live jobs from LinkedIn")
                    return items
                if status in ('FAILED', 'ABORTED'):
                    raise Exception(f"Apify {status}")
                print(f"  Polling... {status}")
        except Exception as e:
            print(f"  Apify error: {e} — using fallback data")
    else:
        print("  No APIFY_TOKEN — using cached job data")

    return [
        {'job_title': 'DevOps Engineer', 'company_name': 'Accenture',
         'location': 'Dublin, Ireland', 'time_posted': 'today',
         'num_applicants': '103 applicants',
         'job_url': 'https://www.linkedin.com/jobs/view/4384547978',
         'apply_url': 'https://www.accenture.com/ie-en/careers/jobdetails?id=R00316490_en',
         'job_description': 'Azure DevOps GitLab CI Terraform Kubernetes AKS Docker Python Bash DevSecOps IaC monitoring CI/CD pipelines cloud infrastructure automation'},
        {'job_title': 'Software Cloud Engineer II', 'company_name': 'Medtronic',
         'location': 'Galway, Ireland', 'time_posted': 'yesterday',
         'num_applicants': '27 applicants',
         'job_url': 'https://www.linkedin.com/jobs/view/4385105554',
         'apply_url': 'https://www.linkedin.com/jobs/view/4385105554',
         'job_description': 'AWS S3 Docker Kubernetes Azure DevOps CI/CD pipelines .NET microservices cloud infrastructure IoT medical devices automation'},
        {'job_title': 'Cloud DevOps Engineer', 'company_name': 'Talent Partners',
         'location': 'Dublin, Ireland', 'time_posted': '1 week ago',
         'num_applicants': '194 applicants',
         'job_url': 'https://www.linkedin.com/jobs/view/4372752882',
         'apply_url': 'https://www.talentpartners.ie/current-openings',
         'job_description': 'Azure AKS Kubernetes Helm Jenkins CI/CD Graylog observability disaster recovery infrastructure automation'},
        {'job_title': 'Database Engineer Postgres AWS', 'company_name': 'SoSafe',
         'location': 'Ireland (Remote)', 'time_posted': '4 days ago',
         'num_applicants': '62 applicants',
         'job_url': 'https://www.linkedin.com/jobs/view/4373819145',
         'apply_url': 'https://jobs.ashbyhq.com/sosafe/9ac62265-6a1c-43ea-b81a-a2d93155c9cf/application',
         'job_description': 'PostgreSQL AWS RDS Aurora CloudWatch GitHub Actions CI/CD Lambda S3 database automation monitoring'},
        {'job_title': 'Associate Cloud Engineer', 'company_name': 'Dell Technologies',
         'location': 'Dublin, Ireland', 'time_posted': '2 days ago',
         'num_applicants': '45 applicants',
         'job_url': 'https://www.linkedin.com/jobs/search/?keywords=associate+cloud+engineer+dell+ireland',
         'apply_url': 'https://jobs.dell.com',
         'job_description': 'AWS GCP Terraform Python CI/CD pipelines cloud automation monitoring Linux scripting infrastructure'},
    ]

# ── Step 2: Score jobs vs resume ──────────────────────────────────────────────
def score_jobs(jobs):
    print(f"[2/4] Scoring {len(jobs)} jobs...")
    if not ANTHROPIC_KEY or not YOUR_RESUME:
        kw = ['terraform','kubernetes','docker','aws','azure','python','bash','linux','ci/cd','devops']
        for j in jobs:
            desc = (j.get('job_description','') + j.get('job_title','')).lower()
            j['score'] = min(95, 50 + sum(4 for k in kw if k in desc))
            j['match_reason'] = 'Keyword match'
        return sorted(jobs, key=lambda x: -x['score'])

    summaries = '\n'.join(
        f"{i}. {j.get('job_title','')} at {j.get('company_name','')}: {j.get('job_description','')[:300]}"
        for i, j in enumerate(jobs))
    try:
        txt = claude(
            'Score job-resume match for DevOps/Cloud roles. Return ONLY a JSON array, no markdown.',
            f"Candidate resume:\n{YOUR_RESUME[:2000]}\n\nJobs:\n{summaries}\n\n"
            f"Return: [{{\"index\": 0, \"score\": 0-100, \"reason\": \"one sentence\"}}]",
            max_tokens=1000)
        scores = json.loads(txt.replace('```json','').replace('```','').strip())
        for s in scores:
            i = s.get('index', -1)
            if 0 <= i < len(jobs):
                jobs[i]['score'] = s.get('score', 50)
                jobs[i]['match_reason'] = s.get('reason', '')
    except Exception as e:
        print(f"  Scoring error: {e}")
        for j in jobs:
            j.setdefault('score', 55)
            j.setdefault('match_reason', '')
    return sorted(jobs, key=lambda x: -x.get('score', 0))

# ── Step 3: Tailor resume (honest, section-complete) ─────────────────────────
TAILOR_SYSTEM = """You are a professional CV writer. Your job is to tailor the candidate's resume for a specific role.

STRICT RULES — follow every one:
1. NEVER add any skill, tool, technology, company, project, certification, or qualification that is NOT in the original resume.
2. NEVER exaggerate or inflate experience levels, years, or scope.
3. KEEP EVERY SECTION from the original: Profile, Experience, Projects, Education, Skills, Certifications, Awards — do not drop any section.
4. Only REWORD, REORDER, and EMPHASISE existing content to better match the job.
5. Use keywords from the job description ONLY where the candidate already has that skill.
6. Start each bullet point with a strong action verb (Built, Deployed, Automated, Designed, Managed, Reduced, Improved, Implemented, Led, Configured, Monitored, Developed).
7. Keep bullet points concise (1 line each where possible).
8. Output plain text only — no tables, no columns, no images.
9. Use these EXACT section headers: PROFILE | EXPERIENCE | PROJECTS | EDUCATION | SKILLS | CERTIFICATIONS
"""

def tailor_resume(job):
    co  = job.get('company_name', '')
    ttl = job.get('job_title', '')
    desc= job.get('job_description', '')[:800]
    print(f"    Tailoring for {co}...")
    if not ANTHROPIC_KEY or not YOUR_RESUME:
        return YOUR_RESUME or '(No resume provided)'
    try:
        return claude(TAILOR_SYSTEM,
            f"Original resume:\n{YOUR_RESUME}\n\n"
            f"Target role: {ttl} at {co}\n"
            f"Job description: {desc}\n\n"
            f"Tailor the resume. Keep ALL sections. Return plain text only.",
            max_tokens=2500)
    except Exception as e:
        return f"Tailoring error: {e}\n\n{YOUR_RESUME}"

# ── Step 4: Build & send email ────────────────────────────────────────────────
def send_email(top_jobs):
    date = datetime.now().strftime('%d %b %Y')
    subj = f"DevOps Job Matches — {date} ({len(top_jobs)} picks, Ireland)"
    print(f"[4/4] Sending email: {subj}")

    sep  = '─' * 62
    dsep = '═' * 62

    lines = [
        dsep,
        f"  DEVOPS JOB MATCHES — {date.upper()}",
        f"  Ireland · Entry & Associate Level · Top {len(top_jobs)} matches",
        dsep, '',
    ]

    for i, j in enumerate(top_jobs, 1):
        apply = j.get('apply_url') or j.get('job_url', '')
        lines += [
            f"{i}. {j.get('job_title','')}",
            f"   Company  : {j.get('company_name','')}",
            f"   Location : {j.get('location','')}",
            f"   Posted   : {j.get('time_posted','')}  ·  {j.get('num_applicants','')}",
            f"   Match    : {j.get('score',0)}%  —  {j.get('match_reason','')}",
            f"   Apply    : {apply}",
            '',
        ]

    lines += [dsep, '', 'TAILORED RESUMES FOR TOP MATCHES', dsep, '']
    for j in top_jobs:
        lines += [
            sep,
            f"  {j.get('job_title','')} — {j.get('company_name','')}",
            sep,
            j.get('tailored_resume', ''),
            '',
        ]

    lines += [
        dsep,
        'To update your resume: GitHub repo → Settings → Secrets → YOUR_RESUME',
        'To view run logs:      GitHub repo → Actions tab',
        dsep,
    ]

    body = '\n'.join(lines)

    if not all([EMAIL_FROM, EMAIL_PASSWORD, EMAIL_TO]):
        print("  Email credentials not set. Job list:")
        for j in top_jobs:
            print(f"  • {j.get('job_title','')} at {j.get('company_name','')} — {j.get('score',0)}%")
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
        print(f"  Sent to {EMAIL_TO}")
    except Exception as e:
        print(f"  Email error: {e}")
        print("  First 500 chars of body:")
        print(body[:500])

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print(f"\n{'═'*62}")
    print(f"  DevOps Job Automation — {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"{'═'*62}\n")

    jobs   = scrape_jobs()
    scored = score_jobs(jobs)
    top    = [j for j in scored if j.get('score', 0) >= MIN_SCORE][:TOP_N]
    if not top:
        top = scored[:min(TOP_N, len(scored))]

    print(f"[3/4] Tailoring resumes for {len(top)} top matches...")
    for j in top:
        j['tailored_resume'] = tailor_resume(j)

    send_email(top)
    print(f"\n  Done — {len(jobs)} scraped, {len(top)} tailored, email sent.")

if __name__ == '__main__':
    main()

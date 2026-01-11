APPLICATION RUNBOOK — chip_dashboard (pravoo.in)

Purpose
This runbook documents exactly how the `chip_dashboard` application is running on the server (srv1178562). It lists the services and files involved, the exact commands to make code changes live on the internet, health checks, backups, and troubleshooting steps. Use this as the single source of operations knowledge for this deployment.

Repository & paths
- Repo root: /root/Chips_dashboard
- Django project: /root/Chips_dashboard/chip_dashboard
- manage.py: /root/Chips_dashboard/chip_dashboard/manage.py
- Virtualenv (project): /root/Chips_dashboard/chip_dashboard/myenv
- SQLite DB (dev fallback): /root/Chips_dashboard/chip_dashboard/db.sqlite3
- Systemd unit: /etc/systemd/system/broker_portal.service
- Nginx site config (example): /etc/nginx/sites-available/django (symlinked to sites-enabled)
- Domain: pravoo.in
- Server public IP: 72.61.148.117

Services in use (what runs and why)
- systemd service `broker_portal` — runs Gunicorn using the project venv, keeps the app always-up and restarts on failure.
  - ExecStart uses: /root/Chips_dashboard/chip_dashboard/myenv/bin/gunicorn broker_portal.wsgi:application --bind 0.0.0.0:8001 --workers 3 --timeout 60
- Gunicorn — WSGI server that executes the Django app (production-facing behind nginx).
- nginx — reverse proxy and TLS terminator (serves SSL certs from Let's Encrypt/Certbot) and proxies requests to Gunicorn on localhost:8001.
- Certbot (Let's Encrypt) — provides TLS certs installed under /etc/letsencrypt/live/pravoo.in/
- PostgreSQL (optional) — production DB is documented in POSTGRESQL_SETUP.md but not necessarily configured here; SQLite is used as a local fallback.
- systemd (OS) — supervises the Gunicorn service, ensures auto-restart, and is used to start/stop services.

Key environment & settings
- DJANGO_SETTINGS_MODULE: broker_portal.settings (set in systemd environment or the settings file)
- ALLOWED_HOSTS must include `pravoo.in` and `72.61.148.117` (configured in broker_portal/settings.py or via env vars)
- USE_SQLITE=1 is supported as a dev fallback. In production, configure Postgres connection env vars and disable USE_SQLITE.

Quick status checks (what to run now)
- Check systemd status (Gunicorn):
  sudo systemctl status broker_portal --no-pager -l
- Tail Gunicorn logs (journal):
  sudo journalctl -u broker_portal -f
- Check nginx status and config:
  sudo nginx -t
  sudo systemctl status nginx
  sudo systemctl reload nginx  # after config changes
- Check listening sockets (confirm binds):
  ss -ltnp | egrep ':8001|:80|:443' || true
- Check site via curl (local & external):
  curl -I -H "Host: pravoo.in" http://127.0.0.1
  curl -I -k -H "Host: pravoo.in" https://127.0.0.1
  curl -I https://pravoo.in

Full deployment steps when code changes (exact commands)
Follow these steps when you have pushed code to the repo and want to deploy changes to the live site.

1) Pull latest code on server
```bash
cd /root/Chips_dashboard
git fetch origin && git pull origin main
```
Why: Ensure server has the authoritative code. If git push from your local machine was rejected earlier, re-run the fetch/pull sequence to sync.

2) Create a quick backup of the current application state
- Application code: create a git backup branch locally (safe rollback):
```bash
cd /root/Chips_dashboard
git switch -c backup-$(date +%Y%m%d%H%M)
git switch main
```
- Database (production):
  - If PostgreSQL (recommended):
```bash
mkdir -p /root/Chips_dashboard/db_backups
PGUSER=dbuser PGPASSWORD=yourpass pg_dump -h localhost -U dbuser -Fc dbname > /root/Chips_dashboard/db_backups/prod_$(date +%Y%m%d%H%M).dump
```
  - If sqlite (fallback):
```bash
cd /root/Chips_dashboard/chip_dashboard
[ -f db.sqlite3 ] && cp db.sqlite3 db.sqlite3.bak.$(date +%Y%m%d%H%M)
```
Why: Always back up DB before running migrations.

3) Install/update python dependencies (if requirements changed)
```bash
cd /root/Chips_dashboard
/root/Chips_dashboard/chip_dashboard/myenv/bin/pip install -r requirements.txt
```

4) Apply database migrations
- NOTES: A previous migration attempt failed with ValueError about `core.customuser`. If that error is present, stop here and perform the Troubleshooting migrations section below. Otherwise run:
```bash
cd /root/Chips_dashboard/chip_dashboard
# For Postgres, ensure environment/config points to Postgres.
sudo -u www-data /root/Chips_dashboard/chip_dashboard/myenv/bin/python manage.py migrate --noinput
# For sqlite fallback (dev only)
USE_SQLITE=1 /root/Chips_dashboard/chip_dashboard/myenv/bin/python manage.py migrate --noinput
```

5) Collect static files
```bash
cd /root/Chips_dashboard/chip_dashboard
/root/Chips_dashboard/chip_dashboard/myenv/bin/python manage.py collectstatic --noinput
```
Ensure `STATIC_ROOT` in settings.py points to a directory that nginx serves.

6) Restart Gunicorn systemd service so new code is used
```bash
sudo systemctl daemon-reload
sudo systemctl restart broker_portal
sudo systemctl enable broker_portal
sudo systemctl status broker_portal --no-pager -l
```
Watch logs for errors:
```bash
sudo journalctl -u broker_portal -n 200 --no-pager
```

7) Reload nginx if you changed nginx config or static files
```bash
sudo nginx -t && sudo systemctl reload nginx
```

8) Verify site is up
```bash
# local via nginx proxy
curl -I -k -H "Host: pravoo.in" https://127.0.0.1
# public
curl -I https://pravoo.in
```

Health checks and monitoring commands
- Check Gunicorn worker timeouts and errors:
  sudo journalctl -u broker_portal -n 200 --no-pager | egrep "TIMEOUT|ERROR|Traceback|CRITICAL"
- Check for CSRF errors in logs:
  sudo journalctl -u broker_portal -n 200 --no-pager | egrep "CSRF|Forbidden"
- Check nginx errors:
  sudo tail -n 200 /var/log/nginx/error.log

Troubleshooting: migrations (lazy reference to core.customuser)
If `manage.py migrate` fails with an error like:
```
ValueError: The field admin.LogEntry.user was declared with a lazy reference to 'core.customuser', but app 'core' doesn't provide model 'customuser'.
```
Do this:
1) Check AUTH_USER_MODEL value in settings:
```bash
grep -n "AUTH_USER_MODEL" broker_portal/settings.py || true
```
It should be `AUTH_USER_MODEL = 'core.CustomUser'` if your custom user model is `CustomUser` in `core.models`.

2) Inspect model and migrations:
```bash
sed -n '1,240p' core/models.py
grep -R "customuser" -n core/migrations || true
```
3) Fix options:
- If AUTH_USER_MODEL is wrong, update it and re-run migrations.
- If migrations reference a wrong name (typo/case), create a corrective migration or (dev only) recreate DB.
- If unsure, ask for help: I can inspect and suggest a precise fix.

Troubleshooting: Gunicorn worker TIMEOUTs
Symptoms: journald shows `CRITICAL WORKER TIMEOUT` and `Worker exiting` frequently.
Fixes:
- Increase Gunicorn timeout and/or number of workers in the systemd unit ExecStart arguments, e.g. `--timeout 120 --workers 4`.
- If your app performs blocking I/O, consider using an asynchronous worker class (gevent) or background tasks.
Update unit example:
```
ExecStart=/root/Chips_dashboard/chip_dashboard/myenv/bin/gunicorn broker_portal.wsgi:application \
  --name broker_portal --bind 0.0.0.0:8001 --workers 4 --timeout 120
```
Then:
```bash
sudo systemctl daemon-reload
sudo systemctl restart broker_portal
```

Troubleshooting: CSRF failures
- Ensure nginx forwards Host and proto headers. Example nginx location block must include:
```
proxy_set_header Host $host;
proxy_set_header X-Real-IP $remote_addr;
proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
proxy_set_header X-Forwarded-Proto $scheme;
```
- Ensure `SESSION_COOKIE_SECURE` and `CSRF_COOKIE_SECURE` are True for HTTPS in settings.

Check for other processes occupying ports (free up 8000/8001)
```bash
ss -ltnp | egrep ':8000|:8001' || true
# Kill a PID (if safe) e.g. sudo kill <pid>
```

Rollback & emergency actions
- Quick rollback to previous code commit:
```bash
cd /root/Chips_dashboard
git checkout HEAD~1
sudo systemctl restart broker_portal
```
- Restore DB (sqlite):
```bash
cd /root/Chips_dashboard/chip_dashboard
cp db.sqlite3.bak.YOURTIMESTAMP db.sqlite3
sudo systemctl restart broker_portal
```
- Revert the pushed commit remotely (use carefully): create a revert commit or use GitHub to revert a PR. Avoid force-push unless absolutely required.

Routine operational commands (cheat sheet)
- Restart service: sudo systemctl restart broker_portal
- View status: sudo systemctl status broker_portal --no-pager -l
- Tail logs: sudo journalctl -u broker_portal -f
- Check nginx conf: sudo nginx -t ; sudo systemctl reload nginx
- Check listening sockets: ss -ltnp | egrep ':8001|:80|:443' || true
- Curl test: curl -I -k https://pravoo.in

Git workflow notes (how we handled push conflicts earlier)
- If `git push` is rejected because remote contains new commits:
  - Fetch remote: git fetch origin
  - Inspect differences: git log --oneline HEAD..origin/main
  - Create a local backup branch: git switch -c backup-YYYYMMDDHHMM
  - Rebase local changes: git pull --rebase origin main (or git rebase origin/main)
  - Resolve conflicts, then git push origin main
  - If you prefer merging: git merge origin/main then push

Appendix: Example systemd unit (actual file used on this host)
Path: /etc/systemd/system/broker_portal.service
```
[Unit]
Description=Gunicorn daemon for broker_portal Django app
After=network.target

[Service]
User=root
Group=root
Environment="PATH=/root/Chips_dashboard/chip_dashboard/myenv/bin"
Environment="DJANGO_SETTINGS_MODULE=broker_portal.settings"
WorkingDirectory=/root/Chips_dashboard/chip_dashboard
ExecStart=/root/Chips_dashboard/chip_dashboard/myenv/bin/gunicorn broker_portal.wsgi:application \
    --name broker_portal \
    --bind 0.0.0.0:8001 \
    --workers 3 \
    --timeout 60
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

Final notes
- The site is already publicly available via nginx -> Gunicorn on port 8001 and TLS is configured for `pravoo.in`.
- Migrations are the highest-risk step — always backup the DB before applying migrations and verify AUTH_USER_MODEL and migrations consistency.
- I can perform the deployment steps for you (pull, migrate, collectstatic, restart service) or inspect migrations if you'd like me to do that now.

Document history
- Created: 2026-01-11
- Author: automation (assistant)

# Quick Security Setup Guide

## 🚀 Quick Start (5 Minutes)

### Step 1: Install Dependencies

```bash
pip install -r requirements.txt
```

### Step 2: Create Environment File

Create a `.env` file in the project root:

```bash
# Copy the example (if .env.example exists)
cp .env.example .env

# Or create manually
touch .env
```

### Step 3: Generate SECRET_KEY

```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

Copy the output and add to `.env`:

```env
SECRET_KEY=your-generated-key-here
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1
```

### Step 4: Verify Installation

```bash
python manage.py check --deploy
```

This will check for common security issues.

### Step 5: Run Migrations

```bash
python manage.py migrate
```

### Step 6: Create Superuser

```bash
python manage.py createsuperuser
```

### Step 7: Run Server

```bash
python manage.py runserver
```

---

## 🔒 Production Checklist

Before deploying to production:

- [ ] Change `SECRET_KEY` in `.env`
- [ ] Set `DEBUG=False` in `.env`
- [ ] Configure `ALLOWED_HOSTS` with your domain
- [ ] Set up HTTPS/SSL certificate
- [ ] Configure email settings
- [ ] Use PostgreSQL (not SQLite)
- [ ] Set up proper static file serving
- [ ] Configure backups
- [ ] Review `SECURITY_DOCUMENTATION.md`

---

## ⚠️ Important Notes

1. **NEVER commit `.env` file** - It's in `.gitignore`
2. **Always use HTTPS in production**
3. **Keep dependencies updated** - Run `pip list --outdated` regularly
4. **Monitor security.log** - Check for suspicious activity

---

## 📚 More Information

See `SECURITY_DOCUMENTATION.md` for complete security details.


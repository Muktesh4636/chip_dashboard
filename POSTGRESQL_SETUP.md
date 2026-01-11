# PostgreSQL Setup Guide

This project now uses PostgreSQL for better performance, scalability, and efficiency.

## Prerequisites

1. **Install PostgreSQL** on your system:
   - **macOS**: `brew install postgresql@15` (or latest version)
   - **Ubuntu/Debian**: `sudo apt-get install postgresql postgresql-contrib`
   - **Windows**: Download from [PostgreSQL Official Website](https://www.postgresql.org/download/windows/)

2. **Start PostgreSQL service**:
   - **macOS**: `brew services start postgresql@15`
   - **Linux**: `sudo systemctl start postgresql`
   - **Windows**: PostgreSQL service should start automatically

## Setup Steps

### 1. Create PostgreSQL Database

```bash
# Connect to PostgreSQL
psql postgres

# Create database
CREATE DATABASE broker_portal;

# Create user (optional, or use default 'postgres' user)
CREATE USER broker_user WITH PASSWORD 'your_secure_password';

# Grant privileges
GRANT ALL PRIVILEGES ON DATABASE broker_portal TO broker_user;

# Exit PostgreSQL
\q
```

### 2. Install Python Dependencies

```bash
pip install -r requirements.txt
```

This will install `psycopg2-binary` (PostgreSQL adapter for Python).

### 3. Configure Environment Variables

Create a `.env` file in the project root (copy from `.env.example`):

```bash
cp .env.example .env
```

Edit `.env` and update database credentials:

```env
DB_NAME=broker_portal
DB_USER=postgres          # or your custom user
DB_PASSWORD=your_password
DB_HOST=localhost
DB_PORT=5432
```

### 4. Run Migrations

```bash
# Create migrations (if needed)
python3 manage.py makemigrations

# Apply migrations to PostgreSQL
python3 manage.py migrate
```

### 5. Create Superuser (if needed)

```bash
python3 manage.py createsuperuser
```

## Migrating from SQLite to PostgreSQL

If you have existing data in SQLite:

### Option 1: Fresh Start (Recommended for Development)

1. Backup your SQLite database (optional):
   ```bash
   cp db.sqlite3 db.sqlite3.backup
   ```

2. Run migrations on PostgreSQL:
   ```bash
   python3 manage.py migrate
   ```

3. Create new superuser:
   ```bash
   python3 manage.py createsuperuser
   ```

### Option 2: Migrate Existing Data

1. **Export from SQLite**:
   ```bash
   python3 manage.py dumpdata > data.json
   ```

2. **Switch to PostgreSQL** (update `.env` file)

3. **Run migrations on PostgreSQL**:
   ```bash
   python3 manage.py migrate
   ```

4. **Load data into PostgreSQL**:
   ```bash
   python3 manage.py loaddata data.json
   ```

## Verification

Test the connection:

```bash
python3 manage.py dbshell
```

You should see PostgreSQL prompt: `broker_portal=#`

Type `\dt` to list tables, then `\q` to exit.

## Performance Benefits

PostgreSQL provides:
- ✅ **Better concurrency**: Handles multiple simultaneous connections efficiently
- ✅ **ACID compliance**: Full transaction support
- ✅ **Advanced features**: JSON fields, full-text search, advanced indexing
- ✅ **Scalability**: Can handle large datasets and high traffic
- ✅ **Production-ready**: Industry standard for production deployments
- ✅ **Better performance**: Optimized query execution and indexing

## Troubleshooting

### Connection Error

If you get connection errors:

1. **Check PostgreSQL is running**:
   ```bash
   # macOS
   brew services list
   
   # Linux
   sudo systemctl status postgresql
   ```

2. **Verify credentials** in `.env` file

3. **Check PostgreSQL logs**:
   ```bash
   # macOS (Homebrew)
   tail -f /opt/homebrew/var/log/postgresql@15.log
   
   # Linux
   sudo tail -f /var/log/postgresql/postgresql-*.log
   ```

### Permission Denied

If you get permission errors:

```bash
# Grant privileges
psql postgres
GRANT ALL PRIVILEGES ON DATABASE broker_portal TO your_user;
\q
```

### Port Already in Use

If port 5432 is already in use:

1. Find the process: `lsof -i :5432`
2. Update `DB_PORT` in `.env` to use a different port
3. Or stop the conflicting PostgreSQL instance

## Production Deployment

For production, ensure:

1. **Strong password** for database user
2. **SSL enabled**: Set `DB_SSLMODE=require` in production `.env`
3. **Connection pooling**: Already configured in `settings.py`
4. **Backup strategy**: Set up regular PostgreSQL backups
5. **Monitoring**: Monitor database performance and connections

## Useful PostgreSQL Commands

```bash
# Connect to database
psql -U postgres -d broker_portal

# List all databases
\l

# List tables in current database
\dt

# Describe a table
\d table_name

# View database size
SELECT pg_size_pretty(pg_database_size('broker_portal'));

# Exit
\q
```


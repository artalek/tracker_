#!/usr/bin/env bash
set -euo pipefail

domain="${1:-}"
if [[ ! "$domain" =~ ^[a-zA-Z0-9-]+(\.eu)?\.pythonanywhere\.com$ ]]; then
    printf 'Usage: bash deploy/pythonanywhere.sh username.pythonanywhere.com\n' >&2
    exit 2
fi

cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
if [[ ! -x .venv/bin/python ]]; then
    "${PYTHON_BIN:-python3.13}" -m venv .venv
fi

python_bin=.venv/bin/python
"$python_bin" -m pip install --no-cache-dir -r requirements.txt

"$python_bin" - "$domain" <<'PY'
from pathlib import Path
from os import open as open_file
from secrets import token_urlsafe
from sys import argv

domain = argv[1]
database = Path("db.sqlite3").resolve()
configuration = Path(".env")
try:
    with open(configuration, "x", encoding="utf-8", opener=lambda path, flags: open_file(path, flags, 0o600)) as dotenv:
        dotenv.write(
            "DJANGO_DEBUG=0\n"
            f"DJANGO_SECRET_KEY={token_urlsafe(50)}\n"
            f"DJANGO_ALLOWED_HOSTS={domain}\n"
            f"DJANGO_CSRF_TRUSTED_ORIGINS=https://{domain}\n"
            "DJANGO_TRUST_PROXY=1\n"
            f"DATABASE_URL=sqlite:///{database}\n"
            "PRIVACY_OPERATOR_NAME=\n"
            "PRIVACY_CONTACT_EMAIL=\n"
        )
except FileExistsError:
    pass
configuration.chmod(0o600)
PY

export DJANGO_DEBUG=0
"$python_bin" manage.py migrate --noinput
"$python_bin" manage.py collectstatic --noinput --verbosity 0
"$python_bin" manage.py check --deploy
printf 'Project: %s\nVirtualenv: %s/.venv\nStatic directory: %s/staticfiles\n' "$PWD" "$PWD" "$PWD"

FROM python:3.12-slim

# Day of the build (build-arg of the CI): the Debian security updates are fetched again at least once a day instead
# of coming from the layer cache (libzstd CVE-2026-124851, 26/11/2026: fixed in trixie-security, missed by a cached layer)
ARG SECURITE_DEBIAN_DU=local
RUN echo "Debian security updates of ${SECURITE_DEBIAN_DU}" && apt-get update && apt-get upgrade -y --no-install-recommends && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PORT=8000

WORKDIR /app

RUN useradd --create-home --uid 10001 --user-group app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN DJANGO_SECRET_KEY=collectstatic-build-only POSTGRES_PASSWORD=collectstatic-build-only python manage.py collectstatic --noinput \
    && mkdir -p mediafiles prive && chown app:app mediafiles prive

USER 10001:10001

EXPOSE 8000

ENV FORWARDED_ALLOW_IPS=127.0.0.1
CMD ["sh", "-c", "exec gunicorn config.wsgi:application --bind 0.0.0.0:${PORT} --workers ${WEB_CONCURRENCY:-2} --access-logfile - --logger-class config.journal_gunicorn.JournalSansJeton --forwarded-allow-ips \"${FORWARDED_ALLOW_IPS}\""]

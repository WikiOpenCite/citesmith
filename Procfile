web: gunicorn --bind=0.0.0.0 --workers=4 --forwarded-allow-ips=* citesmith.web.web:app
migrate: python -m citesmith --log-level INFO migrate
process: python3 -m citesmith --log-level INFO process
combine: python3 -m citesmith --log-level INFO combine
publish: python3 -m citesmith --log-level INFO publish
watch: python3 -m citesmith --log-level INFO watch
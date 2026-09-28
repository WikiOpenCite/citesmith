web: gunicorn --bind=0.0.0.0 --workers=4 --forwarded-allow-ips=* citesmith.web.web:app
migrate: python -m citesmith migrate
process: python3 -m citesmith process
combine: python3 -m citesmith combine
publish: python3 -m citesmith publish
watch: python3 -m citesmith watch
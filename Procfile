web: gunicorn --bind=0.0.0.0 --workers=4 --forwarded-allow-ips=* citesmith.web.web:app
migrate: python -m citesmith --log-level INFO migrate
process: python3 -m citesmith --log-level INFO dump process
combine: python3 -m citesmith --log-level INFO dump combine
publish: python3 -m citesmith --log-level INFO dump publish
watch: python3 -m citesmith --log-level INFO dump watch
openalex-watch: python3 -m citesmith --log-level INFO openalex watch
openalex-process: python3 -m citesmith --log-level INFO openalex process
openalex-combine: python3 -m citesmith --log-level INFO openalex combine

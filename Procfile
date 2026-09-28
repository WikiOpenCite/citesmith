web: gunicorn --bind=0.0.0.0 --workers=4 --forwarded-allow-ips=* citesmith.web.web:app
migrate: python -m citesmith -c /data/project/citescoop/config.toml migrate
process: python3 -m citesmith -c /data/project/citescoop/config.toml process
combine: python3 -m citesmith -c /data/project/citescoop/config.toml combine
publish: python3 -m citesmith -c /data/project/citescoop/config.toml publish
watch: python3 -m citesmith -c /data/project/citescoop/config.toml watch
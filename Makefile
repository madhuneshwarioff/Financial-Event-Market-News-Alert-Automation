# Convenience targets. Everything here is a plain command you can also type.

.PHONY: help install demo run schedule test export site clean

help:
	@echo "install   install dependencies"
	@echo "demo      run the pipeline on bundled data and print the brief"
	@echo "run       run the pipeline live and deliver on configured channels"
	@echo "schedule  stay resident and run on the configured timer"
	@echo "test      run the test suite"
	@echo "export    rebuild website/data/dashboard.json"
	@echo "site      serve the website at http://localhost:8000"
	@echo "clean     remove caches and the local alert database"

install:
	pip install -r requirements.txt

demo:
	python run.py --demo --dry-run

run:
	python run.py

schedule:
	python run.py --schedule

test:
	pytest -q

export:
	python run.py --demo --export-only

site:
	cd website && python -m http.server 8000

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache
	rm -f data/alerts.db

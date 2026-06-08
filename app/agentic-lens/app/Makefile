.PHONY: test-integration

# Run from repo root. Install: pip install -r requirements-dev.txt
# Override Python: make test-integration PY=./agentic-lens/.venv/bin/python
PY ?= python3

test-integration:
	PYTHONPATH=. $(PY) -m pytest tests/ -q

PYTHON ?= python3
APP_PYTHON ?= .venv/bin/python
BUNDLE ?=

.PHONY: run dev setup editor test
run dev: setup
	$(APP_PYTHON) -m plate $(if $(BUNDLE),"$(BUNDLE)")

setup: .venv/.plate-dependencies editor

.venv/.plate-dependencies: requirements.txt
	test -x .venv/bin/python || $(PYTHON) -m venv .venv
	.venv/bin/python -m pip install -r requirements.txt
	touch $@

editor: plate/web/vendor/editor.js

node_modules/.plate-dependencies: package.json package-lock.json
	npm ci --no-audit --no-fund
	touch $@

plate/web/vendor/editor.js: plate/web/editor.js node_modules/.plate-dependencies
	npm run build

test:
	$(APP_PYTHON) -m unittest discover -s tests -v

PYTHON ?= python3
APP_PYTHON ?= $(PYTHON)
BUNDLE ?=

.PHONY: run dev test
run dev:
	$(APP_PYTHON) -m plate $(if $(BUNDLE),"$(BUNDLE)")

test:
	$(APP_PYTHON) -m unittest discover -s tests -v

.PHONY: install test

install:
	python -m pip install -e ".[test]"

test:
	python -m pytest

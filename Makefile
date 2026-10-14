.PHONY: install test
install:
	python3 -m pip install -e .
test:
	python3 -m unittest discover -s tests -v

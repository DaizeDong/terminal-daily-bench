# Makefile to simplify some common development tasks.
# Run 'make help' for a list of commands.

PYTHON=`which python`

default: help

help:
	@echo "Available commands:"
	@sed -n '/^[a-zA-Z0-9_.]*:/s/:.*//p' <Makefile | sort

test:
	pixi run test-all

lint:
	pixi run lint

coverage:
	pixi run -e py311 coverage
	pixi run -e py311 coverage-combine
	pixi run -e py311 coverage-report

coverage-xml:
	pixi run -e py311 coverage
	pixi run -e py311 coverage-combine
	pixi run -e py311 coverage-xml

clean:
	$(PYTHON) setup.py clean
	find . -name '*.pyc' -delete
	find . -name '*~' -delete

release:
	@rm -rf dist/
	python -m build
	hatch publish
	@echo "Reminder: Add release on github https://github.com/andialbrecht/sqlparse/releases"

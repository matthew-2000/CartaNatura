PYTHON ?= python3
MANAGE := $(PYTHON) manage.py

.PHONY: install migrate run test check collectstatic

install:
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install -r requirements.txt

migrate:
	$(MANAGE) migrate

run:
	$(MANAGE) runserver 127.0.0.1:8000

test:
	$(MANAGE) test cartaNatura

check:
	$(MANAGE) check

collectstatic:
	$(MANAGE) collectstatic --noinput

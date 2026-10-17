UV ?= uv

.PHONY: dev test lint typecheck build integration e2e release-offline db-prepare db-images db-up db-migrate db-test db-status db-stop
dev:
	$(UV) run --project backend --locked python scripts/stage1_local.py serve --approved-schema system-monitor

test:
	$(UV) run --project backend --locked python -m unittest discover -s tests/package -v
	$(UV) run --project backend --locked pytest backend/tests/unit -q
	$(UV) run --project backend --locked python scripts/frontend.py test

lint:
	$(UV) run --project backend --locked ruff check --config backend/pyproject.toml backend/src backend/tests backend/migrations scripts
	$(UV) run --project backend --locked ruff format --check --config backend/pyproject.toml backend/src backend/tests backend/migrations scripts
	$(UV) run --project backend --locked python scripts/frontend.py lint

typecheck:
	cd backend && $(UV) run --locked mypy src
	$(UV) run --project backend --locked python scripts/frontend.py typecheck

build:
	$(UV) run --project backend --locked python scripts/build_stage1.py

integration:
	$(UV) run --project backend --locked python scripts/local_mariadb.py new-test --run

e2e:
	$(UV) run --project backend --locked python scripts/frontend.py e2e

release-offline:
	$(UV) run --project backend --locked python scripts/release_offline.py

db-prepare:
	$(UV) run --project backend --locked python scripts/local_mariadb.py prepare

db-images:
	$(UV) run --project backend --locked python scripts/prepare_local_images.py --connected

db-up:
	$(UV) run --project backend --locked python scripts/local_mariadb.py up

db-migrate:
	$(UV) run --project backend --locked python scripts/local_mariadb.py migrate

db-test:
	$(UV) run --project backend --locked python scripts/local_mariadb.py new-test --run

db-status:
	$(UV) run --project backend --locked python scripts/local_mariadb.py status

db-stop:
	$(UV) run --project backend --locked python scripts/local_mariadb.py stop

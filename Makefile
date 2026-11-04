.PHONY: help dev down db psql db-ui query migrate load validate measure universe api web narrate demo build test clean

help:
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | sed 's/:.*## /\t/' | expand -t22

dev: db migrate load   ## Bring up the stack, migrate, load the universe
	@echo "db ready on :5432 — now run 'make web'"

db:                    ## Start Postgres + Redis
	cd infra && docker compose up -d
	@printf 'waiting for postgres'; \
	until docker compose -f infra/docker-compose.yml exec -T db pg_isready -U atlas -d atlas >/dev/null 2>&1; \
	do printf '.'; sleep 1; done; echo ' up'

psql:                  ## Open a SQL shell (no local psql needed)
	docker compose -f infra/docker-compose.yml exec db psql -U atlas -d atlas

db-ui:                 ## Open the database in a browser
	@docker compose -f infra/docker-compose.yml up -d dbui
	@printf 'waiting for pgweb'; \
	until curl -s -o /dev/null http://localhost:8081; do printf '.'; sleep 1; done; echo ' up'
	@echo "   http://localhost:8081"
	@open http://localhost:8081 2>/dev/null || true

query:                 ## Run one query: make query Q="select count(*) from entity"
	@docker compose -f infra/docker-compose.yml exec -T db psql -U atlas -d atlas -c "$(Q)"

down:                  ## Stop the stack
	cd infra && docker compose down

migrate:               ## Apply migrations
	docker compose -f infra/docker-compose.yml exec -T db \
	  psql -v ON_ERROR_STOP=1 -U atlas -d atlas -f /migrations/0001_initial_schema.sql
	@echo "schema applied"

load:                  ## Load data/ CSVs into Postgres
	python3 -I scripts/load_csv.py

validate:              ## Validate every collection CSV
	@python3 -I scripts/validate_collection.py data/companies/*.csv data/aliases/*.csv

measure:               ## Re-measure corpus cost against real filings
	python3 -I scripts/measure_corpus.py

universe:              ## Rebuild the US universe from SEC
	python3 -I scripts/build_us_universe.py

api:                   ## Run the read API on :8000
	cd apps/api && python3 -m uvicorn main:app --reload --port 8000

narrate:               ## Generate the voice-over (macOS 'say'; ATLAS_VOICE to change)
	python3 -I scripts/narrate.py

demo: narrate          ## Record the full explainer video (needs web + api running)
	python3 -I scripts/record_demo.py

web:                   ## Run the frontend
	cd apps/web && npm run dev

build:                 ## Production build of the frontend
	cd apps/web && npm run build

test:                  ## Run all tests
	cd apps/web && npm run typecheck
	python3 -I -m pytest -q tests 2>/dev/null || echo "(no python tests yet)"

clean:
	rm -rf apps/web/dist apps/web/node_modules

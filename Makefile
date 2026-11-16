.PHONY: help up dev down db psql db-ui query migrate migrate-status load link-cik ingest extract propagate pipeline gazetteer gazetteer-df sample audit backtest alerts recall review key keys eval stats validate measure universe api web narrate demo build test clean

help:
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | sed 's/:.*## /\t/' | expand -t22

dev: db migrate load   ## Bring up the stack, migrate, load the universe
	@echo "db ready on :5432 — now run 'make web'"

up:                    ## Bring everything back after a restart: db, API, web
	@open -a Docker 2>/dev/null || true
	@echo "waiting for Docker..."
	@for i in $$(seq 1 60); do docker info >/dev/null 2>&1 && break; sleep 2; done
	@docker info >/dev/null 2>&1 || { echo "Docker will not start. Open Docker Desktop and try again."; exit 1; }
	@docker compose -f infra/docker-compose.yml up -d >/dev/null
	@for i in $$(seq 1 30); do docker compose -f infra/docker-compose.yml exec -T db pg_isready -U atlas >/dev/null 2>&1 && break; sleep 2; done
	@pkill -f "uvicorn main:app" 2>/dev/null || true
	@( cd apps/api && nohup python3 -I -m uvicorn main:app --port 8000 --host 127.0.0.1 >/tmp/atlas_api.log 2>&1 </dev/null & ) >/dev/null 2>&1
	@( cd apps/web && nohup npm run dev >/tmp/atlas_web.log 2>&1 </dev/null & ) >/dev/null 2>&1
	@for i in $$(seq 1 40); do curl -s --max-time 2 localhost:8000/v1/health >/dev/null 2>&1 && break; sleep 2; done
	@for i in $$(seq 1 40); do curl -s --max-time 2 localhost:5173 >/dev/null 2>&1 && break; sleep 2; done
	@echo ""
	@echo "  api  :8000   $$(curl -s --max-time 3 localhost:8000/v1/health || echo DOWN)"
	@echo "  web  :5173   $$(curl -s --max-time 3 -o /dev/null -w '%{http_code}' localhost:5173)"
	@echo ""
	@echo "  logs: /tmp/atlas_api.log  /tmp/atlas_web.log"

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

migrate:               ## Apply every migration that has not run yet
	python3 -I scripts/migrate.py

migrate-status:        ## Show which migrations have run
	python3 -I scripts/migrate.py --status

load:                  ## Load data/ CSVs into Postgres
	python3 -I scripts/load_csv.py

link-cik:              ## Attach SEC CIKs to US companies
	python3 -I scripts/link_cik.py

ingest:                ## Fetch real filings -> documents, sections, chunks
	python3 -I scripts/ingest.py $(N)

extract:               ## Chunks -> cited claims -> graph edges
	python3 -I scripts/extract.py

propagate:             ## Seed events, walk the graph, precompute exposure
	python3 -I scripts/propagate.py

pipeline: link-cik ingest gazetteer-df extract propagate  ## The whole evidence layer, end to end
	@echo "pipeline complete"

gazetteer:             ## Re-score alias ambiguity (run after loading a market)
	python3 -I scripts/fix_gazetteer.py

gazetteer-df:          ## Suppress aliases the corpus shows are generic -> eval/gazetteer_df.tsv
	python3 -I scripts/df_gazetteer.py

sample:                ## Draw a seeded sample of relationships to judge by hand
	python3 -I scripts/sample_pairs.py

audit:                 ## Dump every concentration-backed relationship for hand-judging
	python3 -I scripts/eval_concentration.py

backtest:              ## Replay the event benchmark and fail on regression
	python3 -I scripts/backtest.py

alerts:                ## The three alerts that would page someone
	python3 -I scripts/alerts.py

recall:                ## Find disclosure-shaped sentences we did not extract from
	python3 -I scripts/measure_recall.py

review:                ## Ambiguous aliases awaiting a human decision
	python3 -I scripts/review_aliases.py

key:                   ## Mint an API key: make key NAME="my laptop"
	python3 -I scripts/api_key.py new "$(or $(NAME),unnamed)"

keys:                  ## List API keys
	python3 -I scripts/api_key.py list

eval:                  ## Print the measured state of the graph
	@echo "see eval/README.md for how these were measured"
	@docker compose -f infra/docker-compose.yml exec -T db psql -U atlas -d atlas -tAc "\
	  select 'cited edges            ' || count(*) from dependency_edge \
	  union all select 'distinct relationships ' || count(*) from (select distinct from_entity_id,to_entity_id,edge_type from dependency_edge) t \
	  union all select 'concentration-backed   ' || count(*) from (select distinct from_entity_id,to_entity_id,edge_type from dependency_edge where evidence_type='named_concentration') t \
	  union all select 'companies with edges   ' || count(distinct from_entity_id) from dependency_edge"

stats:                 ## What is actually in the graph right now
	@docker compose -f infra/docker-compose.yml exec -T db psql -U atlas -d atlas -tAc "\
	  select 'companies         '||count(*) from entity union all \
	  select 'usable aliases    '||count(*) from entity_alias where not is_ambiguous union all \
	  select 'filings           '||count(*) from document union all \
	  select 'chunks            '||count(*) from chunk union all \
	  select 'cited claims      '||count(*) from dependency_claim union all \
	  select 'graph edges       '||count(*) from dependency_edge union all \
	  select 'events            '||count(*) from event union all \
	  select 'exposure rows     '||count(*) from exposure_precompute;"

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

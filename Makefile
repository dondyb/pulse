.PHONY: up down logs test typecheck cron reset-demo

up:            ## Build and start everything
	docker compose up --build

down:          ## Stop everything (data is kept)
	docker compose down

logs:          ## Follow api, worker and cron logs
	docker compose logs -f api worker cron

test:          ## Backend tests (uses a separate <db>_test database)
	docker compose run --rm --no-deps api python -m pytest -q tests

typecheck:     ## Frontend type check
	docker compose run --rm --no-deps frontend npm run typecheck

cron:          ## Run the dispatcher once, now
	docker compose run --rm cron python -m app.tasks.dispatch_due

reset-demo:    ## DESTRUCTIVE: delete all data and reseed (asks for confirmation)
	./scripts/reset-demo.sh

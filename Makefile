# Makefile — common hackathon commands
.PHONY: up down logs seed train

up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f --tail=200

seed:
	docker compose exec tender-service python -m app.scripts.seed_fixtures

train:
	python ml/training/train_catboost.py --fixtures data/fixtures/tenders.json

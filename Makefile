.PHONY: up down build logs restart

up:
	docker compose up -d

build:
	docker compose build

down:
	docker compose down

logs:
	docker compose logs -f

restart:
	docker compose down
	docker compose up -d

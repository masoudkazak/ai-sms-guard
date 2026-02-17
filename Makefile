run:
	docker compose -f docker-compose.dev.yml up --build -d
up:
	docker compose -f docker-compose.dev.yml up -d
down:
	docker compose -f docker-compose.dev.yml down
down-v:
	docker compose -f docker-compose.dev.yml down -v
postgres:
	docker exec -it postgres_dev psql -U smartrabbit -d smartrabbit
logs:
	docker compose -f docker-compose.dev.yml logs -f

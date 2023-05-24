FROM docker/compose:debian-1.29

COPY docker-compose.yml /app/docker-compose.yml

WORKDIR /app

ENTRYPOINT ["docker", "compose", "up"]

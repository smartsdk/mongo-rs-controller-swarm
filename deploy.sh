#!/bin/sh
docker network create  --opt encrypted -d overlay backend
docker stack deploy -c docker-compose.yml mongo

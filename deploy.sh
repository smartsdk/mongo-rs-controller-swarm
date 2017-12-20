#!/bin/sh
set -o allexport
. ./mongo-rs.env
docker network create  --opt encrypted -d overlay ${BACKEND_NETWORK_NAME}
docker stack deploy -c docker-compose.yml ${STACK_NAME}

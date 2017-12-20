#!/bin/sh
set -o allexport
. ./mongo-rs.env
docker stack remove ${STACK_NAME}
docker network rm ${BACKEND_NETWORK_NAME}

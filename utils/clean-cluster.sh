#!/bin/bash
WORKER=${2:-2}
docker-machine rm swarm-manager

for i in $(seq 1 $WORKER); do
  docker-machine rm swarm-$i
done

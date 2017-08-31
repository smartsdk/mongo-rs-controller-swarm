#!/bin/bash
WORKER=${2:-2}
docker-machine start swarm-manager

for i in $(seq 1 $WORKER); do
  docker-machine start swarm-$i
done

docker-machine ls

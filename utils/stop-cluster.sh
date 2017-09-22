#!/bin/bash
WORKER=${2:-2}
docker-machine stop swarm-manager

for i in $(seq 1 $WORKER); do
  docker-machine stop swarm-$i
done

docker-machine ls

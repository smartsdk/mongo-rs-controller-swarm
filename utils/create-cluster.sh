#!/bin/bash
WORKER=${2:-2}

#=========================
# Creating cluster members
#=========================
echo "### Creating $MANAGER managers"
docker-machine create --driver virtualbox --virtualbox-memory 2048 swarm-manager

echo "### Creating $WORKER workers"
for i in $(seq 1 $WORKER); do
  docker-machine create --driver virtualbox --virtualbox-memory 2048 swarm-$i
done

#===============
# Starting swarm
#===============
MANAGER_IP=$(docker-machine ip swarm-manager)
echo "### Initializing main master: swarm-manager"
docker-machine ssh swarm-manager docker swarm init \
  --advertise-addr $MANAGER_IP

#===============
# Adding members
#===============
MANAGER_TOKEN=$(docker-machine ssh swarm-manager docker swarm join-token --quiet manager)
WORKER_TOKEN=$(docker-machine ssh swarm-manager docker swarm join-token --quiet worker)

for i in $(seq 1 $WORKER); do
  echo "### Joining worker: swarm-manager"
  docker-machine ssh swarm-$i docker swarm join \
  --token $WORKER_TOKEN \
  $MANAGER_IP:2377
done

docker-machine ssh swarm-manager docker node ls

echo "### Join your client to the cluster using:"
echo "  eval \$(docker-machine env swarm-manager)"
echo "### or run using:"
echo "  docker-machine ssh swarm-manager docker node ls"

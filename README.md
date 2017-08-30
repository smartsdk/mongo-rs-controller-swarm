# MongoDB replica-set controller for Swarm Cluster

This repository provide a dockerized controller for a Mongo db replica-set deployed using a Docker Swarm

## How to use
First, you need to have a Docker Swarm (docker >= 17.06.0-ce) already setup.
Then, simply run...

    sh deploy.sh

Allow some time while images are pulled in the nodes and services are deployed. After a couple of minutes, you can check if all services are up, as usual, running...

    $ docker service ls
    ID                  NAME                     MODE                REPLICAS            IMAGE                            PORTS
    813gplgsyi6z        mongo_mongo              global              3/3                 mongo:3.2                        *:27017->27017/tcp
    g5rxax0gucbn        mongo_mongo-controller   replicated          1/1                 martel/mongo-replica-ctrl:test   

The mongo service need to be deployed in "global" mode if you want to use storage persistence (this is to avoid that more than one instance is deployed on the same node).

The controller that maintain the status of the replica-set should be deployed in 1 single instance over a Swarm manager.

## Features
- [x] The script is able to connect to a pre-existing replica-set
- [x] The docker compose recipe include a simple healthcheck script for MongoDB
- [x] The script is able to detect a new primary node
- [x] The script is able to force the election of a new primary node, when the replica-set is inconsistent
- [x] The script is able to build a replica-set from scratch
- [x] The script is able to add and remove nodes dynamically according to the evolution of the swarm cluster
- [x] Given the about restart on failure is recommended as policy, this ensure that the scripts restart when it exit -1 and when the node where it is running is removed / drained (you need more than one master node!)
- [X] The repository includes a basic set of Travis CI tests that tests the script behavior against basic conditions in a single swarm node and without data persistence (initialization, scale up, scale down)

## To do
- [ ] Support authentication
- [ ] Add utilities to launch a Swarm Cluster to allow 1 click test
- [ ] Add Travis CI tests to tests mongo primary and secondary container failure 

## Contributions
Contributions are welcome in the form of pull request.

# MongoDB replica-set controller for Docker Swarm cluster

This repository provides a dockerized controller for a Mongo DB replica-set deployed on a Docker Swarm cluster.

## How to use
First, you need to have a Docker Swarm (docker >= 17.06.0-ce) already setup.
Secondly you need to create an overlay network called `backend` (when creating the network and setting up the Swarm cluster, *be careful with MTU issues!* Locally you won't have any, but using cloud providers, you may hit several ones):

* `docker network create  --opt encrypted -d overlay backend`

(to change the default MTU add `--opt com.docker.network.driver.mtu=MTU_VALUE`)

Then, simply run

* `docker stack deploy -c docker-compose.yml STACK_NAME`

Alternatively, you can use the simple [script](deploy.sh) we created that covers both steps:

* `sh deploy.sh`

Allow some time while images are pulled in the nodes and services are deployed. After a couple of minutes, you can check if all services are up, as usual, running:

```
$ docker service ls
ID                  NAME                MODE                REPLICAS            IMAGE                              PORTS
hmld6tiwr5o0        mongo_mongo         global              0/3                 mongo:3.2                          *:27017->27017/tcp
uppaix6drfps        mongo_controller    replicated          1/1                 martel/mongo-replica-ctrl:latest   
```  

You can also check the operations performed by the *controller* reading the logs:

```
$ docker service logs -f mongo_controller
mongo_controller.1.7x6ujhg5naw7@swarm-1    | INFO:__main__:Waiting mongo service (and tasks) (mongo_mongo) to start
mongo_controller.1.7x6ujhg5naw7@swarm-1    | ERROR:__main__:Expired attempts waiting for mongo service (mongo_mongo)
mongo_controller.1.sv8eztwisitz@swarm-manager    | INFO:__main__:Waiting mongo service (and tasks) (mongo_mongo) to start
mongo_controller.1.sv8eztwisitz@swarm-manager    | INFO:__main__:Mongo service is up and running
mongo_controller.1.sv8eztwisitz@swarm-manager    | INFO:__main__:To remove: {'10.0.0.3', '10.0.0.4'}
mongo_controller.1.sv8eztwisitz@swarm-manager    | INFO:__main__:To add: {'10.0.0.7', '10.0.0.6'}
mongo_controller.1.sv8eztwisitz@swarm-manager    | INFO:__main__:new replSetReconfig: {'ok': 1.0}
mongo_controller.1.sv8eztwisitz@swarm-manager    | INFO:__main__:Primary is: 10.0.0.6
```  

To remove the service:

* `docker stack undeploy STACK_NAME`
* `docker network rm backend`

You can configure the following environment variables for deploying your stack using the provided [`docker-compose.yml`](docker-compose.yml) file (the variables are used in the controller service, so they are important, without configuring them, the service won't work correctly):

* `MONGO_VERSION`, the default value is `3.2`
* `REPLICASET_NAME`, the default value is `rs`
* `MONGO_PORT`, the default value is `27017`
* `OVERLAY_NETWORK_NAME`, the default value is `backend`
* `STACK_NAME`, the default value is `mongo`
* `MONGO_SERVICE_NAME`, the default value is `${STACK_NAME:}_mongo`


Few hints, to customize the [`docker-compose.yml`](docker-compose.yml) orchestration according to your needs:

* To use data persistence (which we recommend in production settings), the *mongo* service needs to be deployed in **global mode** (see [`docker-compose.yml` line 5](docker-compose.yml#L5)). This is to avoid that more than one instance is deployed on the same node and that different instances concurrently access the same MongoDB data space on the filesystem.

* The *controller* that maintains the status of the replica-set must be deployed in a single instance over a Swarm manager node (see [`docker-compose.yml` line 32](docker-compose.yml#L32)). **Multiple instances of the Controller, may perform conflicting actions!** Also, to ensure that the controller is restarted in case of error, there is a restart policy in the the [`docker-compose.yml`](docker-compose.yml#L53).

* For HA purposes in a production environment your Swarm cluster should have more than one manager. This allows the *controller* to be start on different nodes in case of issues.

* The `docker-compose.yml` makes use of an external network since it is meant to be used in combination with other services that access the Mongo replica-set. To open the access to the Mongo cluster outside the Swarm overly network, you can uncomment the `Ports` section in the [`docker-compose.yml`](docker-compose.yml#L8) file.

* The Mongo [health check script](mongo-healthcheck) serves the only purpose of verifying the status of the MongoDB service. No check on cluster status is made. The cluster status is checked and managed by the *controller* service.

* We used *secrets* to pass the MongoDB health check script to the MongoDB containers (see [`docker-compose.yml` line 15](docker-compose.yml#L15)). While this is not the original purpose of *secrets*, this allows to reuse directly the official Mongo images without changes.

* If you are not sure if the *controller* is behaving correctly. Enable the `DEBUG` environment variable and check the logs of the container  (uncomment [`docker-compose.yml` line 42](docker-compose.yml#L42)).

* **N.B.** Don't use a service name starting with *mongo* for other services in the same stack. This may result in the controller to think that mongo is running while it is not. This is related to the way filters works in Docker (I consider it a bug). Of course, it can be fixed (see To Dos).

## Features
- [x] The script is able to connect to a pre-existing replica-set
- [x] The docker compose recipe include a simple healthcheck script for MongoDB
- [x] The script is able to detect a new primary node
- [x] The script is able to force the election of a new primary node, when the replica-set is inconsistent
- [x] The script is able to build a replica-set from scratch
- [x] The script is able to add and remove nodes dynamically according to the evolution of the swarm cluster
- [x] Given the about restart on failure is recommended as policy, this ensure that the scripts restart when it exit -1 and when the node where it is running is removed / drained (you need more than one master node!)
- [x] The repository includes a basic set of Travis CI tests that tests the script behavior against basic conditions in a single swarm node and without data persistence (initialization, scale up, scale down)
- [x] The recipe include [Nosqlclient](https://www.nosqlclient.com) as mongodb management tool.

## To do
- [ ] Support authentication to MongoDB
- [ ] Add utilities to launch a Swarm Cluster and allow 1 click test
- [ ] Add Travis CI tests to tests mongo primary and secondary container failure
- [ ] Improve `get_mongo_service` function to avoid conflict with other services which name start with `mongo`

## Contributions
Contributions are welcome in the form of pull request.

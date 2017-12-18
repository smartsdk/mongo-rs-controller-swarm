#!/bin/sh

oneTimeSetUp(){
  miniswarm delete
  miniswarm start 3
  eval $(docker-machine env ms-manager0)
  docker network create  --attachable --opt encrypted -d overlay backend
  docker stack deploy -c docker-compose.yml mongo
  docker run --name client --network=backend -d mongo:3.2 tail -f /dev/null
  echo "Created MongoDB Client"
}

# Start a new MongoDB cluster with persistence data and checks that the controller configure it correctly.

testSetUpMongoIsRunning(){
  sleep 120
  result=$(docker service ls -f name=mongo_mongo --format "{{.Name}}:{{.Mode}}")
  assertEquals "mongo_mongo:global" "${result}"
}

testSetUpControllerIsRunning(){
  result=$(docker service ls -f name=mongo_controller --format "{{.Name}}:{{.Mode}}")
  assertEquals "mongo_controller:replicated" "${result}"
}

testSetUpMongoReplicas(){
  result=$(docker service ls -f name=mongo_mongo --format "{{.Name}}:{{.Replicas}}")
  assertEquals "mongo_mongo:3/3" "${result}"
}

testSetUpControllerReplicas(){
  result=$(docker service ls -f name=mongo_controller --format "{{.Name}}:{{.Replicas}}")
  assertEquals "mongo_controller:1/1" "${result}"
}

testSetUpMongoClusterStatus(){
  result=$(docker exec client mongo --quiet mongo_mongo/admin --eval "db.runCommand( { replSetGetStatus : 1 } )['ok']")
  assertEquals "1" "${result}"
}

testSetUpMongoClusterSize(){
  result=$(docker exec client mongo --quiet mongo_mongo/admin --eval "db.runCommand( { replSetGetStatus : 1 } )['members'].length")
  assertEquals "3" "${result}"
}

# Kill container

testKillMongo(){
  container=$(docker ps -f name=mongo_mongo --format {{.ID}})
  docker kill ${container}
  sleep 10 #time needed to kill container
  result=$(docker service ls -f name=mongo_mongo --format "{{.Name}}:{{.Replicas}}")
  assertEquals "mongo_mongo:2/3" "${result}"
}

testKillMongoReplicas(){
  sleep 60 #time needed to download mongo image and start it
  result=$(docker service ls -f name=mongo_mongo --format "{{.Name}}:{{.Replicas}}")
  assertEquals "mongo_mongo:3/3" "${result}"
}

testSetUpMongoClusterStatus(){
  result=$(docker exec client mongo --quiet mongo_mongo/admin --eval "db.runCommand( { replSetGetStatus : 1 } )['ok']")
  assertEquals "1" "${result}"
}

testKillMongoClusterSize(){
  result=$(docker exec client mongo --quiet mongo_mongo/admin --eval "db.runCommand( { replSetGetStatus : 1 } )['members'].length")
  assertEquals "3" "${result}"
}

# Stop Swarm-2 node

testStopSwarm(){
  docker node update ms-worker0 --availability drain
  docker node update ms-worker0 --availability pause
  sleep 10 #time needed to kill container
  result=$(docker service ls -f name=mongo_mongo --format "{{.Name}}:{{.Replicas}}")
  assertEquals "mongo_mongo:2/2" "${result}"
}

testStopSwarmReplicas(){
  sleep 60 #time needed to download mongo image and start it
  result=$(docker service ls -f name=mongo_mongo --format "{{.Name}}:{{.Replicas}}")
  assertEquals "mongo_mongo:2/2" "${result}"
}

testStopSwarmClusterStatus(){
  result=$(docker exec client mongo --quiet mongo_mongo/admin --eval "db.runCommand( { replSetGetStatus : 1 } )['ok']")
  assertEquals "1" "${result}"
}

testStopSwarmClusterSize(){
  result=$(docker exec client mongo --quiet mongo_mongo/admin --eval "db.runCommand( { replSetGetStatus : 1 } )['members'].length")
  assertEquals "2" "${result}"
}

# Re-Start Swarm-2 node
testStartSwarm(){
  docker node update ms-worker0 --availability active
  sleep 120 #time needed to kill container
  result=$(docker service ls -f name=mongo_mongo --format "{{.Name}}:{{.Replicas}}")
  assertEquals "mongo_mongo:3/3" "${result}"
}

testStartSwarmReplicas(){
  sleep 10 #time needed to download mongo image and start it
  result=$(docker service ls -f name=mongo_mongo --format "{{.Name}}:{{.Replicas}}")
  assertEquals "mongo_mongo:3/3" "${result}"
}

testStartSwarmClusterStatus(){
  result=$(docker exec client mongo --quiet mongo_mongo/admin --eval "db.runCommand( { replSetGetStatus : 1 } )['ok']")
  assertEquals "1" "${result}"
}

testStartSwarmClusterSize(){
  result=$(docker exec client mongo --quiet mongo_mongo/admin --eval "db.runCommand( { replSetGetStatus : 1 } )['members'].length")
  assertEquals "3" "${result}"
}

# Stop Swarm-Manager node

testStopSwarmManager(){
  docker node promote ms-worker0
  docker rm -fv client
  eval $(docker-machine env ms-worker0)
  docker run --name client --network=backend -d mongo:3.2 tail -f /dev/null
  docker node update ms-manager0 --availability drain
  docker node update ms-manager0 --availability pause
  sleep 120 #time needed to kill container
  result=$(docker service ls -f name=mongo_mongo --format "{{.Name}}:{{.Replicas}}")
  assertEquals "mongo_mongo:2/2" "${result}"
}

testStopSwarmManagerControllerMoved(){
  result=$(docker service ls -f name=mongo_controller --format "{{.Name}}:{{.Replicas}}")
  assertEquals "mongo_controller:1/1" "${result}"
}

testStopSwarmManagerReplicas(){
  result=$(docker service ls -f name=mongo_mongo --format "{{.Name}}:{{.Replicas}}")
  assertEquals "mongo_mongo:2/2" "${result}"
}

testStopSwarmManagerClusterStatus(){
  result=$(docker exec client mongo --quiet mongo_mongo/admin --eval "db.runCommand( { replSetGetStatus : 1 } )['ok']")
  assertEquals "1" "${result}"
}

testStopSwarmManagerClusterSize(){
  result=$(docker exec client mongo --quiet mongo_mongo/admin --eval "db.runCommand( { replSetGetStatus : 1 } )['members'].length")
  assertEquals "2" "${result}"
}

testStopSwarmManagerRestore(){
  docker node update ms-manager0 --availability active
  docker rm -fv client
  eval $(docker-machine env ms-manager0)
  docker run --name client --network=backend -d mongo:3.2 tail -f /dev/null
  docker node demote ms-worker0
  sleep 120 #time needed to kill container
  result=$(docker service ls -f name=mongo_mongo --format "{{.Name}}:{{.Replicas}}")
  assertEquals "mongo_mongo:3/3" "${result}"
}

# Restart MongoDB cluster

testRestartMongoIsRunning(){
  docker stack rm mongo
  docker stack deploy -c docker-compose.yml mongo
  sleep 120 #time needed to restart
  result=$(docker service ls -f name=mongo_mongo --format "{{.Name}}:{{.Mode}}")
  assertEquals "mongo_mongo:global" "${result}"
}

testRestartControllerIsRunning(){
  result=$(docker service ls -f name=mongo_controller --format "{{.Name}}:{{.Mode}}")
  assertEquals "mongo_controller:replicated" "${result}"
}

testRestartMongoReplicas(){
  result=$(docker service ls -f name=mongo_mongo --format "{{.Name}}:{{.Replicas}}")
  assertEquals "mongo_mongo:3/3" "${result}"
}

testRestartControllerReplicas(){
  result=$(docker service ls -f name=mongo_controller --format "{{.Name}}:{{.Replicas}}")
  assertEquals "mongo_controller:1/1" "${result}"
}

testRestartMongoClusterStatus(){
  result=$(docker exec client mongo --quiet mongo_mongo/admin --eval "db.runCommand( { replSetGetStatus : 1 } )['ok']")
  assertEquals "1" "${result}"
}

testRestartMongoClusterSize(){
  result=$(docker exec client mongo --quiet mongo_mongo/admin --eval "db.runCommand( { replSetGetStatus : 1 } )['members'].length")
  assertEquals "3" "${result}"
}

oneTimeTearDown(){
  docker rm -fv client
  docker stack remove mongo
  sleep 50
  docker network rm backend
  miniswarm delete
}

# load shunit2
. shunit2

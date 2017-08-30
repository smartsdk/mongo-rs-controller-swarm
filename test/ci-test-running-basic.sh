#!/bin/sh

# Tests if the script is deployed correctly

testMongoIsRunning(){
   sleep 1
   result=$(docker service ls -f name=mongo_mongo --format "{{.Name}}:{{.Mode}}")
   assertEquals "mongo_mongo:replicated" "${result}"
}

testControllerIsRunning(){
   sleep 1
   result=$(docker service ls -f name=mongo_controller --format "{{.Name}}:{{.Mode}}")
   assertEquals "mongo_controller:replicated" "${result}"
}

testMongoReplicas(){
   sleep 10
   result=$(docker service ls -f name=mongo_mongo --format "{{.Name}}:{{.Replicas}}")
   assertEquals "mongo_mongo:3/3" "${result}"
}

testControllerReplicas(){
   sleep 1
   result=$(docker service ls -f name=mongo_controller --format "{{.Name}}:{{.Replicas}}")
   assertEquals "mongo_controller:1/1" "${result}"
}

testMongoClusterStatus(){
   sleep 10
   result=$(mongo --quiet localhost/admin --eval "db.runCommand( { replSetGetStatus : 1 } )['ok']")
   assertEquals "1" "${result}"
}

testMongoClusterSize(){
   sleep 10
   result=$(mongo --quiet localhost/admin --eval "db.runCommand( { replSetGetStatus : 1 } )['members'].length")
   assertEquals "3" "${result}"
}

# load shunit2
. shunit2

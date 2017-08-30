#!/bin/sh

testScaleUpMongo(){
   docker service scale mongo_mongo=4
   sleep 60
   result=$(docker service ls -f name=mongo_mongo --format "{{.Name}}:{{.Replicas}}")
   assertEquals "mongo_mongo:4/4" "${result}"
}

testMongoClusterStatusAfterScaleUp(){
   sleep 10
   result=$(mongo --quiet localhost/admin --eval "db.runCommand( { replSetGetStatus : 1 } )['ok']")
   assertEquals "1" "${result}"
}

testMongoClusterSizeAfterScaleUp(){
   sleep 10
   result=$(mongo --quiet localhost/admin --eval "db.runCommand( { replSetGetStatus : 1 } )['members'].length")
   assertEquals "4" "${result}"
}

testScaleDownMongo(){
   docker service scale mongo_mongo=3
   sleep 60
   result=$(docker service ls -f name=mongo_mongo --format "{{.Name}}:{{.Replicas}}")
   assertEquals "mongo_mongo:3/3" "${result}"
}


testMongoClusterStatusAfterScaleDown(){
   sleep 10
   result=$(mongo --quiet localhost/admin --eval "db.runCommand( { replSetGetStatus : 1 } )['ok']")
   assertEquals "1" "${result}"
}

testMongoClusterSizeAfterScaleDown(){
   sleep 10
   result=$(mongo --quiet localhost/admin --eval "db.runCommand( { replSetGetStatus : 1 } )['members'].length")
   assertEquals "3" "${result}"
}

# load shunit2
. shunit2

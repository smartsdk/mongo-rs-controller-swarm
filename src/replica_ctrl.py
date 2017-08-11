"""
This script is used to setup and mantain a MongoDB replicase on a Docker Swarm.

It is intended to be used with the docker-compose.yml in the mongodb replica recipe.

IMPORTANT: There should not be more than one process running this script in the swarm.

HOW IT WORKS (Overview):
- Scans mongod instances in the swarm
- Checks if a replicaset is already condigured
- If configured:
    - Load the replicaset configuration
    - If the old replicaset lost the primary node, force a reconfiguration
- If not configured:
    - Picks an arbitrary instance to act as a replicaset primary
    - Configures the replicaset on it
- Keeps on listening to changes in the original set of mongod instances
- Reconfigures replicaset if a change was perceived.

# TODO: Add tests
"""
import docker
import logging
import os
import pymongo as pm
import time
import sys


def get_required_env_variables():
    REQUIRED_VARS = [
        'OVERLAY_NETWORK_NAME',
        'MONGO_SERVICE_NAME',
        'REPLICASET_NAME',
        'MONGO_PORT'
    ]
    envs = {}
    for rv in REQUIRED_VARS:
        envs[rv.lower()] = os.environ[rv]

    if not all(envs.values()):
        raise RuntimeError("Missing required ENV variables. {}".format(envs))

    envs['mongo_port'] = int(envs['mongo_port'])
    return envs


def get_mongo_service(dc, mongo_service_name):
    filter = {}
    filter['name']=mongo_service_name
    for s in dc.services.list(filters=filter):
        if s.name == mongo_service_name:
            return s
    msg = "Error: Could not find mongo service with name {}. \
           Did you correctly deploy the stack with both services?.\
          ".format(mongo_service_name)
    logger = logging.getLogger(__name__)
    logger.error(msg)
    sys.exit(1)
    return


def is_service_up(mongo_service):
    logger = logging.getLogger(__name__)
    if len(get_running_tasks(mongo_service)) > 0:
        return True
    return False


def get_tasks_ips(tasks, overlay_network_name):
    tasks_ips = []
    for t in tasks:
        for n in t['NetworksAttachments']:
            if n['Network']['Spec']['Name'] == overlay_network_name:
                ip = n['Addresses'][0].split('/')[0]  # clean prefix from ip
                tasks_ips.append(ip)
    return tasks_ips


def get_primary(tasks_ips, replicaset_name, mongo_port):
    logger = logging.getLogger(__name__)
    logger.info("searching primary")
    for t in tasks_ips:
        mc = pm.MongoClient(t, mongo_port)
        try:
            if mc.is_primary:
                mc.close()
                return t
        except:
            mc.close()
            logger.info("{} is not primary".format(t))
        mc.close()
    return None

def get_secondaries(tasks_ips, replicaset_name, mongo_port):
    logger = logging.getLogger(__name__)
    logger.info("searching secondaries")
    for t in tasks_ips:
        mc = pm.MongoClient(t, mongo_port)
        try:
            #it seams that mc.secondaries is not working
            if mc.secondaries is not None and mc.secondaries != set():
                logger.info("secondaries: {}".format(mc.secondaries))
                mc.close()
                return mc.secondaries
        except:
            mc.close()
        mc.close()
    return None


def get_current_members(mongo_tasks_ips, replicaset_name, mongo_port):
    current_ips = set()
    logger = logging.getLogger(__name__)
    for t in mongo_tasks_ips:
        mc = pm.MongoClient(t, mongo_port)
        try:
            config = mc.admin.command("replSetGetConfig")['config']
            for m in config['members']:
                current_ips.add(m['host'].split(":")[0])
            mc.close()
        except:
            mc.close()
    logger.info("Current members in mongo configuration: {}".format(current_ips))
    return current_ips


def create_cluster(mongo_tasks_ips, replicaset_name, mongo_port):
    logger = logging.getLogger(__name__)
    config = create_mongo_config(mongo_tasks_ips, replicaset_name, mongo_port)
    logger.info("Initial config: {}".format(config))
    # Choose a primary and configure replicaset
    primary_ip = list(mongo_tasks_ips)[0]
    primary = pm.MongoClient(primary_ip, mongo_port)
    res = None
    try:
        res = primary.admin.command("replSetInitiate", config)
    except:
        res = primary.admin.command("replSetReconfig", config, force=True)
    primary.close()
    logger.info("replSetInitiate: {}".format(res))

def create_mongo_config(tasks_ips, replicaset_name, mongo_port):
    members = []
    for i, ip in enumerate(tasks_ips):
        members.append({
          '_id': i,
          'host': "{}:{}".format(ip, mongo_port)
        })
    config = {
        '_id': replicaset_name,
        'members': members,
        'version': 1
    }
    return config


def update_config(primary_ip, current_ips, new_ips, replicaset_name, mongo_port):
    logger = logging.getLogger(__name__)
    if not new_ips.difference(current_ips) and not current_ips.difference(new_ips):
        return
    else:
        # Actually not too different from what mongo does:
        # https://github.com/mongodb/mongo/blob/master/src/mongo/shell/utils.js
        to_remove = set(current_ips) - set(new_ips)
        to_add = set(new_ips) - set(current_ips)
        assert to_remove or to_add

        logger.info("To remove {}".format(to_remove))
        logger.info("To add {}".format(to_add))

        force = False
        if (primary_ip in to_remove) or primary_ip is None:
            logger.info("Primary {} not available".format(primary_ip))
            force = True
            #let's see if a new primary was elected
            primary_ip = get_primary(list(new_ips), replicaset_name, mongo_port)
            #if not let's find the first mongo that is member of the old cluster
            if primary_ip is None:
                primary_ip = list(set(new_ips)-set(to_add))[0]

        cli = pm.MongoClient(primary_ip, mongo_port)
        config = cli.admin.command("replSetGetConfig")['config']
        logger.info("Old Members: {}".format(config['members']))

        if to_remove:
            # Note: As of writing, when a node goes down with a task running
            # a global service, Swarm is not tearing down that task and hence
            # this removal part has not been fully tested.
            logger.info("To remove: {}".format(to_remove))
            new_members = [m for m in config['members'] if m['host'].split(":")[0] not in to_remove]
            config['members'] = new_members

        logger.info("Members after remove: {}".format(config['members']))

        if to_add:
            logger.info("To add: {}".format(to_add))
            offset = max([m['_id'] for m in config['members']]) + 1
            for i, ip in enumerate(to_add):
                config['members'].append({
                  '_id': offset + i,
                  'host': "{}:{}".format(ip, mongo_port)
                })

        config['version'] += 1
        logger.info("New config: {}".format(config))

        # Apply new config
        res = cli.admin.command("replSetReconfig", config, force=force)
        cli.close()
        logger.info("replSetReconfig: {}".format(res))


def get_running_tasks(mongo_service):
    tasks = []
    filter = {}
    filter['desired-state']="running"
    for t in mongo_service.tasks(filters=filter):
        if t['Status']['State'] == "running":
            tasks.append(t)
    return tasks

def manage_replica(mongo_service, overlay_network_name, replicaset_name, mongo_port):
    logger = logging.getLogger(__name__)

    service_down = True
    attempts = 0

    logger.info('Waiting mongo services to start')
    while(service_down and attempts<10):
        service_down = not is_service_up(mongo_service)
        attempts = attempts + 1
        time.sleep(10)

    if service_down:
        msg = "Error: Mongo no mongo service task is running."
        sys.exit(1)
        return

    logger.info("Mongo service is running after {} attempts".format(attempts))

    # Get mongo tasks ips
    mongo_tasks_ips = get_tasks_ips(get_running_tasks(mongo_service), overlay_network_name)

    logger.info("Mongo tasks ips: {}".format(mongo_tasks_ips))

    primary_ip = get_primary(mongo_tasks_ips, replicaset_name, mongo_port)

    logger.info("Primary IP is {}".format(primary_ip))

    current_ips = get_current_members(mongo_tasks_ips, replicaset_name, mongo_port)

    if primary_ip is None and current_ips == set():
        current_ips = set(mongo_tasks_ips)
        create_cluster(current_ips, replicaset_name, mongo_port)
    else:
        new_ips = set(mongo_tasks_ips)
        update_config(primary_ip, current_ips, new_ips, replicaset_name, mongo_port)

    # Respond to changes
    while True:
        time.sleep(10)
        current_ips = get_current_members(get_tasks_ips(get_running_tasks(mongo_service), overlay_network_name), replicaset_name, mongo_port)
        new_ips = set(get_tasks_ips(get_running_tasks(mongo_service), overlay_network_name))
        update_config(primary_ip, current_ips, new_ips, replicaset_name, mongo_port)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)

    envs = get_required_env_variables()
    dc = docker.from_env()

    mongo_service = get_mongo_service(dc, envs.pop('mongo_service_name'))
    if mongo_service:
       manage_replica(mongo_service, **envs)

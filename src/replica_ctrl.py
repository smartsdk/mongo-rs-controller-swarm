"""
This script is used to setup and maintain a MongoDB replicaset on a Docker Swarm.

IMPORTANT: It is intended to be used with the docker-compose.yml in the mongodb replica recipe.
This basically means 2 things:
 1 - There should not be more than one process running this script in the swarm.
 2 - There should be maximum one replica per swarm node. This is achieved using "global" deployment mode.

HOW IT WORKS (Overview):
- Scans running mongod instances in the swarm
- Checks if a replicaset is already configured
- If configured:
    - Loads the replicaset configuration
    - If the old replicaset lost the primary node, waits for a new election. In lack of a new primary,
    it forces a reconfiguration.
- If not configured:
    - Picks an arbitrary instance to act as a replicaset primary
    - Configures the replicaset on it
- Keeps on listening to changes in the original set of mongod instances IPs
- Reconfigures replicaset if a change was perceived.

INPUT: Via environment variables. See get_required_env_variables.

# TODO: Add tests
"""
from pymongo.errors import PyMongoError, OperationFailure, ServerSelectionTimeoutError
import docker
import logging
import os
import pymongo as pm
import sys
import time


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
    mongo_services = [s for s in dc.services.list() if s.name == mongo_service_name]
    assert len(mongo_services) <= 1, "Unexpected: multiple docker services with the same name '{}': {}".format(mongo_service_name, mongo_services)

    if mongo_services:
        return mongo_services[0]

    msg = "Error: Could not find mongo service with name {}. \
           Did you correctly deploy the stack with both services?.\
          ".format(mongo_service_name)
    logger = logging.getLogger(__name__)
    logger.error(msg)


def is_service_up(mongo_service):
    return mongo_service and len(get_running_tasks(mongo_service)) > 0


def get_running_tasks(mongo_service):
    tasks = []
    for t in mongo_service.tasks(filters={'desired-state': "running"}):
        if t['Status']['State'] == "running":
            tasks.append(t)
    return tasks


def get_tasks_ips(tasks, overlay_network_name):
    tasks_ips = []
    for t in tasks:
        for n in t['NetworksAttachments']:
            if n['Network']['Spec']['Name'] == overlay_network_name:
                ip = n['Addresses'][0].split('/')[0]  # clean prefix from ip
                tasks_ips.append(ip)
    return tasks_ips


def init_replica(mongo_tasks_ips, replicaset_name, mongo_port):
    """
    Init a MongoDB replicaset from the scratch.

    :param mongo_tasks_ips:
    :param replicaset_name:
    :param mongo_port:
    :return:
    """
    config = create_mongo_config(mongo_tasks_ips, replicaset_name, mongo_port)
    logger = logging.getLogger(__name__)
    logger.debug("Initial config: {}".format(config))

    # Choose a primary and configure replicaset
    primary_ip = list(mongo_tasks_ips)[0]
    primary = pm.MongoClient(primary_ip, mongo_port)
    try:
        res = primary.admin.command("replSetInitiate", config)
    except OperationFailure as e:
        logger.debug("replSetInitiate already configured, forcing configuration ({})".format(e))
        res = primary.admin.command("replSetReconfig", config, force=True)
    finally:
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


def gather_configured_members_ips(mongo_tasks_ips, mongo_port):
    current_ips = set()
    logger = logging.getLogger(__name__)
    for t in mongo_tasks_ips:
        mc = pm.MongoClient(t, mongo_port)
        try:
            config = mc.admin.command("replSetGetConfig")['config']
            for m in config['members']:
                current_ips.add(m['host'].split(":")[0])
            # Let's accept the first configuration found. Read as room for improvement!
            break
        except ServerSelectionTimeoutError as ssete:
            logger.debug("cannot connect to {} to get configuration, failed ({})".format(t,ssete))
        except OperationFailure as of:
            logger.debug("no configuration found in node {} ({})".format(t,of))
        finally:
            mc.close()
    logger.debug("Current members in mongo configurations: {}".format(current_ips))
    return current_ips

def get_primary_ip(tasks_ips, mongo_port):
    logger = logging.getLogger(__name__)

    primary_ips = []
    for t in tasks_ips:
        mc = pm.MongoClient(t, mongo_port)
        try:
            if mc.is_primary:
                primary_ips.append(t)
        except ServerSelectionTimeoutError as ssete:
            logger.debug("cannot connect to {} check if primary, failed ({})".format(t,ssete))
        except OperationFailure as of:
            logger.debug("no configuration found in node {} ({})".format(t,of))
        finally:
            mc.close()

    if len(primary_ips) > 1:
        logger.warning("Multiple primaries were found ({}). Let's use the first.".format(primary_ips))

    if primary_ips:
        logger.info("Primary is: {}".format(primary_ips[0]))
        return primary_ips[0]


def update_config(primary_ip, current_ips, new_ips, mongo_port):
    # Actually not too different from what mongo does:
    # https://github.com/mongodb/mongo/blob/master/src/mongo/shell/utils.js
    to_remove = set(current_ips) - set(new_ips)
    to_add = set(new_ips) - set(current_ips)
    assert to_remove or to_add

    logger = logging.getLogger(__name__)
    force = False
    if primary_ip in to_remove or primary_ip is None:
        logger.debug("Primary ({}) no longer available".format(primary_ip))
        force = True

        # Let's see if a new primary was elected
        attempts = 3
        primary_ip = None
        while attempts and not primary_ip:
            time.sleep(10)
            primary_ip = get_primary_ip(list(new_ips), mongo_port)
            attempts -= 1
            logger.debug("No new primary yet automatically elected...".format(primary_ip))

        if primary_ip is None:
            # If not, let's find the first mongo that is member of the old cluster
            old_members = list(new_ips - to_add)
            primary_ip = old_members[0] if old_members else list(new_ips)[0]
            logger.debug("Choosing {} as the new primary".format(primary_ip))

    cli = pm.MongoClient(primary_ip, mongo_port)
    try:
        config = cli.admin.command("replSetGetConfig")['config']
        logger.debug("Old Members: {}".format(config['members']))

        if to_remove:
            # Note: As of writing, when a node goes down with a task running
            # a global service, Swarm is not tearing down that task and hence
            # this removal part has not been fully tested.
            logger.info("To remove: {}".format(to_remove))
            new_members = [m for m in config['members'] if m['host'].split(":")[0] not in to_remove]
            config['members'] = new_members

        if to_add:
            logger.info("To add: {}".format(to_add))

            if config['members']:
                offset = max([m['_id'] for m in config['members']]) + 1
            else:
                offset = 0

            for i, ip in enumerate(to_add):
                config['members'].append({
                    '_id': offset + i,
                    'host': "{}:{}".format(ip, mongo_port)
                })

        config['version'] += 1
        logger.debug("New config: {}".format(config))

        # Apply new config
        res = cli.admin.command("replSetReconfig", config, force=force)
        logger.info("new replSetReconfig: {}".format(res))
    finally:
        cli.close()


def manage_replica(mongo_service, overlay_network_name, replicaset_name, mongo_port):
    """
    To manage the replica is to:
    - Configure replicaset
        If there was no replica before, create one from scratch.
        If there was a replica (e.g, this script was restarted), that replicaset could be either fine or broken.
            If the replicaset was healthy, move on to the "watching" phase.
            Else, force a reconfiguration.
    - Watch for changes in tasks ips
        When IP changes are detected, the replica will break, so we must fix it on the fly.

    :param mongo_service:
    :param overlay_network_name:
    :param replicaset_name:
    :param mongo_port:
    :return:
    """
    logger = logging.getLogger(__name__)

    # Get mongo tasks ips
    mongo_tasks = get_running_tasks(mongo_service)
    mongo_tasks_ips = get_tasks_ips(mongo_tasks, overlay_network_name)
    logger.debug("Mongo tasks ips: {}".format(mongo_tasks_ips))

    current_member_ips = gather_configured_members_ips(mongo_tasks_ips, mongo_port)
    logger.debug("Current mongo ips: {}".format(current_member_ips))
    primary_ip = get_primary_ip(current_member_ips, mongo_port)
    logger.debug("Current primary ip: {}".format(primary_ip))

    if len(current_member_ips) == 0:
        # Starting from the scratch
        logger.info("No previous valid configuration, starting replicaset from scratch")
        current_member_ips = set(mongo_tasks_ips)
        init_replica(current_member_ips, replicaset_name, mongo_port)

    # Watch for IP changes. If IPs remain stable we assume MongoDB maintains the replicaset working fine.
    # TODO: Test what happens with an IP swap of members of a working replicaset.
    while True:
        time.sleep(10)
        new_member_ips = set(get_tasks_ips(get_running_tasks(mongo_service), overlay_network_name))
        if current_member_ips.symmetric_difference(new_member_ips):
            update_config(primary_ip, current_member_ips, new_member_ips, mongo_port)
        current_member_ips = new_member_ips
        primary_ip = get_primary_ip(new_member_ips, mongo_port)


if __name__ == '__main__':
    # INPUT: Via environment variables
    dc = docker.from_env()
    envs = get_required_env_variables()
    mongo_service_name = envs.pop('mongo_service_name')

    # Simple logging
    if 'DEBUG' is os.environ:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)
    logger.info('Waiting mongo service (and tasks) ({}) to start'.format(mongo_service_name))

    # Make sure Mongo is up and running
    attempts = 10
    mongo_service = None
    service_down = True
    while attempts and service_down:
        time.sleep(5)
        mongo_service = get_mongo_service(dc, mongo_service_name)
        service_down = not is_service_up(mongo_service)
        attempts -= 1
    if attempts <= 0 or not mongo_service:
        logger.error('Expired attempts waiting for mongo service ({})'.format(mongo_service_name))
        sys.exit(1)

    logger.info("Mongo service is up and running")
    manage_replica(mongo_service, **envs)

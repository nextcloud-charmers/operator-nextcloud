#!/usr/bin/env python3
# Copyright 2020 Erik Lönroth
# See LICENSE file for licensing details.
import logging
import subprocess as sp
import sys
import os
import stat
import socket
from pathlib import Path
import json
import re
from ops.charm import CharmBase
from ops.main import main
from ops.framework import StoredState
from ops.model import (
    ActiveStatus,
    BlockedStatus,
    MaintenanceStatus,
    WaitingStatus
)
import utils
import emojis
from occ import Occ
from interface_http import HttpProvider
import interface_redis
import interface_mount
from charms.data_platform_libs.v0.data_interfaces import DatabaseCreatedEvent
from charms.data_platform_libs.v0.data_interfaces import DatabaseRequires


logger = logging.getLogger(__name__)

NEXTCLOUD_ROOT = os.path.abspath('/var/www/nextcloud')
NEXTCLOUD_CONFIG_PHP = os.path.abspath('/var/www/nextcloud/config/config.php')
NEXTCLOUD_CEPH_CONFIG_PHP = os.path.join(NEXTCLOUD_ROOT, 'config/ceph.config.php')


class NextcloudCharm(CharmBase):
    _stored = StoredState()

    def __init__(self, *args):
        super().__init__(*args)
        # Postgres
        self.database = DatabaseRequires(self, relation_name="database", database_name="nextcloud")
        # Haproxy

        self.haproxy = HttpProvider(self, 'website', socket.getfqdn(), 80)
        # Redis
        self.redis = interface_redis.RedisClient(self, "redis")

        self._stored.set_default(nextcloud_datadir='/var/www/nextcloud/data/',
                                 nextcloud_fetched=False,
                                 nextcloud_initialized=False,
                                 database_available=False,
                                 apache_configured=False,
                                 php_configured=False,
                                 ceph_configured=False,
                                 config_altered_on_disk=False,
                                 redis_info=dict())

        event_bindings = {
            self.on.install: self._on_install,
            self.on.config_changed: self._on_config_changed,
            self.on.start: self._on_start,
            self.on.leader_elected: self._on_leader_elected,
            self.database.on.database_created: self._on_database_created,
            self.database.on.endpoints_changed: self._on_database_created,
            self.redis.on.redis_available: self._on_redis_available,
            self.redis.on.redis_broken: self._on_redis_broken,
            self.on.update_status: self._on_update_status,
            self.on.cluster_relation_changed: self._on_cluster_relation_changed,
            self.on.cluster_relation_joined: self._on_cluster_relation_joined,
            self.on.cluster_relation_departed: self._on_cluster_relation_departed,
            self.on.cluster_relation_broken: self._on_cluster_relation_broken,
            self.on.ceph_relation_changed: self._on_ceph_relation_changed,
            self.on.datadir_storage_attached: self._on_datadir_storage_attached,
            self.on.datadir_storage_detaching: self._on_datadir_storage_detaching
        }

        # Relation: shared-fs (Interface: mount)
        self._sharedfs = interface_mount.NFSMountClient(self, "shared-fs")
        self.framework.observe(self._sharedfs.on.nfsmount_available,
                               self._on_nfsmount_available)

        for event, handler in event_bindings.items():
            self.framework.observe(event, handler)

        action_bindings = {
            self.on.add_missing_indices_action: self._on_add_missing_indices_action,
            self.on.convert_filecache_bigint_action: self._on_convert_filecache_bigint_action,
            self.on.maintenance_action: self._on_maintenance_action,
            self.on.set_trusted_domain_action: self._on_set_trusted_domain_action,
            self.on.get_admin_password_action: self._on_get_admin_password_action,
        }

        for action, handler in action_bindings.items():
            self.framework.observe(action, handler)

    def _on_install(self, event):
        logger.debug(emojis.EMOJI_CORE_HOOK_EVENT + sys._getframe().f_code.co_name)
        self.unit.status = MaintenanceStatus("installing dependencies...")
        utils.install_apt_update()
        utils.install_dependencies()
        utils.install_backup_dependencies()
        if not self._stored.nextcloud_fetched:
            # Fetch nextcloud to /var/www/
            try:
                self.unit.status = MaintenanceStatus("installing (from resource).")
                tarfile_path = self.model.resources.fetch('nextcloud-tarfile')
                utils.extract_nextcloud(tarfile_path)
            except Exception as e:
                logger.debug("Extracting resources failed - trying network." + str(e))
                self.unit.status = MaintenanceStatus("installing (from network).")
                utils.fetch_and_extract_nextcloud(self.config.get('nextcloud-tarfile'))
            utils.set_nextcloud_permissions(self)
            self.unit.status = MaintenanceStatus("installed")
            self._stored.nextcloud_fetched = True

    def updateClusterRelationData(self):
        """
        Trigger update of the cluster-relation data.
        """
        logger.debug("Updating cluster relation data config.php on disk.")
        cluster_rel = self.model.relations['cluster'][0]
        with open(NEXTCLOUD_CONFIG_PHP) as f:
            nextcloud_config = f.read()
            cluster_rel.data[self.app]['nextcloud_config'] = str(nextcloud_config)

    def _on_config_changed(self, event):
        """
        Any configuration change trigger a complete reconfigure of
        the php and apache and also a restart of apache.
        :param event:
        :return:
        """
        logger.debug(emojis.EMOJI_CORE_HOOK_EVENT + sys._getframe().f_code.co_name)
        self._config_apache()
        self._config_php()
        if self.model.unit.is_leader():
            self._config_overwriteprotocol()
            self._config_overwritecliurl()
            self._config_default_phone_region()
            self.updateClusterRelationData()
            # Untoggle this after we have ran updateClusterRelationData
            self._stored.config_altered_on_disk = False

        self._config_debug()
        sp.check_call(['systemctl', 'restart', 'apache2.service'])
        if self.config.get('backup-host') and self._stored.nextcloud_initialized and self._stored.database_available:
            self.unit.status = MaintenanceStatus("Configuring backup")
            utils.config_backup(self.config, self._stored.nextcloud_datadir, self._stored.dbhost,
                                self._stored.dbuser, self._stored.dbpass)
        self._on_update_status(event)

    # Only leader is running this hook (verify this)
    def _on_leader_elected(self, event):
        logger.debug(emojis.EMOJI_CORE_HOOK_EVENT + sys._getframe().f_code.co_name)
        logger.debug("!!!!!!!! I'm new nextcloud leader !!!!!!!!")
        self.update_config_php_trusted_domains()

    def update_config_php_trusted_domains(self):
        """
        Updates trusted domains on peer relation
        Updates nextcloud via occ-command with trusted domains
        Updates the nexcloud_config peer relation data.
        This should only be run on the unit leader.
        """
        if not os.path.exists(NEXTCLOUD_CONFIG_PHP):
            return

        cluster_rel = self.model.relations['cluster'][0]
        rel_unit_ip = [cluster_rel.data[u]['ingress-address'] for u in cluster_rel.units]
        this_unit_ip = cluster_rel.data[self.model.unit]['ingress-address']
        rel_unit_ip.append(this_unit_ip)
        Occ.update_trusted_domains_peer_ips(rel_unit_ip)
        self.updateClusterRelationData()

    def update_relation_ceph_config_php(self):
        if not os.path.exists(NEXTCLOUD_CEPH_CONFIG_PHP):
            return
        cluster_rel = self.model.relations['cluster'][0]
        with open(NEXTCLOUD_CEPH_CONFIG_PHP) as f:
            ceph_config = f.read()
            cluster_rel.data[self.app]['ceph_config'] = str(ceph_config)

    def _on_cluster_relation_joined(self, event):
        logger.debug(emojis.EMOJI_CLOUD + sys._getframe().f_code.co_name)
        if self.model.unit.is_leader():
            if not self._stored.nextcloud_initialized:
                event.defer()
                return
            self.framework.breakpoint('joined')
            self.update_config_php_trusted_domains()

    def _on_cluster_relation_changed(self, event):
        """
        When a change on the config happens:
        Peers (non-leaders) pull in config from (cluster) relation and writes to local disk.
        """
        logger.debug(emojis.EMOJI_CLOUD + sys._getframe().f_code.co_name)
        if not self.model.unit.is_leader():
            if 'nextcloud_config' not in event.relation.data[self.app]:
                event.defer()
                return

            nextcloud_config = event.relation.data[self.app]['nextcloud_config']
            with open(NEXTCLOUD_CONFIG_PHP, "w") as f:
                f.write(nextcloud_config)

            # TODO: only create .ocdata file for debug since it scale out
            # will only work with a shared-fs like NFS.
            self._make_ocdata_for_occ()

            if 'ceph_config' in event.relation.data[self.app]:
                ceph_config = event.relation.data[self.app]['ceph_config']
                with open(NEXTCLOUD_CEPH_CONFIG_PHP, "w") as f:
                    f.write(ceph_config)

            # Set correct permissions
            utils.set_nextcloud_permissions(self)

    def _on_cluster_relation_departed(self, event):
        logger.debug(emojis.EMOJI_CLOUD + sys._getframe().f_code.co_name)
        self.framework.breakpoint('departed')
        if self.model.unit.is_leader():
            self.update_config_php_trusted_domains()

    def _on_cluster_relation_broken(self, event):
        logger.debug(emojis.EMOJI_CLOUD + sys._getframe().f_code.co_name)
        pass

    def _on_database_created(self, event: DatabaseCreatedEvent) -> None:
        """
        Event is fired when postgres database is created.
        * Only leader gets to install or configure nextcloud.
        * Only leader get to run crontabs.
        Other peers will copy the configuration and therefore must trust that
        nextcloud is initialized and that we have a database.
        """
        # We have a database.
        self._stored.database_available = True

        # Leader gets to initialize and run crontabs
        if self.model.unit.is_leader() and not self._stored.nextcloud_initialized:
            utils.set_nextcloud_permissions(self)
            self._init_nextcloud()
            self._add_initial_trusted_domain()
            utils.setPrettyUrls()
            utils.installCrontab()
            Occ.setBackgroundCron()
            if self._is_nextcloud_installed():
                self._stored.nextcloud_initialized = True
                self._on_update_status(event)
            else:
                self._stored.nextcloud_initialized = False
                logger.error("FAILED initializing Nextcloud, check logs.")
                raise SystemExit(1)

    def _on_database_relation_removed(self, event) -> None:
        """Event is fired when relation with postgres is broken."""
        self._stored.database_available = False
        self.unit.status = WaitingStatus("Waiting for database relation")
        raise SystemExit(0)

    def _on_start(self, event):
        logger.debug(emojis.EMOJI_CORE_HOOK_EVENT + sys._getframe().f_code.co_name)
        if not self._is_nextcloud_installed():
            logger.debug("Nextcloud not installed, defering start.")
            event.defer()
            return
        try:
            sp.check_call(['systemctl', 'restart', 'apache2.service'])
            self._on_update_status(event)
            utils.open_port('80')
        except sp.CalledProcessError as e:
            print(e)
            sys.exit(-1)

    def _on_datadir_storage_attached(self, event):
        """
        If this event is fired, we are told to use a custom datadir.
        So, we set that here for this charm and remember that.
        """
        logger.debug(emojis.EMOJI_COMPUTER_DISK + sys._getframe().f_code.co_name)
        self._stored.nextcloud_datadir = str(event.storage.location)

    def _on_datadir_storage_detaching(self, event):
        logger.debug(emojis.EMOJI_COMPUTER_DISK + sys._getframe().f_code.co_name)
        pass

    def _on_add_missing_indices_action(self, event):
        logger.debug(emojis.EMOJI_ACTION_EVENT + sys._getframe().f_code.co_name)
        o = Occ.db_add_missing_indices()
        event.set_results({"occ-output": o})

    def _on_convert_filecache_bigint_action(self, event):
        """
        Action to convert-filecache-bigint on the database via occ
        This action places the site in maintenance mode to protect it
        while this action runs.
        """
        if self.model.unit.is_leader():
            logger.debug(emojis.EMOJI_ACTION_EVENT + sys._getframe().f_code.co_name)
            Occ.maintenance_mode(enable=True)
            o = Occ.db_convert_filecache_bigint()
            event.set_results({"occ-output": o})
            Occ.maintenance_mode(enable=False)
        else:
            event.set_results({"message": "Only leader unit can run this action. Nothing was done."})

    def _on_maintenance_action(self, event):
        """
        Action to take the site in or out of maintenance mode.
        :param event: boolean
        :return:
        """
        logger.debug(emojis.EMOJI_ACTION_EVENT + sys._getframe().f_code.co_name)
        o = Occ.maintenance_mode(enable=event.params['enable'])
        event.set_results({"occ-output": o})

    def _on_get_admin_password_action(self, event):
        """
        This action gets the content of the /root/.onetimelogin
        ... and then removes it.
        Effectively, it only works once.
        """
        logger.debug(emojis.EMOJI_ACTION_EVENT + sys._getframe().f_code.co_name)
        logger.warning("get-admin-password action invoked.")

        if os.path.exists('/root/.onetimelogin'):
            with open('/root/.onetimelogin', 'r') as f:
                p = f.read()
                event.set_results({"initial-admin-password": p})
                os.remove('/root/.onetimelogin')
        else:
            event.set_results({"initial-admin-password": "NOT AVAILABLE"})

    def _config_php(self):
        """
        Renders the phpmodule for nextcloud (nextcloud.ini)
        This is instead of manipulating the system wide php.ini
        which might be overwitten or changed from elsewhere.
        """
        self.unit.status = MaintenanceStatus("config php...")
        phpmod_context = {
            'max_file_uploads': self.config.get('php_max_file_uploads'),
            'upload_max_filesize': self.config.get('php_upload_max_filesize'),
            'post_max_size': self.config.get('php_post_max_size'),
            'memory_limit': self.config.get('php_memory_limit')
        }
        utils.config_php(phpmod_context, Path(self.charm_dir / 'templates'), 'nextcloud.ini.j2')
        self._stored.php_configured = True

    def _config_apache(self):
        """
        Configured apache
        """
        self.unit.status = MaintenanceStatus("config apache....")
        utils.config_apache2(Path(self.charm_dir / 'templates'), 'nextcloud.conf.j2')
        self._stored.apache_configured = True

    def _init_nextcloud(self):
        """
        Initializes nextcloud via the nextcloud occ interface.
        :return:
        """
        self.unit.status = MaintenanceStatus("initializing nextcloud...")

        # Generate a onetime password (retrieved by action)
        p = utils.generatePassword()
        with open('/root/.onetimelogin', 'w+') as f:
            f.write(p)
            os.chmod('/root/.onetimelogin', stat.S_IREAD)

        # Collect database information from relation.
        db_data = self.fetch_postgres_relation_data()

        ctx = {'dbtype': 'pgsql',
               'dbname': db_data.get("db_name", None),
               'dbhost': db_data.get("db_host", None),
               'dbport': db_data.get("db_port", None),
               'dbpass': db_data.get("db_password", None),
               'dbuser': db_data.get("db_username", None),
               'adminpassword': p,
               'adminusername': 'admin',
               'datadir': str(self._stored.nextcloud_datadir)
               }

        # Install Nextcloud
        cp = Occ.maintenance_install(ctx)
        if cp.returncode == 0:
            self.unit.status = MaintenanceStatus("initialized nextcloud...")
        else:
            self.unit.status = BlockedStatus("Initialization failed this is what I know: " + cp.stdout)
            logger.error("Error while initializing nextcloud.")
            sys.exit(-1)

    def _add_initial_trusted_domain(self):
        """
        Adds in 2 trusted domains:
        1. ingress address.
        2. fqdn config
        :return:
        """
        # Adds the fqdn to trusted domains (if set)
        if self.config['fqdn']:
            Occ.config_system_set_trusted_domains(self.config['fqdn'], 1)
        ingress_addr = self.model.get_binding('website').network.ingress_address
        # Adds the ingress_address to trusted domains
        Occ.config_system_set_trusted_domains(ingress_addr, 2)

    def _on_update_status(self, event):
        """
        Evaluate the internal state to report on status.
        """
        logger.debug(emojis.EMOJI_CORE_HOOK_EVENT + sys._getframe().f_code.co_name)
        # Log integrity of config.
        self._checkLogConfigDiff()

        if not self._stored.nextcloud_fetched:
            self.unit.status = BlockedStatus("Nextcloud not fetched.")

        elif not self._stored.nextcloud_initialized:
            self.unit.status = BlockedStatus("Nextcloud not initialized.")

        elif not self._stored.apache_configured:
            self.unit.status = BlockedStatus("Apache not configured.")

        elif not self._stored.php_configured:
            self.unit.status = BlockedStatus("PHP not configured.")

        elif not self._stored.database_available:
            self.unit.status = BlockedStatus("No database.")

        elif self._stored.config_altered_on_disk:
            # At this point, a configure event will unblock.
            # This should really be handled better somehow.
            # For now - it will be visual.
            self.unit.status = WaitingStatus("Warning: Local changes to config.php")
        else:
            try:
                v = self._nextcloud_version()
                if self.model.unit.is_leader():
                    # Only leader need to set app version
                    self.unit.set_workload_version(v)
                    # Set the active status to the running version.
                    self.unit.status = ActiveStatus(v + " " + emojis.EMOJI_CLOUD)
                else:
                    self.unit.status = ActiveStatus(v + " " + emojis.EMOJI_CLOUD)
            except Exception as e:
                logger.error("Failed query Nextcloud occ for status: ", e)
                sys.exit(-1)

    def _on_redis_available(self, event):
        """
        When redis is available, apache needs a restart.
        /var/www/nextcloud/config/redis.config.php - modified
        /etc/php/X.Y/mods-available/redis_session.ini - modified
        """
        sp.run(['systemctl', 'restart', 'apache2.service'])

    def _on_redis_broken(self, event):
        """
        When redis integration removed, apache needs a restart.
        /var/www/nextcloud/config/redis.config.php - removed
        /etc/php/X.Y/mods-available/redis_session.ini - removed
        """
        sp.run(['systemctl', 'restart', 'apache2.service'])

    def _on_set_trusted_domain_action(self, event):
        domain = event.params['domain']
        Occ.config_system_set_trusted_domains(domain, 1)
        self.update_config_php_trusted_domains()

    def _on_nfsmount_available(self, event):
        # systemd mount unit in place, so lets start it.
        cmd = "systemctl start media-nextcloud-data.mount"
        sp.run(cmd.split())

        # Put site in maintenance.
        # sudo -u www-data php /path/to/nextcloud/occ maintenance:mode --on
        Occ.maintenance_mode(enable=True)

        # Set ownership
        cmd = "chown www-data:www-data /media/nextcloud/data"
        sp.run(cmd.split())

        # Make sure the directory is a nextcloud datadir
        # touch $datadirectory/.ocdata (/media/nextcloud/data)
        cmd = "sudo -u www-data touch /media/nextcloud/data/.ocdata"
        sp.run(cmd.split())

        # Fix up permission on nfs mount
        cmd = "chmod 0770 /media/nextcloud/data/"
        sp.run(cmd.split())

        # Set new datadir
        cmd = "sudo -u www-data php occ config:system:set datadirectory --value=/media/nextcloud/data/"
        sp.run(cmd.split(), cwd="/var/www/nextcloud/")

        # Cleanup cache
        cmd = "sudo -u www-data php occ files:cleanup"
        sp.run(cmd.split(), cwd="/var/www/nextcloud/")

        # sudo -u www-data php /path/to/nextcloud/occ maintenance:mode --off
        Occ.maintenance_mode(enable=False)

    def _on_ceph_relation_changed(self, event):
        if not self.model.unit.is_leader():
            return
        ceph_user = event.relation.data[event.app].get('ceph_user')
        rados_gw_hostname = event.relation.data[event.app].get('rados_gw_hostname')
        rados_gw_port = event.relation.data[event.app].get('rados_gw_port')
        if ceph_user and rados_gw_hostname and rados_gw_port:
            self.framework.breakpoint('ceph-changed')
            ceph_user = json.loads(ceph_user)
            self.unit.status = MaintenanceStatus("Begin config ceph.")
            ceph_info = {
                'ceph_key': ceph_user['keys'][0]['access_key'],
                'ceph_secret': ceph_user['keys'][0]['secret_key'],
                'rados_gw_hostname': rados_gw_hostname,
                'rados_gw_port': rados_gw_port
            }
            utils.config_ceph(ceph_info, Path(self.charm_dir / 'templates'), 'ceph.config.php.j2')
            self._stored.ceph_configured = True
            self.unit.status = MaintenanceStatus("ceph config complete.")
            self.update_relation_ceph_config_php()

    def _config_overwriteprotocol(self):
        """
        Configures nextcloud overwriteprotocol to http or https.
        :return:
        """
        if self._stored.nextcloud_initialized:
            Occ.overwriteprotocol(self.config.get('overwriteprotocol'))

    def _config_debug(self):
        """
        Configures nextcloud system:debug from config value.
        :return:
        """
        if self._stored.nextcloud_initialized:
            Occ.setDebug(self.config.get('debug'))

    def _config_overwritecliurl(self):
        """
        Configures nextcloud overwrite-cli-url config value.
        :return:
        """
        if self._stored.nextcloud_initialized:
            Occ.overwriteCliUrl(self.config.get('overwrite-cli-url'))

    def _config_default_phone_region(self):
        """
        Configures nextcloud overwriteprotocol to http or https.
        :return:
        """
        if self._stored.nextcloud_initialized:
            Occ.defaultPhoneRegion(self.config.get('default-phone-region'))

    def _make_ocdata_for_occ(self):
        """
        This create a .ocdata file which nextcloud wants or will error
        on all occ commands.
        """
        if not self._stored.nextcloud_datadir.exists():
            self._stored.nextcloud_datadir.mkdir()
        if not self._stored.nextcloud_datadir.joinpath('.ocdata').exists():
            self._stored.nextcloud_datadir.joinpath('.ocdata').touch()

    def _is_nextcloud_installed(self):
        status = Occ.status()
        logger.debug(status)
        try:
            match = re.findall(r'\{.*?\}', status.stdout)
            return json.loads(match[0])['installed']
        except IndexError:
            return False
        except Exception as e:
            print("Failed determining installation status: ", e)
            sys.exit(-1)

    def _nextcloud_version(self):
        logger.debug("Determined nextcloud version: " + json.loads(Occ.status().stdout)['version'])
        return json.loads(Occ.status().stdout)['version']

    def _checkLogConfigDiff(self):
        """
        Compares nextcloud config.php with cluster/peer with application databag.
        Logs this information only.
        """
        cluster_rel = self.model.relations['cluster'][0]
        try:
            if 'nextcloud_config' in cluster_rel.data[self.app]:
                with open(NEXTCLOUD_CONFIG_PHP) as f:
                    nextcloud_config = f.read()
                    if cluster_rel.data[self.app]['nextcloud_config'] == str(nextcloud_config):
                        logger.info("No manual/local changes to nextcloud config.php detected.")
                    else:
                        # Toggle this information. Resolve it within config_changed.
                        self._stored.config_altered_on_disk = True
                        logger.warning("Manual/local changes to config.php detected, \
                                       will be overwritten by config updates!")
            else:
                logger.info("nextcloud_config key not found in cluster_rel.data.")
        except KeyError:
            logger.error("Error accessing cluster_rel.data dictionary.")

    def fetch_postgres_relation_data(self) -> dict:
        """
        Get relational data.
        """
        data = self.database.fetch_relation_data()
        logger.debug("Got following database data: %s", data)
        for key, val in data.items():
            if not val:
                continue
            logger.info("New PSQL database endpoint is %s", val["endpoints"])
            host, port = val["endpoints"].split(":")
            db_data = {
                "db_host": host,
                "db_port": port,
                "db_username": val["username"],
                "db_password": val["password"],
                "db_name": val["database"],
                "pgsql_version": val["version"]
            }
            return db_data
        self.unit.status = WaitingStatus("Waiting for database relation")
        raise SystemExit(0)


if __name__ == "__main__":
    main(NextcloudCharm)

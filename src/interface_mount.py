#!/usr/bin/env python3

import logging
from pathlib import Path
import subprocess as sp


from ops.framework import (
    EventBase,
    EventSource,
    Object,
    ObjectEvents,
)

import utils

logger = logging.getLogger()


class NFSMountAvailableEvent(EventBase):
    """NFSMountAvailableEvent"""


class MountEvents(ObjectEvents):
    """Mount events"""

    nfsmount_available = EventSource(NFSMountAvailableEvent)


class NFSMountClient(Object):
    """NFSMount Client Interface."""

    on = MountEvents()

    def __init__(self, charm, relation_name):
        """Observe relation_changed."""
        super().__init__(charm, relation_name)
        self._charm = charm
        self._relation_name = relation_name

        # relation-created
        self.framework.observe(
            self._charm.on[self._relation_name].relation_created,
            self._on_relation_created
        )

        # realation-changed
        self.framework.observe(
            self._charm.on[self._relation_name].relation_changed,
            self._on_relation_changed
        )

    def _on_relation_changed(self, event):
        """" Render the mount unit file, but dont start it as you
        might want to do things before the mount takes place. """
        event_unit_data = event.relation.data.get(event.unit)
        if not event_unit_data:
            event.defer()
            return
        ctx = event_unit_data.items()
        logger.info("Remote NFS data: " + str(ctx))
        utils.install_nfs_systemd_mount(Path(self._charm.charm_dir / 'templates'),
                                        'media-nextcloud-data.mount.j2', ctx)

        # Reload daemons
        cmd = "systemctl daemon-reload"
        sp.run(cmd.split())

        # Let the world know we're done.
        self.on.nfsmount_available.emit()

    def _on_relation_created(self, event):
        """ Install NFS deps """
        cmd = 'apt install -y rpcbind nfs-common'
        sp.run(cmd.split(), check=True)

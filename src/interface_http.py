#!/usr/bin/python3
"""HTTP interface (provides side)."""

from ops.framework import Object
import logging
import utils


class HttpProvider(Object):
    """
    Http interface provider interface.
    """

    def __init__(self, charm, relation_name, hostname="", port=80):
        """Set the initial data.
        """
        super().__init__(charm, relation_name)
        self.charm = charm
        self._relation_name = relation_name
        self._hostname = hostname  # FQDN of host passed on in relations
        self._port = port
        self._haproxy_service_name = "nextcloud"

        self.framework.observe(
            charm.on[relation_name].relation_joined, self._on_relation_joined
        )
        self.framework.observe(
            charm.on[relation_name].relation_changed, self._on_relation_changed
        )
        self.framework.observe(
            charm.on[relation_name].relation_departed, self._on_relation_departed
        )

    def _on_relation_joined(self, event):
        """

        A joining reverse-proxy is added to the list of _trusted_proxies
        """
        if self.charm.model.unit.is_leader():
            if not self.charm._is_nextcloud_installed():
                logging.debug("Defering relation_joined until nextcloud is installed.")
                event.defer()
                return
            else:
                raddr = event.relation.data[event.unit]['private-address']
                logging.debug(f"Adding a trusted_proxy: {raddr}")
                utils.addTrustedProxy(raddr)

    def _on_relation_changed(self, event):
        raddr = event.relation.data[event.unit]['private-address']
        logging.debug(f"Set relation data for remote unit: {raddr}")
        event.relation.data[self.model.unit]['hostname'] = self._hostname
        event.relation.data[self.model.unit]['port'] = str(self._port)
        event.relation.data[self.model.unit]['service_name'] = "nextcloud"

    def _on_relation_departed(self, event):
        """
        Re-adds only joined units to _trusted_proxies
        (Effectively removing departed units)
        """
        if self.charm.model.unit.is_leader():
            if not self.charm._is_nextcloud_installed():
                logging.debug("Defering relation_departed until nextcloud is installed.")
                event.defer()
                return
            else:
                # TODO: Figure out how to remove a single unit since it seems not avilable
                # in this hook (private-address is not available in the data bucket)
                utils.deleteTrustedProxies()
                logging.debug("Re-adding remaning units:" + str(event.relation.units))
                for u in event.relation.units:
                    raddr = event.relation.data[u]['private-address']
                    utils.addTrustedProxy(raddr)
                    # utils.deleteTrustedProxy(raddr)

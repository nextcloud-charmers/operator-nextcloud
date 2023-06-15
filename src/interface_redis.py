#!/usr/bin/env python3
import logging
from pathlib import Path
import subprocess as sp
import jinja2
import utils

from ops.framework import (
    EventBase,
    EventSource,
    Object,
    ObjectEvents,
)


logger = logging.getLogger()


class RedisAvailableEvent(EventBase):
    """RedisAvailableEvent."""


class RedisBrokenEvent(EventBase):
    """RedisBrokenEvent."""


class RedisEvents(ObjectEvents):
    """Redis events."""
    redis_available = EventSource(RedisAvailableEvent)
    redis_broken = EventSource(RedisBrokenEvent)


class RedisClient(Object):
    """Redis Client Interface."""

    on = RedisEvents()

    def __init__(self, charm, relation_name):
        """Observe relation_changed."""
        super().__init__(charm, relation_name)
        self._charm = charm
        self._relation_name = relation_name
        # Observe the relation-changed hook event and bind
        # self.on_relation_changed() to handle the event.
        self.framework.observe(
            self._charm.on[self._relation_name].relation_changed,
            self._on_relation_changed
        )
        self.framework.observe(
            self._charm.on[self._relation_name].relation_broken,
            self._on_relation_broken
        )

    def _on_relation_changed(self, event):
        event_unit_data = event.relation.data.get(event.unit)
        if not event_unit_data:
            event.defer()
            return
        password = event_unit_data.get('password')
        host = event_unit_data.get('hostname')
        port = event_unit_data.get('port')

        if (host and port):
            redis_info = {
                'redis_password': password,
                'redis_hostname': host,
                'redis_port': port,
            }

            # Configure redis
            self.config_redis(redis_info)
            self.config_redis_session(redis_info)

            # Announce that redis is configured.
            self.on.redis_available.emit()
        else:
            logger.warning("REDIS INFO NOT AVAILABLE WHEN IT SHOULD.")
            event.defer()
            return

    def _on_relation_broken(self, event):
        """
        Emit the broken event.
        """
        # Remove redis info by setting None.
        self.config_redis(None)
        self.config_redis_session(None)
        logger.info("Redis relation was removed, configs purged.")
        self.on.redis_broken.emit()

    def config_redis(self, redis_info, template='redis.config.php.j2') -> str:
        """
        Configure redis.
        Return the rendered config as text or emtpy string.
        """
        templates_path = Path(self._charm.charm_dir / 'templates')
        if redis_info is None:
            file_path = '/var/www/nextcloud/config/redis.config.php'
            target = Path(file_path)
            if target.exists():
                target.unlink()
            else:
                pass
            return ""
        else:
            template = jinja2.Environment(
                loader=jinja2.FileSystemLoader(templates_path)
            ).get_template(template)
            target = Path('/var/www/nextcloud/config/redis.config.php')
            rendered_content = template.render(redis_info)
            target.write_text(rendered_content)
        return rendered_content

    def config_redis_session(self, redis_info, template='redis_session.ini.j2'):
        """
        Puts redis session manager in place and enables the mod.
        Removes the file if redis_info = None.

        Returns the rendered config or empty string.
        """
        templates_path = Path(self._charm.charm_dir / 'templates')
        if redis_info is None:
            target_72 = Path('/etc/php/7.2/mods-available/redis_session.ini')
            target_74 = Path('/etc/php/7.4/mods-available/redis_session.ini')
            target_81 = Path('/etc/php/8.1/mods-available/redis_session.ini')
            if utils.get_phpversion() == "7.4":
                if target_74.exists():
                    target_74.unlink()
            elif utils.get_phpversion() == "7.2":
                if target_72.exists():
                    target_72.unlink()
            elif utils.get_phpversion() == "8.1":
                if target_81.exists():
                    target_81.unlink()
            return ""
        else:
            template_env = jinja2.Environment(
                loader=jinja2.FileSystemLoader(templates_path)
            )
            template = template_env.get_template(template)
            target_72 = Path('/etc/php/7.2/mods-available/redis_session.ini')
            target_74 = Path('/etc/php/7.4/mods-available/redis_session.ini')
            target_81 = Path('/etc/php/8.1/mods-available/redis_session.ini')
            rendered_content = template.render(redis_info)
            if utils.get_phpversion() == "7.4":
                target_74.write_text(rendered_content)
            elif utils.get_phpversion() == "7.2":
                target_72.write_text(rendered_content)
            elif utils.get_phpversion() == "8.1":
                target_81.write_text(rendered_content)
            sp.check_call(['phpenmod', 'redis_session'])
            return rendered_content

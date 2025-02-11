#!/bin/bash

# juju run --unit postgresql/0 'sudo -u postgres pg_dump -d nextcloud  > /tmp/nextcloud-database-backup-file.db'
juju run --unit postgresql/0 'sudo -u postgres pg_dump -Fc -d nextcloud  > /tmp/nextcloud-database-backup-file.db'
juju scp postgresql/0:/tmp/nextcloud-database-backup-file.db .

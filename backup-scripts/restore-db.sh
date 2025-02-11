#!/bin/bash

pg_restore --no-owner --clean --host=10.51.45.221 --username=operator --password -d testdb nextcloud-database-backup-file.db

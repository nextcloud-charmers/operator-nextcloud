#!/bin/bash
#
# Create ssh-keys for root first and move over public key to backup_host
#
set -x

echo "Running backup" | wall

/root/scripts/backup/Nextcloud-Backup-Restore/NextcloudBackup.sh > /root/backuplog.log 2>&1

rsync -v --remove-source-files -Aax -e "ssh -p {{ backup_port }}" /backups/* {{ backup_user }}@{{ backup_host }}: >> /root/backuplog.log 2>&1

if grep --quiet -i ERROR /root/backuplog.log;
then
    /root/scripts/backup/slack-notifier.py -m "Backup FAILED!" -w {{ slack_webhook }} || true
    /root/scripts/backup/pagerduty-notifier.py -t {{ pagerduty_token }} -e {{ pagerduty_email }} -s {{ pagerduty_serviceid }} -m 'Backup FAILED!' || true
else
    /root/scripts/backup/slack-notifier.py -m "Backup complete." -w {{ slack_webhook }} || true
fi

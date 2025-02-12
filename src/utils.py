import logging
import subprocess as sp
from subprocess import CompletedProcess
import sys
import os
import requests
import tarfile
from pathlib import Path
import jinja2
import json
import io
import string
from random import randint, choice
from occ import Occ
import charms.operator_libs_linux.v0.apt as apt
from charms.operator_libs_linux.v0.apt import PackageNotFoundError, PackageError

logger = logging.getLogger(__name__)

def _modify_port(start=None, end=None, protocol='tcp', hook_tool="open-port"):
    assert protocol in {'tcp', 'udp', 'icmp'}
    if protocol == 'icmp':
        start = None
        end = None

    if start and end:
        port = f"{start}-{end}/"
    elif start:
        port = f"{start}/"
    else:
        port = ""
    sp.run([hook_tool, f"{port}{protocol}"])


def enable_ping():
    _modify_port(None, None, protocol='icmp', hook_tool="open-port")


def disable_ping():
    _modify_port(None, None, protocol='icmp', hook_tool="close-port")


def open_port(start, end=None, protocol="tcp"):
    _modify_port(start, end, protocol=protocol, hook_tool="open-port")


def close_port(start, end=None, protocol="tcp"):
    _modify_port(start, end, protocol=protocol, hook_tool="close-port")


def set_nextcloud_permissions(charm):
    """
    Set ownershow to www-data for nextcloud locations.
    """
    _datadir = str(charm._stored.nextcloud_datadir)
    cmd = ['chown', '-R', 'www-data:www-data', '/var/www/nextcloud', _datadir]
    sp.run(cmd, cwd='/var/www/nextcloud')


def install_dependencies():
    """
    Installs package dependencies for the supported distros.
    :return:
    """
    distro_codename = sp.check_output(['lsb_release', '-sc'], universal_newlines=True).strip()
    if 'focal' == distro_codename:
        _install_dependencies_focal()
    elif 'bionic' == distro_codename:
        _install_dependencies_bionic()
    elif 'jammy' == distro_codename:
        _install_dependencies_jammy()
    elif 'noble' == distro_codename:
        _install_dependencies_noble()
    else:
        raise RuntimeError(f"No valid series found to install package dependencies for {distro_codename}")


def install_apt_update():
    command = ["sudo", "apt", "update", "-y"]
    sp.run(command, check=True)


def install_backup_dependencies():
    try:
        packages = ['pigz',
                    'postgresql-client',
                    'python3-pip']
        command = ["sudo", "apt", "install", "-y"]
        command.extend(packages)
        sp.run(command, check=True)
    except sp.CalledProcessError as e:
        print(e)
        sys.exit(-1)
    try:
        packages = ['pdpyras==4.4.0']
        command = ["sudo", "pip3", "install"]
        command.extend(packages)
        sp.run(command, check=True)
    except sp.CalledProcessError as e:
        print(e)
        sys.exit(-1)


def _install_dependencies_bionic():
    """
    Install packages that is needed by nextcloud to work with this charm.
    Inspired by: https://github.com/nextcloud/vm/blob/master/nextcloud_install_production.sh
    """
    try:
        packages = ['apache2',
                    'libapache2-mod-php7.2',
                    'php7.2-gd',
                    'php7.2-json',
                    'php7.2-mysql',
                    'php7.2-pgsql',
                    'php7.2-curl',
                    'php7.2-mbstring',
                    'php7.2-intl',
                    'php7.2-imagick',
                    'php7.2-zip',
                    'php7.2-xml',
                    'php-apcu',
                    'php-redis',
                    'php-smbclient']
        command = ["sudo", "apt", "install", "-y"]
        command.extend(packages)
        sp.run(command, check=True)
    except sp.CalledProcessError as e:
        print(e)
        sys.exit(-1)


def _install_dependencies_focal():
    """
    Install packages that is needed by nextcloud to work with this charm.
    Inspired by: https://github.com/nextcloud/vm/blob/master/nextcloud_install_production.sh
    :return:
    """
    try:
        packages = ['apache2',
                    'libapache2-mod-php7.4',
                    'php7.4-fpm',
                    'php7.4-intl',
                    'php7.4-ldap',
                    'php7.4-imap',
                    'php7.4-gd',
                    'php7.4-pgsql',
                    'php7.4-curl',
                    'php7.4-xml',
                    'php7.4-zip',
                    'php7.4-mbstring',
                    'php7.4-soap',
                    'php7.4-json',
                    'php7.4-gmp',
                    'php7.4-bz2',
                    'php7.4-bcmath',
                    'php7.4-imagick',
                    'php-pear',
                    'php-apcu',
                    'php-redis']
        command = ["sudo", "apt", "install", "-y"]
        command.extend(packages)
        sp.run(command, check=True)
    except sp.CalledProcessError as e:
        print(e)
        sys.exit(-1)


def _install_dependencies_jammy():
    """
    Install packages that is needed by nextcloud to work with this charm.
    Inspired by: https://github.com/nextcloud/vm/blob/main/nextcloud_install_production.sh
    :return:
    """
    packages = "apache2 php8.1 libapache2-mod-php8.1 php8.1-curl php8.1-xml \
                php8.1-pgsql php8.1-mbstring php8.1-gd php8.1-redis \
                php8.1-intl php8.1-gmp php8.1-bcmath php8.1-imagick \
                php8.1-zip php8.1-fpm php8.1-intl php8.1-ldap".split()

    try:
        sp.run('sudo apt remove php8.1-common -y'.split(), check=True)
        command = ["sudo", "DEBIAN_FRONTEND=noninteractive", "apt", "install", "-y"]
        command.extend(packages)
        sp.run(command, check=True)
    except sp.CalledProcessError as e:
        print(e)
        sys.exit(-1)

def _install_dependencies_noble():
    """
    Install packages that is needed by nextcloud to work with this charm.
    Inspired by: https://github.com/nextcloud/vm/blob/main/nextcloud_install_production.sh
    :return:
    """
    packages = [
        "php8.3-common", "php8.3-opcache", "php8.3-readline", "php8.3-cli", "php8.3-fpm",
        "libapache2-mod-php8.3", "php8.3-igbinary", "php8.3-imagick", "php8.3-redis", "php8.3",
        "php8.3-bcmath", "php8.3-curl", "php8.3-gd", "php8.3-gmp", "php8.3-intl", "php8.3-ldap",
        "php8.3-mbstring", "php8.3-pgsql", "php8.3-xml", "php8.3-zip"
    ]

    try:
        apt.update()
        apt.add_package(packages)
    except PackageNotFoundError:
        logger.error("a specified package not found in package cache or on system")
        sys.exit(1)
    except PackageError as e:
        logger.error("could not install package. Reason: %s", e.message)
        sys.exit(1)

def fetch_and_extract_nextcloud(tarfile_url):
    """
    Fetch and Install nextcloud from internet
    Sources are about 100M.
    """
    # tarfile_url = 'https://download.nextcloud.com/server/releases/nextcloud-18.0.3.tar.bz2'
    # checksum = '7b67e709006230f90f95727f9fa92e8c73a9e93458b22103293120f9cb50fd72'
    try:
        response = requests.get(tarfile_url, allow_redirects=True, stream=True)
        dst = Path('/var/www/')
        with tarfile.open(fileobj=io.BytesIO(response.content), mode='r:bz2') as tfile:
            tfile.extractall(path=dst)
    except sp.CalledProcessError as e:
        print(e)
        sys.exit(-1)


def extract_nextcloud(tarfile_path):
    """
    Install nextcloud from tarfile
    """
    dst = Path('/var/www/')
    with tarfile.open(tarfile_path, mode='r:bz2') as tfile:
        tfile.extractall(path=dst)


def config_apache2(templates_path, template):
    """
    Configures apache2
    """
    template = jinja2.Environment(
        loader=jinja2.FileSystemLoader(templates_path)
    ).get_template(template)
    target = Path('/etc/apache2/sites-available/nextcloud.conf')
    ctx = {}
    target.write_text(template.render(ctx))
    # Enable required modules.
    for module in ['rewrite', 'headers', 'env', 'dir', 'mime', 'setenvif', 'proxy_fcgi']:
        sp.call(['a2enmod', module])
    # Disable default site
    sp.check_call(['a2dissite', '000-default'])
    # Enable nextcloud site (wich will be default)
    sp.check_call(['a2ensite', 'nextcloud'])


def install_nfs_systemd_mount(templates_path, template, ctx):
    """
    Installs nfs systemd.mount unit file
    ctx = {'nfs_host': <iphostname>, 'appname': <appname>}
    """
    template = jinja2.Environment(
        loader=jinja2.FileSystemLoader(templates_path)
    ).get_template(template)
    target = Path('/etc/systemd/system/media-nextcloud-data.mount')
    target.write_text(template.render(ctx))
    sp.call(['systemctl', 'daemon-reload'])


def config_php(phpmod_context, templates_path, template):
    """
    Renders the phpmodule for nextcloud (nextcloud.ini)
    This is instead of manipulating the system wide php.ini
    which might be overwitten or changed from elsewhere.
    """
    template = jinja2.Environment(
        loader=jinja2.FileSystemLoader(templates_path)
    ).get_template(template)
    target_72 = Path('/etc/php/7.2/mods-available/nextcloud.ini')
    target_74 = Path('/etc/php/7.4/mods-available/nextcloud.ini')
    target_81 = Path('/etc/php/8.1/mods-available/nextcloud.ini')
    if get_phpversion() == "7.4":
        target_74.write_text(template.render(phpmod_context))
    elif get_phpversion() == "7.2":
        target_72.write_text(template.render(phpmod_context))
    elif get_phpversion() == "8.1":
        target_81.write_text(template.render(phpmod_context))
    sp.check_call(['phpenmod', 'nextcloud'])


def config_ceph(ceph_info, templates_path, template):
    """
    Renders the phpmodule for nextcloud (nextcloud.ini)
    This is instead of manipulating the system wide php.ini
    which might be overwitten or changed from elsewhere.
    """
    template = jinja2.Environment(
        loader=jinja2.FileSystemLoader(templates_path)
    ).get_template(template)
    target = Path('/var/www/nextcloud/config/ceph.config.php')
    target.write_text(template.render(ceph_info))


def get_phpversion():
    """
    Get php version X.Y from the running system.
    Supports
    - 7.2 (bionic),
    - 7.4 (focal)
    :return: string
    """
    response = sp.check_output(['php', '-v']).decode()
    lines = response.split("\n")
    if "PHP 7.4" in lines[0]:
        return "7.4"
    elif "PHP 7.2" in lines[0]:
        return "7.2"
    elif "PHP 8.1" in lines[0]:
        return "8.1"
    else:
        raise RuntimeError("No valid PHP version found in check")


def config_backup(config, data_dir_path, db_host, db_user, db_pass):
    """
    Installs backup scripts and cronjob for scheduled backups.
    """
    # Replace all backup scripts with new ones from the charm.
    sp.check_call("rm -rf /root/scripts/backup", shell=True)
    sp.check_call("mkdir -p /root/scripts/backup", shell=True)
    sp.check_call("cp -r scripts/backup/* /root/scripts/backup/", shell=True)
    sp.check_call("cp scripts/backup/backup-cron /etc/cron.d/", shell=True)

    # Configuring run_backup.sh script
    run_backup_info = {
        "backup_host": config.get("backup-host"),
        "backup_port": config.get("backup-port"),
        "backup_user": config.get("backup-user"),
        "slack_webhook": config.get("backup-slack-webhook"),
        "pagerduty_serviceid": config.get("backup-pagerduty-serviceid"),
        "pagerduty_token": config.get("backup-pagerduty-token"),
        "pagerduty_email": config.get("backup-pagerduty-email")
    }
    template = jinja2.Environment(
        loader=jinja2.FileSystemLoader("scripts/backup")
    ).get_template("run_backup.sh")
    target = Path('/root/scripts/backup/run_backup.sh')
    target.write_text(template.render(run_backup_info))

    # Configuring Nextcloud-Backup-Restore.conf
    backup_conf_info = {
        "data_dir": data_dir_path,
        "db_host": db_host,
        "db_user": db_user,
        "db_pass": db_pass
    }
    template = jinja2.Environment(
        loader=jinja2.FileSystemLoader("scripts/backup/Nextcloud-Backup-Restore")
    ).get_template("NextcloudBackupRestore.conf")
    target = Path('/root/scripts/backup/Nextcloud-Backup-Restore/NextcloudBackupRestore.conf')
    target.write_text(template.render(backup_conf_info))


def getTrustedProxies():
    """
    Returns a json object with the trusted_proxies
    """
    cmd = ("sudo -u www-data php /var/www/nextcloud/occ config:system:get trusted_proxies --output=json")
    s = sp.run(cmd.split(), cwd='/var/www/nextcloud',
               stdout=sp.PIPE, stderr=sp.PIPE, universal_newlines=True)
    # Load an empty dict into json if no trusted proxy exists.
    if s.stdout == '':
        return json.loads(str(dict()))
    return json.loads(s.stdout)


def addTrustedProxy(host):
    """
    Adds a trusted proxy to nextcloud config.php.
    """
    curmax = len(getTrustedProxies())
    setTrustedProxy(host, curmax + 1)


def deleteTrustedProxies() -> CompletedProcess:
    """
    Removes all trusted_proxies from config via occ by setting an empty value.
    """
    cmd = ("sudo -u www-data php /var/www/nextcloud/occ config:system:set"
           " trusted_proxies "
           " --value=")
    return sp.run(cmd.split(), cwd='/var/www/nextcloud',
                  stdout=sp.PIPE, stderr=sp.PIPE, universal_newlines=True)


def deleteTrustedProxy(host) -> CompletedProcess:
    """
    Removes a host from trusted_proxies.
    Returns:
    """
    ps = getTrustedProxies()
    for (idx, val) in ps.items():
        if val == host:
            cmd = ("sudo -u www-data php /var/www/nextcloud/occ config:system:set"
                   f" trusted_proxies {idx} --value=")
            return sp.run(cmd.split(), cwd='/var/www/nextcloud',
                          stdout=sp.PIPE, stderr=sp.PIPE, universal_newlines=True)


def setTrustedProxy(host, index) -> CompletedProcess:
    """
    Sets a trusted proxy on the given index.
    """
    cmd = ("sudo -u www-data php /var/www/nextcloud/occ config:system:set"
           " trusted_proxies {index}"
           " --value={host} ").format(index=index, host=host)
    return sp.run(cmd.split(), cwd='/var/www/nextcloud',
                  stdout=sp.PIPE, stderr=sp.PIPE, universal_newlines=True)


def installCrontab():
    """
    Injects the crontab for www-data
    """
    os.system("echo '*/5  *  *  *  * php -f /var/www/nextcloud/cron.php' | crontab -u www-data -")


def generatePassword():
    """
    Generate a random password.
    For use with setting admin credentials
    """
    characters = string.ascii_letters + string.punctuation + string.digits
    return "".join(choice(characters) for x in range(randint(8, 16)))


def setPrettyUrls():
    """
    Use URL rewrite, "Pretty URL". Removes index.php from url:
    https://nextcloud.dwellir.com/index.php/login -> https://nextcloud.dwellir.com/login
    """
    Occ.setRewriteBase()
    Occ.updateHtaccess()

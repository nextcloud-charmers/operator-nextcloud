import subprocess as sp
from subprocess import CompletedProcess
import logging
import sys

logger = logging.getLogger(__name__)


class Occ:

    @staticmethod
    def delete_trusted_proxies() -> CompletedProcess:
        """
        Removes all trusted_proxies from config via occ.
        """
        cmd = ("sudo -u www-data php /var/www/nextcloud/occ config:system:set"
               " trusted_proxies "
               " --value=''")
        return sp.run(cmd.split(), cwd='/var/www/nextcloud',
                      stdout=sp.PIPE, stderr=sp.PIPE, universal_newlines=True)

    @staticmethod
    def set_trusted_proxy(host, index) -> CompletedProcess:
        """
        Sets a trusted proxy on the given index.
        """
        #
        # TODO: Check that the input is really a IP or host.
        #
        cmd = ("sudo -u www-data php /var/www/nextcloud/occ config:system:set"
               " trusted_proxies {index}"
               " --value={host} ").format(index=index, host=host)
        return sp.run(cmd.split(), cwd='/var/www/nextcloud',
                      stdout=sp.PIPE, stderr=sp.PIPE, universal_newlines=True)

    @staticmethod
    def config_system_set_trusted_domains(domain, index) -> CompletedProcess:
        """
        Adds a trusted domain to nextcloud config.php with occ
        """

        cmd = ("sudo -u www-data php /var/www/nextcloud/occ config:system:set"
               " trusted_domains {index}"
               " --value={domain} ").format(index=index, domain=domain)
        return sp.run(cmd.split(), cwd='/var/www/nextcloud',
                      stdout=sp.PIPE, stderr=sp.PIPE, universal_newlines=True)

    @staticmethod
    def remove_trusted_domain(domain):
        """
        Removes a trusted domain from nextcloud with occ
        """
        current_domains = Occ.config_system_get_trusted_domains()
        if domain in current_domains:
            current_domains.remove(domain)
            # First delete all trusted domains from config.php
            # since they might have indices not in order.
            Occ.config_system_delete_trusted_domains()
            if current_domains:
                # Now, add all the domains with indices in order starting from 0
                for index, domain in enumerate(current_domains):
                    Occ.config_system_set_trusted_domains(domain, index)

    @staticmethod
    def config_system_delete_trusted_domains() -> CompletedProcess:
        cmd = "sudo -u www-data php /var/www/nextcloud/occ \
                                  config:system:delete trusted_domains"
        return sp.run(cmd.split(), cwd='/var/www/nextcloud',
                      stdout=sp.PIPE, stderr=sp.PIPE, universal_newlines=True)

    @staticmethod
    def config_system_get_trusted_domains() -> CompletedProcess:
        """
        Get all current trusted domains in config.php with occ
        return list
        """
        cmd = "sudo -u www-data php /var/www/nextcloud/occ \
                           config:system:get trusted_domains"
        return sp.run(cmd.split(), cwd='/var/www/nextcloud',
                      stdout=sp.PIPE, stderr=sp.PIPE, universal_newlines=True)
        # domains = output.stdout.split()

    @staticmethod
    def update_trusted_domains_peer_ips(domains):
        current_domains = Occ.config_system_get_trusted_domains().stdout.split()
        # Copy 'localhost' and fqdn but replace all peers IP:s
        # with the ones currently available in the relation.
        new_domains = current_domains[0:2] + domains[:]
        Occ.config_system_delete_trusted_domains()
        for index, d in enumerate(new_domains):
            Occ.config_system_set_trusted_domains(d, index)

    @staticmethod
    def db_add_missing_indices() -> CompletedProcess:
        cmd = "sudo -u www-data php /var/www/nextcloud/occ db:add-missing-indices"
        return sp.run(cmd.split(), cwd='/var/www/nextcloud',
                      stdout=sp.PIPE, stderr=sp.PIPE, universal_newlines=True)

    @staticmethod
    def db_convert_filecache_bigint() -> CompletedProcess:
        cmd = "sudo -u www-data php /var/www/nextcloud/occ \
               db:convert-filecache-bigint --no-interaction"
        return sp.run(cmd.split(), cwd='/var/www/nextcloud',
                      stdout=sp.PIPE, stderr=sp.PIPE, universal_newlines=True)

    @staticmethod
    def maintenance_mode(enable) -> CompletedProcess:
        m = "--on" if enable else "--off"
        cmd = f"sudo -u www-data php /var/www/nextcloud/occ maintenance:mode {m}"
        return sp.run(cmd.split(), cwd='/var/www/nextcloud',
                      stdout=sp.PIPE, stderr=sp.PIPE, universal_newlines=True)

    @staticmethod
    def maintenance_install(ctx) -> CompletedProcess:
        """
        Initializes nextcloud via the nextcloud occ interface.
        :return: <CompletedProcess>
        """
        cmd = ("sudo -u www-data /usr/bin/php occ maintenance:install "
               "--database {dbtype} --database-name {dbname} "
               "--database-host {dbhost} --database-pass {dbpass} "
               "--database-user {dbuser} --admin-user {adminusername} "
               "--admin-pass {adminpassword} "
               "--data-dir {datadir} ").format(**ctx)
        cp = sp.run(cmd.split(), cwd='/var/www/nextcloud',
                    stdout=sp.PIPE, stderr=sp.PIPE, universal_newlines=True)

        # Remove potential passwords from reaching the log.
        cp.args[13] = '*********'
        cp.args[19] = '*********'

        if not cp.returncode == 0:
            logger.error("Failed initializing nextcloud: " + str(cp))
        else:
            # TODO: Dont log the cp object since it may have passwords in it. Strip it away here?
            logger.info("Suceess initializing nextcloud: " + str(cp))

        return cp

    @staticmethod
    def status() -> CompletedProcess:
        """
        Returns CompletedProcess with nextcloud status in .stdout as json.
        """
        cmd = "sudo -u www-data /usr/bin/php occ status --output=json --no-warnings"
        return sp.run(cmd.split(), cwd='/var/www/nextcloud',
                      stdout=sp.PIPE, stderr=sp.PIPE, universal_newlines=True)

    @staticmethod
    def overwriteprotocol(protocol='http') -> CompletedProcess:
        """
        Sets the overwrite protocol with occ
        :return:
        """
        if protocol == "http" or protocol == "https":
            logger.info("Setting overwriteprotocol to: " + protocol)
            cmd = ("sudo -u www-data /usr/bin/php occ config:system:set overwriteprotocol --value=" + protocol)
            return sp.run(cmd.split(), cwd='/var/www/nextcloud',
                          stdout=sp.PIPE, stderr=sp.PIPE, universal_newlines=True)
        else:
            logger.error("Unsupported overwriteprotocol provided as config: " + protocol)
            sys.exit(-1)

    @staticmethod
    def defaultPhoneRegion(regionCode) -> CompletedProcess:
        """
        Sets the default_phone_region with occ
        :return:
        """
        valid_codes = ['AD', 'AE', 'AF', 'AG', 'AI', 'AL', 'AM', 'AO', 'AQ', 'AR', 'AS', 'AT', 'AU', 'AW', 'AX', 'AZ', 'BA', 'BB',
        'BD', 'BE', 'BF', 'BG', 'BH', 'BI', 'BJ', 'BL', 'BM', 'BN', 'BO', 'BQ', 'BR', 'BS', 'BT', 'BV', 'BW', 'BY',
        'BZ', 'CA', 'CC', 'CD', 'CF', 'CG', 'CH', 'CI', 'CK', 'CL', 'CM', 'CN', 'CO', 'CR', 'CU', 'CV', 'CW', 'CX',
        'CY', 'CZ', 'DE', 'DJ', 'DK', 'DM', 'DO', 'DZ', 'EC', 'EE', 'EG', 'EH', 'ER', 'ES', 'ET', 'FI', 'FJ', 'FK',
        'FM', 'FO', 'FR', 'GA', 'GB', 'GD', 'GE', 'GF', 'GG', 'GH', 'GI', 'GL', 'GM', 'GN', 'GP', 'GQ', 'GR', 'GS',
        'GT', 'GU', 'GW', 'GY', 'HK', 'HM', 'HN', 'HR', 'HT', 'HU', 'ID', 'IE', 'IL', 'IM', 'IN', 'IO', 'IQ', 'IR',
        'IS', 'IT', 'JE', 'JM', 'JO', 'JP', 'KE', 'KG', 'KH', 'KI', 'KM', 'KN', 'KP', 'KR', 'KW', 'KY', 'KZ', 'LA',
        'LB', 'LC', 'LI', 'LK', 'LR', 'LS', 'LT', 'LU', 'LV', 'LY', 'MA', 'MC', 'MD', 'ME', 'MF', 'MG', 'MH', 'MK',
        'ML', 'MM', 'MN', 'MO', 'MP', 'MQ', 'MR', 'MS', 'MT', 'MU', 'MV', 'MW', 'MX', 'MY', 'MZ', 'NA', 'NC', 'NE',
        'NF', 'NG', 'NI', 'NL', 'NO', 'NP', 'NR', 'NU', 'NZ', 'OM', 'PA', 'PE', 'PF', 'PG', 'PH', 'PK', 'PL', 'PM',
        'PN', 'PR', 'PS', 'PT', 'PW', 'PY', 'QA', 'RE', 'RO', 'RS', 'RU', 'RW', 'SA', 'SB', 'SC', 'SD', 'SE', 'SG',
        'SH', 'SI', 'SJ', 'SK', 'SL', 'SM', 'SN', 'SO', 'SR', 'SS', 'ST', 'SV', 'SX', 'SY', 'SZ', 'TC', 'TD', 'TF',
        'TG', 'TH', 'TJ', 'TK', 'TL', 'TM', 'TN', 'TO', 'TR', 'TT', 'TV', 'TW', 'TZ', 'UA', 'UG', 'UM', 'US', 'UY',
        'UZ', 'VA', 'VC', 'VE', 'VG', 'VI', 'VN', 'VU', 'WF', 'WS', 'YE', 'YT', 'ZA', 'ZM', 'ZW']
        if regionCode in valid_codes:
            logger.info("Setting default_phone_region to: " + regionCode)
            cmd = ("sudo -u www-data /usr/bin/php occ config:system:set default_phone_region --value=" + regionCode)
            return sp.run(cmd.split(), cwd='/var/www/nextcloud',
                          stdout=sp.PIPE, stderr=sp.PIPE, universal_newlines=True)
        else:
            logger.error("Unsupported phone region code provided as config: " + regionCode)
            sys.exit(-1)

    @staticmethod
    def setBackgroundCron() -> CompletedProcess:
        """
        Sets the background job scheulder to cron
        """
        cmd = "sudo -u www-data /usr/bin/php occ background:cron --no-warnings"
        return sp.run(cmd.split(), cwd='/var/www/nextcloud',
                      stdout=sp.PIPE, stderr=sp.PIPE, universal_newlines=True)

    @staticmethod
    def setRewriteBase() -> CompletedProcess:
        """
        Use URL rewrite, "Pretty URL". Removes index.php from url:
        https://nextcloud.dwellir.com/index.php/login -> https://nextcloud.dwellir.com/login
        updateHtaccess() must run for this to have effect.
        """
        cmd = "sudo -u www-data php occ config:system:set htaccess.RewriteBase --value='/'"
        return sp.run(cmd.split(), cwd='/var/www/nextcloud',
                      stdout=sp.PIPE, stderr=sp.PIPE, universal_newlines=True)

    @staticmethod
    def updateHtaccess() -> CompletedProcess:
        """
        Updates the .htaccess file. Needed for some settings to have effect, e.g. setRewriteBase().
        """
        cmd = "sudo -u www-data php occ maintenance:update:htaccess"
        return sp.run(cmd.split(), cwd='/var/www/nextcloud',
                      stdout=sp.PIPE, stderr=sp.PIPE, universal_newlines=True)

    @staticmethod
    def overwriteCliUrl(url) -> CompletedProcess:
        """
        Specify the base URL for any URLs which are generated within Nextcloud using any kind of command
        line tools (cron or occ). The value should contain the full base URL: https://nextcloud.dwellir.com
        """
        cmd = f"sudo -u www-data php occ config:system:set overwrite.cli.url --value={url}"
        return sp.run(cmd.split(), cwd='/var/www/nextcloud',
                      stdout=sp.PIPE, stderr=sp.PIPE, universal_newlines=True)

    @staticmethod
    def setDebug(onoff: bool) -> CompletedProcess:
        """
        Set the debug flag in config.php
        """
        cmd = f"sudo -u www-data php occ config:system:set debug --type=boolean --value={onoff}"
        return sp.run(cmd.split(), cwd='/var/www/nextcloud',
                      stdout=sp.PIPE, stderr=sp.PIPE, universal_newlines=True)

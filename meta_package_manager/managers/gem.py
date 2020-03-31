# -*- coding: utf-8 -*-
#
# Copyright Kevin Deldycke <kevin@deldycke.com> and contributors.
# All Rights Reserved.
#
# This program is Free Software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA  02111-1307, USA.

import os
import re
from shutil import which

from boltons.cacheutils import cachedproperty

from ..base import PackageManager
from ..platform import LINUX, MACOS, WINDOWS
from ..version import parse_version
from . import logger


class Gem(PackageManager):

    platforms = frozenset([LINUX, MACOS, WINDOWS])

    name = "Ruby Gems"

    # Default to the version shipped with the latest maintained macOS version,
    # i.e. macOS 10.13 High Sierra, which is bundled with gem 2.5.2.
    requirement = '2.5.0'

    global_args = [
        '--quiet',  # Silence command progress meter
    ]

    def get_version(self):
        """ Fetch version from ``gem --version`` output.

        Raw CLI output samples:

        .. code-block:: shell-session

            $ gem --version
            3.0.3
        """
        return parse_version(self.run([self.cli_path, '--version']))

    @cachedproperty
    def cli_path(self):
        """ Fully qualified path to the package manager CLI.

        Automaticaly search the location of the CLI in the system.

        Returns `None` if CLI is not found or is not a file.
        """

        if not self.cli_name:
            return None
        env_path = ":".join([
            "/usr/local/opt/ruby/bin/gem",
            "/usr/local/opt/ruby/bin",
            "/usr/local/bin",
            os.environ.get("PATH")
        ])
        cli_path = which(self.cli_name, mode=os.F_OK, path=env_path)
        if not cli_path:
            return None
        cli_path = which(cli_path, mode=os.F_OK, path=env_path)

        logger.debug(
            "CLI found at {}".format(cli_path) if cli_path
            else "{} CLI not found.".format(self.cli_name))
        return cli_path

    @cachedproperty
    def installed(self):
        """ Fetch installed packages from ``gem list`` output.

        Raw CLI output samples:

        .. code-block:: shell-session

            $ gem list

            *** LOCAL GEMS ***

            bigdecimal (default: 1.4.1)
            bundler (default: 1.17.2)
            CFPropertyList (2.3.6)
            cmath (default: 1.0.0)
            csv (default: 3.0.9)
            date (default: 2.0.0)
            fileutils (1.4.1, default: 1.1.0)
            io-console (0.5.6, default: 0.4.7)
            ipaddr (default: 1.2.2)
            molinillo (0.5.4, 0.4.5, 0.2.3)
            nokogiri (1.5.6)
            psych (2.0.0)
            rake (0.9.6)
            rdoc (4.0.0)
            sqlite3 (1.3.7)
            test-unit (2.0.0.0)
        """
        installed = {}

        output = self.run([self.cli_path, 'list'] + self.global_args)

        if output:
            regexp = re.compile(r'(\S+) \((.+)\)')
            for package in output.splitlines():
                match = regexp.match(package)
                if match:
                    package_id, versions = match.groups()
                    # Guess latest installed version.
                    version = max([
                        parse_version(v)
                        for v in re.compile(r',|default:| ').split(versions)
                        if v])
                    installed[package_id] = {
                        'id': package_id,
                        'name': package_id,
                        'installed_version': version}

        return installed

    def search(self, query):
        """ Fetch matching packages from ``gem search`` output.

        Raw CLI output samples:

        .. code-block:: shell-session

            $ gem search python

            *** REMOTE GEMS ***

            bee_python (0.2.3)
            fluent-plugin-airbrake-python (0.2)
            logstash-filter-python (0.0.1 java)
            pythonconfig (1.0.1)
            rabbit-slide-niku-erlangvm-for-pythonista (2015.09.12)
            RubyToPython (0.0)
        """
        matches = {}

        output = self.run([self.cli_path, 'search', query] + self.global_args)

        if output:
            regexp = re.compile(r'(\S+) \((.+)\)')
            for package in output.splitlines():
                match = regexp.match(package)
                if match:
                    package_id, version = match.groups()
                    matches[package_id] = {
                        'id': package_id,
                        'name': package_id,
                        'latest_version': parse_version(version.split()[0]),
                        'exact': self.exact_match(query, package_id)}

        return matches

    @cachedproperty
    def outdated(self):
        """ Fetch outdated packages from ``gem outdated`` output.

        Raw CLI output samples:

        .. code-block:: shell-session

            $ gem outdated
            did_you_mean (1.0.0 < 1.0.2)
            io-console (0.4.5 < 0.4.6)
            json (1.8.3 < 2.0.1)
            minitest (5.8.3 < 5.9.0)
            power_assert (0.2.6 < 0.3.0)
            psych (2.0.17 < 2.1.0)
        """
        outdated = {}

        output = self.run([self.cli_path, 'outdated'] + self.global_args)

        if output:
            regexp = re.compile(r'(\S+) \((\S+) < (\S+)\)')
            for package in output.splitlines():
                match = regexp.match(package)
                if match:
                    package_id, current_version, latest_version = \
                        match.groups()
                    outdated[package_id] = {
                        'id': package_id,
                        'name': package_id,
                        'installed_version': parse_version(current_version),
                        'latest_version': parse_version(latest_version)}

        return outdated

    def upgrade_cli(self, package_id=None):
        cmd = [self.cli_path, 'update', '--user-install'] + self.global_args
        # Installs require `sudo` on system ruby.
        # I (@tresni) recommend doing something like:
        #     $ sudo dseditgroup -o edit -a -t user wheel
        # And then do `visudo` to make it so the `wheel` group does not require
        # a password. There is a line already there for it, you just need to
        # uncomment it and save.)
        # if self.cli_path == '/usr/bin/gem':
        #     cmd.insert(0, '/usr/bin/sudo')
        if package_id:
            cmd.append(package_id)
        return cmd

    def upgrade_all_cli(self):
        return self.upgrade_cli()

    def cleanup(self):
        """ Run ``gem cleanup`` CLI.

        Raw CLI output samples:

        .. code-block:: shell-session

            $ gem cleanup
            Cleaning up installed gems...
            Attempting to uninstall test-unit-3.2.9
            Unable to uninstall test-unit-3.2.9:
                Gem::FilePermissionError: You don't have write permissions \
                for the /Library/Ruby/Gems/2.6.0 directory.
            Attempting to uninstall did_you_mean-1.3.0
            Unable to uninstall did_you_mean-1.3.0:
                Gem::FilePermissionError: You don't have write permissions \
                for the /Library/Ruby/Gems/2.6.0 directory.
            Clean up complete
        """
        super(Gem, self).cleanup()
        self.run([self.cli_path, 'cleanup'] + self.global_args)

#!/usr/bin/env python
"""Utility to help with generating MFA (STS) tokens and update AWS creds config."""
# ****************************************************************************
# *   Keyring TOTP Generator                                                 *
# *                                                                          *
# *   Copyright (C) 2018 by Jeremy Falling except where noted.               *
# *                                                                          *
# *   This program is free software: you can redistribute it and/or modify   *
# *   it under the terms of the GNU General Public License as published by   *
# *   the Free Software Foundation, either version 3 of the License, or      *
# *   (at your option) any later version.                                    *
# *                                                                          *
# *   This program is distributed in the hope that it will be useful,        *
# *   but WITHOUT ANY WARRANTY; without even the implied warranty of         *
# *   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the          *
# *   GNU General Public License for more details.                           *
# *                                                                          *
# *   You should have received a copy of the GNU General Public License      *
# *   along with this program.  If not, see <http://www.gnu.org/licenses/>.  *
# ****************************************************************************

import argparse
import configparser
import logging
import signal
import sys
from boto.sts import STSConnection
from os.path import expanduser, join

import aws_mfa_helper

# optional requirement
try:
    from totp_generator.core_utils import KeyringTotpGenerator

except ImportError:
    pass

# backwards compatibility for py2
try:
    input = raw_input
except NameError:
    pass

PROGNAME = aws_mfa_helper.__progname__
VERSION = aws_mfa_helper.__version__
MFA_SERIAL_CONFIG_KEY = 'helper_mfa_serial'
TOTP_SERVICE_CONFIG_KEY = 'helper_totp_service_name'
MFA_CREDS_SUFFIX = '-mfa'

logging.basicConfig(level=logging.INFO)
logging.getLogger()
logger = logging.getLogger()


def signal_handler(signal, frame):
    """Catch interrupts and exit without a stack trace."""
    print('\nExiting...\n')
    sys.exit(0)


def show_version():
    """Show version info and exit."""
    print('{name} version {ver}\n'.format(name=PROGNAME, ver=VERSION))
    sys.exit(0)


def profile_selection(aws_creds):
    """
    User selection of aws profile.

    :param aws_creds: user creds dict
    :return: name of aws profile
    """
    choices = list()
    i = 0
    for key, key_val in aws_creds.items():
        if not key.endswith(MFA_CREDS_SUFFIX) and key is not 'DEFAULT':
            i += 1
            choices.append(key)
            print('{i}: {k}'.format(i=i, k=key))

    while True:
        user_in = input('\nPick AWS profile: ')
        try:
            sel = int(user_in) - 1
            # range is exclusive
            if int(sel) in range(0, i + 1):
                break
        except ValueError:
            pass

        print("Your selection is not valid. Try again.")

    return choices[int(sel)]


def duration_selection():
    """
    User selection of token duration.

    :return: int between 900 and 129600
    """

    while True:
        user_in = input('\nEnter token lifetime in seconds (900-129600) [86400]: ')
        if not user_in:
            return 86400

        try:
            sel = int(user_in) - 1
            # range is exclusive
            if int(sel) in range(899, 129601):
                break
        except ValueError:
            pass

        print("Your selection is not valid. Try again.")

    return user_in


def mfa_entry(aws_conf, profile):
    """
    Try to generate TOTP code if totp_generator is installed. Otherwise prompt user for code.

    :param aws_conf: AWS config configparser.ConfigParser object
    :param profile: Name of AWS config profile
    :return: Six digit MFA code as string
    """
    if 'totp_generator.core_utils' in sys.modules:
        try:
            # totp_generator is installed.
            full_profile = 'profile {n}'.format(n=profile)
            try:
                totp_service = aws_conf[full_profile][TOTP_SERVICE_CONFIG_KEY]
            except KeyError:
                raise KeyError('{k} was not found in AWS config. Cannot auto-generate TOTP code'.format(
                    k=TOTP_SERVICE_CONFIG_KEY))
            code = KeyringTotpGenerator().get_totp_code(totp_service)
            logger.debug('Got TOTP code from totp_generator')

            return code

        except Exception as err:
            logger.debug('Failed to get TOTP code from totp_generator: {e}'.format(e=err))

    while True:
        user_in = input('\nEnter MFA code: ')
        try:
            int(user_in)
            break
        except ValueError:
            pass

        print("Your selection is not valid. Try again.")

    return user_in


def get_mfa_device(config, profile):
    """
    Verify that config is not missing required custom elements.

    :param config: AWS config configparser.ConfigParser object
    :param profile: Name of AWS config profile
    :return: Bool
    """
    full_profile = 'profile {n}'.format(n=profile)

    try:
        tmp = config[full_profile][MFA_SERIAL_CONFIG_KEY]
    except KeyError:
        print('ERROR: you must add {c} to your AWS conf profile with the ARN of your MFA device! Example: \
\n[profile {p}]\n\
{c} = iam::ACCOUNT-NUMBER-WITHOUT-HYPHENS:mfa/MFA-DEVICE-ID\n'.format(
            c=MFA_SERIAL_CONFIG_KEY, p=profile))
        exit(1)

    return config[full_profile][MFA_SERIAL_CONFIG_KEY]


def get_sts_creds(profile, duration, device_id, mfa_code):
    """
    Get STS creds from AWS.

    :param profile: AWS creds profile name
    :param duration: Token lifetime
    :param device_id: MFA device ARN
    :param mfa_code: MFA TOTP code
    :return:
    """
    sts_connection = STSConnection(profile_name=profile)

    sts_creds = sts_connection.get_session_token(
        duration=duration,
        mfa_serial_number="{device_id}".format(device_id=device_id),
        mfa_token=mfa_code
    )

    return sts_creds


def update_aws_creds(aws_creds, profile, sts_creds):
    """
    Update STS profile with STS creds.

    :param aws_creds: AWS creds dict
    :param profile: Name of AWS config profile (without MFA suffix)
    :param sts_creds: AWS creds boto.sts.credentials.Credentials object
    :return: configparser.ConfigParser object
    """
    sts_profile = '{p}{s}'.format(p=profile, s=MFA_CREDS_SUFFIX)
    if sts_profile not in aws_creds:
        aws_creds[sts_profile] = dict()

    aws_creds[sts_profile]['aws_access_key_id'] = sts_creds.access_key
    aws_creds[sts_profile]['aws_secret_access_key'] = sts_creds.secret_key
    # support both session and security keys as various utilities require one or the other
    aws_creds[sts_profile]['aws_session_token'] = sts_creds.session_token
    aws_creds[sts_profile]['aws_security_token'] = sts_creds.session_token

    return aws_creds


def read_aws_file(filepath):
    """
    Read AWS config file.

    :param aws_creds_file: Full path to AWS creds file
    :return: configparser.ConfigParser
    """
    config = configparser.ConfigParser()
    config.read(filepath)

    return config


def save_aws_creds(aws_creds_file, config):
    """
    Write AWS config to file.
    :param aws_creds_file: AWS creds file path.
    :param config: AWS creds boto.sts.credentials.Credentials object
    :return: None
    """
    with open(aws_creds_file, 'w') as configfile:
        config.write(configfile)

    return


def load_helper_config(home):
    """
    Load aws helper config.
    :param home: path to user home
    :return: None
    """
    file_path = join(home, '.aws_mfa_helper.cfg')
    try:
        config = read_aws_file(file_path)
        logger.debug('Loaded helper config.')

        if config.get('mfa_creds_suffix'):
            logger.debug('Setting MFA_CREDS_SUFFIX to {s}'.format(s=config['mfa_creds_suffix']))

            global MFA_CREDS_SUFFIX
            MFA_CREDS_SUFFIX = config['mfa_creds_suffix']
    except Exception:
        pass

    return


def main():
    signal.signal(signal.SIGINT, signal_handler)
    parser = argparse.ArgumentParser(description='AWS MFA Helper\n\n' +
                                                 'Reads AWS config and automates obtaining and updating AWS creds with' +
                                                 ' STS tokens',
                                     formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument('-d', '--debug', action='store_true', help='enable debug logging')
    parser.add_argument('-v', '--version', action='store_true', help='show version and exit')
    args = parser.parse_args()

    # handle flags
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    if args.version:
        show_version()

    user_home = expanduser("~")
    aws_creds_file = join(user_home, '.aws', 'credentials')
    aws_config_file = join(user_home, '.aws', 'config')

    load_helper_config(user_home)

    if 'totp_generator.core_utils' in sys.modules:
        logger.debug('totp_generatior is installed. Will attempt to automate TOTP generation.')

    print('AWS MFA Helper\n')

    aws_creds = read_aws_file(aws_creds_file)
    aws_conf = read_aws_file(aws_config_file)

    profile = profile_selection(aws_creds)

    device_id = get_mfa_device(aws_conf, profile)

    duration = duration_selection()

    mfa_code = mfa_entry(aws_conf, profile)

    sts_creds = get_sts_creds(profile, duration, device_id, mfa_code)

    aws_creds = update_aws_creds(aws_creds, profile, sts_creds)

    save_aws_creds(aws_creds_file, aws_creds)

    print('\nUpdated AWS profile {p} with STS credentials. Credentials expire at {d}'.format(p=profile,
                                                                                             d=sts_creds.expiration))


if __name__ == '__main__':
    main()

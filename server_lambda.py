#!/usr/bin/python

import logging
import re
import json
import boto3
import socket
from passlib.context import CryptContext
from dynips.lib import S3Bucket, getFullHostname, getMaxErrors, kickManager


class MyException(Exception):

    def __init__(self, code, record, msg):
        self.code = code
        self.msg = msg
        self.record = record


def recordError(bucket, name, msg):
    '''
    Record the fact that an error occurred for the specifed
    name, which is either a username or an IP address. We do this
    by creating a file with the name <name>.ERROR.<ord>, where <ord>
    is the next higest ordinal for the given name.

    If the number of ERROR files reaches MAX_ERRORS, we lock the
    user or IP by writing the file <name>.LOCK.
    '''

    ords = [f.ord
                for f in bucket.iterStateFiles(base=name, ext=bucket.ERROR_EXT)
            if f.ord is not None]

    bucket.writeStateFile(
        name,
        bucket.ERROR_EXT,
        json.dumps({'error': msg}),
        ord=(max(ords) if ords else 0) + 1)

    if len(ords) + 1 >= getMaxErrors():
        bucket.writeLockFile(name, msg)


def lambda_handler(event, context):
    '''
    This is the dynips server lambda function.

    The event dict contains the following items obtained
    from the https request:

    remote_addr: The IP of the remote client
    key: The key param (i.e. the user password)
    host: The host param (hostname to be registered)
    ip: The IP param (an optional IP to assign to the host)
    expire: The expire param (the value 'no' means to mark the host hold)
    '''

    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    result = {}

    bucket = None
    user = None
    client_ip = event['remote_addr']

    key = event.get('key')
    if key:
        # Hide the key in logs
        event['key'] = '****'

    logger.info('Request: {}'.format( str(event)))

    try:
        bucket = S3Bucket()

        if bucket.isLocked(client_ip):
            raise MyException(
                401, False, "IP '{}' is locked".format(client_ip))

        result['ip'] = client_ip

        host = event.get('host')
        if host:
            host_match = re.match('(([a-zA-Z0-9]+)(-[a-zA-Z0-9]+)?)$', host)

            if not host_match:
                raise MyException(
                    400, False, "Invalid host param '{}'".format(host))

            user = host_match.group(2)

            if bucket.isLocked(user):
                raise MyException(
                    401, False, "User '{}' is locked".format(user))

            user_file = bucket.getUserFile(user)

            if not user_file:
                raise MyException(
                    401, True, "Unknown user '{}'".format(user))

            fqdn = getFullHostname(host)

            try:
                cur_ip = socket.gethostbyname(fqdn)
            except Exception as e:
                logger.error('Error looking up {}: {}'.format(fqdn, str(e)))
                cur_ip = 'unknown'

            if key:
                user_data = json.load(user_file.get()['Body'])

                hash = user_data.get( 'keyhash')
                if not hash:
                    raise MyException(
                        500, False, 'The user configuration is damaged')

                if not CryptContext(
                        schemes=['pbkdf2_sha256']).verify(key, hash):

                    raise MyException(
                        401, True,
                        "Unknown user '{}' or invalid key '****'".format(
                            user))

                new_ip = event.get('ip')
                if new_ip:
                    if not re.match(
                            '[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$', new_ip):
                        raise MyException(
                            400, False, "Invalid IP '{}'".format(new_ip))
                else:
                    new_ip = client_ip

                if cur_ip != new_ip:
                    action = 'updated'
                    result['new_ip'] = new_ip
                    ok, commit_result = bucket.setHostIP(host, new_ip)

                    if ok:
                        kickManager(bucket.session)
                        logger.info(
                            'Route53 result: {}'.format( str(commit_result)))
                    else:
                        logger.error(
                            'Route53 result: {}'.format( str(commit_result)))
                        raise MyException(
                            500, 'Internal error updating host IP')
                else:
                    action = 'no_change'

                result['action'] = action
                bucket.writePingFile(host, new_ip, event.get('expire') == 'no')

            # Set these after validating user credentials
            # so that we don't reveal information if the
            # credentials are invalid.
            #
            result['host'] = getFullHostname(host)
            result['cur_ip'] = cur_ip

    except MyException as e:
        logger.error(e.msg)

        if e.record and bucket is not None:
            recordError(bucket, client_ip, e.msg)

            if user:
                recordError(bucket, user, e.msg)

        # NOTE: The format of the error message must match the
        # pattern expected in the integration response defined in
        # create-server-api
        #
        raise Exception( '{}: {}'.format( e.code, e.msg))

    except:
        logging.exception( 'Woops')
        raise Exception('500: Internal error')

    logger.info('Result: {}'.format( result))
    return result


if __name__ == '__main__':
    logging.basicConfig()

    from argparse import ArgumentParser

    parser = ArgumentParser(description='Test dynips server')
    parser.add_argument('client_ip')
    parser.add_argument('--host')
    parser.add_argument('--key')
    parser.add_argument('--expire')
    parser.add_argument('--ip')

    args = parser.parse_args()

    print str(lambda_handler(
        {
            'expire': args.expire,
            'host': args.host,
            'key': args.key,
            'ip': args.ip,
            'remote_addr': args.client_ip
        }, {}))

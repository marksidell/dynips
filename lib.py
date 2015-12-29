import boto3
import json
import re
import collections
import datetime
import pytz

from params import Params


USERS_FOLDER = 'users/'
STATE_FOLDER = 'state/'


def getStateFilename(basename, ext, ord=None):
    name = ''.join((STATE_FOLDER, basename.lower(), '.', ext))
    if ord is not None:
        name = ''.join((name, '.', str(ord)))
    return name


def getUserFilename(user):
    return ''.join((USERS_FOLDER, user.lower()))


def getExpiryTime(max_age=None):
    return datetime.datetime.now(pytz.UTC) - \
        datetime.timedelta(
            seconds=Params.MAX_AGE if max_age is None else max_age)


def getFullHostname(host):
    return ''.join((host, '.', Params.DOMAIN_ROOT))


def getMaxErrors():
    return Params.MAX_ERRORS


def argToTuple(arg):
    if arg is None:
        return ()
    elif isinstance(arg, str):
        return (arg,)
    else:
        return tuple(arg)


StateFile = collections.namedtuple(
    'StateFile', 'file item host user sub ip ext ord')
UserFile = collections.namedtuple(
    'UserFile', 'file user')


class S3Bucket():
    PING_EXT = 'ping'
    HOLD_EXT = 'hold'
    EXPIRED_EXT = 'expired'
    ERROR_EXT = 'error'
    LOCK_EXT = 'lock'

    def __init__(
            self,
            access_key_id=None, secret_access_key=None, session_token=None):
        self.session = boto3.Session(
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            aws_session_token=session_token)
        self.s3 = self.session.resource("s3")
        self.bucket = self.s3.Bucket(Params.S3_BUCKET)
        self.files = {f.key: f for f in self.bucket.objects.all()}

    # A generator to iterate the state files.
    # base and ext are optional filters.
    # Return a StateFile named tuple.
    #
    def genStateFiles(self, base=None, ext=None):
        base = argToTuple(base)
        ext = argToTuple(ext)

        for k, f in self.files.iteritems():
            match = re.match(
                STATE_FOLDER +
                '(?P<item>(?P<host>'
                '(?P<user>[a-zA-Z0-9]+)(?:-(?P<sub>[a-zA-Z0-9]+))?)|'
                '(?P<ip>[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+))'
                '\.(?P<ext>[a-z]+)(?:\.(?P<ord>[0-9]+))?$',
                k)

            if match and \
                    (not base or match.group('item') in base) and \
                    (not ext or match.group('ext') in ext):
                yield StateFile(
                    file=f,
                    item=match.group('item'),
                    host=match.group('host'),
                    user=match.group('user'),
                    sub=match.group('sub'),
                    ip=match.group('ip'),
                    ext=match.group('ext'),
                    ord=int(match.group('ord')) if match.group('ord') else None)

    # A generator to iterate the user files.
    # Return a USerFile named tuple.
    #
    def genUserFiles(self):
        for k, f in self.files.iteritems():
            match = re.match(USERS_FOLDER + '([a-zA-Z0-9]+)', k)
            if match:
                yield UserFile(file=f, user=match.group(1))

    def getFile(self, filename):
        return self.files.get(filename)

    def writeStateFile(self, name, ext, body, ord=None):
        self.bucket.put_object(
            Key=getStateFilename(name, ext, ord), Body=body)

    def isLocked(self, name):
        return getStateFilename(name, self.LOCK_EXT) in self.files

    def getLockFile(self, name):
        return self.getFile(getStateFilename(name, self.LOCK_EXT))

    def writeLockFile(self, name, msg):
        self.writeStateFile(name, self.LOCK_EXT, json.dumps({'error': msg}))

    def getUserFile(self, user):
        return self.getFile(getUserFilename(user))

    def writeUserFile(self, user, body):
        self.bucket.put_object(Key=getUserFilename(user), Body=body)

    def writePingFile(self, hostname, ip, hold):
        self.writeStateFile(
            hostname, self.PING_EXT, json.dumps({'ip': ip}))

        expired_file = self.getFile(getStateFilename(hostname, 'expired'))
        if expired_file:
            expired_file.delete()

        hold_file = self.getFile(getStateFilename(hostname, self.HOLD_EXT))

        if hold and not hold_file:
            self.writeStateFile(
                hostname, self.HOLD_EXT, json.dumps({'ip': ip}))
        elif not hold and hold_file:
            hold_file.delete()

    def setHostIP(self, host, ip):
        result = self.session.client('route53').change_resource_record_sets(
            HostedZoneId=Params.ROUTE53_ZONE_ID,
            ChangeBatch={
                'Changes':
                    [
                        {
                            'Action': 'UPSERT',
                            'ResourceRecordSet':
                            {
                                'Name': getFullHostname(host),
                                'Type': 'A',
                                'TTL': Params.TTL,
                                'ResourceRecords':
                                    [{'Value':
                                        ip if ip else Params.DEFAULT_IP}]
                            }
                        }
                    ]
            })

        change_info = result.get('ChangeInfo')
        bOk = change_info and 'PENDING' == change_info.get('Status')

        return (bOk, result)

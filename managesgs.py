from __future__ import print_function

import lib
import json
import re
import collections
import socket
import logging
import boto3

from params import Params

HostIp = collections.namedtuple('HostIp', 'host ip')
PortRange = collections.namedtuple('PortRange', 'begin end protocol')

logger = logging.getLogger()
logger.setLevel(logging.INFO)


class Permissions:
    def __init__(self):
        self.map = collections.defaultdict(dict)

    def addPorts(self, range):
        self.map[range] = collections.defaultdict(dict)

    def addCIDR(self, cidr):
        for r,v in self.map.iteritems():
            v[cidr] = False

    def addPermission(self, range, cidr):
        self.map[range][cidr] = False

    def has(self, range, cidr):
        if range in self.map:
            cidrs = self.map[range]

            if cidr in cidrs:
                cidrs[cidr] = True
                return True

        return False

    def getUpdates(self, name, id, action):
        r = []

        for range, cidrs in self.map.iteritems():
            ip_ranges = []
            for cidr in (c for c,f in cidrs.iteritems() if not f):
                ip_ranges.append({ 'CidrIp':cidr })
                logger.info(
                    '{}/{}: {} {}:{}-{} {}'.format(
                        name,
                        id,
                        action,
                        range.protocol,
                        range.begin,
                        range.end,
                        cidr))

            if ip_ranges:
                r.append({
                    'IpProtocol': range.protocol,
                    'FromPort': range.begin,
                    'ToPort': range.end,
                    'IpRanges': ip_ranges
                })

        return r


class SG:
    def __init__(self, name, id, ports):
        self.permissions = Permissions()
        self.name = name
        self.id = id

        if ports:
            for p in ports:
                first_port= p['port']
                self.permissions.addPorts(
                    PortRange(
                        first_port,
                        p.get('last_port', first_port),
                        p.get('ip_protocol', 'tcp')))
        else:
            self.permissions.addPorts( PortRange(0, 65535, 'tcp'))
            self.permissions.addPorts( PortRange(0, 65535, 'udp'))
            self.permissions.addPorts( PortRange(-1, -1, 'icmp'))

    def addCIDR(self, cidr):
        self.permissions.addCIDR( cidr)

    def hasPermission(self, range, cidr):
        return self.permissions.has(range, cidr)

    def getUpdates(self, action):
        return self.permissions.getUpdates(self.name, self.id, action)


def addHost( sgs, host, cidr, groups):
    for g in groups:
        if g in sgs:
            sgs[g].addCIDR(cidr)
        else:
            logger.warning(
                'Host {} {} references unknown group {}.'.format(host,cidr,g))


def manageSecurityGroups(session=None, dry_run=False):
    '''
    Update security groups.
    '''

    if session is None:
        session = boto3.Session()

    s3 = session.resource('s3')
    ec2 = session.client('ec2')
    ec2_resource = session.resource('ec2')
    route53 = session.client('route53')

    # Read the SG config file and strip comments from the json text
    #
    sg_filename = Params.SG_FILE.split( '/', 1)
    sg_file = s3.Object( sg_filename[0], sg_filename[1]).get()

    json_lines= []

    for line in sg_file['Body'].read().split( '\n'):
        i = line.find( '#')
        if i < 0:
            i = len(line)
        json_lines.append( line[:i])

    config = json.loads( ' '.join( json_lines))
    sg_defs= config['security_groups']

    sgs_by_name = {}
    sgs_by_id = {}

    for aws_sg in ec2.describe_security_groups()['SecurityGroups']:
        name = aws_sg['GroupName']
        sg_def = sg_defs.get(name)

        if sg_def:
            id = aws_sg['GroupId']
            sg = SG(name, id, sg_def.get('ports'))
            sgs_by_name[name] = sg
            sgs_by_id[id] = sg


    for name in sg_defs:
        if name not in sgs_by_name:
            logger.warning('Security group not found in AWS: {}'.format( name))

    # Get the list of dynips hostnames.
    # The resulting name_map maps each hostname root to a list of
    # HostIp tuples consisting of (hostname, ip).
    #
    name_map= collections.defaultdict(list)

    rresets = route53.list_resource_record_sets(
                HostedZoneId=Params.ROUTE53_ZONE_ID)['ResourceRecordSets']

    re_expn = '(?P<host>(?P<root>[a-zA-Z0-9]+)(-[a-zA-Z0-9]+)?)\\.{}\\.$'.format(
                    Params.DOMAIN_ROOT.replace('.', '\\.'))

    for r in (r for r in rresets if r['Type']=='A'):
        match= re.match(re_expn, r['Name'])
        if match:
            ip= r.get('ResourceRecords')[0].get('Value')

            if ip and ip != Params.DEFAULT_IP:
                name_map[match.group('root')].append(
                    HostIp(match.group('host'), ip))

    for h in config['hosts']:
        host = h.get('host')
        cidr = h.get('ip')
        groups = h.get('groups')

        if (not host and not cidr) or not groups:
            print( 'Host definition is invalid: {}'.format( str(h)))

        else:
            if host:
                cidr = ''

                if host.endswith( '*'):
                    root = host[:-1]
                    map = name_map.get(root)
                    if map:
                        for n in map:
                            addHost( sgs_by_name, host, n.ip+'/32', groups)
                    else:
                        logger.warning(
                            'Dynip user {} has no hostnames.'.format(root))
                else:
                    try:
                        cidr = socket.gethostbyname( host)+'/32'
                    except:
                        logger.error( 'Failed to find IP for {}'.format( host))

            # Ignore non-public IPs.
            # We do this because sometimes Chuck's dyndns IPs are
            # reported incorrectly to dyndns.
            #
            if cidr and (not host or not re.match( '(10\\.)|(192\\.168)', cidr)) :
                addHost(sgs_by_name, host, cidr, groups)


    for id, sg in sgs_by_id.iteritems():
        try:
            aws_sg = ec2_resource.SecurityGroup(id)

            to_remove = Permissions()

            for p in aws_sg.ip_permissions:
                range = PortRange( p['FromPort'], p['ToPort'], p['IpProtocol'])

                for cidr in (r['CidrIp'] for r in p['IpRanges']):
                    if not sg.hasPermission(range, cidr):
                        to_remove.addPermission(range, cidr)

            remove = to_remove.getUpdates(sg.name, id, 'remove')

            if remove and not dry_run:
                aws_sg.revoke_ingress(IpPermissions=remove)

            add = sg.getUpdates('add')

            if add and not dry_run:
                aws_sg.authorize_ingress(IpPermissions=add)

        except Exception as e:
            print( 'ERROR: failed to update SG {}: {}'.format(id, str(e)))

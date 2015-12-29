import boto3

import lib


def expireHosts(bucket=None, max_age=None):
    '''Expire all hostnames that have not been updated
    more recently than max_age seconds ago, and that
    are not marked hold.

    Active hostnames are those with files having a
    PING extension. Hostnames being held have files
    with a HOLD extension. To expire a host, we
    delete the PING file and replace it with an
    EXPIRED file.
    '''

    if bucket is None:
        bucket = lib.S3Bucket()

    expired = []
    candidates = []
    holds = set()
    expiry_time = lib.getExpiryTime(max_age)

    # Build a list of candidate hosts to expire (all PING files)
    # and a set of hosts being held (all HOLD files).
    #
    for f in bucket.genStateFiles(ext=[bucket.PING_EXT, bucket.HOLD_EXT]):
        if f.ext == bucket.PING_EXT:
            if f.file.last_modified < expiry_time:
                candidates.append(f)
        else:
            holds.add(f.host)

    for f in (x for x in candidates if x.host not in holds):
        bucket.setHostIP(f.host, None)
        bucket.writeStateFile(
            f.host, bucket.EXPIRED_EXT, f.file.get()['Body'].read())
        f.file.delete()
        expired.append(f.host)

    return expired

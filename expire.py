import boto3
import lib


def expireHosts( bucket=None, max_age=None):
    if bucket is None:
        bucket = lib.S3Bucket()

    expired = []
    candidates = []
    holds = set()
    expiry_time = lib.getExpiryTime( max_age)

    for f in bucket.genStateFiles( ext=[bucket.PING_EXT,bucket.HOLD_EXT]):
        if f.ext == bucket.PING_EXT:
            if f.file.last_modified < expiry_time:
                candidates.append( f)
        else:
            holds.add( f.host)

    for f in (x for x in candidates if x.host not in holds):
        bucket.setHostIP( f.host, None)
        bucket.writeStateFile( f.host, bucket.EXPIRED_EXT, f.file.get()['Body'].read())
        f.file.delete()
        expired.append( f.host)

    return expired

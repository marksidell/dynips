#!/usr/bin/python

import logging
import dynips.expire


def lambda_handler(event, context):
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    try:
        result = dynips.expire.expireHosts()
        logger.info(
            'Expired: %s' % (','.join(result) if result else 'Nothing'))

    except Exception as e:
        logger.error(str(e))

    return {}


if __name__ == '__main__':
    logging.basicConfig()

    lambda_handler({}, {})

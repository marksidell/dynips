#!/usr/bin/python

import logging
import dynips.expire


def lambda_handler(event, context):
    '''
    This is the expirer lambda function. It simply
    calls expireHosts() and logs the list of expired
    hosts.
    '''

    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    try:
        result = dynips.expire.expireHosts()

        if not result:
            result.append('Nothing')

        for h in result:
            logger.info('Expired: {}'.format(h))

    except:
        logging.exception( 'Woops')

    return {}


if __name__ == '__main__':
    logging.basicConfig()

    lambda_handler({}, {})

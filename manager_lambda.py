#!/usr/bin/python

import logging
import dynips.managesgs


def lambda_handler(event, context):
    '''
    This is the security grion lambda function.
    '''

    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    try:
        dynips.managesgs.manageSecurityGroups()

    except:
        logging.exception( 'Woops')

    return {}


if __name__ == '__main__':
    logging.basicConfig()

    lambda_handler({}, {})

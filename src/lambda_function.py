import collections
import datetime
import gzip
import json
import logging
import os
import time
import urllib2
from base64 import b64decode
from StringIO import StringIO

# set logger
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# print correct response status code and return True if we need to retry
def shouldRetry(e):
    if e.code == 400:
        logger.error("Got 400 code from Logz.io. This means that some of your logs are too big, or badly formatted. response: {0}".format(e.reason))
    elif e.code == 401:
        logger.error("You are not authorized with Logz.io! Token OK? dropping logs...")
    else:
        logger.error("Got {0} while sending logs to Logz.io, response: {1}".format(e.code, e.reason))
        return True
    return False

# send in bulk JSONs object to logzio
def sendToLogzio(jsonStrLogsList,logzioUrl):
    headers = {"Content-type": "application/json"}
    maxRetries = 3
    sleepBetweenRetries = 5
    for currTry in reversed(xrange(maxRetries)):
        request = urllib2.Request(logzioUrl, data='\n'.join(jsonStrLogsList), headers=headers)
        try:
            response = urllib2.urlopen(request)
            statusCode = response.getcode()
            logger.info("Successfully sent bulk of " + str(len(jsonStrLogsList)) + " logs to Logz.io!")
            return
        except (IOError) as e:
            if (shouldRetry(e)):
                logger.info("Failure is retriable - Trying {} more times".format(currTry))
                time.sleep(sleepBetweenRetries)
            else:
                raise IOError("Failed to send logs")

    raise RuntimeError("Retries attempts exhausted. Failed sending to Logz.io")

def extractAwsLogsData(event):
    try:
        logsDataDecoded = event['awslogs']['data'].decode('base64')
        logsDataUnzipped = gzip.GzipFile(fileobj=StringIO(logsDataDecoded)).read()
        logsDataDict = json.loads(logsDataUnzipped)
        return logsDataDict
    except ValueError as e:
        logger.error("Got exception while loading json, message: {}".format(e))
        raise ValueError("Exception: json loads")


def lambda_handler(event, context):
    logzioUrl = "{0}/?token={1}&type={2}".format(os.environ['URL'], os.environ['TOKEN'], os.environ['TYPE'])

    awsLogsData = extractAwsLogsData(event)

    logger.info("About to send {} logs".format(len(awsLogsData['logEvents'])))
    jsonStrLogsList =[]
    for log in awsLogsData['logEvents']:
        if not isinstance(log, collections.Mapping):
            raise TypeError("Expected log inside logEvents to be a Dict but found another type")

        if '@timestamp' not in log:
            log['@timestamp'] = str(log['timestamp'])

        log['logStream'] = awsLogsData['logStream']
        log['messageType'] = awsLogsData['messageType']
        log['owner'] = awsLogsData['owner']
        log['logGroup'] = awsLogsData['logGroup']

        jsonStrLogsList.append(json.dumps(log))

    sendToLogzio(jsonStrLogsList,logzioUrl)

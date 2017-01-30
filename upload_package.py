import os
import sys
import urllib2
import argparse
import logging
import poster

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--url', required=True, dest='url', help='url')
    parser.add_argument('--filename', required=True, dest='filename', help='filename')
    parser.add_argument('--field', dest='field', help='field name', default='uploaded')
    parameters = parser.parse_args()

    if not os.path.exists(parameters.filename):
        logging.error('dont exists %s' % parameters.filename)
        sys.exit(1)

    # Register the streaming http handlers with urllib2
    poster.streaminghttp.register_openers()

    with open(parameters.filename, "rb") as f:
        datagen, headers = poster.encode.multipart_encode({parameters.field: f})
        # Create the Request object
        request = urllib2.Request(parameters.url, datagen, headers)
        # Actually do the request, and get the response
        handler = urllib2.urlopen(request)
        logging.info( handler.read() )
        if handler.getcode() == 200:    
            sys.exit(0)
        else:
            sys.exit(1)

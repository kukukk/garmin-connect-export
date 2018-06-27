#!/usr/bin/python
# -*- coding: utf-8 -*-

"""
File:               gcexport.py
Original Author:    Kyle Krafka (https://github.com/kjkjava/)
Date:               April 28, 2015
Description:        This script will export fitness data from Garmin Connect
                    See README.md for more detailed information
"""

from urllib import urlencode
from datetime import datetime
from getpass import getpass
from sys import argv
from os.path import isdir
from os.path import isfile
from os import mkdir

import urllib
import urllib2
import cookielib
import json
import re

import argparse

script_version = '1.0.0'
current_date = datetime.now().strftime('%Y-%m-%d')
activities_directory = './' + current_date + '_garmin_connect_export'

parser = argparse.ArgumentParser()

parser.add_argument('--version', help="print version and exit", action="store_true")
parser.add_argument('--username', help="your Garmin Connect username (otherwise, you will be prompted)", nargs='?')
parser.add_argument('--password', help="your Garmin Connect password (otherwise, you will be prompted)", nargs='?')

parser.add_argument('-d', '--directory', nargs='?', default=activities_directory,
                    help="the directory to export to (default: './YYYY-MM-DD_garmin_connect_export')")

args = parser.parse_args()

if args.version:
    print argv[0] + ", version " + script_version
    exit(0)

cookie_jar = cookielib.CookieJar()
opener = urllib2.build_opener(urllib2.HTTPCookieProcessor(cookie_jar))


# print cookie_jar

# url is a string, post is a dictionary of POST parameters, headers is a dictionary of headers.
def http_req(url, post=None, headers=None):
    request = urllib2.Request(url)
    # Tell Garmin we're some supported browser.
    browser = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/54.0.2816.0 Safari/537.36'
    request.add_header('User-Agent', browser)
    if headers:
        for header_key, header_value in headers.iteritems():
            request.add_header(header_key, header_value)
    if post:
        # print "POSTING"
        post = urlencode(post)  # Convert dictionary to POST parameter string.
    # print request.headers
    # print cookie_jar
    # print post
    # print request
    response = opener.open(request, data=post)  # This line may throw a urllib2.HTTPError.

    # N.B. urllib2 will follow any 302 redirects.
    # Also, the "open" call above may throw a urllib2.HTTPError which is checked for below.
    # print response.getcode()
    if response.getcode() == 204:
        # For activities without GPS coordinates, there is no GPX download (204 = no content).
        # Write an empty file to prevent re-downloading it.
        print 'Writing empty file since there was no GPX activity data...'
        return ''
    elif response.getcode() != 200:
        raise Exception('Bad return code (' + str(response.getcode()) + ') for: ' + url)

    return response.read()


print 'Welcome to Garmin Connect Exporter!'

# Create directory for data files.
if isdir(args.directory):
    print 'Warning: Output directory already exists. Will skip already-downloaded files and append to the CSV file.'

username = args.username if args.username else raw_input('Username: ')
password = args.password if args.password else getpass()

# Maximum number of activities you can request at once.
# Used to be 100 and enforced by Garmin for older endpoints; for the current endpoint 'url_gc_search'
# the limit is not known (I have less than 1000 activities and could get them all in one go)
limit_maximum = 1000

max_tries = 3

WEBHOST = "https://connect.garmin.com"
REDIRECT = "https://connect.garmin.com/post-auth/login"
BASE_URL = "http://connect.garmin.com/en-US/signin"
GAUTH = "http://connect.garmin.com/gauth/hostname"
SSO = "https://sso.garmin.com/sso"
CSS = "https://static.garmincdn.com/com.garmin.connect/ui/css/gauth-custom-v1.2-min.css"

data = {'service': REDIRECT,
        'webhost': WEBHOST,
        'source': BASE_URL,
        'redirectAfterAccountLoginUrl': REDIRECT,
        'redirectAfterAccountCreationUrl': REDIRECT,
        'gauthHost': SSO,
        'locale': 'en_US',
        'id': 'gauth-widget',
        'cssUrl': CSS,
        'clientId': 'GarminConnect',
        'rememberMeShown': 'true',
        'rememberMeChecked': 'false',
        'createAccountShown': 'true',
        'openCreateAccount': 'false',
        'usernameShown': 'false',
        'displayNameShown': 'false',
        'consumeServiceTicket': 'false',
        'initialFocus': 'true',
        'embedWidget': 'false',
        'generateExtraServiceTicket': 'false'}

print urllib.urlencode(data)

# URLs for various services.
url_gc_login = 'https://sso.garmin.com/sso/login?' + urllib.urlencode(data)
url_gc_post_auth = 'https://connect.garmin.com/modern/activities?'
url_gc_summary = 'https://connect.garmin.com/proxy/activity-search-service-1.2/json/activities?start=0&limit=1'
url_gc_search = 'https://connect.garmin.com/modern/proxy/activitylist-service/activities/search/activities?'
url_gc_activity = 'https://connect.garmin.com/modern/proxy/activity-service/activity/'
url_gc_original_activity = 'http://connect.garmin.com/proxy/download-service/files/activity/'

# Initially, we need to get a valid session cookie, so we pull the login page.
print 'Request login page'
http_req(url_gc_login)
print 'Finish login page'

# Now we'll actually login.
post_data = {'username': username, 'password': password, 'embed': 'true', 'lt': 'e1s1', '_eventId': 'submit',
             'displayNameRequired': 'false'}  # Fields that are passed in a typical Garmin login.
print 'Post login data'
login_response = http_req(url_gc_login, post_data)
print 'Finish login post'

# extract the ticket from the login response
pattern = re.compile(r".*\?ticket=([-\w]+)\";.*", re.MULTILINE | re.DOTALL)
match = pattern.match(login_response)
if not match:
    raise Exception(
        'Did not get a ticket in the login response. Cannot log in. Did you enter the correct username and password?')
login_ticket = match.group(1)
print 'login ticket=' + login_ticket

print 'Request authentication'
# print url_gc_post_auth + 'ticket=' + login_ticket
http_req(url_gc_post_auth + 'ticket=' + login_ticket)
print 'Finished authentication'

# We should be logged in now.
if not isdir(args.directory):
    mkdir(args.directory)

# If the user wants to download all activities, first download one,
# then the result of that request will tell us how many are available
# so we will modify the variables then.
print "Making result summary request ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"
print url_gc_summary
result = http_req(url_gc_summary)
print "Finished result summary request ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"

# Modify total_to_download based on how many activities the server reports.
json_results = json.loads(result)
total_to_download = int(json_results['results']['totalFound'])

total_downloaded = 0

# This while loop will download data from the server in multiple chunks, if necessary.
while total_downloaded < total_to_download:
    # Maximum chunk size 'limit_maximum' ... 400 return status if over maximum.
    # So download maximum or whatever remains if less than maximum.
    # As of 2018-03-06 I get return status 500 if over maximum
    if total_to_download - total_downloaded > limit_maximum:
        num_to_download = limit_maximum
    else:
        num_to_download = total_to_download - total_downloaded

    search_params = {'start': total_downloaded, 'limit': num_to_download}
    # Query Garmin Connect
    print "Making activity request ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"
    print url_gc_search + urlencode(search_params)
    result = http_req(url_gc_search + urlencode(search_params))
    print "Finished activity request ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"

    json_results = json.loads(result)

    # search = json_results['results']['search']

    # Pull out just the list of activities.
    activities = json_results

    # Process each activity.
    for a in activities:
        # Display which entry we're working on.
        print 'Garmin Connect activity: [' + str(a['activityId']) + ']',
        print a['activityName']

        # Retrieve also the detail data from the activity (the one displayed on
        # the https://connect.garmin.com/modern/activity/xxx page), because some
        # data are missing from 'a' (or are even different, e.g. for my activities
        # 86497297 or 86516281)
        activity_details = None
        details = None
        tries = max_tries
        while tries > 0:
            activity_details = http_req(url_gc_activity + str(a['activityId']))
            details = json.loads(activity_details)
            # I observed a failure to get a complete JSON detail in about 5-10 calls out of 1000
            # retrying then statistically gets a better JSON ;-)
            if len(details['summaryDTO']) > 0:
                tries = 0
            else:
                print 'retrying for ' + str(a['activityId'])
                tries -= 1
                if tries == 0:
                    raise Exception(
                        'Did not get "summaryDTO" after ' + str(max_tries) + ' tries for ' + str(a['activityId']))

        data_directory = args.directory + '/' + a['activityType']['typeKey'].replace("/", " - ")
        if not isdir(data_directory):
            mkdir(data_directory)
        data_filename = data_directory + '/activity_' + str(a['activityId']) + '.zip'
        download_url = url_gc_original_activity + str(a['activityId'])
        file_mode = 'wb'

        if isfile(data_filename):
            print '\tData file already exists; skipping...'
            continue

        # Download the data file from Garmin Connect.
        # If the download fails (e.g., due to timeout), this script will die, but nothing
        # will have been written to disk about this activity, so just running it again
        # should pick up where it left off.
        print '\tDownloading file...',

        try:
            data = http_req(download_url)
        except urllib2.HTTPError as e:
            # Handle expected (though unfortunate) error codes; die on unexpected ones.
            if e.code == 404:
                # For manual activities (i.e., entered in online without a file upload), there is no original file.
                # Write an empty file to prevent re-downloading it.
                print 'Writing empty file since there was no original activity data...',
                data = ''
            else:
                raise Exception('Failed. Got an unexpected HTTP error (' + str(e.code) + download_url + ').')

        save_file = open(data_filename, file_mode)
        save_file.write(data)
        save_file.close()

        print 'Done.'
    total_downloaded += num_to_download
# End while loop for multiple chunks.


print 'Done!'

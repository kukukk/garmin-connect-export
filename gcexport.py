#!/usr/bin/python
# -*- coding: utf-8 -*-

from urllib import urlencode
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

script_version = '2020-06-20'

parser = argparse.ArgumentParser()
parser.add_argument('--version', help='print version and exit', action='store_true')
parser.add_argument('--username', help='your Garmin Connect username (otherwise, you will be prompted)', nargs='?')
parser.add_argument('--password', help='your Garmin Connect password (otherwise, you will be prompted)', nargs='?')
parser.add_argument('--directory', help='the directory to export to (otherwise, you will be prompted)', nargs='?')
args = parser.parse_args()

if args.version:
    print(argv[0] + ', version ' + script_version)
    exit(0)

cookie_jar = cookielib.CookieJar()
opener = urllib2.build_opener(urllib2.HTTPCookieProcessor(cookie_jar))


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
        post = urlencode(post)  # Convert dictionary to POST parameter string.
    response = opener.open(request, data=post)  # This line may throw a urllib2.HTTPError.

    # N.B. urllib2 will follow any 302 redirects.
    if response.getcode() != 200:
        raise Exception('Bad return code (' + str(response.getcode()) + ') for: ' + url)

    return response.read()


print('Welcome to Garmin Connect Exporter!')

directory = args.directory if args.directory else raw_input('Directory: ')
username = args.username if args.username else raw_input('Username: ')
password = args.password if args.password else getpass()

# Check directory for data files
if isdir(directory):
    print 'Warning: Output directory already exists. Will skip already-downloaded files.'
else:
    mkdir(directory)

# Maximum number of activities you can request at once.  Set and enforced by Garmin.
limit_maximum = 1000
# Maximum number or retries
max_tries = 3

webhost = 'https://connect.garmin.com'
redirect = 'https://connect.garmin.com/modern/'
base_url = 'https://connect.garmin.com/en-US/signin'
sso = 'https://sso.garmin.com/sso'
css = 'https://static.garmincdn.com/com.garmin.connect/ui/css/gauth-custom-v1.2-min.css'
login_data = {
    'service': redirect,
    'webhost': webhost,
    'source': base_url,
    'redirectAfterAccountLoginUrl': redirect,
    'redirectAfterAccountCreationUrl': redirect,
    'gauthHost': sso,
    'locale': 'en_US',
    'id': 'gauth-widget',
    'cssUrl': css,
    'clientId': 'GarminConnect',
    'rememberMeShown': 'true',
    'rememberMeChecked': 'false',
    'createAccountShown': 'true',
    'openCreateAccount': 'false',
    'displayNameShown': 'false',
    'consumeServiceTicket': 'false',
    'initialFocus': 'true',
    'embedWidget': 'false',
    'generateExtraServiceTicket': 'true',
    'generateTwoExtraServiceTickets': 'false',
    'generateNoServiceTicket': 'false',
    'globalOptInShown': 'true',
    'globalOptInChecked': 'false',
    'mobile': 'false',
    'connectLegalTerms': 'true',
    'locationPromptShown': 'true',
    'showPassword': 'true',
}

# URLs for various services.
url_gc_login = 'https://sso.garmin.com/sso/signin?' + urllib.urlencode(login_data)
url_gc_post_auth = 'https://connect.garmin.com/modern/activities?'
url_gc_profile = 'https://connect.garmin.com/modern/profile'
url_gc_userstats = 'https://connect.garmin.com/modern/proxy/userstats-service/statistics/'
url_gc_list = 'https://connect.garmin.com/modern/proxy/activitylist-service/activities/search/activities?'
url_gc_activity = 'https://connect.garmin.com/modern/proxy/activity-service/activity/'
url_gc_original_activity = 'http://connect.garmin.com/proxy/download-service/files/activity/'

# Initially, we need to get a valid session cookie, so we pull the login page.
print('Request login page')
http_req(url_gc_login)

# Now we'll actually login.
post_data = {
    "username": username,
    "password": password,
    "embed": "false",
    "rememberme": "on",
}
post_headers = {"referer": url_gc_login}

print('Post login data')
LOGIN_RESPONSE = http_req(url_gc_login + '#', post_data, post_headers).decode()
# Extract the ticket from the login response.
pattern = re.compile(r".*\?ticket=([-\w]+)\";.*", re.MULTILINE | re.DOTALL)
match = pattern.match(LOGIN_RESPONSE)
if not match:
    raise Exception('Did not get a ticket in the login response. Cannot log in. Did you enter the correct username and password?')
login_ticket = match.group(1)

print('Request authentication URL: ' + url_gc_post_auth + 'ticket=' + login_ticket)
http_req(url_gc_post_auth + "ticket=" + login_ticket)

# To download all activities, query the userstats on the profile page to know how many are available
print('Getting display name via: ' + url_gc_profile)
profile_page = http_req(url_gc_profile).decode()
# Extract the display name from the profile page, it should be in there as \"displayName\":\"eschep\"
pattern = re.compile(r".*\\\"displayName\\\":\\\"([-\w]+)\\\".*", re.MULTILINE | re.DOTALL)
match = pattern.match(profile_page)
if not match:
    raise Exception('Did not find the display name in the profile page.')
display_name = match.group(1)

print('Getting user stats via: ' + url_gc_userstats + display_name)
result = http_req(url_gc_userstats + display_name)

# Extract total activities count
json_results = json.loads(result)
total_to_download = int(json_results['userMetrics'][0]['totalActivities'])

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
    print('Activity list URL: ' + url_gc_list + urlencode(search_params))
    activity_list = http_req(url_gc_list + urlencode(search_params))

    # Pull out just the list of activities.
    activities = json.loads(activity_list)

    # Process each activity.
    for a in activities:
        # Display which entry we're working on.
        print('Garmin Connect activity: [' + str(a['activityId']) + ']' + ' ' + a['activityName'])

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
                print('Retrying for ' + str(a['activityId']))
                tries -= 1
                if tries == 0:
                    raise Exception('Did not get "summaryDTO" after ' + str(max_tries) + ' tries for ' + str(a['activityId']))

        data_directory = directory + '/' + a['activityType']['typeKey'].replace("/", " - ")
        if not isdir(data_directory):
            mkdir(data_directory)
        data_filename = data_directory + '/activity_' + str(a['activityId']) + '.zip'
        download_url = url_gc_original_activity + str(a['activityId'])
        file_mode = 'wb'

        if isfile(data_filename):
            print('\tData file already exists; skipping...')
            continue

        # Download the data file from Garmin Connect.
        # If the download fails (e.g., due to timeout), this script will die, but nothing
        # will have been written to disk about this activity, so just running it again
        # should pick up where it left off.
        print('\tDownloading file...'),
        try:
            data = http_req(download_url)
        except urllib2.HTTPError as e:
            # Handle expected (though unfortunate) error codes; die on unexpected ones.
            if e.code == 404:
                # For manual activities (i.e., entered in online without a file upload), there is no original file.
                # Write an empty file to prevent re-downloading it.
                print('\tWriting empty file since there was no original activity data...')
                data = ''
            else:
                raise Exception('Failed. Got an unexpected HTTP error (' + str(e.code) + download_url + ').')

        save_file = open(data_filename, file_mode)
        save_file.write(data)
        save_file.close()

        print('Done.')
    total_downloaded += num_to_download


print('Finished!')

# Ignore code verification added on 2020-03-18 by: Seraphin
# Reason: legacy file, too much work to make it compliant
# flake8: noqa
import json

import aa_flask_cache
import aa_globals
import aa_loggers
import aa_users
import requests
import ujson
from flask import session
from settings.settings import *

########### Settings import for different environments ##########
if isProduction():
    from settings.settings_prod import *
elif isStaging():
    from settings.settings_staging import *
elif isStagingNew():
    from settings.settings_staging_static import *
else:
    isDevelopment()
    from settings.settings_dev import *

log = aa_loggers.logging.getLogger(__name__)
###################################################################


cache = aa_flask_cache.getCacheObject()

CACHE_API_SLACK_TIMEOUT = 300

CACHE_AUTH_SLACK_TIMEOUT = 10

import aa_helper_methods


######################################################################
######################  PUBLIC METHODS  ##############################
######################################################################
class ApiSlack():

    @cache.memoize(timeout=CACHE_API_SLACK_TIMEOUT)
    def APIgetAllEmailsForLabelIdAndDatesAndFilter(self, user_id: int, organization_id: int, date_first):
        ''' LabelID = Slack Channel
        date_first is included , can be either datetime or str Instance
        date_last is included - so we always add 1 day / use end of day for time filtering - , can be either datetime
        or str Instance
        in SLACK's case, this means adding 3600*24 to timestamp calculation
        '''

        messages, contacts = [], []

        date_first = aa_helper_methods.anteater_giveMeAStringForADate(date_first)

        try:
            conversations_all = self.APIgetAllEmailsWithLabelAndDatesAndTeam(date_first=date_first)

            # remove messages from AntEater bot from analysis and results - otherwise we report on our own activity
            # which biases results)
            conversations = _filterSlackConversationsRemoveAntEaterMessages(conversations_all)

            # parse interactions
            for message in conversations:
                try:
                    aa_api_data.parse_and_store_insights_from_message(message=message,
                                                                      organization_id=organization_id,
                                                                      user_id=user_id)

                except Exception as e:
                    log.error(e, exc_info=True)


        except Exception as e:
            log.error(e, exc_info=True)

        return messages


    @cache.memoize(timeout=CACHE_API_SLACK_TIMEOUT)  # DO NOT CHECK ME IN -  DEBUG
    def APIgetAllEmailsWithLabelAndDatesAndTeam(self, date_first):
        ''' date_first, date_last are either instances of str or datetime.datetime'''
        ''' with date filter'''

        conversations = []  # = emails

        list_channels = self.APIgetLabels()
        for channel in list_channels:
            try:
                slack_channel_msgs = _getChannelMessagesDictionaryFromSlackAPIWithDates(channel.get('id'),
                                                                                        date_first)
                for message in slack_channel_msgs:
                    conversations.append(aa_api_data.parse_message_from_slack(message=message,
                                                                              channel_name=channel.get('name')))

            except Exception as e:
                log.error(e, exc_info=True)

        log.info(f"SLACK API - retrieved {len(conversations)} conversations from {len(list_channels)} channels")

        # cleanup None conversations (Sep 2019 - sometimes conversations are None objects)
        res = list(filter(None, conversations))

        return res

    def APIgetLabels(self):
        ''' returns slack channels (non archived) in AntEater format'''
        API_Channels = get_channels()
        result = []
        if API_Channels:
            for channel in API_Channels:
                if channel.get('is_archived') is False:  # ignore archived channels
                    new_result = {}
                    new_result['id'] = channel.get('id')
                    new_result['slack_id'] = channel.get('id')
                    new_result['name'] = '#' + channel.get('name')
                    new_result['messagesTotal'] = '/'
                    result.append(new_result)
                else:
                    log.info('Slack list ignore archived channel - ', channel.get('name'))

        return result

    def get_user_id(self):
        user_id = None

        token = loadSlackOauthTokenForCurrentUser()
        if token:
            payload = {"token": token.access_token}
            user = requests.get("https://slack.com/api/auth.test", params=payload).json()

            if user.get('ok'):
                user_id = user.get('user_id')

        return user_id


def _getTeamNameDomainEmailFromSlackAPI():
    ''' returns  from Slack with info about the team'''
    res = []

    slack_oauth_token = loadSlackOauthTokenForCurrentUser()  # hack Nov 2018  because it doesn't seem like
    # Flask-Dance is loading the correct token
    if slack_oauth_token:
        payload = {'types': 'public_channel',
                   "token": slack_oauth_token.access_token}
        response = requests.get("https://slack.com/api/team.info", params=payload).json()
        if response.get('ok') == True:
            if 'team' in response:
                name = response['team'].get('name')
                domain = response['team'].get('domain')
                email_domain = response['team'].get('email_domain')
                return name, domain, email_domain

    return None, None, None


def _filterSlackConversationsForTopic(filter_topic, conversations_all):
    """
    date_first is included
    date_last is included - so we always add 1 day / use end of day for time filtering
    This is where we add 3600*24 seconds to take into account today's messages
    """

    if filter_topic and len(filter_topic) > 0:
        conversations = []
        for conversation in conversations_all:  # filter on date
            if filter_topic in conversation.get('Snippet'):
                conversations.append(conversation)
        print("SLACK API - filtering ", len(conversations), " conversations on topic")
        return conversations

    else:
        return conversations_all  # don't filter


def _filterSlackConversationsRemoveAntEaterMessages(conversations_all):
    """
    date_first is included
    date_last is included - so we always add 1 day / use end of day for time filtering
    This is where we add 3600*24 seconds to take into account today's messages
    """

    conversations = [conversation for conversation in conversations_all
                     if conversation.sender[0].name not in ['@AnteaterDev', '@Anteater']]

    return conversations


def _DEPRECATED_filterSlackConversationsBetweenDateFirstAndDateLast(date_first, date_last, conversations_all):
    """
    DEPRECATED - NOW DOING THIS ON THE API SIDE
    date_first is included
    date_last is included - so we always add 1 day / use end of day for time filtering
    This is where we add 3600*24 seconds to take into account today's messages
    """
    # convert date_first and last to timestamp From
    # https://stackoverflow.com/questions/8777753/converting-datetime-date-to-utc-timestamp-in-python
    import time
    input_date_first = aa_helper_methods.build_tz_aware_datetime(date_first)
    input_date_last = aa_helper_methods.build_tz_aware_datetime(date_last)
    timestamp_date_first = time.mktime(input_date_first.timetuple()) - (3600 * 24)  # remove a full day - date_first is
    # today, we want end of day time
    timestamp_date_last = time.mktime(input_date_last.timetuple()) + (
            3600 * 24)  # add a full day - date_last is today,
    # we want end of day time

    conversations = []
    for conversation in conversations_all:  # filter on date
        try:
            if conversation.get('timestamp') > timestamp_date_first and conversation.get(
                    'timestamp') < timestamp_date_last:
                conversations.append(conversation)
        except Exception as e:
            print(
                "SLACK Exception - _DEPRECATED_filterSlackConversationsBetweenDateFirstAndDateLast() - invalid "
                "conversation",
                e)

    print("SLACK API - filtering ", len(conversations), " conversations on date")
    return conversations


def get_channels():
    ''' returns list of dicts from Slack with list of channels'''
    result = []

    slack_oauth_token = loadSlackOauthTokenForCurrentUser()  # hack Nov 2018  because it doesn't seem like
    # Flask-Dance is loading the correct token

    if slack_oauth_token:
        payload = {'types': 'public_channel',
                   "token": slack_oauth_token.access_token}
        response = requests.get("https://slack.com/api/conversations.list", params=payload)
        content = {}
        if response.status_code==200:
            content = response.json()
        if content.get('ok') == True:
            for channel in content.get('channels'):
                result.append(channel)

        else:
            log.warning(f"{content}")

    return result


@cache.memoize(timeout=CACHE_AUTH_SLACK_TIMEOUT)
def _getSlackUserTimeZoneOffsetForUserId(slack_user_id):
    ''' reutrns int value tz offset from Slack User info query'''
    tz_offset = None
    user_info = _getSlackUserInfoForUserId(slack_user_id)
    if user_info:
        id, display_name, real_name, email, pic, is_bot, user_info_dic = user_info
        if user_info_dic:
            tz_offset = user_info_dic.get('tz_offset')

    return tz_offset


@cache.memoize(timeout=CACHE_AUTH_SLACK_TIMEOUT)
def _getSlackUserTimeZoneForUserId(slack_user_id):
    ''' reutrns int value tz offset from Slack User info query'''
    timezone = None
    user_info = _getSlackUserInfoForUserId(slack_user_id)
    if user_info:
        id, display_name, real_name, email, pic, is_bot, user_info_dic = user_info
        if user_info_dic:
            timezone = user_info_dic.get('tz')

    return timezone


@cache.memoize(timeout=CACHE_AUTH_SLACK_TIMEOUT)
def _getSlackUserInfoForUserId(slack_user_id):
    if slack_user_id:
        id, display_name, real_name, email, pic, is_bot, user_info_dic = None, None, None, None, None, False, None

        token = loadSlackOauthTokenForCurrentUser()
        params = {"token": token.access_token,
                "user": slack_user_id}
        response = requests.get(url='https://slack.com/api/users.info', params=params)
        data = None
        if response.status_code == 200:
            data = response.json()

        if data and data.get('ok'):
            user = data.get('user')
            if user.get('id') == slack_user_id:
                id = user.get('id')
                display_name = user.get('profile').get('display_name')
                real_name = user.get('profile').get('real_name')
                email = user.get('profile').get('email')
                pic = user.get('profile').get('image_192')
                is_bot = user.get('is_bot')
                user_info_dic = user
                res = id, display_name, real_name, email, pic, is_bot, user_info_dic
                return res
        else:
            log.warning('Could not get user info')
            user=None
            response = requests.get(url='https://slack.com/api/auth.test', params=data)
            if response.status_code == 200:
                user = response.json()
            if user and user.get('ok'):
                id = user.get('user_id')

        aa_globals.setUserCacheValueForKey('slack_user_id', id)

        return id, display_name, real_name, email, pic, is_bot, user_info_dic  ## None

    return None


@cache.memoize(timeout=CACHE_AUTH_SLACK_TIMEOUT)
def _getSlackUserIdForUserName(slack_user_name):
    ''' returns e.g. @U024BE7LH for @alex '''
    ## remove leading @
    if slack_user_name.startswith('@'):
        slack_user_name = slack_user_name[1:]

    slack_user_name = slack_user_name.replace(' ', '')

    id = None
    dict_users = _getUsersDictDictionaryFromSlackAPICached()

    for key, user in dict_users.items():
        if user.get('profile').get('real_name').replace(' ', '') == slack_user_name:
            id = user.get('id')
            break
        if user.get('profile').get('display_name').replace(' ', '') == slack_user_name:
            id = user.get('id')
            break

    return id


@cache.memoize(timeout=CACHE_AUTH_SLACK_TIMEOUT)
def _getSlackUserInfoForUserName(slack_user_name):
    ''' slack_user_name '''
    ''' returns id, name, real_name, email, pic, is_bot'''
    ''' lookup user id and use standard method above'''
    ''' accepts both real Slack username and prepended with @ '''
    ''' e.g. @Alexandre_Ackermans or Alexandre_Ackermans'''

    id = _getSlackUserIdForUserName(slack_user_name)

    return _getSlackUserInfoForUserId(id)


def _getUsersDictDictionaryFromSlackAPICached():
    ''' return a dict for fast user lookup '''

    res = None

    if not res or len(res) == 0:
        res = {}
        lst = _getUsersListDictionaryFromSlackAPICached()
        for user in lst:
            res[user.get('id')] = user

    return res


def _getUsersListDictionaryFromSlackAPICached():
    slack_oauth_token = loadSlackOauthTokenForCurrentUser()
    return _getUsersListDictionaryFromSlackAPICachedWithToken(slack_oauth_token)


@cache.memoize(timeout=CACHE_AUTH_SLACK_TIMEOUT)
def _getUsersListDictionaryFromSlackAPICachedWithToken(slack_oauth_token):
    ''' returns a list of dict from Slack API with users'''
    ''' Always Hits SlackAPI '''

    res = None

    if not res or len(res) == 0:
        res = []

        # hack Nov 2018  because it doesn't seem like Flask-Dance is loading the correct token
        if slack_oauth_token:
            payload = {
                "token": slack_oauth_token.access_token,
                'types': 'public_channel'}  # http://docs.python-requests.org/en/master/user/quickstart/
            resp = requests.get("https://slack.com/api/users.list", params=payload)
            content = ujson.loads(resp.content)
            if content.get('ok') == True:
                for user in content.get('members'):
                    res.append(user)
    return res


import aa_api_data


@cache.memoize(timeout=CACHE_API_SLACK_TIMEOUT)
def _getChannelMessagesDictionaryFromSlackAPIWithDates(channel_id, date_first=None):
    ''' date_first, date_last are either instances of str or datetime.datetime'''
    ''' returns list of dict from Slack with messages for channel [ID]'''

    slack_oauth_token = loadSlackOauthTokenForCurrentUser()

    if slack_oauth_token:
        payload = {'channel': channel_id,
                   "token": slack_oauth_token.access_token,
                   'count': 1000}

        if not (isinstance(date_first, str) and date_first.lower() == 'all'):
            payload['oldest'] = aa_helper_methods.build_tz_aware_datetime(date_first).timestamp()

        resp = requests.get("https://slack.com/api/conversations.history", params=payload)
        content = {}
        if resp.status_code == 200:
            content = resp.json()
        if content.get('error') == 'not_in_channel':
            requests.post("https://slack.com/api/conversations.join", params=payload)
            resp = requests.get("https://slack.com/api/conversations.history", params=payload)
            content = resp.json()
        if content.get('ok') == True:
            res = []
            for msg in content.get('messages'):
                res.append(msg)

            print('SLACK _getChannelMessagesDictionaryFromSlackAPIWithDates for channel_id', channel_id, ' - ',
                  str(len(res)), 'msgs')
            return res

    print('SLACK _getChannelMessagesDictionaryFromSlackAPIWithDates for channel_id', channel_id, ' - None')
    return None


#####################################################################
##############  SLACK AUTH METHODS  #############
#####################################################################

from aa_sqlalchemy import db, OAuth
from requests_oauthlib import OAuth2Session


def deleteSlackOauthTokenForCurrentUserFromDb():
    ''' hack Nov 2018  because it doesn't seem like Flask-Dance is loading the correct token
    so we delete the saved token from db
    '''
    result = db.session.query(OAuth).filter(OAuth.user_id == aa_users.get_current_user_id(),
                                            OAuth.provider == 'slack').delete()

    db.session.commit()

    return result


def loadSlackOauthTokenForCurrentUser():
    ''' hack Nov 2018  because it doesn't seem like Flask-Dance is loading the correct token
    so we load the saved token from db, and adjust parameters to use this new object
    '''
    slack_oauth_token_from_db = loadSlackOauthTokenForCurrentUserFromDb()  # hack Nov 2018  because it doesn't seem
    # like Flask-Dance is loading the correct token
    # if slack_oauth_token_from_db:
    #     slack_request_oauth = slack._get_current_object() #get object behind proxy - see
    #     #https://github.com/maxcountryman/flask-login/issues/9
    #
    #     slack_oauth_token_from_db.base_url = slack_request_oauth.base_url
    #     slack_oauth_token_from_db.blueprint = slack_request_oauth.blueprint
    #     slack_oauth_token_from_db.scope = slack_request_oauth.scope
    return slack_oauth_token_from_db
    # else:
    #     return None


def loadSlackOauthTokenForCurrentUserFromDb():
    ''' hack Nov 2018  because it doesn't seem like Flask-Dance is loading the correct token
    so we load the saved token from db, create a new Oauth2Session, and returns it so we can get the access_token
    from this new object
    '''
    slack_user_id = session.get('flask_user_id_inbound')
    if slack_user_id:
        print('SLACK - unauthenticated mode - impersonate user... ', end='', flush=True)

        slack_oauth_token = loadSlackOauthTokenForUserFromDb(slack_user_id=slack_user_id)
        if slack_oauth_token:
            print(' ** SUCCESFUL ** ', end='', flush=True)
        else:
            print('ERROR - SLACK - unauthenticated mode - could not find db token')
    else:
        slack_oauth_token = loadSlackOauthTokenForUserFromDb(anteater_user_id=aa_users.get_current_user_id())

    return slack_oauth_token


# @cache.memoize(timeout=CACHE_AUTH_SLACK_TIMEOUT) #TODO : improve this to allow caching while not giving an error
#  just after Slack login
def loadSlackOauthDbEntryForUserFromDb(slack_user_id=None, anteater_user_id=None):
    ''' slack_user_id = U7MJ089TQ'''
    ''' anteater_user_id = 13'''

    try:

        if slack_user_id:  # lookup the json content in db record to find the right token
            # see https://docs.sqlalchemy.org/en/latest/orm/extensions/indexable.html
            query1 = db.session.query(OAuth).filter(OAuth.provider == 'slack',
                                                    OAuth.slack_user_id == slack_user_id).order_by(
                OAuth.created_at.desc())
            oauth_db = query1.first()
            if oauth_db:
                return oauth_db

            if (not oauth_db):
                print('ERROR - SLACK - error loading SLACK db token')

        if anteater_user_id:
            oauth_db = db.session.query(OAuth).filter(OAuth.user_id == anteater_user_id,
                                                      OAuth.provider == 'slack').order_by(
                OAuth.created_at.desc()).first()
            if oauth_db:
                return oauth_db

    except Exception as e:
        print("SLACK ERROR - DB loadSlackOauthTokenForUserFromDb() -", e)

    return None


# cannot pickle
def loadSlackOauthTokenForUserFromDb(slack_user_id=None, anteater_user_id=None):
    oauth_session = None
    oauth_db = loadSlackOauthDbEntryForUserFromDb(slack_user_id, anteater_user_id)
    if oauth_db and oauth_db.custom_token:
        oauth_session = OAuth2Session(
            token=json.loads(oauth_db.custom_token),
            client_id=API_SLACK_CLIENT_ID,
        )

    return oauth_session


######################################################################
#######################  HELPER METHODS  ##############################
######################################################################

@cache.memoize(timeout=24 * 3600)
def _getSubsetListForEmailsList(msg_list):
    subset_list = []
    subset_list.append(msg_list)
    return subset_list

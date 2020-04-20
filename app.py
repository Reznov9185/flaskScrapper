# -*- coding: utf-8 -*-

import os
import flask
import requests
import time
import redis
import statistics

import google.oauth2.credentials
import google_auth_oauthlib.flow
import googleapiclient.discovery

from flask import request
from database import *
from models import *
from tasks import *
from sqlalchemy import join
from sqlalchemy.sql import select
from sqlalchemy import and_

# This variable specifies the name of a file that contains the OAuth 2.0
# information for this application, including its client_id and client_secret.
CLIENT_SECRETS_FILE = "client_secret.json"

# This OAuth 2.0 access scope allows for full read/write access to the
# authenticated user's account and requires requests to use an SSL connection.
SCOPES = ['https://www.googleapis.com/auth/youtube.force-ssl']
API_SERVICE_NAME = 'youtube'
API_VERSION = 'v3'

# When running locally, disable OAuthlib's HTTPs verification.
# ACTION ITEM for developers:
#     When running in production *do not* leave this option enabled.
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'
os.environ['OAUTHLIB_RELAX_TOKEN_SCOPE'] = '1'

app = flask.Flask(__name__)
# Note: A secret key is included in the sample so that it works.
# If you use this code in your application, replace this with a truly secret
# key. See https://flask.palletsprojects.com/quickstart/#sessions.
app.secret_key = 'REPLACE ME - this value is here as a placeholder.'

app.config.update(
    CELERY_BROKER_URL='redis://localhost:6379',
    CELERY_RESULT_BACKEND='redis://localhost:6379'
)
celery = make_celery(app)


#################################
# Celery Async Background Jobs
#################################


@celery.task()
def connect_youtube():
    init_db()
    try:
        credential = Cred.query.order_by(-Cred.id).first()
        credential = credential.serialize()
        if credential:
            # Load credentials from the database
            credentials = google.oauth2.credentials.Credentials(
                credential["token"],
                refresh_token=credential["refresh_token"],
                token_uri=credential["token_uri"],
                client_id=credential["client_id"],
                client_secret=credential["client_secret"],
                scopes=credential["scopes"]
            )

            youtube = googleapiclient.discovery.build(
                API_SERVICE_NAME, API_VERSION, credentials=credentials)

            return youtube
        else:
            return None
    except:
        return None


@celery.task()
def scrap_channel_videos(page_token=None):
    # For scraping and storing videos for the authorized channel
    with app.app_context():
        youtube = connect_youtube()
        if youtube is None:
            return None
        results = youtube.channels().list(mine=True, part='contentDetails').execute()
        # For a single channel now...
        uploads_playlist_id = \
            results['items'][0]['contentDetails']['relatedPlaylists']['uploads']
        results = youtube.playlistItems() \
            .list(playlistId=uploads_playlist_id, part='contentDetails',
                  pageToken=page_token) \
            .execute()
        videos = results['items']
        for video_item in videos:
            video_id = video_item['contentDetails']['videoId']
            already_stored = Video.query.filter(Video.youtube_id == video_id).all()
            if len(already_stored) == 0:
                # For storing video_id from youtube
                entry = Video(youtube_id=video_id)
                db_session.add(entry)
                db_session.commit()
        if 'nextPageToken' in results:
            scrap_channel_videos.delay(results['nextPageToken'])

        return 'Channel Video Ids are now fetched!'


@celery.task()
def scrap_video_data():
    # For scraping and storing video data like title, tags and stats
    init_db()
    with app.app_context():
        youtube = connect_youtube()
        if youtube is None:
            return None
        for video in Video.query.all():
            data = youtube.videos().list(id=video.youtube_id,
                                         part='statistics, snippet').execute()
            if 'items' in data:
                video_data = data['items']
                if len(video_data) > 0:
                    # Fetching Video Titles & ChannelId
                    if 'snippet' in video_data[0]:
                        video.title = video_data[0]['snippet']['title']
                        video.channel_id = video_data[0]['snippet']['channelId']
                        db_session.commit()
                        already_stored_tag = VideoTag.query.filter(
                            VideoTag.video_id == video.id
                        ).all()
                        if len(already_stored_tag) == 0:
                            if 'tags' in video_data[0]['snippet']:
                                tags = video_data[0]['snippet']['tags']
                                if len(tags) > 0:
                                    for tag in tags:
                                        tag_obj = VideoTag(tag_name=tag, video_id=video.id)
                                        db_session.add(tag_obj)
                                        db_session.commit()
                    if 'statistics' in video_data[0]:
                        stat_obj = Statistic(
                            video_id=video.id,
                            comment_count=video_data[0]['statistics']['commentCount'],
                            dislike_count=video_data[0]['statistics']['dislikeCount'],
                            favorite_count=video_data[0]['statistics']['favoriteCount'],
                            like_count=video_data[0]['statistics']['likeCount'],
                            view_count=video_data[0]['statistics']['viewCount'],
                        )
                        db_session.add(stat_obj)
                        db_session.commit()

        return 'Videos stats are now fetched!'


@celery.task(name="periodic_task")
def periodic_task():
    # This is the task which run per minute(as configured in tasks.py)
    # It will fetch the video statistics
    # Youtube APIv3 can't do it without Oauth2, which expires so can't be called like this!
    scrap_video_data.delay()
    print('Hi! from periodic_task')


#################################
# APP Command Routes
#################################


# Algorithm: If you can Authorize other clients via scrap_video_data(through connect_youtube),
# you can store multiple channels videos and run things with all those
@app.route('/fetch_videos')
def fetch_videos():
    try:
        result = scrap_channel_videos.delay()
        msg = result.wait()
        msg = 'Your channel videos are being fetched!'
    except:
        msg = 'Please go to the Authorize flow first!'

    data = {'message': msg,
            'next': flask.url_for('fetch_video_stats', _external=True)}
    return flask.jsonify(**data)


@app.route('/fetch_video_stats')
def fetch_video_stats():
    try:
        result = scrap_video_data.delay()
        msg = result.wait()
        msg = 'You videos data are being fetched!'
    except:
        msg = 'Please go to the Authorize flow first!'
    data = {'message': msg,
            'next': flask.url_for('videos_performances', _external=True)}
    return flask.jsonify(**data)


@app.route('/videos')
def channel_videos():
    if 'credentials' not in flask.session:
        return flask.redirect('authorize')

    # Load credentials from the session.
    credentials = google.oauth2.credentials.Credentials(
        **flask.session['credentials'])

    # Save credentials back to session in case access token was refreshed.
    # ACTION ITEM: In a production app, you likely want to save these
    #              credentials in a persistent database instead.
    flask.session['credentials'] = credentials_to_dict(credentials)

    youtube = googleapiclient.discovery.build(
        API_SERVICE_NAME, API_VERSION, credentials=credentials)

    results = youtube.channels().list(mine=True, part='contentDetails').execute()
    # For a single channel now...
    uploads_playlist_id = \
        results['items'][0]['contentDetails']['relatedPlaylists']['uploads']
    results = youtube.playlistItems() \
        .list(playlistId=uploads_playlist_id, part='contentDetails',
              pageToken=request.args.get('pageToken')) \
        .execute()

    return flask.jsonify(**results)


@app.route('/video_stats')
def video_stats():
    if 'credentials' not in flask.session:
        return flask.redirect('authorize')

    # Load credentials from the session.
    credentials = google.oauth2.credentials.Credentials(
        **flask.session['credentials'])

    # Save credentials back to session in case access token was refreshed.
    # ACTION ITEM: In a production app, you likely want to save these
    #              credentials in a persistent database instead.
    flask.session['credentials'] = credentials_to_dict(credentials)

    youtube = googleapiclient.discovery.build(
        API_SERVICE_NAME, API_VERSION, credentials=credentials)

    # results = youtube.channels().list(mine=True, part='contentDetails').execute()
    results = youtube.videos().list(id='V_NSCPPSTfs', part='statistics, snippet').execute()

    return flask.jsonify(**results)


#################################
# API Routes
#################################


@app.route('/api/v1/videos_performances')
def videos_performances():
    #############################
    # Expected: Video performance (first hour views divided by channels all videos first hour views median)
    # Issue: first hour views is from youtube report api(not API-V3), which has some other issues as well
    # Check: https://developers.google.com/youtube/reporting/v1/reports
    # Implement: How each video is doing compared to first entries(earliest stats on this platform)!
    #############################

    records = db_session.query(Video).join(Statistic, Video.id == Statistic.video_id).all()
    report = {}
    views_list = []
    for record in records:
        # Beginning Views
        first_views = record.statistics.order_by(Statistic.id).first()
        # Recent Views
        last_views = record.statistics.order_by(-Statistic.id).first()
        # New Views
        diff_views = last_views.view_count - first_views.view_count
        views_list.append(diff_views)
        report[str(record.title)] = {'current_views': str(last_views.view_count),
                                     'prev_views': str(first_views.view_count),
                                     'diff': str(diff_views)}
        # Updating last performance to the Video Model Object
        record.last_stat = float(diff_views)
        db_session.commit()

    return flask.jsonify(**report)


@app.route('/api/v1/videos')
def videos():
    report = {'items': []}
    # For sort 'by_performances'
    if request.args.get('sort') is not None:
        if request.args.get('sort') == 'by_performances':
            data = Video.query.order_by(Video.last_stat.desc()).all()
        else:
            data = Video.query.all()
    # For filter 'by_tags'
    elif request.args.get('filter') is not None:
        # Leaving the untagged ones behind
        # Joined with filter params
        data = db_session.query(Video) \
            .join(VideoTag,
                  and_(Video.id == VideoTag.video_id,
                       VideoTag.tag_name == request.args.get('filter'))) \
            .all()
    else:
        data = Video.query.all()
    if data is not None:
        for item in data:
            report['items'].append(
                item.as_dict()
            )
    return flask.jsonify(**report)


#################################
# Index and Auth + Test Routes
#################################

@app.route('/authorize')
def authorize():
    # Create flow instance to manage the OAuth 2.0 Authorization Grant Flow steps.
    flow = google_auth_oauthlib.flow.Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE, scopes=SCOPES)

    # The URI created here must exactly match one of the authorized redirect URIs
    # for the OAuth 2.0 client, which you configured in the API Console. If this
    # value doesn't match an authorized URI, you will get a 'redirect_uri_mismatch'
    # error.
    flow.redirect_uri = flask.url_for('oauth2callback', _external=True)

    authorization_url, state = flow.authorization_url(
        # Enable offline access so that you can refresh an access token without
        # re-prompting the user for permission. Recommended for web server apps.
        access_type='offline',
        # Enable incremental authorization. Recommended as a best practice.
        include_granted_scopes='true')

    # Store the state so the callback can verify the auth server response.
    flask.session['state'] = state

    return flask.redirect(authorization_url)


@app.route('/oauth2callback')
def oauth2callback():
    # Specify the state when creating the flow in the callback so that it can
    # verified in the authorization server response.
    state = flask.session['state']

    flow = google_auth_oauthlib.flow.Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE, scopes=SCOPES, state=state)
    flow.redirect_uri = flask.url_for('oauth2callback', _external=True)

    # Use the authorization server's response to fetch the OAuth 2.0 tokens.
    authorization_response = flask.request.url
    flow.fetch_token(authorization_response=authorization_response)

    # Store credentials in the session.
    # ACTION ITEM: In a production app, you likely want to save these
    #              credentials in a persistent database instead.
    credentials = flow.credentials
    flask.session['credentials'] = credentials_to_dict(credentials)
    save_credentials_to_db(credentials)

    return flask.redirect(flask.url_for('fetch_videos'))


@app.route('/revoke')
def revoke():
    if 'credentials' not in flask.session:
        return ('You need to <a href="/authorize">authorize</a> before ' +
                'testing the code to revoke credentials.')

    credentials = google.oauth2.credentials.Credentials(
        **flask.session['credentials'])

    revoke = requests.post('https://oauth2.googleapis.com/revoke',
                           params={'token': credentials.token},
                           headers={'content-type': 'application/x-www-form-urlencoded'})

    status_code = getattr(revoke, 'status_code')
    if status_code == 200:
        return ('Credentials successfully revoked.' + print_index_table())
    else:
        return ('An error occurred.' + print_index_table())


@app.route('/clear')
def clear_credentials():
    if 'credentials' in flask.session:
        del flask.session['credentials']
    return ('Credentials have been cleared.<br><br>' +
            print_index_table())


@app.route('/test')
def test_api_request():
    if 'credentials' not in flask.session:
        return flask.redirect('authorize')

    # Load credentials from the session.
    credentials = google.oauth2.credentials.Credentials(
        **flask.session['credentials'])

    youtube = googleapiclient.discovery.build(
        API_SERVICE_NAME, API_VERSION, credentials=credentials)

    channel = youtube.channels().list(mine=True, part='snippet').execute()

    # Save credentials back to session in case access token was refreshed.
    # ACTION ITEM: In a production app, you likely want to save these
    #              credentials in a persistent database instead.
    flask.session['credentials'] = credentials_to_dict(credentials)

    return flask.jsonify(**flask.session['credentials'])


def credentials_to_dict(credentials):
    return {'token': credentials.token,
            'refresh_token': credentials.refresh_token,
            'token_uri': credentials.token_uri,
            'client_id': credentials.client_id,
            'client_secret': credentials.client_secret,
            'scopes': credentials.scopes}


def save_credentials_to_db(credentials):
    init_db()
    entry = Cred(
        credentials.token,
        credentials.refresh_token,
        credentials.token_uri,
        credentials.client_id,
        credentials.client_secret,
        credentials.scopes
    )
    db_session.add(entry)
    db_session.commit()


def print_index_table():
    return ('<h2 style="text-align: center; color: grey">YouTube API-V3 Scrapper</h2>' +
            '<h3>APP: </h3>' +
            '<table>' +
            '<tr><td><b>Step 1. </b><a href="/authorize">Please Authorize with Oauth2.0</a></td>' +
            '<td>Go directly to the authorization flow. If there are stored ' +
            '    credentials, you still might not be prompted to reauthorize ' +
            '    the application.</td></tr>' +
            '<tr><td><b>Optional. </b><a href="/videos">Channel Videos</a></td>' +
            '<td>See the video list of your channels.</td></tr>' +
            '<tr><td><b>Step 2. </b><a href="/fetch_videos">Fetch Channel Videos</a></td>' +
            '<td>To fetch videos from your channel.</td></tr>' +
            '<tr><td><b>Step 3. </b><a href="/fetch_video_stats">Fetch Video Data</a></td>' +
            '<td>To fetch data from your channels videos.</td></tr>' +
            '<tr><td><b>Optional. </b><a href="/revoke">Revoke current credentials</a></td>' +
            '<td>Revoke the access token associated with the current user ' +
            '    session. After revoking credentials, if you go to the test ' +
            '    page, you should see an <code>invalid_grant</code> error.' +
            '</td></tr></table>' +
            '<br/><br/>' +
            '<h3>APIs: </h3>' +
            '<table>' +
            '<tr><td><b>1. </b><a href="/api/v1/videos_performances">Videos Performances</a></td>' +
            '<td>To see how your channels videos are doing!.</td></tr>' +
            '<tr><td><b>2. </b><a href="/api/v1/videos?sort=by_performances">Sort Videos</a></td>' +
            '<td>(By Performances) - For now only with Most (last_stats).</td></tr>' +
            '<tr><td><b>3. </b><a href="/api/v1/videos?filter=test">Filter Videos</a></td>' +
            '<td>(By Tags) - Changed the Filter Parameter on the URI and check!</td></tr>' +
            '</table>'
            )


if __name__ == '__main__':
    # When running locally, disable OAuthlib's HTTPs verification.
    # ACTION ITEM for developers:
    #     When running in production *do not* leave this option enabled.
    os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

    # Specify a hostname and port that are set as a valid redirect URI
    # for your API project in the Google API Console.
    app.run('localhost', 5000, debug=True)


@app.teardown_appcontext
def shutdown_session(exception=None):
    db_session.remove()


@app.route('/')
def index():
    return print_index_table()

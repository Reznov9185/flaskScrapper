# -*- coding: utf-8 -*-

import os
import flask
import requests
import time
import redis

import google.oauth2.credentials
import google_auth_oauthlib.flow
import googleapiclient.discovery

from flask import request
from database import *
from models import *
from tasks import *

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


@celery.task()
def add_together(a, b):
    return a + b


@celery.task()
def connect_youtube():
    init_db()
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


@celery.task()
def scrap_channel_videos():
    with app.app_context():
        youtube = connect_youtube()
        results = youtube.channels().list(mine=True, part='contentDetails').execute()
        # For a single channel now...
        uploads_playlist_id = \
            results['items'][0]['contentDetails']['relatedPlaylists']['uploads']
        results = youtube.playlistItems() \
            .list(playlistId=uploads_playlist_id, part='contentDetails') \
            .execute()
        videos = results['items']
        for video_item in videos:
            video_id = video_item['contentDetails']['videoId']
            already_stored = Video.query.filter(Video.youtube_id == video_id).all()
            if already_stored is None:
                entry = Video(youtube_id=video_id)
                db_session.add(entry)
                db_session.commit()
        # if 'nextPageToken' in results:
        #     print('############\n')
        #     print(results['nextPageToken'])
        #     print('############\n')
        #     scrap_channel_videos.delay()

        return videos

@celery.task()
def scrap_video_data():
    init_db()
    with app.app_context():
        youtube = connect_youtube()
        for video in Video.query.all():
            data = youtube.videos().list(id=video.youtube_id,
                                         part='statistics, snippet').execute()
            video_data = data['items']
            if len(video_data) > 0:
                video.title = video_data[0]['snippet']['title']
                video.channel_id = video_data[0]['snippet']['channelId']
                tags = video_data[0]['snippet']['tags']
                # return tags
                if len(tags) > 0:
                    for tag in tags:
                        tag_obj = Tag(title=tag, video_id=video.id)
                        db_session.add(tag_obj)
                        db_session.commit()
                db_session.commit()
            return video_data


@app.route('/')
def index():
    return print_index_table()


@app.route('/db_test')
def db_test():
    epoch_time = int(time.time())
    init_db()
    entry = Video('ABCDEFG' + str(epoch_time), 'ChannelXYZ' + str(epoch_time), 'Title of my video!')
    db_session.add(entry)
    db_session.commit()
    results = entry.serialize()

    return flask.jsonify(results)


@app.route('/celery_test')
def celery_test():
    result = add_together.delay(23, 42)
    test = result.wait()
    print(test)
    return 'Hurray! See the console...'


@app.route('/fetch_videos')
def fetch_videos():
    result = scrap_channel_videos.delay()
    test = result.wait()
    print(test)
    # result = scrap_video_data.delay()
    # test = result.wait()
    # print(test)
    return 'Hurray! See the console...'


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
    print(type(flask.session['credentials']['scopes']))

    return flask.jsonify(**flask.session['credentials'])


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
    print(type(uploads_playlist_id))
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

    return flask.redirect(flask.url_for('test_api_request'))


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
    return ('<table>' +
            '<tr><td><a href="/authorize">Test the auth flow directly</a></td>' +
            '<td>Go directly to the authorization flow. If there are stored ' +
            '    credentials, you still might not be prompted to reauthorize ' +
            '    the application.</td></tr>' +
            '<tr><td><a href="/videos">Channel Videos</a></td>' +
            '<td>See the video list of your channels.</td></tr>' +
            '<tr><td><a href="/revoke">Revoke current credentials</a></td>' +
            '<td>Revoke the access token associated with the current user ' +
            '    session. After revoking credentials, if you go to the test ' +
            '    page, you should see an <code>invalid_grant</code> error.' +
            '</td></tr>' +
            '<tr><td><a href="/clear">Clear Flask session credentials</a></td>' +
            '<td>Clear the access token currently stored in the user session. ' +
            '    After clearing the token, if you <a href="/test">test the ' +
            '    API request</a> again, you should go back to the auth flow.' +
            '</td></tr></table>')


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

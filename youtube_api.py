# Copyright 2019 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
#!/usr/bin/python
import datetime
import http.client as httplib
import random
import time

import auth
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaInMemoryUpload
import httplib2


# Explicitly tell the underlying HTTP transport library not to retry, since
# we are handling retry logic ourselves.
httplib2.RETRIES = 1

# Maximum number of times to retry before giving up.
MAX_RETRIES = 10

# Always retry when these exceptions are raised.
RETRIABLE_EXCEPTIONS = (
    httplib2.HttpLib2Error,
    IOError,
    httplib.NotConnected,
    httplib.IncompleteRead,
    httplib.ImproperConnectionState,
    httplib.CannotSendRequest,
    httplib.CannotSendHeader,
    httplib.ResponseNotReady,
    httplib.BadStatusLine,
)

# Always retry when an apiclient.errors.HttpError with one of these status
# codes is raised.
RETRIABLE_STATUS_CODES = [500, 502, 503, 504]

# This OAuth 2.0 access scope allows an application to upload files to the
# authenticated user's YouTube channel, but doesn't allow other types of access.
YOUTUBE_API_SERVICE_NAME = 'youtube'
YOUTUBE_API_VERSION = 'v3'
MISSING_CLIENT_SECRETS_MESSAGE = 'WARNING: Please configure OAuth 2.0'

_YOUTUBE_OPTIONS = {
    'title': 'creative-mango tool upload',
    'description': 'creative-mango tool upload',
    'category': '22',
    'keywords': '',
    'privacyStatus': 'unlisted',
}
_YOUTUBE_SCOPES = [
    'https://www.googleapis.com/auth/youtube.readonly',
    'https://www.googleapis.com/auth/youtube.upload',
]
_YOUTUBE_TOKEN_JSON = 'config/yt_token.json'


class YTService:
  """Provides YouTube API service."""

  def __init__(self, _YOUTUBE_SECRETS_JSON):
    """Builds YouTube credentials and initiaties a instance to call the API.

    Args:
      _YOUTUBE_SECRETS_JSON: YouTube API Secrets in a json file.
    """
    # Obtain credentials for YT API
    credential = Credentials.from_authorized_user_file(
        _YOUTUBE_TOKEN_JSON, _YOUTUBE_SCOPES
    )

    self._YOUTUBE_SERVICE = build(
        YOUTUBE_API_SERVICE_NAME, YOUTUBE_API_VERSION, credentials=credential
    )

  def initialize_upload(self, buffer):
    """Initializes video upload.

    Args:
      buffer: string, Bytes of video content.

    Returns:
      youtube_id: id of the uploaded video.
    """
    if not buffer:
      return

    tags = None
    if _YOUTUBE_OPTIONS.get('keywords'):
      tags = _YOUTUBE_OPTIONS.get('keywords').split(',')

    body = dict(
        snippet=dict(
            title=_YOUTUBE_OPTIONS.get('title'),
            description=_YOUTUBE_OPTIONS.get('description'),
            tags=tags,
            categoryId=_YOUTUBE_OPTIONS.get('category'),
        ),
        status=dict(privacyStatus=_YOUTUBE_OPTIONS.get('privacyStatus')),
    )

    # Call the API's videos.insert method to create and upload the video.
    insert_request = self._YOUTUBE_SERVICE.videos().insert(
        part=','.join(body.keys()),
        body=body,
        media_body=MediaInMemoryUpload(
            buffer, mimetype='video/mp4', chunksize=-1, resumable=True
        ),
    )

    return self.resumable_upload(insert_request)

  def resumable_upload(self, insert_request):
    """This method implements an exponential backoff strategy to resume a failed upload.

    Args:
      insert_request: object, The request body.

    Returns:
      youtube_id: id of the uploaded video on YouTube.
    """
    response = None
    error = None
    retry = 0
    youtube_id = None
    while response is None:
      try:
        _, response = insert_request.next_chunk()
        if response is not None:
          if 'id' in response:
            youtube_id = response['id']
            return youtube_id
          else:
            raise ValueError(
                'The upload failed with an unexpected response: {}'.format(
                    response
                )
            )
      except HttpError as e:
        if e.resp.status in RETRIABLE_STATUS_CODES:
          error = 'A retriable HTTP error {} occurred:\n{}'.format(
              e.resp.status, e.content
          )
        else:
          raise
      except RETRIABLE_EXCEPTIONS as e:
        error = 'A retriable error occurred: {}'.format(e)

      if error is not None:
        retry += 1
        if retry > MAX_RETRIES:
          raise ValueError('No longer attempting to retry.')

        max_sleep = 2 * retry
        sleep_seconds = random.random() * max_sleep
        print(
            'YouTube sleeping {} seconds and then retrying...'.format(
                sleep_seconds
            )
        )
        time.sleep(sleep_seconds)
    return youtube_id

  def get_youtube_id(self, buffer, title):
    """Uploads the video (buffer) with a given title.

    Args:
      buffer: string, Bytes of video content.
      title: string, titlfe of the video to be uploaded.

    Returns:
      id of the uploaded video on YouTube.
    """
    if len(title) > 100:
      title = title[0:100]
    if title:
      _YOUTUBE_OPTIONS['title'] = title
    return self.initialize_upload(buffer)

  def check_upload_finished(self, youtube_id_list):
    """Check if the uploads of the given youtube ids are complete.

    Args:
      youtube_id_list: list of string, list of youtube ids from which uploads
        are triggered.

    Returns:
      Whether all the youtube uploads are finished.
    """
    if not youtube_id_list:
      return True

    # print('Upload status:')
    response = None
    list_request = self._YOUTUBE_SERVICE.videos().list(
        part='processingDetails', id=','.join(youtube_id_list)
    )
    response = list_request.execute()
    result = True
    for stream in response.get('items', []):
      # print('{}: {}'.format(stream['id'],
      # stream['processingDetails']['processingStatus']))
      if stream['processingDetails']['processingStatus'] == 'processing':
        result = False
    return result

  def get_youtube_urls(self, _YOUTUBE_URL, yt_ids_sheet, youtube_window):
    """Retrieve YouTube Videos from YT Channel to use for trafficking.

    Args:
      _YOUTUBE_URL: Youtube base urls used to match the pattern.
      yt_ids_sheet: List of video ids that are already in the sheet.
      youtube_window: The lookback window configured to use for retrieving YT
        videos.

    Returns:
      Array of arrays containing the new video titles and youtube video URLs.
    """
    youtube_files = []
    youtube_start_date = datetime.date.fromtimestamp(
        time.time() - (youtube_window * 30.436875 * 24 * 60 * 60)
    )

    # Retrieve the contentDetails part of the channel resource for the
    # authenticated user's channel.
    channels_response = (
        self._YOUTUBE_SERVICE.channels()
        .list(mine=True, part='contentDetails')
        .execute()
    )

    for channel in channels_response['items']:
      # From the API response, extract the playlist ID that identifies the list
      # of videos uploaded to the authenticated user's channel.
      uploads_pl_id = channel['contentDetails']['relatedPlaylists']['uploads']

    # Retrieve the list of videos uploaded to the authenticated user's channel.
    pls_request = self._YOUTUBE_SERVICE.playlistItems().list(
        playlistId=uploads_pl_id, part='snippet,contentDetails', maxResults=5
    )

    while pls_request:
      playlistitems_list_response = pls_request.execute()

      # Print information about each video.
      for pl_item in playlistitems_list_response['items']:
        if pl_item['snippet']['resourceId']['videoId'] not in yt_ids_sheet:
          yt_ids_sheet.add(pl_item['contentDetails']['videoId'])
          published_date = datetime.date.fromisoformat(
              pl_item['contentDetails']['videoPublishedAt'][0:10]
          )
          if published_date > youtube_start_date:
            youtube_files.append([
                '',
                'VIDEO',
                pl_item['snippet']['title'],
                _YOUTUBE_URL + pl_item['snippet']['resourceId']['videoId'],
            ])

      pls_request = self._YOUTUBE_SERVICE.playlistItems().list_next(
          pls_request, playlistitems_list_response
      )

    return youtube_files

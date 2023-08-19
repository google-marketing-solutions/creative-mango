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
"""Gets the OAuth2 credential from file."""

import os.path
from google.auth.transport.requests import Request
from google.oauth2 import service_account
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import yaml

_TOKEN = 'config/token.json'
_SCOPES = [
    'https://www.googleapis.com/auth/drive',
    'https://www.googleapis.com/auth/spreadsheets',
]
_YOUTUBE_TOKEN = 'config/yt_token.json'
_YOUTUBE_SCOPES = [
    'https://www.googleapis.com/auth/youtube.readonly',
    'https://www.googleapis.com/auth/youtube.upload',
]


def get_credentials_from_file(
    service_account_file='PATH_TO_SERVICE_JSON',
    client_secret_file='PATH_TO_CLIENT_SECRET_JSON',
    scopes=_SCOPES,
    token=_TOKEN,
    port=8008,
):
  """Gets the Oauth2 credentials.

  Args:
    service_account_file: a string of path points to service account file.
    client_secret_file: a string of path points to client secret file.
    scopes: a list of the required scopes strings for this credential.
    token: path to the token.json file.

  Returns:
    An OAuth Credentials object for the authenticated user.
  """
  creds = None

  try:
    if os.path.exists(token):
      creds = Credentials.from_authorized_user_file(token, scopes)
  except:
    raise Exception(
        'Error while load OAuth credentials, no credentials returned.'
    )
  if not creds:
    raise Exception(
        'Error while generating OAuth credentials, no credentials returned.'
    )
  else:
    return creds


if __name__ == '__main__':
  with open('config/setup.yaml', 'r') as ymlfile:
    cfg = yaml.safe_load(ymlfile)
  get_credentials_from_file(
      service_account_file=cfg['serviceAccount'],
      client_secret_file=cfg['clientSecret'],
  )
  if cfg['youtubeServiceEnable']:
    get_credentials_from_file(
        service_account_file=cfg['serviceAccount'],
        client_secret_file=cfg['youtubeSecret'],
        scopes=_YOUTUBE_SCOPES,
        token=_YOUTUBE_TOKEN,
        port=8080,
    )

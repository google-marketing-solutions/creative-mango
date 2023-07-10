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

from google.oauth2 import service_account
from google.oauth2 import credentials
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
import os.path
import yaml

_TOKEN = 'token.json'
_SCOPES = [
    'https://www.googleapis.com/auth/drive',
    'https://www.googleapis.com/auth/spreadsheets',
]
_YOUTUBE_TOKEN = 'yt_token.json'
_YOUTUBE_SCOPES = [
  'https://www.googleapis.com/auth/youtube.readonly',
  'https://www.googleapis.com/auth/youtube.upload',
]

def get_credentials_from_file(service_account_file='PATH_TO_SERVICE_JSON'
    , client_secret_file='PATH_TO_CLIENT_SECRET_JSON', scopes=_SCOPES
    , token=_TOKEN, port=8008):
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

  # Selecting authentication method based on data from setup yaml file.
  if client_secret_file != 'PATH_TO_CLIENT_SECRET_JSON':
    # Append Google Ads API to Scope based on authentication method.
    if 'https://www.googleapis.com/auth/adwords' not in scopes:
      scopes.append('https://www.googleapis.com/auth/adwords')
    
    # Obtain credentials and return.
    if os.path.exists(token):
      creds = credentials.Credentials.from_authorized_user_file(token, scopes)
    if not creds or not creds.valid:
      if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
      else:
        flow = InstalledAppFlow.from_client_secrets_file(
          client_secret_file, scopes)
        creds = flow.run_local_server(port=port)
        with open(token, 'w') as token:
          token.write(creds.to_json())
  elif service_account_file != 'PATH_TO_SERVICE_JSON':
    return service_account.Credentials.from_service_account_file(
      service_account_file, scopes=scopes)
  
  if not creds or not creds.valid:
    raise Exception("Error while generating OAuth credentials, no credentials returned.")
  else:
    return creds

if __name__ == '__main__':
  with open('config/setup.yaml', 'r') as ymlfile:
    cfg = yaml.safe_load(ymlfile)
  get_credentials_from_file(service_account_file=cfg['serviceAccount'], client_secret_file=cfg['clientSecret'])
  if cfg['youtubeServiceEnable']:
    get_credentials_from_file(service_account_file=cfg['serviceAccount'], client_secret_file=cfg['youtubeSecret']
                             , scopes=_YOUTUBE_SCOPES, token=_YOUTUBE_TOKEN, port=8080)
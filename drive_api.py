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
import re
import io
from urllib import parse
import requests
import os.path
from datetime import datetime, timedelta

from googleapiclient.discovery import build
from googleapiclient import http

# The format of Drive URL

_DRIVE_URL_FORMAT_WITH_OPEN = 'drive.google.com/open?id='
_DRIVE_URL_FORMAT_WITH_FILE = 'drive.google.com/file/d/'
_DRIVE_URL = 'drive.google.com'


class DriveService():
  """Provides Drive APIs to download images from Drive.

  Attributes:
    _service: service that is used for making Drive v3 API calls.
  """

  def __init__(self, credential):
    """Creates a instance of drive service to handle requests.

    Args:
      credential: Drive APIs credentials.
    """
    self._drive_service = build('drive', 'v3', credentials=credential)

  def _download_asset(self, url):
    """Downloads an asset based on url, from drive or the web (e.g.

    YouTube).

    Args:
      url: url to fetch the asset from.

    Returns:
      asset data array.
    """
    if _DRIVE_URL in url:
      return self._download_drive_asset(url)
    else:
      response = requests.get(url)
    return io.BytesIO(response.content).read()

  def _download_drive_asset(self, url):
    """Downloads an asset from Google Drive.

    Args:
      url: Drive url of the asset.

    Returns:
      image_buffer: asset data array.

    Raises:
      ValueError: Unknown Drive URL.
    """
    image_id = ''
    try:
      image_id = self._retrieve_drive_id_from_url(url)
    except:
      raise ValueError(
          'Unable to prase the Drive URL. Kindly check the Drive URL of image exists.'
      )
    request = self._drive_service.files().get_media(fileId=image_id)
    file_handler = io.BytesIO()
    downloader = http.MediaIoBaseDownload(file_handler, request)
    done = False

    while done is False:
      _, done = downloader.next_chunk()
    file_handler.seek(0)
    image_buffer = file_handler.read()

    return image_buffer

  def _retrieve_drive_id_from_url(self, url):
    """Retrieves image id from Drive URL.

    Args:
      url: Drive url of the image.

    Returns:
      Drive id.

    Raises:
      ValueError: Unknown Drive URL.
    """
    if _DRIVE_URL_FORMAT_WITH_OPEN in url:
      return parse.urlparse(url).query.split('id=')[-1]
    elif _DRIVE_URL_FORMAT_WITH_FILE in url:
      return re.search('/file/d/([^/]+)', url).group(1)
    else:
      raise ValueError('Unable to prase the Drive URL. '
                       'Kindly check the Drive URL of image exists.')

  def _get_files_from_drive(self, drive_folder_ids):
    """Requests a list of folders that the service account has access to.

    Args:
      drive_folder_ids: Target google drive folder ids.

    Returns:
      results: list of files.
    """
    results = []
    date = (datetime.now() - timedelta(hours=24)).isoformat('T')[:-3] + 'Z'

    if not drive_folder_ids:
      drive_folder_ids = self._get_drive_folder_ids()

    for folder_id in drive_folder_ids:
      # request list of files in the target folder (images, videos)
      query = f"'{folder_id}' in parents and createdTime > '{date}' and trashed = false"
      file_list = self._get_drive_files(query)

      for file in file_list:
        file_name, _ = os.path.splitext(file['name'])
        asset_name = file_name
        file_url = 'https://drive.google.com/file/d/' + file['id']
        # checking created day and media type
        file_type = file['mimeType'].split('/')[0].upper()
        # Finding a file created within the last 24 hours >
        if file_type in ('VIDEO', 'IMAGE'):
          results.append(['', file_type, asset_name, file_url])

    return results

  def _get_drive_folder_ids(self):
    """Get google drive folder ids.

    Returns:
      drive_folder_ids: List of google drive folder ids.
    """
    query = f"mimeType='application/vnd.google-apps.folder' and trashed = false"
    all_file_list = self._get_drive_files(query)

    drive_folder_ids = []
    for folder in all_file_list:
      drive_folder_ids.append(folder['id'])

    return drive_folder_ids

  def _get_drive_files(self, query):
    """Get file list in google drive.

    Args:
      query: query for searching files in google drive.

    Returns:
      file_list: List of files.
    """
    file_list = []
    page_token = None
    while True:
      result = self._drive_service.files().list(
          q=query,
          spaces='drive',
          fields='files(id, name, mimeType, createdTime), nextPageToken',
          pageSize=1000,
          pageToken=page_token,
          supportsAllDrives=True,
          includeItemsFromAllDrives=True).execute()
      file_list += result.get('files')
      page_token = result.get('nextPageToken')
      if not page_token:
        break
    return file_list

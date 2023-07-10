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
"""Update image/video asset file urls in the Upload Sheet."""
from urllib import parse

import auth
import drive_api
import sheets_api
import yaml
import youtube_api

# Upload sheet range for drive urls
_UPLOAD_RANGE = 'Upload!A2:D'
_YOUTUBE_URL = 'https://www.youtube.com/watch?v='
_YOUTUBE_SHEET_RANGE = 'YT List!A2:A'


def get_file_youtube(spreadsheet_ids, credential
                     , youtube_secrets, yt_ids_sheet
                     , youtube_window):
  """Function to retrieve YouTube videos and write them to the sheet.

  Get video urls via YouTube API, and update in Upload Sheet.

  Args:
    spreadsheet_ids: Google Sheets Ids.
    credential: api credentials for Google sheets.
    youtube_secrets: authentication secrets file for YT API access.
    yt_ids_sheet: List of video ids that are already in the sheet.
    youtube_window: The lookback window configured to use for retrieving
        YT videos.
  """

  for spreadsheet_id in spreadsheet_ids:
    # Get YouTube Video IDs
    sheets_service = sheets_api.SheetsService(credential, spreadsheet_id)
    youtube_service = youtube_api.YTService(youtube_secrets)
    new_youtube_files = youtube_service.get_youtube_urls(
        _YOUTUBE_URL, yt_ids_sheet, youtube_window)
    sheets_service.write_to_sheet(_UPLOAD_RANGE, new_youtube_files)


def get_file_main(spreadsheet_ids, service_account, client_secret
                  , drive_folder_ids, youtube_secrets
                  , youtube_service_enable, youtube_window):
  """Main function for get_file.py.

  Get image & video file urls via Google Drive API,
  and update in Upload Sheet.

  Args:
    spreadsheet_ids: Google Sheets Ids.
    service_account: service account file path.
    client_secret: client secret file path.
    drive_folder_ids: Target google drive folder ids.
    youtube_secrets: oAuth credential for YouTube API.
    youtube_service_enable: If true, tool will upload videos to YouTube channel.
    youtube_window: If set, int with number of months to retrieve YT videos for.
  """
  # Get credentials for Drive & Sheets API
  credential = auth.get_credentials_from_file(service_account_file=service_account
                                              , client_secret_file=client_secret)

  # Get Drive file lists
  drive_service = drive_api.DriveService(credential)
  files = drive_service._get_files_from_drive(drive_folder_ids)
  yt_ids_sheet = set()

  for spreadsheet_id in spreadsheet_ids:
    sheets_service = sheets_api.SheetsService(credential, spreadsheet_id)
    uploading_rows = sheets_service.get_spreadsheet_values(_UPLOAD_RANGE)
    yt_list_rows = sheets_service.get_spreadsheet_values(_YOUTUBE_SHEET_RANGE)
    files_in_upload_sheet = set()
    new_files = []
    for row in yt_list_rows:
      if len(row) == 1:
        if _YOUTUBE_URL in row[0]:
          yt_ids_sheet.add(parse.urlparse(row[0]).query.split('v=')[-1].split('&')[0])
    for row in uploading_rows:
      if len(row) == 4:
        files_in_upload_sheet.add(row[3])
        if _YOUTUBE_URL in row[3]:
          yt_ids_sheet.add(parse.urlparse(row[3]).query.split('v=')[-1].split('&')[0])
    for file in files:
      if file[3] not in files_in_upload_sheet:
        new_files.append(file)
    sheets_service.write_to_sheet(_UPLOAD_RANGE, new_files)

  if(youtube_service_enable and youtube_window):
    get_file_youtube(spreadsheet_ids, credential, youtube_secrets
                     , yt_ids_sheet, youtube_window)


if __name__ == '__main__':
  with open('config/setup.yaml', 'r') as ymlfile:
    cfg = yaml.safe_load(ymlfile)
  if 'driveFolderIds' not in cfg.keys():
    cfg['driveFolderIds'] = None
  if 'youtubeWindow' not in cfg.keys():
    cfg['youtubeWindow'] = None
  get_file_main(
      spreadsheet_ids=cfg['spreadsheetIds'],
      service_account=cfg['serviceAccount'],
      client_secret=cfg['clientSecret'],
      drive_folder_ids=cfg['driveFolderIds'],
      youtube_secrets=cfg['youtubeSecret'],
      youtube_service_enable=cfg['youtubeServiceEnable'],
      youtube_window=cfg['youtubeWindow'])

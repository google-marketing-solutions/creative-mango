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
"""Main operation script for Creative mango.

This script will run each step in following order:
get_file.py -> creative_remover.py -> creative_uploader.py ->
(optional)refresh_mapping_sheet.py
Please set configs in config/setup.yaml file before running the script.
"""
import datetime

import creative_remover
import creative_uploader
import get_file
import refresh_mapping_sheet
import yaml

_SET_UP_FILE = 'config/setup.yaml'


def init_config(setup_file):
  """Get configs from config/setup.yaml file.

  Args:
    setup_file: Path for setup.yaml.

  Returns:
    cfg: configs.
  """
  with open(setup_file, 'r') as ymlfile:
    cfg = yaml.safe_load(ymlfile)
  return cfg


def main():
  """Main Operation for creative mango."""
  start_time = datetime.datetime.today()
  print(f'START TIME: {start_time}')

  cfg = init_config(setup_file=_SET_UP_FILE)
  if 'driveFolderIds' not in cfg.keys():
    cfg['driveFolderIds'] = None
  if 'youtubeWindow' not in cfg.keys():
    cfg['youtubeWindow'] = None

  # STEP 1. Get list of IMAAGE & VIDEO File url and update in the Upload Sheet.
  print(
      '--------------------------Start retrieving image & video url operation-----------------------'
  )
  try:
    get_file.get_file_main(
        spreadsheet_ids=cfg['spreadsheetIds'],
        service_account=cfg['serviceAccount'],
        client_secret=cfg['clientSecret'],
        drive_folder_ids=cfg['driveFolderIds'],
        youtube_secrets=cfg['youtubeSecret'],
        youtube_service_enable=cfg['youtubeServiceEnable'],
        youtube_window=cfg['youtubeWindow'])
  except Exception as error:
    print('Unable to complete adding assets to Upload Sheet:', repr(error))
  print(
      '--------------------------End retrieving image & video url operation-----------------------'
  )

  # STEP 2. Remove time sensitive & low performing assets and evaluate asset
  # performance.
  print(
      '--------------------------Start delete & performance evaluation operation-----------------------'
  )
  try:
    creative_remover.remover_main(
        spreadsheet_ids=cfg['spreadsheetIds'],
        service_account=cfg['serviceAccount'],
        client_secret=cfg['clientSecret'],
        ads_account=cfg['adsAccount'])
  except Exception as error:
    print('Unable to complete removing the assets:', repr(error))
  print(
      '--------------------------End delete & performance evaluation  operation-----------------------'
  )

  # STEP 3. Upload new assets in the Upload Sheet.
  print(
      '--------------------------Start Upload operation-----------------------')
  try:
    creative_uploader.uploader_main(
        spreadsheet_ids=cfg['spreadsheetIds'],
        service_account=cfg['serviceAccount'],
        client_secret=cfg['clientSecret'],
        ads_account=cfg['adsAccount'],
        youtube_secrets=cfg['youtubeSecret'],
        youtube_service_enable=cfg['youtubeServiceEnable'])
  except Exception as error:
    print('Unable to complete uploading the assets:', repr(error))
  print('--------------------------End Upload operation-----------------------')

  # STEP 4. If refreshMappingSheetEnable is true, update the Mapping Sheet with
  # up-to-date information.
  if cfg['refreshMappingSheetEnable']:
    print(
        '--------------------------Start Updating mapping sheet operation-----------------------'
    )
    try:
      refresh_mapping_sheet.refresh_mapping_main(
          spreadsheet_ids=cfg['spreadsheetIds'],
          service_account=cfg['serviceAccount'],
          client_secret=cfg['clientSecret'],
          ads_account=cfg['adsAccount'])
    except Exception as error:
      print('Unable to complete updating the mapping sheet:', repr(error))
    print(
        '--------------------------End Updating mapping sheet operation-----------------------'
    )

  end_time = datetime.datetime.today()
  print(f'END TIME: {end_time} / Execution time: {end_time - start_time}')


if __name__ == '__main__':
  main()

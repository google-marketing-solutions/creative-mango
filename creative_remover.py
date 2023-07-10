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
"""Provides customized creative tool to delete assets.

Customer will update delete conditions in Google Spreadsheet. (Performance
Managed Sheet)
This tool will find low performing assets based on the delete conditions and
automatically delete them.
"""

import datetime
import enum
import yaml
from googleapiclient.errors import HttpError

import ads_api_error_translation
import ads_service_api
import auth
import sheets_api

from google.ads import googleads

# Number of columns in the Time Managed sheet should be 12.
_NUMBER_OF_TIME_MANAGED_SHEET_COLUMNS = 12

# Number of conditions in Performance Condition Sheet.
_NUMBER_OF_PERFORMANCE_CONDITIONS = 7

# Sheet names and ranges
_PERFORMANCE_CONDITION_SHEET_RANGE = 'Performance Conditions!B2:B8'
_TIME_MANAGE_SHEET_NAME = 'Time Managed'
_TIME_MANAGED_SHEET_RANGE = 'Time Managed!A2:L'
_CHANGE_HISTORY_SHEET_RANGE = 'Change History!A2:K'

# today date
_TODAY = datetime.datetime.today()


class TimeManagedColumn(enum.IntEnum):
  """Enum class to indicate column indices in the Time Managed sheet."""
  AD_GROUP_ALIAS = 0
  CREATIVE_TYPE = 1
  CREATIVE_NAME = 2
  IMAGE_VIDEO_URL = 3
  CUSTOMER_ID = 4
  AD_GROUP_ID = 5
  ASSET_ID_OR_TEXT = 6
  START_DATE = 7
  END_DATE = 8
  DELETE_BY_PERFORMANCE = 9
  PERFORMANCE = 10
  ERROR_NOTE = 11


class PerformanceCondition(enum.IntEnum):
  """Enum class to indicate performance evaluation conditions in the Performance Condition sheet."""
  ACTIVE_DAYS = 0
  DURATION = 1
  IMPRESSIONS = 2
  CONVERSIONS = 3
  CONVERSIONS_VALUE = 4
  CTR = 5
  CLICKS = 6


class MinimumAdGroupAsset(enum.IntEnum):
  """Enum class to indicate minimum number of creatives in one ad group."""
  HEADLINE = 2
  DESCRIPTION = 2
  IMAGE = 1
  VIDEO = 5


def check_date_format(target_date):
  """Checks the date format.

  Args:
    target_date: date to check the format.

  Returns:
    execution result.
    result: If date is in the correct format, return the date in datetime
    format. If error occurs, return error message.

  Raises:
    ValueError: Date format value error.
    Exception: Unknown error while checking the date format.
  """
  try:
    date_split = datetime.datetime.strptime(target_date, '%Y-%m-%d')
    result = datetime.datetime(date_split.year, date_split.month,
                               date_split.day).date()
  except ValueError:
    result = ('END_DATE is not correct format. Kindly follow the '
              'format of YYYY-MM-DD.')
    return False, result
  except Exception as e:
    result = (f'Please check the END_DATE in the Time Managed Sheet. Error: '
              f'{str(e)}')
    return False, result

  return True, result


def unqualified_to_delete(ads_service, customer_id, ad_group_id, asset_type):
  """Checks the number of assets in the AdGroup.

  If the number of assets (per asset_type) is smaller than the number defined
  in the Class MinimumAdGroupAsset,
  Append to the list and return.

  Args:
    ads_service: Google ads api service.
    customer_id: Google ads customer id.
    ad_group_id: Ad group id.
    asset_type: Asset type.

  Returns:
    execution result.
    error_message: Error message.

  Raises:
    GoogleAdsException: If Google Ads API error occurs.
    Exception: If unknown error occurs while retrieving current number of
    assets.
  """
  try:
    creative_number = ads_service._get_ad_and_ad_type(customer_id, ad_group_id)
  except googleads.errors.GoogleAdsException as failures:
    error_message = ''
    for error in failures.failure.errors:
      error_message += ads_api_error_translation.translate_ads_api_errors(
          error.message)
    return False, error_message
  except Exception as e:
    error_message = f'Unable to read current number of assets: {str(e)}'
    return False, error_message

  if asset_type == 'HEADLINE':
    if creative_number[0]['HEADLINE'] <= MinimumAdGroupAsset.HEADLINE:
      error_message = (f'Not enough headlines in the AdGroup. The number of '
                       f'headline should be greater than '
                       f'{MinimumAdGroupAsset.HEADLINE}')
      return False, error_message
  elif asset_type == 'DESCRIPTION':
    if creative_number[0]['DESCRIPTION'] <= MinimumAdGroupAsset.DESCRIPTION:
      error_message = (f'Not enough descriptions in the AdGroup. The number '
                       f'of description should be greater than '
                       f'{MinimumAdGroupAsset.DESCRIPTION}')
      return False, error_message
  elif asset_type == 'IMAGE':
    if creative_number[0]['IMAGE'] <= MinimumAdGroupAsset.IMAGE:
      error_message = (f'Not enough images in the AdGroup. The number of '
                       f'image should be greater than '
                       f'{MinimumAdGroupAsset.IMAGE}')
      return False, error_message
  elif asset_type == 'VIDEO':
    if creative_number[0]['VIDEO'] <= MinimumAdGroupAsset.VIDEO:
      error_message = (f'Not enough videos in the AdGroup. The number of '
                       f'video should be greater than '
                       f'{MinimumAdGroupAsset.VIDEO}')
      return False, error_message

  return True, ''


def delete_asset_from_ads(ads_service, customer_id, ad_group_id,
                          asset_to_remove, asset_type):
  """Delete asset operation.

  Args:
    ads_service: Google ads api service.
    customer_id: Google ads customer id.
    ad_group_id: Ad group id.
    asset_to_remove: For text assets, text itself. For media assets, asset id.
    asset_type: Asset type.

  Returns:
    delete result.
    error_message: Error message.

  Raises:
    GoogleAdsException: If Google Ads API error occurs.
    Exception: If unknown error occurs while deleting the asset.
  """
  try:
    if asset_type == 'HEADLINE':
      ads_service._remove_headline_asset_from_campaign(asset_to_remove,
                                                       customer_id, ad_group_id)
    elif asset_type == 'DESCRIPTION':
      ads_service._remove_description_asset_from_campaign(
          asset_to_remove, customer_id, ad_group_id)
    elif asset_type == 'IMAGE':
      ads_service._remove_image_asset_from_campaign(asset_to_remove,
                                                    customer_id, ad_group_id)
    elif asset_type == 'VIDEO':
      ads_service._remove_video_asset_from_campaign(asset_to_remove,
                                                    customer_id, ad_group_id)
  except googleads.errors.GoogleAdsException as failures:
    error_message = ''
    for error in failures.failure.errors:
      error_message += ads_api_error_translation.translate_ads_api_errors(
          error.message)
    return False, error_message
  except Exception as e:
    error_message = f'Unable to delete: {str(e)}'
    return False, error_message

  return True, ''


def remove_asset(ads_service, customer_id, ad_group_id, asset_to_remove,
                 asset_type):
  """Remove asset from the ad.

  Check the number of current asset in the ad first, and if there is enough
  assets, remove the asset.

  Args:
    ads_service: Google Ads API service.
    customer_id: Google ads customer id.
    ad_group_id: Ad group id.
    asset_to_remove: For text assets, text itself. For media assets, asset id.
    asset_type: Asset type.

  Returns:
    result: execution result.
    error_message: error message.
  """
  error_message = ''
  # Check the number of assets in the current AdGroup.
  result, error_message = unqualified_to_delete(ads_service, customer_id,
                                                ad_group_id, asset_type)
  # If the nubmer of assets meets the criteria, delete asset from the ad
  if result:
    result, error_message = delete_asset_from_ads(ads_service, customer_id,
                                                  ad_group_id, asset_to_remove,
                                                  asset_type)

  return result, error_message


def update_error_note(sheets_service, update_errors, time_managed_sheet_id):
  """Update error message in the Time Managed sheet.

  Args:
    sheets_service: Google sheet api service.
    update_errors: row information and error message.
    time_managed_sheet_id: Time Managed Sheet id.

  Raises:
    Exception: If unknown error occurs while updating rows in the Time Managed
    Sheet.
  """
  update_request_list = []
  for update_row in update_errors:
    update_index = update_row[0]
    update_error_note = get_update_error_note(update_row, update_index,
                                              time_managed_sheet_id)
    update_request_list.append(update_error_note)

  try:
    sheets_service.batch_update_requests(update_request_list)
  except Exception as e:
    print(f'Unable to update Time Managed Sheet rows: {str(e)}')


def delete_row_by_index(sheets_service, delete_assets, time_managed_sheet_id):
  """Delete row in the Time Managed sheet.

  Args:
    sheets_service: Google sheet api service.
    delete_assets: row to delete.
    time_managed_sheet_id: Time Managed Sheet id.

  Raises:
    Exception: If unknown error occurs while deleting rows in the Time Managed
    Sheet.
  """
  delete_request_list = []
  i = 1
  for delete_row in delete_assets:
    delete_row_index = delete_row[0]
    delete_request = {
        'deleteDimension': {
            'range': {
                'sheetId': time_managed_sheet_id,
                'dimension': 'ROWS',
                'startIndex': delete_row_index - i,
                'endIndex': delete_row_index - i + 1
            }
        }
    }
    delete_request_list.append(delete_request)
    i += 1

  try:
    sheets_service.batch_update_requests(delete_request_list)
  except Exception as e:
    print(f'Unable to update/delete Time Managed Sheet rows: {str(e)}')


def update_time_managed_sheet(sheets_service, update_errors,
                              time_managed_sheet_id, delete_assets):
  """Update row in Time Managed Sheet.

  Args:
    sheets_service: Google sheet api service.
    update_errors: error messages to update in the Time Managed Sheet.
    time_managed_sheet_id: time managed sheet id.
    delete_assets: assets to delete in the Time Managed Sheet.

  Raises:
    Exception: If unknown error occurs while retrieving data from the Time
    Managed Sheet.
  """
  try:
    sheets_service.clear_sheet_range(f'Time Managed!J2:L')
  except Exception as e:
    print(f'Unable to update Time Managed Sheet rows: {str(e)}')

  if update_errors:
    update_error_note(sheets_service, update_errors, time_managed_sheet_id)

  if delete_assets:
    delete_row_by_index(sheets_service, delete_assets, time_managed_sheet_id)


def write_to_change_history(sheets_service, row_data, message):
  """Write change history.

  Args:
    sheets_service: Google sheet api service.
    row_data: target asset information.
    message: Change history message.

  Raises:
    Exception: If unknown error occurs while writing to the Change History
    Sheet.
  """
  result_log = row_data[:-3].copy()
  try:
    result_log.append(message)
    result_log.append(str(_TODAY))
    sheets_service.write_to_sheet(_CHANGE_HISTORY_SHEET_RANGE, [result_log])
  except Exception as e:
    print(f'Unable to update Change History Sheet: {str(e)}')


def time_managed(ads_service, sheets_service, time_managed_sheet_id,
                 time_managed_rows):
  """Deletes creative if End date in Time Managed Sheet is not empty and is

  Today or if Confirm Delete is True.

  If current number of creative is less than MinimumAdGroupAsset, skip.

  Args:
    ads_service: Google ads api service.
    sheets_service: Google sheet api service.
    time_managed_sheet_id: time managed sheet id.
    time_managed_rows: Data in Time Managed Sheet.

  Returns:
    delete_assets: Deleted assets.
  """
  delete_assets = []
  update_errors = []
  today = _TODAY.date()

  for row in time_managed_rows:
    row_index = row['row_index']
    row_data = row['row']
    customer_id = str(row_data[TimeManagedColumn.CUSTOMER_ID])
    ad_group_id = str(row_data[TimeManagedColumn.AD_GROUP_ID])
    asset_id = str(row_data[TimeManagedColumn.ASSET_ID_OR_TEXT])
    asset_type = str(row_data[TimeManagedColumn.CREATIVE_TYPE]).upper()
    end_date = row_data[TimeManagedColumn.END_DATE]
    perf_note = str(row_data[TimeManagedColumn.PERFORMANCE]).upper()
    delete_by_performance = row_data[TimeManagedColumn.DELETE_BY_PERFORMANCE]
    error_message = ''

    if asset_type not in ['HEADLINE', 'DESCRIPTION', 'IMAGE', 'VIDEO']:
      error_message = f'Please check the creative type'
      update_errors.append([
          row_index, customer_id, ad_group_id, asset_id, asset_type,
          error_message
      ])
      continue

    # Delete asset with end date equal to past or today.
    if end_date:
      check_result, date_result = check_date_format(end_date)
      if check_result:
        end_date = date_result
        if end_date <= today:
          delete_result, error_message = remove_asset(ads_service, customer_id,
                                                      ad_group_id, asset_id,
                                                      asset_type)
          if delete_result:
            delete_assets.append(
                [row_index, customer_id, ad_group_id, asset_id, asset_type])
            write_to_change_history(sheets_service, row_data,
                                    'Creative successfully removed')
          else:
            update_errors.append([
                row_index, customer_id, ad_group_id, asset_id, asset_type,
                error_message
            ])
          continue
      else:
        update_errors.append([
            row_index, customer_id, ad_group_id, asset_id, asset_type,
            date_result
        ])

    # Delete low performance assets.
    if perf_note in ['LOW', 'NO RECENT RECORDS'
                    ] and delete_by_performance == 'TRUE':
      delete_result, error_message = remove_asset(ads_service, customer_id,
                                                  ad_group_id, asset_id,
                                                  asset_type)
      if delete_result:
        delete_assets.append(
            [row_index, customer_id, ad_group_id, asset_id, asset_type])
        write_to_change_history(sheets_service, row_data,
                                'Creative successfully removed')
      else:
        update_errors.append([
            row_index, customer_id, ad_group_id, asset_id, asset_type,
            error_message
        ])

  # Update Time Managed Sheet. (Delete rows & write error message)
  update_time_managed_sheet(sheets_service, update_errors,
                            time_managed_sheet_id, delete_assets)

  return delete_assets


def check_ad_type(ads_service, customer_id, ad_group_id):
  """Check the ad type.

  If it's ACe, return false since Google Ads API currently don't support
  performance reporting for ACe.

  Args:
    ads_service: Google Ads API service.
    customer_id: Google ads customer id.
    ad_group_id: Ad group id.

  Returns:
    execution result.
    error_message: Error message occured while retrieving ad type.

  Raises:
    GoogleAdsException: If Google Ads API error occurs.
    Exception: If unknown error occurs.
  """
  try:
    (_, ad_type) = ads_service._get_ad_and_ad_type(customer_id, ad_group_id)
  except googleads.errors.GoogleAdsException as failures:
    error_message = ''
    for error in failures.failure.errors:
      error_message += ads_api_error_translation.translate_ads_api_errors(
          error.message)
    return False, error_message
  except Exception as e:
    return False, repr(e)

  if ad_type == ads_service._google_ads_client.enums.AdTypeEnum.APP_ENGAGEMENT_AD:
    error_message = f'Performance reporting not supported for ACe Campaigns.'
    return False, error_message

  return True, ''


def check_minimum_days_elapsed(start_date, active_days):
  """Check the minimum days elapsed from the campaign start date.

  If campaign served days is smaller than minimum active days threshold, return
  false.

  Args:
    start_date: campaign start date.
    active_days: minimum active days threshold set in the Performance Condition
      Sheet.

  Returns:
    execution result.
    error_message: Error message occured while checking the minimum days elapsed
    from the campaign start date.
  """
  check_result, check_date_result = check_date_format(start_date)

  if check_result:
    served_days = (_TODAY.date() - check_date_result).days
  else:
    error_message = check_date_result
    return check_result, error_message

  if served_days < active_days:
    error_message = f'Need to serve more days to evaluate performance.'
    return False, error_message

  return True, ''


def get_asset_perf(ads_service, customer_id, ad_group_id, asset_id, asset_type,
                   duration):
  """Retrieve asset performance via Google Ads API.

  Args:
    ads_service: Google Ads API service.
    customer_id: Google ads customer id.
    ad_group_id: Ad group id.
    asset_id: For text assets, text itself. For media assets, asset id.
    asset_type: Asset type.
    duration: duration to evaluate the performance.

  Returns:
    execution result.
    result: asset performance response from the Google Ads API.

  Raises:
    GoogleAdsException: If Google Ads API error occurs.
    Exception: If unknown error occurs.
  """
  try:
    result = ads_service._get_asset_performance_by_metrics(
        customer_id, ad_group_id, asset_id, asset_type, duration)
  except googleads.errors.GoogleAdsException as failures:
    result = ''
    for error in failures.failure.errors:
      result += ads_api_error_translation.translate_ads_api_errors(
          error.message)
    return False, result
  except Exception:
    return False, 'Unknown error occured while retrieving asset performance'

  return True, result


def evaluate_asset_perf(asset_perf, metrics):
  """Evaluate asset performance based on the custom metrics in the Performance Condition Sheet.

  Args:
    asset_perf: asset performance.
    metrics: custom metrics in the Performance Condition Sheet.

  Returns:
    performance evaluation note
  """
  if not asset_perf:
    return 'NO RECENT RECORDS'
  performance_label = asset_perf[0]['performance_label']
  if performance_label != 'LOW':
    return ''

  delete_flag = False
  if metrics['impressions'] != '':
    perf_impressions = int(asset_perf[0]['impressions'])
    if perf_impressions < metrics['impressions']:
      delete_flag = True
    else:
      delete_flag = False
  if metrics['conversions'] != '':
    perf_conversions = int(asset_perf[0]['conversions'])
    if perf_conversions < metrics['conversions']:
      delete_flag = True
    else:
      delete_flag = False
  if metrics['conversions_value'] != '':
    perf_conv_value = float(asset_perf[0]['conversions_value'])
    if perf_conv_value < metrics['conversions_value']:
      delete_flag = True
    else:
      delete_flag = False
  if metrics['ctr'] != '':
    perf_ctr = float(asset_perf[0]['ctr'])
    if perf_ctr < metrics['ctr']:
      delete_flag = True
    else:
      delete_flag = False
  if metrics['clicks'] != '':
    perf_clicks = int(asset_perf[0]['clicks'])
    if perf_clicks < metrics['clicks']:
      delete_flag = True
    else:
      delete_flag = False

  if delete_flag:
    return 'LOW'
  else:
    return ''


def get_update_checkbox(update_row, update_index, time_managed_sheet_id):
  """Gets target cells to update checkbox in the Time Managed Sheet.

  Args:
    update_row: row to update checkbox.
    update_index: row index of the target cell.
    time_managed_sheet_id: Sheet id for the Time Managed Sheet.

  Returns:
    update_checkbox: cell information for updating checkbox.
  """
  if update_row[5] != '':
    update_checkbox = {
        'updateCells': {
            'start': {
                'sheetId': time_managed_sheet_id,
                'rowIndex': update_index - 1,
                'columnIndex': TimeManagedColumn.DELETE_BY_PERFORMANCE
            },
            'rows': [{
                'values': [{
                    'dataValidation': {
                        'condition': {
                            'type': 'BOOLEAN'
                        }
                    }
                }]
            }],
            'fields': 'dataValidation'
        }
    }
  else:
    update_checkbox = {
        'updateCells': {
            'start': {
                'sheetId': time_managed_sheet_id,
                'rowIndex': update_index - 1,
                'columnIndex': TimeManagedColumn.DELETE_BY_PERFORMANCE
            },
            'rows': [{
                'values': [{
                    'userEnteredValue': {
                        'stringValue': update_row[5]
                    },
                    'dataValidation': None
                }]
            }],
            'fields': 'userEnteredValue, dataValidation'
        }
    }
  return update_checkbox


def get_update_perf_note(update_row, update_index, time_managed_sheet_id):
  """Gets target cells to update performance note in the Time Managed Sheet.

  Args:
    update_row: performance note content.
    update_index: row index of the target cell.
    time_managed_sheet_id: Sheet id for the Time Managed Sheet.

  Returns:
    update_perf_note: cell information for updating performance note.
  """
  update_perf_note = {
      'updateCells': {
          'start': {
              'sheetId': time_managed_sheet_id,
              'rowIndex': update_index - 1,
              'columnIndex': TimeManagedColumn.PERFORMANCE
          },
          'rows': [{
              'values': [{
                  'userEnteredValue': {
                      'stringValue': update_row[5]
                  }
              }]
          }],
          'fields': 'userEnteredValue'
      }
  }
  return update_perf_note


def get_update_error_note(update_row, update_index, time_managed_sheet_id):
  """Gets target cells to update error note in the Time Managed Sheet.

  Args:
    update_row: error note content.
    update_index: row index of the target cell.
    time_managed_sheet_id: Sheet id for the Time Managed Sheet.

  Returns:
    update_error_note: cell information for updating error note.
  """
  update_error_note = {
      'updateCells': {
          'start': {
              'sheetId': time_managed_sheet_id,
              'rowIndex': update_index - 1,
              'columnIndex': TimeManagedColumn.ERROR_NOTE
          },
          'rows': [{
              'values': [{
                  'userEnteredValue': {
                      'stringValue': update_row[5]
                  }
              }]
          }],
          'fields': 'userEnteredValue'
      }
  }
  return update_error_note


def update_time_managed_sheet_perf_note(sheets_service, time_managed_sheet_id,
                                        update_perf_note_assets, update_errors):
  """Update performance note, check box and error note in the Time Managed Sheet.

  Args:
    sheets_service: Google sheet api service.
    time_managed_sheet_id: Sheet id for the Time Managed Sheet.
    update_perf_note_assets: list of asset to update performance note.
    update_errors: list of asset to update error note.

  Raises:
    Exception: If unknown error occurs while updating the Time Managed Sheet.
  """
  update_checkbox_list = []
  update_value_request_list = []

  if update_perf_note_assets:
    for update_row in update_perf_note_assets:
      update_index = update_row[0]

      update_perf_note = get_update_perf_note(update_row, update_index,
                                              time_managed_sheet_id)
      update_value_request_list.append(update_perf_note)

      update_checkbox = get_update_checkbox(update_row, update_index,
                                            time_managed_sheet_id)
      update_checkbox_list.append(update_checkbox)

  if update_errors:
    for update_row in update_errors:
      update_index = update_row[0]
      update_error_note = get_update_error_note(update_row, update_index,
                                                time_managed_sheet_id)
      update_value_request_list.append(update_error_note)

  if update_value_request_list:
    try:
      # Update Perf Note / Error Note
      sheets_service.batch_update_requests(update_value_request_list)

    except Exception as e:
      print(
          f'Error while updating performance note in the Time Managed Sheet: {str(e)}'
      )

  if update_checkbox_list:
    try:
      # Update Delete by Performance column (insert checkbox)
      sheets_service.batch_update_requests(update_checkbox_list)

    except Exception as e:
      print(
          f'Error while updating performance note in the Time Managed Sheet: {str(e)}'
      )


def performance_managed(ads_service, sheets_service, conditions,
                        time_managed_sheet_id, time_managed_rows):
  """Performance evaluation.

  Update note in Time Managed Sheet if asset has low performance.

  Args:
      ads_service: Google ads api service.
      sheets_service: Google sheet api service.
      conditions: delete condition metrics.
      time_managed_sheet_id: time managed sheet id.
      time_managed_rows: time managed sheet data.

  Returns:
      update_perf_note_assets: performance note updated asset list.
  """
  # return value
  update_perf_note_assets = []
  update_errors = []

  # Performance evaluation duration
  active_days = conditions[PerformanceCondition.ACTIVE_DAYS]
  duration = conditions[PerformanceCondition.DURATION]

  # Performance evaluation metric
  metrics = {
      'impressions': conditions[PerformanceCondition.IMPRESSIONS],
      'conversions': conditions[PerformanceCondition.CONVERSIONS],
      'conversions_value': conditions[PerformanceCondition.CONVERSIONS_VALUE],
      'ctr': conditions[PerformanceCondition.CTR],
      'clicks': conditions[PerformanceCondition.CLICKS]
  }

  for row in time_managed_rows:
    row_index = row['row_index']
    row_data = row['row']
    customer_id = str(row_data[TimeManagedColumn.CUSTOMER_ID])
    ad_group_id = str(row_data[TimeManagedColumn.AD_GROUP_ID])
    asset_id = str(row_data[TimeManagedColumn.ASSET_ID_OR_TEXT])
    start_date = row_data[TimeManagedColumn.START_DATE]
    asset_type = str(row_data[TimeManagedColumn.CREATIVE_TYPE]).upper()
    current_perf_note = str(row_data[TimeManagedColumn.PERFORMANCE]).upper()
    current_error_note = str(row_data[TimeManagedColumn.ERROR_NOTE])
    error_message = ''

    if asset_type not in ['HEADLINE', 'DESCRIPTION', 'IMAGE', 'VIDEO']:
      continue

    ad_type_result, error_message = check_ad_type(ads_service, customer_id,
                                                  ad_group_id)
    if not ad_type_result:
      if current_error_note:
        error_message = f'{current_error_note} / {error_message}'
      update_errors.append([
          row_index, customer_id, ad_group_id, asset_id, asset_type,
          error_message
      ])
      continue

    date_result, error_message = check_minimum_days_elapsed(
        start_date, active_days)
    if not date_result:
      if current_error_note:
        error_message = f'{current_error_note} / {error_message}'
      update_errors.append([
          row_index, customer_id, ad_group_id, asset_id, asset_type,
          error_message
      ])
      continue

    perf_result, asset_perf = get_asset_perf(ads_service, customer_id,
                                             ad_group_id, asset_id, asset_type,
                                             duration)
    if perf_result:
      new_perf_note = evaluate_asset_perf(asset_perf, metrics)
      if not current_perf_note and new_perf_note == '':
        continue
      update_perf_note_assets.append([
          row_index, customer_id, ad_group_id, asset_id, asset_type,
          new_perf_note
      ])
    else:
      error_message = asset_perf
      if current_error_note:
        error_message = f'{current_error_note} / {error_message}'
      update_errors.append([
          row_index, customer_id, ad_group_id, asset_id, asset_type,
          error_message
      ])
      continue

  update_time_managed_sheet_perf_note(sheets_service, time_managed_sheet_id,
                                      update_perf_note_assets, update_errors)

  return update_perf_note_assets


def get_time_managed_rows(sheets_service):
  """Gets the rows from the "Time Managed" sheet.

  Args:
    sheets_service: Google Sheet APIs service.

  Returns:
    time_managed_rows: An array of arrays. Each subarray contains the asset
    information uploaded via this tool

  Raises:
    HttpError: Unable to read the Time Managed Sheet due to wrong sheet id or
    name.
    Exception: If unknown error occurs while retrieving data from the Time
    Managed Sheet.
  """
  try:
    time_managed_sheet = sheets_service.get_spreadsheet_values(
        _TIME_MANAGED_SHEET_RANGE)

    time_managed_rows = []
    for row_index, row_data in enumerate(time_managed_sheet):
      # Fill in the empty columns
      if len(row_data) < _NUMBER_OF_TIME_MANAGED_SHEET_COLUMNS:
        for _ in range(_NUMBER_OF_TIME_MANAGED_SHEET_COLUMNS - len(row_data)):
          row_data.append('')
      # Must have CustomerId, AdGroupId, AssetId, MediaType, Start Date in the
      # row. Else Skip the rows.
      if row_data[TimeManagedColumn.CUSTOMER_ID] and \
              row_data[TimeManagedColumn.AD_GROUP_ID] and \
              row_data[TimeManagedColumn.ASSET_ID_OR_TEXT] and \
              row_data[TimeManagedColumn.CREATIVE_TYPE] and \
              row_data[TimeManagedColumn.START_DATE]:
        row_data[TimeManagedColumn.CUSTOMER_ID] = (
            row_data[TimeManagedColumn.CUSTOMER_ID].replace('-', '')).replace(
                ' ', '')
        time_managed_rows.append({'row_index': row_index + 2, 'row': row_data})
  except HttpError:
    print('Unable to read the Time Managed sheet. '
          'Verify whether the id/name is correct.')
  except Exception as e:
    print('Unable to read the Time Managed sheet.', repr(e))

  return time_managed_rows


def convert_to_string(val):
  """Convert value to string without white space.

  Args:
    val: value to convert.

  Returns:
    string without white space.
  """
  return str(val).replace(' ', '')


def convert_to_int(val):
  """Convert value to integer after removing white space.

  Args:
    val: value to convert.

  Returns:
    integer.
  """
  return int(str(val).replace(' ', ''))


def convert_to_float(val):
  """Convert value to float after removing white space.

  Args:
    val: value to convert.

  Returns:
    float.
  """
  return float(str(val).replace(' ', ''))


def check_performance_condition_value(conditions):
  """Check the correctness of the values in the Performance Condition Sheet.

  Args:
    conditions: conditions in the Performance Condition Sheet.

  Returns:
    conditions: conditions in the correct data type.

  Raises:
    ValueError: If value is not in the correct format.
  """
  active_days = convert_to_string(conditions[PerformanceCondition.ACTIVE_DAYS])
  duration = convert_to_string(conditions[PerformanceCondition.DURATION])
  impressions = convert_to_string(conditions[PerformanceCondition.IMPRESSIONS])
  conversions = convert_to_string(conditions[PerformanceCondition.CONVERSIONS])
  conversion_value = convert_to_string(
      conditions[PerformanceCondition.CONVERSIONS_VALUE])
  ctr = convert_to_string(conditions[PerformanceCondition.CTR])
  clicks = convert_to_string(conditions[PerformanceCondition.CLICKS])

  if active_days == '':
    raise ValueError(
        'Minimum days elapsed from the creative upload date is empty.')
  else:
    conditions[PerformanceCondition.ACTIVE_DAYS] = convert_to_int(
        conditions[PerformanceCondition.ACTIVE_DAYS])

  if duration == '':
    raise ValueError('Evaluate duration of last N(Duration) days is empty.')
  else:
    conditions[PerformanceCondition.DURATION] = convert_to_int(
        conditions[PerformanceCondition.DURATION])

  if duration == '0':
    raise ValueError(
        'Evaluate duration of last N(Duration) days should be greater than 0.')
  else:
    conditions[PerformanceCondition.DURATION] = convert_to_int(
        conditions[PerformanceCondition.DURATION])

  metrics = [metric for metric in conditions[2:] if metric != '']
  if not metrics:
    raise ValueError(
        'Performance evaluation metrics are all empty. Please fill in at least one metric.'
    )

  if not impressions == '':
    conditions[PerformanceCondition.IMPRESSIONS] = convert_to_int(
        conditions[PerformanceCondition.IMPRESSIONS])
  if not conversions == '':
    conditions[PerformanceCondition.CONVERSIONS] = convert_to_int(
        conditions[PerformanceCondition.CONVERSIONS])
  if not conversion_value == '':
    conditions[PerformanceCondition.CONVERSIONS_VALUE] = convert_to_float(
        conditions[PerformanceCondition.CONVERSIONS_VALUE])
  if not ctr == '':
    conditions[PerformanceCondition.CTR] = convert_to_float(
        conditions[PerformanceCondition.CTR])
  if not clicks == '':
    conditions[PerformanceCondition.CLICKS] = convert_to_int(
        conditions[PerformanceCondition.CLICKS])

  return conditions


def get_performance_conditions_rows(sheets_service):
  """Gets the rows from the "Performance Conditions" sheet.

  Args:
    sheets_service: Google Sheet APIs service.

  Returns:
    conditions: An array that contains conditions for asset performance.

  Raises:
    HttpError: Unable to read the Performance Condition sheet due to wrong sheet
    id or name.
    Exception: If the Performance Condition Sheet is empty or unknown error
    occurs while retrieving data from the Performance Condition sheet.
  """
  conditions = []
  try:
    performance_condition_sheet = sheets_service.get_spreadsheet_values(
        _PERFORMANCE_CONDITION_SHEET_RANGE)

    if len(performance_condition_sheet) == 0:
      raise Exception(
          'Skipping the performance evaluation: Performance condition Sheet is empty.'
      )
    else:
      for val in performance_condition_sheet:
        if val:
          conditions.append(val[0])
        else:
          conditions.append('')

      if len(conditions) < _NUMBER_OF_PERFORMANCE_CONDITIONS:
        for _ in range(_NUMBER_OF_PERFORMANCE_CONDITIONS - len(conditions)):
          conditions.append('')

      conditions = check_performance_condition_value(conditions)

  except HttpError:
    print('Unable to read the Performance Condition sheet. '
          'Verify whether the sheet id/name is correct.')
  except Exception as e:
    print(repr(e))

  return conditions


def get_time_manged_sheet_id(sheets_service):
  """Get sheet id of Time Managed Sheet.

  Args:
    sheets_service: Google Sheet APIs service.

  Returns:
    time_managed_sheet_id: sheet id of Time Managed Sheet.

  Raises:
    Exception: If error occurs while retrieving the Time Managed Sheet ID.
  """
  try:
    time_managed_sheet_id = sheets_service.get_sheet_id_by_name(
        _TIME_MANAGE_SHEET_NAME)
  except Exception as e:
    print(f'Error while retrieving the Time Managed Sheet ID: {str(e)}')
  return time_managed_sheet_id


def remover_main(spreadsheet_ids, service_account, client_secret, ads_account):
  """Main function for creative_remover.py.

  Reads delete condition from spreadsheet, execute deleting actions
  and logs the actions back to history sheet.

  Args:
    spreadsheet_ids: creative mango Google sheets Id list.
    service_account: path to service account file.
    client_secret: client secret file path.
    ads_account: google-ads.yaml file path.
  """
  credential = auth.get_credentials_from_file(service_account_file=service_account, client_secret_file=client_secret)
  ads_service = ads_service_api.AdService(ads_account)

  for spreadsheet_id in spreadsheet_ids:
    sheets_service = sheets_api.SheetsService(credential, spreadsheet_id)
    time_managed_sheet_id = get_time_manged_sheet_id(sheets_service)

    time_managed_rows = get_time_managed_rows(sheets_service)
    delete_assets = time_managed(ads_service, sheets_service,
                                 time_managed_sheet_id, time_managed_rows)

    if delete_assets:
      print(f'Successfully deleted assets: {delete_assets}')
    else:
      print('No assets to delete')

    conditions = get_performance_conditions_rows(sheets_service)
    if conditions:
      new_time_managed_rows = get_time_managed_rows(sheets_service)
      update_perf_note_assets = performance_managed(ads_service, sheets_service,
                                                    conditions,
                                                    time_managed_sheet_id,
                                                    new_time_managed_rows)
      if update_perf_note_assets:
        print(
            'Successfully updated Performance Note for low performing assets: '
            f'{update_perf_note_assets}')
    else:
      print('No low performing assets to update')


if __name__ == '__main__':
  with open('config/setup.yaml', 'r') as ymlfile:
    cfg = yaml.safe_load(ymlfile)

  remover_main(
      spreadsheet_ids=cfg['spreadsheetIds'],
      service_account=cfg['serviceAccount'],
      client_secret=cfg['clientSecret'],
      ads_account=cfg['adsAccount'])

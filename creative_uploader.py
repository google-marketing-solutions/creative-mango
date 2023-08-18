#!/usr/bin/env python
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
"""Provides customized creative tool to upload assets.

Customer will put creative adgroup aliass, actions and links of the asset to a
uploading sheet.
And this tool will map the adgroup alias to mapping sheet and
upload the asset into matched campaign.
"""

import datetime
import enum
import time
import re
from urllib import parse
import yaml

import ads_api_error_translation
import ads_service_api
import auth
import drive_api
import image_handler
import sheets_api
import youtube_api

from google.ads import googleads
from googleapiclient.errors import HttpError

# Defined by customer's mapping size.
# Defined how many columns we want to use during the mapping.
_NUMBER_OF_ADGROUP_ALIAS_RULES = 1

# By definition, mapping sheet has one adgroup alias plus CID and AdGroupId.
_NUMBER_OF_MAPPING_COLUMNS = _NUMBER_OF_ADGROUP_ALIAS_RULES + 2
# By definition, uploading columns have
# AdGroupAlias, Creative Type, Creative Name, Creative URL or Text,
# Creative Name to Replace, Start, End, UsedAdGroupId.
_NUMBER_OF_UPLOADING_COLUMNS = 8

_ASSET_TEXT_LIMIT = 5  # Asset limits are 5 headlines, 5 descriptions each ad group.
_ASSET_MEDIA_LIMIT = 20  # Asset limits are 20 videos and 20 images each ad group.
# By definition, change history sheet has columns of 'Asset Name', 'Media Type',
#'Asset URL or Text', 'Start Date', 'End Date', 'Asset Name to be Replaced', 'Action'.
_CHANGE_HISTORY_SHEET_RANGE = 'Change History!A2:H'
# By definition, mapping sheet has columns of 'AdGroupAlias', 'Customer Id', 'Ad Group Id'.
# This is the range of mapping sheet.
_MAPPING_SHEET_RANGE = 'Mapping!A2:C'
# By definition, 'Upload Sheet' columns have
# AdGroupAlias, Creative Type, Creative Name, Creative URL or Text,
# Creative Name to Replace, Start, End, UsedAdGroupId.
_UPLOAD_SHEET_RANGE = 'Upload!A2:H'
# Change this variable to True if you want the tool to remove all punctuations
# from headline assets.
_TEXT_ASSET_AUTO_MODIFY = False

_USED_ADGROUP_COLUMN = 'Upload!H'
_TIME_MANAGED_SHEET_RANGE = 'Time Managed!A2:I'
_YOUTUBE_SHEET_RANGE = 'YT List!A2:Z'
_YT_URL = 'https://www.youtube.com/watch?v='

youtube_dict = {}


class MappingColumnMap(enum.IntEnum):
  """Enum class to indicate column indices in the mapping sheet."""
  ADGROUP_ALIAS = 0
  CUSTOMER_ID = 1
  AD_GROUP_ID = 2


class UploadColumnMap(enum.IntEnum):
  """Enum class to indicate column indices in the uploading sheet."""
  ADGROUP_ALIAS = 0
  CREATIVE_TYPE = 1
  CREATIVE_NAME_OR_TEXT = 2
  IMAGE_VIDEO_URL = 3
  REPLACE_ASSET = 4
  START_DATE = 5
  END_DATE = 6
  USED_ADGROUP_ID = 7
  ROW_INDEX = 8


def _write_upload_to_time_managed_sheet(sheets_service, uploading_row, asset_id,
                                        customer_id, ad_group_id):
  """Writes to time managed sheet.

  If asset is a time sensitive asset, we put it into time managed sheet.

  Args:
    sheets_service: Google Sheet APIs service.
    uploading_row: one uploaing row in uploading sheet.
    asset_id: asset id.
    customer_id: customer id.
    ad_group_id: ad group id.

  Raises:
    HttpError: If unable to read the Time Managed Sheet due to wrong sheet id or
    name.
    Exception: If unknown error occurs while writing to the Time Managed Sheet.
  """
  today = str(datetime.datetime.today().date())
  if not uploading_row[UploadColumnMap.START_DATE]:
    uploading_row[UploadColumnMap.START_DATE] = today
  time_managed_row_contents = [
      uploading_row[UploadColumnMap.ADGROUP_ALIAS],
      uploading_row[UploadColumnMap.CREATIVE_TYPE],
      uploading_row[UploadColumnMap.CREATIVE_NAME_OR_TEXT],
      uploading_row[UploadColumnMap.IMAGE_VIDEO_URL],
      customer_id,
      ad_group_id,
      asset_id,
      uploading_row[UploadColumnMap.START_DATE],
      uploading_row[UploadColumnMap.END_DATE],
  ]
  try:
    sheets_service.write_to_sheet(_TIME_MANAGED_SHEET_RANGE,
                                  [time_managed_row_contents])
  except HttpError:
    print('Unable to write to time managed sheet. '
          'Verify whether the time managed sheet id/name is correct.')
    return
  except Exception as error:
    print('Unable to write to time managed sheet.', repr(error))
    return


def process_asset_row_removal(ads_service, drive_service, uploading_row,
                              matched_campaign):
  """Removes asset from campaign.

  If the replacing column is not empty, the tool will remove the asset.
  New asset and existing asset's creative Type must match.

  Args:
    ads_service: Google Ads APIs service handler.
    drive_service: Google Drive APIs service handler.
    uploading_row: an array of string from uplading sheet.
    matched_campaign: matched campaign to execute the action.
  """
  if uploading_row[UploadColumnMap.REPLACE_ASSET]:
    remove_asset_by_name(ads_service, drive_service, uploading_row,
                         matched_campaign)
  # remove_asset_by_performance is not in used.
  # else:
  #   remove_asset_by_performance(ads_service, uploading_row, matched_campaign)


def remove_asset_by_performance(ads_service, uploading_row, matched_campaign):
  """Removes asset from campaign by performance.

  Args:
    ads_service: Google Ads APIs service handler.
    uploading_row: an array of string from uplading sheet.
    matched_campaigns: matched campaigns to execute the action.

  Raises:
    ValueError: If asset does not exist.
    TypeError: Unknown asset type.
  """
  asset_type = uploading_row[UploadColumnMap.CREATIVE_TYPE]
  customer_id = matched_campaign[0]
  ad_group_id = matched_campaign[1]
  (ad,
   ad_group_ad_type) = ads_service._get_ad_and_ad_type(customer_id, ad_group_id)

  # ACE campaigns (beta) currently do not have asset level metrics.
  # Not remove any asset by it's performance.
  if ad_group_ad_type == ads_service._google_ads_client.enums.AdTypeEnum.APP_ENGAGEMENT_AD:
    return

  if asset_type == 'DESCRIPTION':
    if ad['DESCRIPTION'] < _ASSET_TEXT_LIMIT:
      return
    asset_performance = ads_service._get_asset_performance_data(
        'DESCRIPTION', customer_id, ad_group_id)
    asset_id = _calculate_least_performance_asset(ads_service,
                                                  asset_performance)
    if not asset_id:
      raise ValueError(
          'Unable to find a DESCRIPTION to be removed by performance.')
    asset_value = ads_service._get_text_asset_value_by_asset_id(
        customer_id, asset_id)
    ads_service._remove_description_asset_from_campaign(asset_value,
                                                        customer_id,
                                                        ad_group_id)

  elif asset_type == 'HEADLINE':
    if ad['HEADLINE'] < _ASSET_TEXT_LIMIT:
      return
    asset_performance = ads_service._get_asset_performance_data(
        'HEADLINE', customer_id, ad_group_id)
    asset_id = _calculate_least_performance_asset(ads_service,
                                                  asset_performance)
    if not asset_id:
      raise ValueError(
          'Unable to find a HEADLINE to be removed by performance.')
    asset_value = ads_service._get_text_asset_value_by_asset_id(
        customer_id, asset_id)
    ads_service._remove_headline_asset_from_campaign(asset_value, customer_id,
                                                     ad_group_id)

  elif asset_type == 'IMAGE':
    if ad['IMAGE'] < _ASSET_MEDIA_LIMIT:
      return

    asset_performance = ads_service._get_asset_performance_data(
        'IMAGE', customer_id, ad_group_id)
    asset_performance = [row for row in asset_performance]
    asset_id = _calculate_least_performance_asset(ads_service,
                                                  asset_performance)
    if not asset_id:
      raise ValueError('Unable to find an IMAGE to be removed by performance.')
    ads_service._remove_image_asset_from_campaign(asset_id, customer_id,
                                                  ad_group_id)

  elif asset_type == 'VIDEO':
    if ad['VIDEO'] < _ASSET_MEDIA_LIMIT:
      return
    asset_performance = ads_service._get_asset_performance_data(
        'VIDEO', customer_id, ad_group_id)
    asset_id = _calculate_least_performance_asset(ads_service,
                                                  asset_performance)
    if not asset_id:
      raise ValueError('Unable to find an VIDEO to be removed by performance.')
    ads_service._remove_video_asset_from_campaign(asset_id, customer_id,
                                                  ad_group_id)
  else:
    raise TypeError(
        'Unknown asset type. Only DESCRIPTION, HEADLINE, IMAGE, VIDEO are allowed.'
    )


def _mask_performance_label(ads_service, performance_label):
  """Custom sorting logic for performance label.

  By definition, performance_label order is LOW < GOOD < BEST.

  Args:
    ads_service: Google Ads APIs service handler.
    performance_label: the value of LOW or GOOD or BEST.

  Returns:
    An int where 0 is LOW, 1 is GOOD and 2 is BEST.

  Raises:
    TypeError: Unknown asset type.
  """
  performance_label_enum = ads_service._google_ads_client.get_type(
      'AssetPerformanceLabelEnum', version='v6')
  if performance_label == performance_label_enum.AssetPerformanceLabel.LOW:
    return 0
  elif performance_label == performance_label_enum.AssetPerformanceLabel.GOOD:
    return 1
  elif performance_label == performance_label_enum.AssetPerformanceLabel.BEST:
    return 2
  else:
    raise TypeError(
        'Invalid performance label. Only LOW, GOOD and BEST are allowed.')


def _get_lowest_label_from_asset_list(ads_service, asset_performance):
  """Gets the lowest performance asset from an asset array.

  By definition, performance_label order is LOW < GOOD < BEST.

  Args:
    ads_service: Google Ads APIs service handler.
    asset_performance: An array of asset with asset performance label.
  Returns: An int where 0 is LOW, 1 is GOOD and 2 is BEST.
  """
  lowest_label = []
  for asset in asset_performance:
    if not lowest_label:
      lowest_label.append(asset)
    else:
      current_lowest_label = _mask_performance_label(
          ads_service, lowest_label[0].ad_group_ad_asset_view.performance_label)
      challenger_label = _mask_performance_label(
          ads_service, asset.ad_group_ad_asset_view.performance_label)

      if current_lowest_label == challenger_label:
        lowest_label.append(asset)
      elif current_lowest_label > challenger_label:
        lowest_label = []
        lowest_label.append(asset)

  return lowest_label


def _calculate_least_performance_asset(ads_service, asset_performance):
  """Calculates least performance asset.

  By definition, least performance is
    (1)performance_label is the LOWEST (LOW < GOOD < BEST).
       Assets which are PENDING, LEARNING or other states are not considered
       for being removed.
    (2)When two or more assets are within the same performance_label,
       the least performant asset is defined as the asset whose has highest of
       COST_PER_NEW_USER. COST_PER_NEW_USER is cost_micros / conversions.
       Note: if there are assets with conversions equal to zero,
       then the least performance assset is the one with highest cost_micros.

  Args:
    ads_service: Google Ads APIs service handler.
    asset_performance: an iterator of asset performance object. Each object
      contains asset id, asset type, performance_label, cost_micros and
      conversions.

  Returns:
    An asset id.
  """
  lowest_label = _get_lowest_label_from_asset_list(ads_service,
                                                   asset_performance)

  lowest_cost_per_user = None
  for asset in lowest_label:
    if lowest_cost_per_user:
      current_lowest_conversions = lowest_cost_per_user.metrics.conversions
      challenger_conversions = asset.metrics.conversions
      current_lowest_cost_micros = lowest_cost_per_user.metrics.cost_micros
      challenger_cost_micros = asset.metrics.cost_micros

      if not challenger_conversions and not current_lowest_conversions:
        if current_lowest_cost_micros < challenger_cost_micros:
          lowest_cost_per_user = asset
      elif not challenger_conversions:
        lowest_cost_per_user = asset
      elif not current_lowest_conversions:
        continue
      elif (current_lowest_cost_micros / current_lowest_conversions <
            challenger_cost_micros / challenger_conversions):
        lowest_cost_per_user = asset
    else:
      lowest_cost_per_user = asset

  if lowest_cost_per_user:
    return lowest_cost_per_user.ad_group_ad_asset_view.asset


def remove_asset_by_name(ads_service, drive_service, uploading_row,
                         matched_campaign):
  """Removes asset from campaign by resource name to replace with a new asset.

  Args:
    ads_service: Google Ads APIs service handler.
    drive_service: Google Drive APIs service handler.
    uploading_row: an array of string from uplading sheet.
    matched_campaign: matched campaign to execute the action.

  Raises:
    TypeError: Unknown asset type.
  """
  asset_type = uploading_row[UploadColumnMap.CREATIVE_TYPE]
  customer_id = matched_campaign[0]
  ad_group_id = matched_campaign[1]

  if asset_type == 'DESCRIPTION':
    ads_service._remove_description_asset_from_campaign(
        uploading_row[UploadColumnMap.REPLACE_ASSET], customer_id, ad_group_id)
  elif asset_type == 'HEADLINE':
    ads_service._remove_headline_asset_from_campaign(
        uploading_row[UploadColumnMap.REPLACE_ASSET], customer_id, ad_group_id)
  elif asset_type == 'IMAGE':
    image_resource_name = get_replace_image_resource_name(
        ads_service, drive_service, uploading_row, customer_id)
    if image_resource_name:
      ads_service._remove_image_asset_from_campaign(image_resource_name,
                                                    customer_id, ad_group_id)
    else:
      print("Replace image doesn't exist.")
  elif asset_type == 'VIDEO':
    youtube_resource_name = get_replace_video_resource_name(
        ads_service, uploading_row, customer_id)
    if youtube_resource_name:
      ads_service._remove_video_asset_from_campaign(youtube_resource_name,
                                                    customer_id, ad_group_id)
  else:
    raise TypeError(
        'Unknow asset type. Only DESCRIPTION, HEADLINE, IMAGE, VIDEO are allowed.'
    )


def get_replace_video_resource_name(ads_service, uploading_row, customer_id):
  """Get video asset resource name with YouTube ID or Drive Url.

  Args:
    ads_service: Google Ads APIs service handler.
    uploading_row: an array of string from uplading sheet.
    customer_id: target customer Id.

  Returns:
    youtube_resource_name: Video(YouTube) asset resource name.
  """
  replace_asset = uploading_row[UploadColumnMap.REPLACE_ASSET]
  # If replace asset is in resource name format, return it.
  if re.match('customers/\d+/assets/\d+$', replace_asset):
    return replace_asset

  # Find matching YouTube id in the YT List and get resource name with it.
  youtube_resource_name = get_video_resource_name(ads_service, customer_id,
                                                  replace_asset)

  return youtube_resource_name


def get_replace_image_resource_name(ads_service, drive_service, uploading_row,
                                    customer_id):
  """Get image asset resource name to replace the asset.

  Args:
    ads_service: Google Ads APIs service handler.
    drive_service: Google Drive APIs service handler.
    uploading_row: an array of string from uplading sheet.
    customer_id: target customer Id.

  Returns:
    image_resource_name: Image asset resource name.
  """
  replace_asset = uploading_row[UploadColumnMap.REPLACE_ASSET]
  # If replace asset is written in asset resource name format, return this value.
  if re.match('customers/\d+/assets/\d+$', replace_asset):
    return replace_asset

  image_resource_name = None
  image_asset_list = ads_service._get_image_asset_list(customer_id)
  # If replace asset is written in url format, download the image and compare md5 hash with existing image assets to find out the resource name.
  if 'http://' in replace_asset or 'https://' in replace_asset:
    image_url = uploading_row[UploadColumnMap.REPLACE_ASSET]
    image_resource_name, _ = image_handler.get_existing_image_asset(
        drive_service, image_asset_list, image_url, None)
  # If replace asset is written in image asset name format, compare image asset name with existing image assets to find out the resouce name
  else:
    image_name = uploading_row[UploadColumnMap.REPLACE_ASSET]
    image_resource_name, _ = image_handler.get_existing_image_asset(
        drive_service, image_asset_list, None, image_name)
  return image_resource_name


def upload_asset(ads_service, drive_service, sheets_service, uploading_row,
                 matched_campaign):
  """Uploads asset to campaign.

  Args:
    ads_service: Google Ads APIs service.
    sheets_service: Google Sheet APIs service.
    uploading_row: one uploaing row in uploading sheet.
    matched_campaign: all campaign which matched to the uploading adgroup alias.

  Returns:
    resource_name: asset resource name.

  Raises:
    TypeError: unknown asset type.
  """

  asset_type = uploading_row[UploadColumnMap.CREATIVE_TYPE]
  customer_id = matched_campaign[0]
  ad_group_id = matched_campaign[1]

  if asset_type == 'DESCRIPTION':
    resource_name = uploading_row[UploadColumnMap.CREATIVE_NAME_OR_TEXT]
    ads_service._add_description_asset_to_campaign(resource_name, customer_id,
                                                   ad_group_id)
  elif asset_type == 'HEADLINE':
    resource_name = uploading_row[UploadColumnMap.CREATIVE_NAME_OR_TEXT]
    ads_service._add_headline_asset_to_campaign(resource_name, customer_id,
                                                ad_group_id)
  elif asset_type == 'IMAGE':
    image_url = uploading_row[UploadColumnMap.IMAGE_VIDEO_URL]
    image_name = uploading_row[UploadColumnMap.CREATIVE_NAME_OR_TEXT]
    resource_name = get_upload_image_resource_name(ads_service, drive_service,
                                                   customer_id, image_url,
                                                   image_name)
    ads_service._add_image_asset_to_campaign(resource_name, customer_id,
                                             ad_group_id)
  elif asset_type == 'VIDEO':
    resource_name = get_video_resource_name(
        ads_service, customer_id,
        uploading_row[UploadColumnMap.IMAGE_VIDEO_URL])

    ads_service._add_video_asset_to_campaign(resource_name, customer_id,
                                             ad_group_id)
  else:
    raise TypeError(
        'Unknow asset type. Only DESCRIPTION, HEADLINE, IMAGE, VIDEO are allowed.'
    )
  # Copy uploaded resources to time managed sheet
  _write_upload_to_time_managed_sheet(sheets_service, uploading_row,
                                      resource_name, customer_id, ad_group_id)

  return resource_name


def get_video_resource_name(ads_service, customer_id, video_asset):
  """Get video asset resource name by searching for YouTube id in the YT List Sheet.

  (youtube_dict)

  Args:
    ads_service: Google Ads APIs service handler.
    customer_id: target customer Id.
    video_asset: YouTube id or Drive URL to upload / replace.

  Returns:
    youtube_resource_name: Video(YouTube) asset resource name.
  """
  # Find matching YouTube id in the YT List with drive url and create new video asset with it.
  if 'http://' in video_asset or 'https://' in video_asset:
    youtube_id = youtube_dict.get(video_asset)
  else:
    youtube_id = video_asset
  youtube_asset = ads_service._create_youtube_asset(youtube_id, customer_id)
  youtube_resource_name = youtube_asset.results[0].resource_name

  return youtube_resource_name


def get_upload_image_resource_name(ads_service, drive_service, customer_id,
                                   image_url, image_name):
  """Search for the same image asset in the account with asset name or image data and return image resource name.

  When there is an existing image asset with the same content but a different
  name, the new name will be dropped silently.

  If the same image doesn't exist, create new image asset and return its
  resource name.

  Args:
    ads_service: Google Ads APIs service handler.
    drive_service: Google Drive APIs service handler.
    customer_id: target customer Id.
    image_url: image asset content url.
    image_name: image asset name.

  Returns:
    image_resource_name: Image asset resource name.
  """
  image_buffer = drive_service._download_asset(image_url)
  image_asset = ads_service._create_image_asset(image_name, image_buffer,
                                                customer_id)
  image_resource_name = image_asset.results[0].resource_name

  return image_resource_name


def add_log_message(uploading_row, matched_campaign, log, resource_name=''):
  """Constructs the messages to write back to change history.

  Args:
    uploading_row: contents of the row as an array in uploading sheet.
    matched_campaign: matched campaign tuple where the tuple is (customer_id,
      ad_group_id)].
    log: error message. resource_name(optional): asset resource name.
      ('customer/{customerId}/assets/{assetId}')

  Returns:
    result_log: An array of result log strings.
  """
  result_log = uploading_row.copy()[:4]
  if matched_campaign:
    customer_id = matched_campaign[0]
    ad_group_id = matched_campaign[1]
  else:
    customer_id = ''
    ad_group_id = ''
  result_log.extend([
      customer_id, ad_group_id, resource_name,
      uploading_row[UploadColumnMap.START_DATE],
      uploading_row[UploadColumnMap.END_DATE], log,
      str(datetime.datetime.today())
  ])

  return result_log


def process_asset_row(ads_service, drive_service, sheets_service, uploading_row,
                      matched_campaigns):
  """Executes one row of actions in uploading sheet.

  For one row of action in uploading sheet, it will
  remove an asset if there is no space for the new asset.
  And then, it uploads one new asset to the matched campaigns.

  Args:
    ads_service: Google Ads APIs service.
    drive_service: Google Drive APIs service.
    sheets_service: Google Sheet APIs service.
    uploading_row: contents of the row as an array in uploading sheet.
    matched_campaigns: List of matched campaigns tuples, each tuple contains
      customer id and ad group id. [(customer_id1, ad_group_id1), ....,
      (customer_idN, ad_group_idN)]

  Returns:
    An array of array of string to write back to change sheet.

  Raises:
    GoogleAdsException: If Google Ads API error occurs.
    ValueError: If value of asset is not in the correct format.
    HttpError: Wrong image link.
    Exception: Unknown error occurs while uploading or removing the asset.
  """
  execution_results = []
  success_campaigns = []

  for matched_campaign in matched_campaigns:
    try:
      process_asset_row_removal(ads_service, drive_service, uploading_row,
                                matched_campaign)
    except googleads.errors.GoogleAdsException as failures:
      errors_result = ''
      for error in failures.failure.errors:
        errors_result += ads_api_error_translation.translate_ads_api_errors(
            error.message)
      result_log = add_log_message(
          uploading_row, matched_campaign,
          'Unable to remove the asset. Errors: ' + errors_result)
    except ValueError as error:
      result_log = add_log_message(
          uploading_row, matched_campaign,
          'Unable to remove the asset. Errors: ' + str(error.args[0]))
    except HttpError:
      result_log = add_log_message(
          uploading_row, matched_campaign, 'Unable to remove the asset. '
          'Kindly check that the image link is correct.')
    except Exception as error:
      result_log = add_log_message(uploading_row, matched_campaign,
                                   'Unable to remove the asset.' + repr(error))
    else:
      try:
        resource_name = upload_asset(ads_service, drive_service, sheets_service,
                                     uploading_row, matched_campaign)
        result_log = add_log_message(uploading_row, matched_campaign,
                                     'Action succeed.', resource_name)
        success_campaigns.append(matched_campaign[1])
      except googleads.errors.GoogleAdsException as failures:
        errors_result = ''
        for error in failures.failure.errors:
          errors_result += ads_api_error_translation.translate_ads_api_errors(
              error.message)
        result_log = add_log_message(
            uploading_row, matched_campaign,
            'Unable to upload the asset. Errors: ' + errors_result)
      except ValueError as error:
        result_log = add_log_message(
            uploading_row, matched_campaign,
            'Unable to upload the asset. Errors: ' + str(error.args[0]))
      except HttpError:
        result_log = add_log_message(
            uploading_row, matched_campaign, 'Unable to upload the asset. '
            'Kindly check that the image link is correct.')
      except Exception as error:
        result_log = add_log_message(
            uploading_row, matched_campaign,
            'Unable to upload the asset.' + repr(error))

    execution_results.append(result_log)
  return (execution_results, '/'.join(success_campaigns))


def map_to_adgroup(uploading_row, mapping_rows):
  """Maps adgroup alias to ad campaigns.

  By definition, adgroup_alias indicates which campaign it should be uploaded
  to. And mapping_rows contains the mapping name with customer id and ad group
  id.

  Args:
    uploading_row: uploading_row.
    mapping_rows: an array of arrays. Each subarray has the mapping rule from
      mapping sheet.

  Returns:
    (matched, [(customer_id1, ad_group_id1), ...., (customer_idN,
    ad_group_idN)])
  """
  matched_campaigns = []
  adgroup_alias = uploading_row[UploadColumnMap.ADGROUP_ALIAS]
  used_adgroup_id = uploading_row[UploadColumnMap.USED_ADGROUP_ID]
  matched = False
  for mapping_row in mapping_rows:
    if adgroup_alias.upper() == mapping_row[
        MappingColumnMap.ADGROUP_ALIAS].upper():
      matched = True
      ad_group_id = mapping_row[MappingColumnMap.AD_GROUP_ID]
      if used_adgroup_id.find(ad_group_id) == -1:
        matched_campaigns.append(
            (mapping_row[MappingColumnMap.CUSTOMER_ID].replace('-', ''),
             ad_group_id))
  return (matched, matched_campaigns)


def handle_start_date_not_today(sheets_service, uploading_sheet_rows):
  """Handles start date not today.

  Args:
    sheets_service: Google Sheet APIs service.
    uploading_sheet_rows: an array of arrays. Each subarray has the uploading
      action from uploading sheet.

  Returns:
    Uploading rows less equal to today

  Raises:
    ValueError: If Start_date is not in the correct format.
    Exception: If unknown error occurs while writing to the Change History
    Sheet.
  """
  today = datetime.datetime.today().date()
  today_uploading_rows = []
  for uploading_row in uploading_sheet_rows:
    if uploading_row[UploadColumnMap.START_DATE]:
      try:
        date_split = datetime.datetime.strptime(
            uploading_row[UploadColumnMap.START_DATE], '%Y-%m-%d')
        row_date = datetime.datetime(date_split.year, date_split.month,
                                     date_split.day).date()
      except ValueError as error:
        try:
          uploading_row.append(
              'START_DATE is not in the correct format of YYYY-MM-DD.')
          sheets_service.write_to_sheet(_CHANGE_HISTORY_SHEET_RANGE,
                                        [uploading_row])
        except Exception as error:
          print('Unable to write to change history spreadsheet. '
                'Verify START_DATE is in the correct format (YYYY-MM-DD).')
      else:
        if row_date <= today:
          today_uploading_rows.append(uploading_row)
    else:
      today_uploading_rows.append(uploading_row)

  return today_uploading_rows


def upload_video_to_youtube(drive_service, youtube_secrets, url, asset_name,
                            new_youtube_ids, youtube_service_enable):
  """Uploads a video to YouTube with a given url and name.

  And adds the id to the list of new_youtube_ids.

  Args:
    drive_service: Google Drive APIs service.
    youtube_secrets: YouTube API service oAuth secret file.
    url: string, url of the video to be uploaded. Can be from Drive or YT.
    asset_name: name of the video to be uploaded.
    new_youtube_ids: list of ids of uploaded videos on YouTube.
    youtube_service_enable: True or False whether youtube api service is
      enabled.
  """

  if not url:
    return
  if url.find('http') == -1:
    youtube_dict[url] = url
    return
  if _YT_URL in url:
    youtube_dict[url] = parse.urlparse(url).query.split('v=')[-1].split('&')[0]
    return
  if not youtube_service_enable:
    return

  youtube_service = youtube_api.YTService(youtube_secrets)
  if not youtube_dict.get(url):
    buffer = drive_service._download_asset(url)
    youtube_id = youtube_service.get_youtube_id(buffer, asset_name)
    # Slow down after uploading Video as YouTube Video requires a while to be ready.
    time.sleep(1)
    if youtube_id:
      youtube_dict[url] = youtube_id
      new_youtube_ids.append([_YT_URL + youtube_id, url, asset_name])
    else:
      youtube_dict[url] = url


def retrieve_youtube_url(drive_service, sheets_service, uploading_sheet_rows,
                         youtube_secrets, youtube_service_enable):
  """Given rows of the upload sheet, it retrieves video url and uploads it to yt.

  Args:
    drive_service: Google Drive APIs service.
    sheets_service: Google Sheet APIs service.
    uploading_sheet_rows: an array of arrays. Each subarray has the uploading
      action from uploading sheet.
    youtube_secrets: YouTube API Secrets in a json file.
    youtube_service_enable: True or False whether youtube api service is
      enabled.

  Raises:
    Exception: Unable to upload YouTube Video. Verify your URL is correct.
  """
  new_youtube_ids = []

  # Get data from YT List Sheet
  try:
    youtube_sheet_rows = sheets_service.get_spreadsheet_values(
        _YOUTUBE_SHEET_RANGE)
    for row in youtube_sheet_rows:
      if row:
        youtube_dict[row[1]] = row[0].split(_YT_URL)[1]
  except:
    pass

  # If uploading video asset to YouTube  channel via API is enabled,
  # upload to YouTube chanel and return YouTube id
  for row in uploading_sheet_rows:
    if row[UploadColumnMap.CREATIVE_TYPE] != 'VIDEO':
      continue
    try:
      asset_name = row[UploadColumnMap.CREATIVE_NAME_OR_TEXT]
      if not asset_name:
        asset_name = row[UploadColumnMap.ADGROUP_ALIAS]

      upload_video_to_youtube(drive_service, youtube_secrets,
                              row[UploadColumnMap.IMAGE_VIDEO_URL], asset_name,
                              new_youtube_ids, youtube_service_enable)
    except Exception:
      result_log = add_log_message(
          row[:7], '',
          'Unable to upload YouTube Video. Verify your URL is correct.')
      sheets_service.write_to_sheet(_CHANGE_HISTORY_SHEET_RANGE, [result_log])
  if youtube_service_enable:
    sheets_service.write_to_sheet(_YOUTUBE_SHEET_RANGE, new_youtube_ids)
    if not new_youtube_ids:
      return
    youtube_service = youtube_api.YTService(youtube_secrets)
    retry_timeout = 60
    current_count = 0
    youtube_id_list = [id[0].replace(_YT_URL, '') for id in new_youtube_ids]
    print('Wait until youtube asset upload finished.')
    while not youtube_service.check_upload_finished(
        youtube_id_list) and current_count < retry_timeout:
      current_count += 1
      time.sleep(1)
    if current_count >= retry_timeout:
      print(
          'Time limit {}s exceeded! Video asset upload may fail. Please re-run the script if the failure occurs.'
          .format(retry_timeout))
    else:
      print('Upload finished! Time spent: {}s'.format(current_count + 1))


def get_mapping_rows(sheets_service):
  """Gets the rows from the sheet that contains the mapping.

  Args:
    sheets_service: Google Sheet APIs service.

  Returns:
    an array of arrays. Each subarray contains the mapping data.

  Raises:
    HttpError: unable to read the Mapping Sheet due to wrong sheet id or name.
    Exception: If unknown error occurs while reading the Mapping Sheet.
  """
  try:
    mapping_sheet_rows = sheets_service.get_spreadsheet_values(
        _MAPPING_SHEET_RANGE)
  except HttpError:
    print('Unable to read the mapping sheet. '
          'Verify whether the mapping sheet id/name is correct.')
  except Exception as error:
    print('Unable to read the mapping sheet. ', repr(error))

  # Checks the correctness of mapping sheets.
  mapping_sheet_rows = [
      row for row in mapping_sheet_rows
      if len(row) >= _NUMBER_OF_MAPPING_COLUMNS
  ]
  return mapping_sheet_rows


def text_asset_auto_modify(text_to_modify, asset_type):
  """Modify text assets.

  Remove punctuation in Headline assets.
  Remove punctucation used sequentially in description.

  Args:
    text_to_modify: text asset to modify.
    asset_type: asset type.

  Returns:
    new_text: modified text.
  """
  # Avoid using punctuation in Headline assets.
  punc = """!”#$%&\()*+,-./:;<=>?@[\\]^_`{|}~"""
  if asset_type == 'HEADLINE':
    table_ = str.maketrans('', '', punc)
    new_text = text_to_modify.translate(table_)
  # Avoid using the same punctucation sequentially in description.
  if asset_type == 'DESCRIPTION':
    text_in_list = list(text_to_modify)
    for idx, word in enumerate(text_in_list[:-1]):
      if word in punc:
        if text_in_list[idx + 1] == word:
          text_in_list[idx] = ''
    new_text = ''.join(text_in_list)

  return new_text


def format_uploading_sheet_value(uploading_sheet_rows):
  """Change the value of the Uploading Sheet to the correct format.

  Args:
    uploading_sheet_rows: Uploading Sheet rows.

  Returns:
    result_uploading_rows: an array of arrays. Each subarray contains the data
    for upload.
  """
  result_uploading_rows = []
  for index in range(len(uploading_sheet_rows)):
    uploading_row = uploading_sheet_rows[index]
    if len(uploading_row) == 0:
      continue
    if uploading_row[UploadColumnMap.ADGROUP_ALIAS]:
      # Formating the uploading rows so they all have same number of columns.
      while len(uploading_row) < _NUMBER_OF_UPLOADING_COLUMNS:
        uploading_row.append('')
      # Making CREATIVE_TYPE not case-sensitive.
      uploading_row[UploadColumnMap.CREATIVE_TYPE] = uploading_row[
          UploadColumnMap.CREATIVE_TYPE].upper()
      if _TEXT_ASSET_AUTO_MODIFY:
        # Avoid using punctuation in Headline assets.
        text_to_modify = uploading_row[UploadColumnMap.CREATIVE_NAME_OR_TEXT]
        asset_type = uploading_row[UploadColumnMap.CREATIVE_TYPE]
        uploading_row[
            UploadColumnMap.CREATIVE_NAME_OR_TEXT] = text_asset_auto_modify(
                text_to_modify, asset_type)

      uploading_row.append(index + 2)
      result_uploading_rows.append(uploading_row)

  return result_uploading_rows


def get_uploading_rows(sheets_service):
  """Gets the rows from the sheet that contains the upload data.

  Args:
    sheets_service: Google Sheet APIs service.

  Returns:
    an array of arrays. Each subarray contains the data for upload.

  Raises:
    HttpError: If unable to read the uploading sheet due to wrong sheet id or
    name.
    Exception: If unknown error occurs while reading the uploading sheet.
  """
  try:
    uploading_sheet_rows = sheets_service.get_spreadsheet_values(
        _UPLOAD_SHEET_RANGE)
  except HttpError:
    print('Unable to read the uploading sheet. '
          'Verify whether the uploading sheet id/name is correct.')
    return
  except Exception as error:
    print('Unable to read the uploading sheet.', repr(error))
    return

  result_uploading_rows = format_uploading_sheet_value(uploading_sheet_rows)
  result_uploading_rows = handle_start_date_not_today(sheets_service,
                                                      result_uploading_rows)
  return result_uploading_rows


def update_used_ad_group_id(sheets_service, uploading_row, success_campaigns):
  """Updates the used adgroup id column in the uploading row.

  Args:
    sheets_service: Google Sheet APIs service.
    uploading_row: row from the Upload sheet.
    success_campaigns: string of matched ad group ids.
  """
  used_ad_group_id = f'{uploading_row[UploadColumnMap.USED_ADGROUP_ID]}/{success_campaigns}'
  sheets_service.update_sheet_columns(
      _USED_ADGROUP_COLUMN + str(uploading_row[UploadColumnMap.ROW_INDEX]),
      [[used_ad_group_id]])


def uploader_main(spreadsheet_ids, service_account, client_secret, ads_account,
                  youtube_secrets, youtube_service_enable):
  """Main function for creative_uploader.py.

  Reads from uploading and mapping sheet, execute uploading actions
  and logs the actions back to history sheet.

  Args:
    spreadsheet_ids: Creative mango Google sheets Id list.
    service_account: path to service account file.
    client_secret: client secret file path.
    ads_account: google-ads.yaml file path.
    youtube_secrets: oAuth credential for YouTube API.
    youtube_service_enable: If true, tool will upload videos to YouTube channel.

  Raises:
    Exception: If error occurs while updating the Sheets.
  """
  credential = auth.get_credentials_from_file(
      service_account_file=service_account, client_secret_file=client_secret)
  ads_service = ads_service_api.AdService(ads_account)
  drive_service = drive_api.DriveService(credential)

  for spreadsheet_id in spreadsheet_ids:
    sheets_service = sheets_api.SheetsService(credential, spreadsheet_id)

    mapping_sheet_rows = get_mapping_rows(sheets_service)
    uploading_sheet_rows = get_uploading_rows(sheets_service)

    # Retrieve YouTube url and if youtubeServiceEnable is true,
    # upload video to YouTube and update YT List
    retrieve_youtube_url(drive_service, sheets_service, uploading_sheet_rows,
                         youtube_secrets, youtube_service_enable)

    for uploading_row in uploading_sheet_rows:
      (matched, matched_campaigns) = map_to_adgroup(uploading_row,
                                                    mapping_sheet_rows)
      if matched:
        (execution_results,
         success_campaigns) = process_asset_row(ads_service, drive_service,
                                                sheets_service, uploading_row,
                                                matched_campaigns)
        if success_campaigns:
          try:
            update_used_ad_group_id(sheets_service, uploading_row,
                                    success_campaigns)
          except Exception:
            print('Unable to update UsedAdGroupId in the Mapping Sheet')

        try:
          sheets_service.write_to_sheet(_CHANGE_HISTORY_SHEET_RANGE,
                                        execution_results)
        except Exception:
          print('Unable to write to change history spreadsheet. '
                'Verify whether the change history sheet id/name is correct.')


if __name__ == '__main__':
  with open('config/setup.yaml', 'r') as ymlfile:
    cfg = yaml.safe_load(ymlfile)

  uploader_main(
      spreadsheet_ids=cfg['spreadsheetIds'],
      service_account=cfg['serviceAccount'],
      client_secret=cfg['clientSecret'],
      ads_account=cfg['adsAccount'],
      youtube_secrets=cfg['youtubeSecret'],
      youtube_service_enable=cfg['youtubeServiceEnable'])

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

import datetime
import enum
import yaml

import ads_api_error_translation
import ads_service_api
import auth
import sheets_api

from google.ads import googleads
from googleapiclient.errors import HttpError

# Do not change this setting
_MAPPING_SHEET_NAME = 'Mapping'
_MAPPING_SHEET_RANGE = f'{_MAPPING_SHEET_NAME}!A2:K'
_MAPPING_SHEET_DATE_COLUMN = f'{_MAPPING_SHEET_NAME}!N1'

# Change this variable to True if you want the tool to automatically fill in the AdGroupAlias with AppId or campaign name.
# Select either _DEFAULT_ALIAS_APPID(app id) or _DEFAULT_ALIAS_CAMPAIGN(campaign name) for default AdGroupAlias.
_DEFAULT_ALIAS_APPID = False
_DEFAULT_ALIAS_CAMPAIGN = False

_TODAY = datetime.datetime.today()


class MappingColumnMap(enum.IntEnum):
  """Enum class to indicate column indices in the mapping sheet."""
  ADGROUP_ALIAS = 0
  CUSTOMER_ID = 1
  AD_GROUP_ID = 2
  AD_GROUP_NAME = 3
  CAMPAIGN_ID = 4
  CAMPAIGN_NAME = 5
  APP_ID = 6
  NUMBER_OF_HEADLINES = 7
  NUMBER_OF_DESCRPITIONS = 8
  NUMBER_OF_IMAGES = 9
  NUMBER_OF_VIDEOS = 10


def get_all_child_customer_ids(ads_service, login_customer_id=None):
  """Get all accessible child account customer ids

  If login customer id is set in the google ads account file (usually for
  clients using MCC account), use this customer id.
  If not, retrieve all customer ids accessible with the service account.

  Args:
    ads_service: Google Ads APIs service handler.
    login_customer_id: Optional manager account ID. If none provided, this
      method will instead list the accounts accessible from the authenticated
      Google Ads account.

  Returns:
    all_child_customer_ids: List of child customer ids
  """
  all_child_customer_ids = []

  # A collection of customer IDs to handle.
  seed_customer_ids = []

  # If a Manager ID was provided in the customerId parameter, it will be the only ID in the list.
  # Otherwise, we will issue a request for all customers accessible by this authenticated Google account.
  if login_customer_id:
    seed_customer_ids = [login_customer_id]
  else:
    print(
        'No manager ID is specified. The example will print the hierarchies of all accessible customer IDs.'
    )
    customer_resource_names = get_customer_resource_names(ads_service)
    for customer_resource_name in customer_resource_names:
      seed_customer_id = get_seed_customer_id(ads_service,
                                              customer_resource_name)
      seed_customer_ids.append(seed_customer_id)

  for seed_customer_id in seed_customer_ids:
    child_accounts = get_child_accounts(ads_service, seed_customer_id)
    for child_account in child_accounts:
      if child_account not in all_child_customer_ids:
        all_child_customer_ids.append(child_account)

  return all_child_customer_ids


def get_customer_resource_names(ads_service):
  """Get all accessible customer resource names.

  Args:
    ads_service: Google Ads APIs service handler.

  Returns:
    customer_resource_names: List of customer resource names.

  Raises:
    GoogleAdsException: Google Ads API error.
    Exception: Unknown error.
  """
  try:
    customer_resource_names = ads_service._list_accessible_customers()
  except googleads.errors.GoogleAdsException as failures:
    print(get_error_message(failures.failure.errors))
  except Exception:
    print('Unknown error occured while getting list of accessible customers')

  return customer_resource_names


def get_seed_customer_id(ads_service, customer_resource_name):
  """Get customer id from the customer resource name.

  Args:
    ads_service: Google Ads APIs service handler.
    customer_resource_name: Google Ads customer resource name.

  Returns:
    seed_customer_id: customer id.

  Raises:
    GoogleAdsException: Google Ads API error.
    Exception: Unknown error.
  """
  try:
    seed_customer_id = ads_service._get_customer_id(customer_resource_name)
  except googleads.errors.GoogleAdsException as failures:
    print(get_error_message(failures.failure.errors))
  except Exception:
    print('Unknown error occured while getting customer id')
  return seed_customer_id


def get_child_accounts(ads_service, seed_customer_id):
  """Get all child accounts under seed customer id.

  Args:
    ads_service: Google Ads APIs service handler.
    seed_customer_id: MCC account customer id.

  Returns:
    child_accounts: List of child account ids.

  Raises:
    GoogleAdsException: Google Ads API error.
    Exception: Unknown error.
  """
  try:
    child_accounts = ads_service._get_all_child_accounts(seed_customer_id)
  except googleads.errors.GoogleAdsException as failures:
    print(get_error_message(failures.failure.errors))
  except Exception:
    print(
        'Unknown error occured while getting list of child account customer ids'
    )

  return child_accounts


def get_error_message(errors):
  """Concatenates multiple error messages into one.

  And calls the ads_api_error_translation for each error translation.

  Args:
    errors: list of errors to be concatenated after translation.

  Returns:
    error_message: Concatenated message.
  """
  error_message = ''
  error_messages = []
  for error in errors:
    error_messages.append(
        ads_api_error_translation.translate_ads_api_errors(error.message))
  error_message = ' '.join(error_messages)

  return error_message


def get_campaign_ad_group_list(ads_service, customer_ids):
  """Get campaign and ad group info including the current number of assets.

  Args:
    ads_service: Google Ads APIs service handler.
    customer_ids: List of customer ids.

  Returns:
    campaign_ad_group_list: List of campaigns and ad group info.

  Raises:
    GoogleAdsException: If Google Ads API error occurs.
    Exception: If unknown error occurs.
  """
  campaign_ad_group_list = []
  for customer_id in customer_ids:
    try:
      results = ads_service._get_campaign_ad_groups(customer_id)
    except googleads.errors.GoogleAdsException as failures:
      print(get_error_message(failures.failure.errors))
    except Exception:
      print(
          f'Unknown error occured while getting campaign and ad group info of customer [{customer_id}]'
      )

    ad_group_id_list = []
    for row in results:
      ad_group_id_list.append(str(row.ad_group.id))
    assetInfo = ads_service._get_ad_and_ad_type_by_ad_group_id_list(
        customer_id, ad_group_id_list)

    for row in results:
      ad_group_id = str(row.ad_group.id)
      ad_group_name = row.ad_group.name
      campaign_id = str(row.campaign.id)
      campaign_name = row.campaign.name
      app_id = row.campaign.app_campaign_setting.app_id

      # Get number of assets in the ad group
      try:
        number_of_assets = assetInfo[ad_group_id]
        number_of_headline = number_of_assets[0]['HEADLINE']
        number_of_description = number_of_assets[0]['DESCRIPTION']
        number_of_image = number_of_assets[0]['IMAGE']
        number_of_video = number_of_assets[0]['VIDEO']

        ad_group_alias = ''
        # Default ad group alias by app id. (return the last word in the app id.)
        if _DEFAULT_ALIAS_APPID:
          ad_group_alias = app_id.split('.')[-1]
        # Default ad group alias by campaign name. (campaign name format: abc.example.xyz.{ad_group_alias}-abc
        # If campaign name is not in this format, return whole campaign name.)
        elif _DEFAULT_ALIAS_CAMPAIGN:
          try:
            campaign_name_split = campaign_name.split('.')
            if len(campaign_name_split) > 1:
              ad_group_alias = campaign_name.split('.')[-1].split('-')[0]
            else:
              ad_group_alias = campaign_name
          except Exception:
            ad_group_alias = campaign_name

        campaign_ad_group_list.append([
            ad_group_alias, customer_id, ad_group_id, ad_group_name,
            campaign_id, campaign_name, app_id, number_of_headline,
            number_of_description, number_of_image, number_of_video
        ])
      except googleads.errors.GoogleAdsException as failures:
        print(get_error_message(failures.failure.errors))
      except Exception:
        print(
            f'Unknown error occured while getting number of assets in ad group [{ad_group_id}]'
        )

  return campaign_ad_group_list


def get_mapping_rows(sheets_service):
  """Read mapping sheet.

  Args:
    sheets_service: Google Sheet api service.

  Returns:
    mapping_sheet_rows: data in the mapping sheet.

  Raises:
    HttpError: If unable to read the Mapping sheet due to wrong sheet id or
    name.
    Exception: If unknown error occurs while reading the Mapping Sheet.
  """
  try:
    mapping_sheet_rows = sheets_service.get_spreadsheet_values(
        _MAPPING_SHEET_RANGE)
  except HttpError:
    print('[HttpError] Unable to read the mapping sheet. '
          'Verify whether the mapping sheet id/name is correct.')
    return
  except Exception as error:
    print('Unable to read the mapping sheet. ' + repr(error))
    return

  # Mapping row should have at least 3 columns (AdGroupAlias, CustomerId, Ad Group Id)
  mapping_sheet_rows = [row for row in mapping_sheet_rows if len(row) >= 3]
  return mapping_sheet_rows


def init_mapping_sheet(sheets_service, campaign_ad_group_list):
  """Initiate mapping sheet with campaign & ad group info.

  Args:
    sheet_service: Google Sheet api service.
    campaign_ad_group_list: campaign and ad group info with current number of
      assets.

  Raises:
    HttpError: If unable to read the Mapping sheet due to wrong sheet id or
    name.
    Exception: If unknown error occurs while reading the Mapping Sheet.
  """
  try:
    sheets_service.write_to_sheet(_MAPPING_SHEET_RANGE, campaign_ad_group_list)
  except HttpError:
    print('[HttpError] Unable to write to the mapping sheet.')
  except Exception as error:
    print('Unable to write to the mapping sheet. ', repr(error))


def write_new_mapping_rows(sheets_service, new_mapping_rows):
  """Clear current mapping sheet and write new mapping rows with up-to-date campaign & ad group info.

  Args:
    sheet_service: Google Sheet api service.
    new_mapping_rows: campaign and ad group info with current number of assets.

  Raises:
    HttpError: If unable to read the Mapping sheet due to wrong sheet id or
    name.
    Exception: If unknown error occurs while reading the Mapping Sheet.
  """
  try:
    sheets_service.clear_sheet_range(_MAPPING_SHEET_RANGE)
    sheets_service.write_to_sheet(_MAPPING_SHEET_RANGE, new_mapping_rows)
  except HttpError:
    print('[HttpError] Unable to write to the mapping sheet.')
  except Exception as error:
    print('Unable to write to the mapping sheet. ', repr(error))


def update_date_in_sheet(sheets_service):
  """ Update last update date in the mapping sheet.

  Args:
    sheet_service: Google Sheet api service.

  Raises:
    HttpError: If unable to read the Mapping sheet due to wrong sheet id or
    name.
    Exception: If unknown error occurs while reading the Mapping Sheet.
  """
  try:
    sheets_service.update_sheet_columns(_MAPPING_SHEET_DATE_COLUMN,
                                        [[str(_TODAY)]])
  except HttpError:
    print('[HttpError] Unable to write to the mapping sheet.')
  except Exception as error:
    print('Unable to write to the mapping sheet. ', repr(error))


def refresh_mapping_main(spreadsheet_ids, service_account, client_secret, ads_account):
  """Main function for refresh_mapping_sheet.py.

  Update Mapping Sheet with up-to-date customer account information.

  Args:
    spreadsheet_ids: Google Sheets Id.
    service_account: path to service account file.
    client_secret: client secret file path.
    ads_account: google-ads.yaml file path.
  """
  credential = auth.get_credentials_from_file(service_account, client_secret)
  ads_service = ads_service_api.AdService(ads_account)

  for spreadsheet_id in spreadsheet_ids:
    sheets_service = sheets_api.SheetsService(credential, spreadsheet_id)

    # Step 1. Get Child Customer Ids
    login_customer_id = None
    with open(ads_account) as file:
      account_file = yaml.safe_load(file)
      if 'login_customer_id' in account_file.keys():
        login_customer_id = str(account_file['login_customer_id'])
    all_child_customer_ids = get_all_child_customer_ids(ads_service,
                                                        login_customer_id)

    # Step 2. Get campaign & ad group info
    campaign_ad_group_list = get_campaign_ad_group_list(ads_service,
                                                        all_child_customer_ids)

    # Step 3. Match with Mapping Sheet
    mapping_sheet_rows = get_mapping_rows(sheets_service)
    if mapping_sheet_rows:
      new_mapping_rows = []
      for row in campaign_ad_group_list:
        ad_group_id = row[MappingColumnMap.AD_GROUP_ID]
        for mapping_row in mapping_sheet_rows:
          mapping_ad_group_id = mapping_row[MappingColumnMap.AD_GROUP_ID]
          if ad_group_id == mapping_ad_group_id:
            if _DEFAULT_ALIAS_APPID or _DEFAULT_ALIAS_CAMPAIGN:
              if mapping_row[MappingColumnMap.ADGROUP_ALIAS] != '':
                row[MappingColumnMap.ADGROUP_ALIAS] = mapping_row[
                    MappingColumnMap.ADGROUP_ALIAS]
            else:
              row[MappingColumnMap.ADGROUP_ALIAS] = mapping_row[
                  MappingColumnMap.ADGROUP_ALIAS]
            break
        new_mapping_rows.append(row)

      new_mapping_rows = sorted(
          new_mapping_rows, key=lambda x: (x[0], x[1], x[2]))

      print(
          '------------------------------Previous Mapping Sheet------------------------------'
      )
      for row in mapping_sheet_rows:
        print(row)
      print(
          '------------------------------Updated Mapping Sheet------------------------------'
      )
      for row in new_mapping_rows:
        print(row)

      write_new_mapping_rows(sheets_service, new_mapping_rows)

    else:
      init_mapping_sheet(sheets_service, campaign_ad_group_list)

    # Step 4. Update date
    update_date_in_sheet(sheets_service)

    print(
        '-----------------------------------------------------------------------------------'
    )
    print('Succesfully updated the Mapping Sheet.')
    print(f'Last update time: {str(_TODAY)}')


if __name__ == '__main__':
  with open('config/setup.yaml', 'r') as ymlfile:
    cfg = yaml.safe_load(ymlfile)

  refresh_mapping_main(
      spreadsheet_ids=cfg['spreadsheetIds'],
      service_account=cfg['serviceAccount'],
      client_secret=cfg['clientSecret'],
      ads_account=cfg['adsAccount'])

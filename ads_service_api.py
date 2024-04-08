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
"""Provides functionality to interact with Google Ads platform."""

from hashlib import md5
import io
import requests
import datetime
import re
import copy

from google.api_core import protobuf_helpers
from google.ads import googleads

_TODAY = datetime.datetime.today()


class AdService():
  """Provides Google ads API service to interact with Ads platform."""

  def __init__(self, ads_account_file):
    """Constructs the AdService instance.

    Args:
      ads_account_file: Path to Google Ads API account file.
    """
    self._google_ads_client = googleads.client.GoogleAdsClient.load_from_storage(
        ads_account_file)
    self._cache_ad_group_ad = {}
    self.prev_image_asset_list = None
    self.prev_customer_id = None

  def _list_accessible_customers(self):
    """List all accessible customer resource names.

    Returns:
      results: list of customer resource names.
    """
    return self._google_ads_client.get_service(
        'CustomerService').list_accessible_customers().resource_names

  def _get_customer_id(self, customer_resource_name):
    """Get customer id from customer resource name.

    Args:
      customer_resource_name: string in this format: customers/1234567890.

    Returns:
      customer_id: customer id.
    """
    m = re.fullmatch('customers/(\d+)', customer_resource_name)
    if not m:
      raise ValueError(
          f'Unable to match customer resource name {customer_resource_name}.')

    return m.group(1)

  def _get_all_child_accounts(self, seed_customer_id):
    """Gets all child account customer ids of given Manager account or login

    customer id.

    Args:
      seed_customer_id: Customer ID to handle.

    Returns:
      child_accounts: list of customer ids.
    """

    query = ('SELECT '
             'customer_client.client_customer, '
             'customer_client.level, '
             'customer_client.manager, '
             'customer_client.descriptive_name, '
             'customer_client.id '
             'FROM '
             'customer_client '
             'WHERE customer_client.level <= 1 '
             'AND customer_client.status = "ENABLED" ')

    # Performs a breadth-first search to build a Dictionary that maps managers
    # to their child accounts (customerIdsToChildAccounts).
    unprocessed_customer_ids = [seed_customer_id]
    child_accounts = []

    while unprocessed_customer_ids:
      customer_id = int(unprocessed_customer_ids.pop(0))  # MCC Account
      response = self._google_ads_client.get_service('GoogleAdsService').search(
          customer_id=str(customer_id), query=query)

      # Iterates over all rows in all pages to get all customer clients under the specified
      # customer's hierarchy.
      for googleads_row in response:
        customer_client = googleads_row.customer_client

        if customer_client.id not in child_accounts:
          if customer_client.manager:
            # A customer can be managed by multiple managers,
            # to prevent duplication, we check if it's already in the dict.
            if customer_client.level == 1:
              unprocessed_customer_ids.append(customer_client.id)
          else:
            child_accounts.append(str(customer_client.id))

    return child_accounts

  def _get_campaign_ad_groups(self, customer_id):
    """Gets an ad group info by customer id and campaign id.

    Args:
      customer_id: customer id.

    Returns:
      List of app campaigns ad groups.
    """
    query = (
        'SELECT campaign.id, campaign.name, '
        'campaign.app_campaign_setting.app_id, ad_group.id, ad_group.name FROM'
        ' ad_group WHERE campaign.advertising_channel_type = "MULTI_CHANNEL" '
        'AND campaign.advertising_channel_sub_type IN ("APP_CAMPAIGN", '
        '"APP_CAMPAIGN_FOR_ENGAGEMENT") AND campaign.status = "ENABLED" AND '
        'ad_group.status = "ENABLED" ')

    return self._google_ads_client.get_service('GoogleAdsService').search(
        customer_id=customer_id, query=query)

  def _get_ad_group_ad(self, customer_id, ad_group_id):
    """Gets ad_group_ad by customer id and ad group id.

    Args:
      customer_id: customer id.
      ad_group_id: ad group id.

    Returns:
      An array of (ad group ad id, ad group ad type).
    """
    id_pair = (customer_id, ad_group_id)

    if id_pair in self._cache_ad_group_ad:
      return self._cache_ad_group_ad[id_pair]

    self._update_cache_ad_group_ad(customer_id)

    if id_pair in self._cache_ad_group_ad:
      return self._cache_ad_group_ad[id_pair]

  def _update_cache_ad_group_ad(self, customer_id):
    """Updates _cache_ad_group_ad.

    Args:
      customer_id: customer id.
    """
    query = ('SELECT ad_group.id, ad_group_ad.ad.id, ad_group_ad.ad.type '
             'FROM ad_group_ad ')

    results = self._google_ads_client.get_service('GoogleAdsService').search(
        customer_id=customer_id, query=query)

    for row in results:
      ad_group_id = str(row.ad_group.id)
      ad_group_ad_id = row.ad_group_ad.ad.id
      ad_group_ad_type = row.ad_group_ad.ad.type_
      new_id_pair = (customer_id, ad_group_id)
      self._cache_ad_group_ad[new_id_pair] = (ad_group_ad_type, ad_group_ad_id)

  def _add_description_asset_to_campaign(self, text, customer_id, ad_group_id):
    """Adds description asset to ad group ad.

    Args:
      text: asset headline or description text.
      customer_id: customer id.
      ad_group_id: ad group id.
    """
    self._perform_text_asset_operation('ADD', 'DESCRIPTION', text, customer_id,
                                       ad_group_id)

  def _remove_description_asset_from_campaign(self, text, customer_id,
                                              ad_group_id):
    """Removes description asset from ad group ad.

    Args:
      text: asset headline or description text.
      customer_id: customer id.
      ad_group_id: ad group id.
    """
    self._perform_text_asset_operation('REMOVE', 'DESCRIPTION', text,
                                       customer_id, ad_group_id)

  def _add_headline_asset_to_campaign(self, text, customer_id, ad_group_id):
    """Adds headline asset to ad group ad.

    Args:
      text: asset headline or description text.
      customer_id: customer id.
      ad_group_id: ad group id.
    """
    self._perform_text_asset_operation('ADD', 'HEADLINE', text, customer_id,
                                       ad_group_id)

  def _remove_headline_asset_from_campaign(self, text, customer_id,
                                           ad_group_id):
    """Removes headline asset from ad group ad.

    Args:
      text: asset headline or description text.
      customer_id: customer id.
      ad_group_id: ad group id.
    """
    self._perform_text_asset_operation('REMOVE', 'HEADLINE', text, customer_id,
                                       ad_group_id)

  def _get_asset_list_by_asset_type(self, asset_type, ad_group_ad_type,
                                    new_list_of_asset):
    """Gets asset array from 'AdOperation' object by asset type.

    Args:
      asset_type: 'HEADLINE' or 'DESCRIPTION' or 'IMAGE' or 'VIDEO'.
      ad_group_ad_type: Ad Type ('APP_AD' or 'APP_ENGAGEMENT_AD').
      new_list_of_asset: Type of 'AdOperation' which contains a copy of ads
        campaign information.

    Returns:
      An array of asset with selected asset type.

    Raises:
      TypeError: unknown campaign type.
    """
    if ad_group_ad_type == self._google_ads_client.enums.AdTypeEnum.APP_AD:
      if asset_type == 'HEADLINE':
        asset_operation = new_list_of_asset.update.app_ad.headlines
      elif asset_type == 'DESCRIPTION':
        asset_operation = new_list_of_asset.update.app_ad.descriptions
      elif asset_type == 'IMAGE':
        asset_operation = new_list_of_asset.update.app_ad.images
      elif asset_type == 'VIDEO':
        asset_operation = new_list_of_asset.update.app_ad.youtube_videos
      else:
        raise TypeError(
            'Unknown campaign type. Only DESCRIPTION, HEADLINE, IMAGE, VIDEO are allowed.'
        )

    elif ad_group_ad_type == self._google_ads_client.enums.AdTypeEnum.APP_ENGAGEMENT_AD:
      if asset_type == 'HEADLINE':
        asset_operation = new_list_of_asset.update.app_engagement_ad.headlines
      elif asset_type == 'DESCRIPTION':
        asset_operation = new_list_of_asset.update.app_engagement_ad.descriptions
      elif asset_type == 'IMAGE':
        asset_operation = new_list_of_asset.update.app_engagement_ad.images
      elif asset_type == 'VIDEO':
        asset_operation = new_list_of_asset.update.app_engagement_ad.videos
      else:
        raise TypeError(
            'Unknown campaign type. Only DESCRIPTION, HEADLINE, IMAGE, VIDEO are allowed.'
        )
    else:
      raise TypeError(
          'Unknown campaign type. Only APP_ENGAGEMENT_AD, APP_AD are allowed.')

    return asset_operation

  def _append_asset_operation(self, asset_operation, asset):
    """Adds asset from an ad.

    Args:
      asset_operation: current asset list of an ad.
      asset: text or asset id to append.

    Raises:
      GoogleAdsException: Google Ads API error.
      Exception: If unknown error occurs.
    """
    try:
      asset_operation.append(asset)
    except googleads.errors.GoogleAdsException as failures:
      error_message = ''
      for error in failures.failure.errors:
        error_message += error.message
      print(error_message)
    except Exception:
      print('Unknown error occured while uploading the asset to the ad.')

  def _remove_asset_operation(self, asset_operation, asset):
    """Remove asset from an ad.

    Args:
      asset_operation: current asset list of an ad.
      asset: text or asset id to remove.

    Raises:
      GoogleAdsException: Google Ads API error.
      ValueError: If the asset does not exist in the adgroup.
      Exception: If unknown error occurs.
    """
    try:
      asset_operation.remove(asset)
    except googleads.errors.GoogleAdsException as failures:
      error_message = ''
      for error in failures.failure.errors:
        error_message += error.message
      print(error_message)
    except ValueError:
      print(
          'Please check if the asset exists in the adgroup. If not, manually delete from the Time Managed Sheet.'
      )
    except Exception:
      print('Unknown error occured while removing the asset from ad.')

  def _perform_text_asset_operation(self, add_or_remove, asset_type, text,
                                    customer_id, ad_group_id):
    """Adds or removes headline or description asset to or from ad group ad.

    Args:
      add_or_remove: 'ADD' text or 'REMOVE' text.
      asset_type: 'HEADLINE' or 'DESCRIPTION'.
      text: asset headline or description text.
      customer_id: customer id.
      ad_group_id: ad group id.

    Raises:
      ValueError: If the ad group id can't match any ad id.
      TypeError: Unknown type.
    """
    if not text:
      raise ValueError('Unable to perform text action. Unknown error.')

    service = self._google_ads_client.get_service('AdService')
    ad_group_ad = self._get_ad_group_ad(customer_id, ad_group_id)

    if not ad_group_ad:
      raise ValueError(f'This {ad_group_id} ad_group does not have ad.'
                       ' Kindly check if the ad group id is correct.')

    (ad_group_ad_type, ad_group_ad_id) = ad_group_ad
    resource_name = f'customers/{customer_id}/ads/{str(ad_group_ad_id)}'
    new_list_of_asset = self._google_ads_client.get_type('AdOperation')
    ad_text_asset = self._google_ads_client.get_type('AdTextAsset')
    ad_text_asset.text = text

    asset_operation = self._get_asset_list_by_asset_type(
        asset_type, ad_group_ad_type, new_list_of_asset)

    self._insert_existing_text_asset(asset_operation, ad_group_ad_id,
                                     ad_group_ad_type, asset_type, customer_id)

    if add_or_remove == 'ADD':
      self._append_asset_operation(asset_operation, ad_text_asset)
    else:
      for asset in asset_operation:
        if asset.text == ad_text_asset.text:
          self._remove_asset_operation(asset_operation, asset)
          break

    new_list_of_asset.update.resource_name = resource_name
    self._google_ads_client.copy_from(
        new_list_of_asset.update_mask,
        protobuf_helpers.field_mask(None, new_list_of_asset.update._pb))

    service.mutate_ads(customer_id=customer_id, operations=[new_list_of_asset])

  def _create_youtube_asset(self, youtube_video_id, customer_id):
    """Creates YouTube video asset from YouTube video id.

    Args:
      youtube_video_id: YouTube video id.
      customer_id: customer id.

    Returns:
      YouTube video asset id.
    """
    asset_service = self._google_ads_client.get_service('AssetService')
    asset_operation = self._google_ads_client.get_type('AssetOperation')

    # asset_operation.create.name = youtube_video_id
    asset_operation.create.youtube_video_asset.youtube_video_id = youtube_video_id

    ad_video_asset = asset_service.mutate_assets(
        customer_id=customer_id, operations=[asset_operation])

    return ad_video_asset

  def _add_video_asset_to_campaign(self, asset_id, customer_id, ad_group_id):
    """Adds video asset to ad group ad.

    Args:
      asset_id: asset_id.
      customer_id: customer id.
      ad_group_id: ad group id.
    """
    self._perform_media_asset_operation('ADD', 'VIDEO', asset_id, customer_id,
                                        ad_group_id)

  def _remove_video_asset_from_campaign(self, asset_id, customer_id,
                                        ad_group_id):
    """Removes video asset from ad group ad.

    Args:
      asset_id: asset_id.
      customer_id: customer id.
      ad_group_id: ad group id.
    """
    self._perform_media_asset_operation('REMOVE', 'VIDEO', asset_id,
                                        customer_id, ad_group_id)

  def _add_image_asset_to_campaign(self, asset_id, customer_id, ad_group_id):
    """Adds image asset to ad group ad.

    Args:
      asset_id: asset_id.
      customer_id: customer id.
      ad_group_id: ad group id.
    """
    self._perform_media_asset_operation('ADD', 'IMAGE', asset_id, customer_id,
                                        ad_group_id)

  def _remove_image_asset_from_campaign(self, asset_id, customer_id,
                                        ad_group_id):
    """Removes image asset from ad group ad.

    Args:
      asset_id: asset_id.
      customer_id: customer id.
      ad_group_id: ad group id.
    """
    self._perform_media_asset_operation('REMOVE', 'IMAGE', asset_id,
                                        customer_id, ad_group_id)

  def _create_ad_asset_by_id(self, asset_type, asset_id):
    """Creates ad asset by asset id.

    Args:
      asset_type: IMAGE or VIDEO.
      asset_id: asset id.

    Returns:
     An ad asset.

    Raises:
      TypeError: Unknown type.
    """
    if asset_type == 'IMAGE':
      ad_asset = self._google_ads_client.get_type('AdImageAsset')
      ad_asset.asset = asset_id

    elif asset_type == 'VIDEO':
      ad_asset = self._google_ads_client.get_type('AdVideoAsset')
      ad_asset.asset = asset_id
    else:
      raise TypeError('Unknow asset type. Only IMAGE, VIDEO are allowed.')

    return ad_asset

  def _perform_media_asset_operation(self, add_or_remove, asset_type, asset_id,
                                     customer_id, ad_group_id):
    """Adds or removes image or YouTube video asset to ad group ad.

    Args:
      add_or_remove: Option for ADD or REMOVE asset.
      asset_type: image or YouTube video.
      asset_id: asset id.
      customer_id: customer id.
      ad_group_id: ad group id.

    Raises:
      ValueError: If the ad group id can't match any ad id or Google Ads API returned errors.
      TypeError: Unknown type.
    """
    try:
        if not asset_id:
            raise ValueError('Unable to perform media action. Unknown error.')

        service = self._google_ads_client.get_service('AdService')
        ad_group_ad = self._get_ad_group_ad(customer_id, ad_group_id)

        if not ad_group_ad:
            raise ValueError(f'This {ad_group_id} ad_group does not have ad.'
                ' Kindly check if the ad group id is correct.')

        (ad_group_ad_type, ad_group_ad_id) = ad_group_ad

        resource_name = f'customers/{customer_id}/ads/{str(ad_group_ad_id)}'

        new_list_of_asset = self._google_ads_client.get_type('AdOperation')

        asset_operation = self._get_asset_list_by_asset_type(
            asset_type, ad_group_ad_type, new_list_of_asset)

        ad_asset = self._create_ad_asset_by_id(asset_type, asset_id)

        self._insert_existing_media_asset(asset_operation, ad_group_ad_id,
                                        ad_group_ad_type, asset_type, customer_id)

        if add_or_remove == 'ADD':
            self._append_asset_operation(asset_operation, ad_asset)
        else:
            self._remove_asset_operation(asset_operation, ad_asset)

        field_mask = None
        prev_field_mask = copy.deepcopy(
            protobuf_helpers.field_mask(None, new_list_of_asset.update._pb))
        # If final asset is empty, field mask will be empty and mutate operation will be skipped. So we need to use prev field mask in that case.
        if not asset_operation:
            field_mask = prev_field_mask
        else:
            field_mask = protobuf_helpers.field_mask(None,
                                               new_list_of_asset.update._pb)

        new_list_of_asset.update.resource_name = resource_name
        self._google_ads_client.copy_from(new_list_of_asset.update_mask, field_mask)   
        service.mutate_ads(customer_id=customer_id, operations=[new_list_of_asset])
    except googleads.errors.GoogleAdsException as failures:
      error_message = ''
      for error in failures.failure.errors:
        error_message += error.message
      raise ValueError(error_message)

  def _create_image_asset(self, image_name, image_buffer, customer_id):
    """Creates image assets with a given name from the Upload Sheet and data from image buffer.

    When there is an existing image asset with the same content but a different
    name, the new name will be dropped silently.

    Args:
      image_name: image asset name from Upload Sheet.
      image_buffer: image data downloaded from Google Drive.
      customer_id: target Google Ads customer id.

    Returns:
      ad_image_asset: New image asset created.
    """
    asset_service = self._google_ads_client.get_service('AssetService')
    asset_operation = self._google_ads_client.get_type('AssetOperation')
    asset = asset_operation.create

    asset.type_ = self._google_ads_client.enums.AssetTypeEnum.IMAGE
    asset.image_asset.data = image_buffer
    asset.name = image_name
    ad_image_asset = asset_service.mutate_assets(
        customer_id=customer_id, operations=[asset_operation])
    return ad_image_asset

  def _get_image_asset_list(self, customer_id):
    """Gets image asset list from customer account.

    Args:
      customer_id: customer id.

    Returns:
      A dictionary where key is resource name and value is array of asset name,
      url, md5 hash.
    """
    query = ('SELECT asset.id, asset.name, asset.type, '
             'asset.image_asset.full_size.url FROM asset WHERE asset.type IN '
             '("IMAGE")')

    results = self._google_ads_client.get_service('GoogleAdsService').search(
        customer_id=customer_id, query=query)

    image_asset_list = {}
    for row in results:
      image_md5_hash = self._get_md5_hash_of_image_asset(
          customer_id, row.asset.resource_name,
          row.asset.image_asset.full_size.url)
      image_asset_list[row.asset.resource_name] = [
          row.asset.name, row.asset.image_asset.full_size.url, image_md5_hash
      ]
    self._store_prev_image_asset_list(customer_id, image_asset_list)
    return image_asset_list

  def _get_md5_hash_of_image_asset(self, customer_id, resource_name, url):
    """Gets md5 hash of image asset by searching previous list or calculating from image.

    Args:
      customer_id: target Google Ads customer id.
      resource_name: resource name of target image assset
      url: url of target image assset

    Returns:
      Md5 hexdigest of target image asset.
    """
    image_md5_hash = self._search_hash_from_prev_list(customer_id,
                                                      resource_name, url)
    if image_md5_hash:
      return image_md5_hash
    image_buffer = io.BytesIO(requests.get(url).content).read()
    result = md5(image_buffer)
    return result.hexdigest()

  def _search_hash_from_prev_list(self, customer_id, resource_name, url):
    """Searches md5 hash of image asset from previous search result.

    Args:
      customer_id: target customer id.
      resource_name: resource name of target image assset
      url: url of target image assset

    Returns:
      Md5 hexdigest of target image asset. Return None if not exists.
    """
    if self.prev_customer_id != customer_id:
      return None
    if not self.prev_image_asset_list:
      return None
    if resource_name not in self.prev_image_asset_list:
      return None
    if url != self.prev_image_asset_list[resource_name][1]:
      return None
    return self.prev_image_asset_list[resource_name][2]

  def _store_prev_image_asset_list(self, customer_id, image_asset_list):
    """Stores image asset list for reuse of md5 hash calcualtion results.

    Args:
      customer_id: target customer id.
      image_asset_list: image assset list
    """
    self.prev_customer_id = customer_id
    self.prev_image_asset_list = image_asset_list

  def _get_ad_and_ad_type_by_ad_group_id_list(self, customer_id,
                                              ad_group_id_list):
    """Gets Ad type and Ad by ad group list.

    Args:
      customer_id: customer id.
      ad_group_id_list: ad group id list.

    Returns:
      A dictionary of tuple where the tuple is (Ad object, Ad type) and the
      dictionary is (Ad group id, tuple).

    Raises:
      ValueError: ad group id doesn't exist.
    """
    if not ad_group_id_list:
      return []

    self._update_cache_ad_group_ad(customer_id)

    ad_group_ad_id_list = []
    for ad_group_id in ad_group_id_list:
      id_pair = (customer_id, ad_group_id)

      if id_pair not in self._cache_ad_group_ad:
        continue
      ad_group_ad_id_list.append(str(self._cache_ad_group_ad[id_pair][1]))

    response = self._get_asset_by_ad_group_ad_id_list(customer_id,
                                                      ad_group_ad_id_list)
    ret = {}
    for row in response:
      ad_group_id = str(row.ad_group.id)
      id_pair = (customer_id, ad_group_id)
      ret[ad_group_id] = self._aggregate_asset_result(
          [row], self._cache_ad_group_ad[id_pair][0])
    return ret

  def _get_ad_and_ad_type(self, customer_id, ad_group_id):
    """Gets Ad type and Ad by ad groupd id.

    Args:
      customer_id: customer id.
      ad_group_id: ad group id.

    Returns:
      A tuple where the tuple is (Ad object, Ad type).

    Raises:
      ValueError: ad group id doesn't have ad.
    """
    ad_group_ad = self._get_ad_group_ad(customer_id, ad_group_id)

    if not ad_group_ad:
      raise ValueError(f'This {ad_group_id} ad_group does not have ad.'
                       ' Kindly check if the ad group id is correct.')

    (ad_group_ad_type, ad_group_ad_id) = ad_group_ad
    response = self._get_asset_by_ad_group_ad_id(customer_id, ad_group_ad_id)
    return self._aggregate_asset_result(response, ad_group_ad_type)

  def _aggregate_asset_result(self, response, ad_group_ad_type):
    """Aggregates ad_group_ad query result by number of assets.

    Args:
      response: ad_group_ad query result.
      ad_group_ad_type: ad group ad type.

    Returns:
      A dictionary of asset count.
    """
    count = {}
    count['DESCRIPTION'] = 0
    count['HEADLINE'] = 0
    count['VIDEO'] = 0
    count['IMAGE'] = 0
    if ad_group_ad_type == self._google_ads_client.enums.AdTypeEnum.APP_AD:
      for row in response:
        count['DESCRIPTION'] = count['DESCRIPTION'] + len(
            row.ad_group_ad.ad.app_ad.descriptions)
        count['HEADLINE'] = count['HEADLINE'] + len(
            row.ad_group_ad.ad.app_ad.headlines)
        count['IMAGE'] = count['IMAGE'] + len(row.ad_group_ad.ad.app_ad.images)
        count['VIDEO'] = count['VIDEO'] + len(
            row.ad_group_ad.ad.app_ad.youtube_videos)
    else:
      for row in response:
        count['DESCRIPTION'] = count['DESCRIPTION'] + len(
            row.ad_group_ad.ad.app_engagement_ad.descriptions)
        count['HEADLINE'] = count['HEADLINE'] + len(
            row.ad_group_ad.ad.app_engagement_ad.headlines)
        count['IMAGE'] = count['IMAGE'] + len(
            row.ad_group_ad.ad.app_engagement_ad.images)
        count['VIDEO'] = count['VIDEO'] + len(
            row.ad_group_ad.ad.app_engagement_ad.videos)

    return (count, ad_group_ad_type)

  def _get_asset_performance_data(self, asset_type, customer_id, ad_group_id):
    """Gets asset performance data from an ad group.

    Retrieves performance_label, cost_micros, conversions.

    Args:
      asset_type: 'HEADLINE' or 'DESCRIPTION' or 'IMAGE' or 'VIDEO'.
      customer_id: customer id.
      ad_group_id: ad group id.

    Returns:
      An iterator of asset performance object.
    """
    # Rename the asset type to ad_group_ad_asset_view field_type.
    # For HEADLINE and DESCRIPTION, they are the same in ad_group_ad_asset_view field_type.
    if asset_type == 'IMAGE':
      asset_type = 'MARKETING_IMAGE'
    elif asset_type == 'VIDEO':
      asset_type = 'YOUTUBE_VIDEO'

    query = (
        'SELECT '
        'ad_group_ad_asset_view.performance_label, '
        'ad_group_ad_asset_view.asset, '
        'ad_group_ad_asset_view.field_type, '
        'metrics.cost_micros, '
        'metrics.conversions '
        'FROM '
        'ad_group_ad_asset_view '
        f'WHERE ad_group.id = {ad_group_id} '
        'AND ad_group_ad_asset_view.enabled = True AND segments.date DURING '
        'LAST_14_DAYS AND ad_group_ad_asset_view.performance_label IN ("BEST",'
        ' "GOOD", "LOW") '
        f'AND ad_group_ad_asset_view.field_type = "{asset_type}" ')

    return self._google_ads_client.get_service('GoogleAdsService').search(
        customer_id=customer_id, query=query)

  def _get_asset_by_ad_group_ad_id(self, customer_id, ad_group_ad_id):
    """Gets asset data from an ad group.

    Args:
      customer_id: customer id.
      ad_group_ad_id: ad group ad id.

    Returns:
      An iterator of asset data object.
    """
    query = ('SELECT '
             'ad_group_ad.ad.id, '
             'ad_group_ad.ad.app_ad.descriptions, '
             'ad_group_ad.ad.app_ad.headlines, '
             'ad_group_ad.ad.app_ad.youtube_videos, '
             'ad_group_ad.ad.app_ad.images, '
             'ad_group_ad.ad.app_engagement_ad.descriptions, '
             'ad_group_ad.ad.app_engagement_ad.headlines, '
             'ad_group_ad.ad.app_engagement_ad.videos, '
             'ad_group_ad.ad.app_engagement_ad.images '
             'FROM ad_group_ad '
             f'WHERE ad_group_ad.ad.id = {ad_group_ad_id}')

    return self._google_ads_client.get_service('GoogleAdsService').search(
        customer_id=customer_id, query=query)

  def _get_asset_by_ad_group_ad_id_list(self, customer_id, ad_group_ad_id_list):
    """Gets asset data from an ad group list.

    Args:
      customer_id: customer id.
      ad_group_ad_id_list: ad group ad id list.

    Returns:
      An iterator of asset data object.
    """
    query = ('SELECT '
             'ad_group.id,'
             'ad_group_ad.ad.id, '
             'ad_group_ad.ad.app_ad.descriptions, '
             'ad_group_ad.ad.app_ad.headlines, '
             'ad_group_ad.ad.app_ad.youtube_videos, '
             'ad_group_ad.ad.app_ad.images, '
             'ad_group_ad.ad.app_engagement_ad.descriptions, '
             'ad_group_ad.ad.app_engagement_ad.headlines, '
             'ad_group_ad.ad.app_engagement_ad.videos, '
             'ad_group_ad.ad.app_engagement_ad.images '
             'FROM ad_group_ad '
             f'WHERE ad_group_ad.ad.id in ({",".join(ad_group_ad_id_list)})')
    return self._google_ads_client.get_service('GoogleAdsService').search(
        customer_id=customer_id, query=query)

  def _insert_existing_text_asset(self, asset_operation, ad_group_ad_id,
                                  ad_group_ad_type, asset_type, customer_id):
    response = self._get_asset_by_ad_group_ad_id(
        str(customer_id), str(ad_group_ad_id))
    if ad_group_ad_type == self._google_ads_client.enums.AdTypeEnum.APP_AD:
      for row in response:
        if asset_type == 'HEADLINE':
          if(row.ad_group_ad.ad.app_ad.headlines):
            for texts in row.ad_group_ad.ad.app_ad.headlines:
              text_asset = self._google_ads_client.get_type('AdTextAsset')
              text_asset.text = texts.text
              asset_operation.append(text_asset)
        else:
          if(row.ad_group_ad.ad.app_ad.descriptions):
            for texts in row.ad_group_ad.ad.app_ad.descriptions:
              text_asset = self._google_ads_client.get_type('AdTextAsset')
              text_asset.text = texts.text
              asset_operation.append(text_asset)
    else:
      for row in response:
        if asset_type == 'HEADLINE':
          if(row.ad_group_ad.ad.app_engagement_ad.headlines):
            for texts in row.ad_group_ad.ad.app_engagement_ad.headlines:
              text_asset = self._google_ads_client.get_type('AdTextAsset')
              text_asset.text = texts.text
              asset_operation.append(text_asset)
        else:
          if(row.ad_group_ad.ad.app_engagement_ad.descriptions):
            for texts in row.ad_group_ad.ad.app_engagement_ad.descriptions:
              text_asset = self._google_ads_client.get_type('AdTextAsset')
              text_asset.text = texts.text
              asset_operation.append(text_asset)

  def _insert_existing_media_asset(self, asset_operation, ad_group_ad_id,
                                   ad_group_ad_type, asset_type, customer_id):
    response = self._get_asset_by_ad_group_ad_id(
        str(customer_id), str(ad_group_ad_id))
    if ad_group_ad_type == self._google_ads_client.enums.AdTypeEnum.APP_AD:
      for row in response:
        if asset_type == 'IMAGE':
          if(row.ad_group_ad.ad.app_ad.images):
            for media in row.ad_group_ad.ad.app_ad.images:
                ad_asset = self._google_ads_client.get_type('AdImageAsset')
                ad_asset.asset = media.asset
            asset_operation.append(media)
        else:
            if(row.ad_group_ad.ad.app_ad.youtube_videos):
                for media in row.ad_group_ad.ad.app_ad.youtube_videos:
                    ad_asset = self._google_ads_client.get_type('AdVideoAsset')
                    ad_asset.asset = media.asset
                    asset_operation.append(ad_asset)
    else:
      for row in response:
        if asset_type == 'IMAGE':
            if(row.ad_group_ad.ad.app_engagement_ad.images):
                for media in row.ad_group_ad.ad.app_engagement_ad.images:
                    ad_asset = self._google_ads_client.get_type('AdImageAsset')
                    ad_asset.asset = media.asset
                    asset_operation.append(media)
        else:
            if(row.ad_group_ad.ad.app_engagement_ad.videos):
                for media in row.ad_group_ad.ad.app_engagement_ad.videos:
                    ad_asset = self._google_ads_client.get_type('AdVideoAsset')
                    ad_asset.asset = media.asset
                    asset_operation.append(ad_asset)

  def _get_text_asset_value_by_asset_id(self, customer_id, asset_id):
    """Gets text asset value by asset id.

    Args:
      customer_id: customer id.
      asset_id: asset id.

    Returns:
      Text asset value.
    """
    query = ('SELECT '
             'asset.resource_name, '
             'asset.text_asset.text '
             'FROM '
             'asset '
             f'WHERE asset.resource_name = "{asset_id}"')
    result = self._google_ads_client.get_service('GoogleAdsService').search(
        customer_id=customer_id, query=query)
    for row in result:
      return row.asset.text_asset.text
    return ''

  def _get_asset_performance_by_metrics(self, customer_id, ad_group_id,
                                        target_asset_id, asset_type, duration):
    """Gets asset performance data from an ad group.

    Retrieves performance_label, cost_micros, conversions.

    Args:
      asset_type: 'HEADLINE' or 'DESCRIPTION' or 'IMAGE' or 'VIDEO'.
      customer_id: customer id.
      ad_group_id: ad group id.
      target_asset_id: asset id for media assets, text for text assets.
      asset_type: asset type.
      duration: performance evaluation duration.

    Returns:
      perf_result: A list of asset performance.
    """
    if asset_type == 'IMAGE':
      asset_type = 'MARKETING_IMAGE'
    elif asset_type == 'VIDEO':
      asset_type = 'YOUTUBE_VIDEO'

    start_date = (_TODAY - datetime.timedelta(days=duration)).date()
    end_date = (_TODAY - datetime.timedelta(days=1)).strftime('%Y-%m-%d')

    query = (
        'SELECT '
        'ad_group_ad_asset_view.asset, '
        'ad_group_ad_asset_view.field_type, '
        'ad_group_ad_asset_view.performance_label,  '
        'asset.text_asset.text, '
        'metrics.impressions, '
        'metrics.conversions, '
        'metrics.conversions_value, '
        'metrics.ctr, '
        'metrics.clicks '
        'FROM ad_group_ad_asset_view '
        f'WHERE ad_group.id = {ad_group_id} '
        f'AND segments.date BETWEEN "{start_date}" AND "{end_date}" '
        f'AND ad_group_ad_asset_view.field_type = "{asset_type}" '
        'AND ad_group_ad_asset_view.enabled = True AND '
        'ad_group_ad_asset_view.performance_label IN ("LOW", "GOOD", "BEST") ')

    if asset_type == 'HEADLINE' or asset_type == 'DESCRIPTION':
      query += f'AND asset.text_asset.text = "{target_asset_id}" '

    results = self._google_ads_client.get_service('GoogleAdsService').search(
        customer_id=customer_id, query=query)
    perf_result = []

    for row in results:
      # get asset_id
      # For HEADLINE and DESCRIPTION, asset id is text itself
      if asset_type == 'HEADLINE' or asset_type == 'DESCRIPTION':
        asset_id = row.asset.text_asset.text
      else:
        asset_id = row.ad_group_ad_asset_view.asset
      # performance_label
      performance_label_enum = self._get_performance_label()
      performance_label = str(
          performance_label_enum[row.ad_group_ad_asset_view.performance_label])

      if asset_id == target_asset_id:
        perf = {
            'ad_group_id': ad_group_id,
            'asset_id': asset_id,
            'asset_type': asset_type,
            'performance_label': performance_label,
            'impressions': row.metrics.impressions,
            'conversions': row.metrics.conversions,
            'conversions_value': row.metrics.conversions_value,
            'ctr': row.metrics.ctr,
            'clicks': row.metrics.clicks
        }
        perf_result.append(perf)

    return perf_result

  def _get_performance_label(self):
    """Gets performance_label dict.

    Returns:
      result: name & enum value of performance label.
    """
    result = self._google_ads_client.get_type(
        'AssetPerformanceLabelEnum').AssetPerformanceLabel
    enum_to_dict = result.__dict__['_member_map_']
    result = {}
    for k, v in enum_to_dict.items():
      result[v.value] = k
    return result

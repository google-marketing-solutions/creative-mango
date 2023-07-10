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
"""Provides image md5 functionality."""

from hashlib import md5
import io
import requests


def calculate_md5_digest(image_buffer):
  """Calculates md5 hash by image pixels.

  Args:
    image_buffer: image pixels in bytes.

  Returns:
    Md5 hexdigest.
  """
  result = md5(image_buffer)
  return result.hexdigest()


def get_existing_image_asset(drive_service, image_asset_list, image_url,
                             image_name):
  """Search for the same image asset in the account with either image name or image md5 hash data and return resource name and image data.

  Args:
    drive_service: Google Drive service.
    image_asset_list: a dictionary where key is asset id and value is asset
      name.
    image_url: Image Drive url to upload or image name to replace.
    image_name: Image name to upload or image name to replace.

  Returns:
    image_resouce_name: Image asset resource name. Return None if doesn't
    exists. (format: customers/{customerId}/assets/{assetId})
    image_buffer: image data. Return None if asset already exist in the same
    account.
  """
  # Check by image asset name first to reduce hash calculation time. (Asset name is unique within an account).
  if image_name:
    for image in image_asset_list.items():
      image_resouce_name = image[0]
      image_asset_name = image[1][0]

      if (image_asset_name == image_name):
        return image_resouce_name, None

  # Check by image contents.
  image_buffer = None
  if image_url:
    image_buffer = drive_service._download_asset(image_url)
    image_md5_hash = calculate_md5_digest(image_buffer)
    for image in image_asset_list.items():
      image_resouce_name = image[0]
      existing_image_md5_hash = image[1][2]
      if existing_image_md5_hash == image_md5_hash:
        return image_resouce_name, None
  return None, image_buffer

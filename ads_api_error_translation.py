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
"""Provides functionality to translate ads api errors to more readable."""


def translate_ads_api_errors(error):
  """Makes Google Ads API errors more readable.

  Args:
    error: Google Ads APIs error.

  Returns:
    Translation of Google Ads APIs errors.
  """
  if error == 'Cannot use empty field mask in update operation.':
    return ('Failed to replace asset. e.g. Cannot find the asset to be '
            'replaced.')
  elif error == 'Too many.':
    return ('Too many. The AdGroup has no space for this asset. ')
  elif error == 'Too short.':
    return ('YouTube id is too short.')
  elif error == 'Too long.':
    return ('Asset name is too long.')
  elif error == 'The error code is not in this version.':
    return (
        'Please check if there is policy issues in the campaign or '
        'adgroup.(e.g. disapproved assets)'
    )
  return error

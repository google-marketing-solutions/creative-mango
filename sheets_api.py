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
"""Provides Google Sheets API to read and write sheets."""

from googleapiclient import discovery


class SheetsService():
  """Creates sheets service to read and write sheets.

  Attributes:
    _sheets_services: service that is used for making Sheets API calls.
    _spreadsheet_id: id of the spreadsheet to read from and write to.
  """

  def __init__(self, credentials, spreadsheet_id):
    """Creates a instance of sheets service to handle requests."""
    self._sheets_service = discovery.build(
        'sheets', 'v4', credentials=credentials).spreadsheets()
    self._spreadsheet_id = spreadsheet_id

  def get_spreadsheet_values(self, field_range):
    """Gets values from sheet.

    Args:
      field_range: string representation of sheet range. For example,
        "SheetName!A:C".

    Returns:
      Array of arrays of values in selectd field range.
    """

    result = self._sheets_service.values().get(
        spreadsheetId=self._spreadsheet_id, range=field_range).execute()
    return result.get('values', [])

  def clear_sheet_range(self, field_range):
    """Clears values in sheet by field range.

    Args:
      field_range: string representation of sheet range. For example,
        "SheetName!A:C".
    """
    self._sheets_service.values().clear(
        spreadsheetId=self._spreadsheet_id, range=field_range).execute()

  def write_to_sheet(self, field_range, values):
    """Writes data into sheet.

    Args:
      field_range: string representation of sheet range. For example,
        "SheetName!A:C".
      values: values to write into sheet.
    """
    body = {'values': values}
    values = self._sheets_service.values().append(
        spreadsheetId=self._spreadsheet_id,
        range=field_range,
        valueInputOption='RAW',
        body=body).execute()
    return values

  def update_sheet_columns(self, field_range, values):
    """Writes data into sheet.

    Args:
      field_range: string representation of sheet range. For example,
        "SheetName!A:C".
      values: values to write into sheet.
    """
    body = {'values': values}
    values = self._sheets_service.values().update(
        spreadsheetId=self._spreadsheet_id,
        range=field_range,
        valueInputOption='RAW',
        body=body).execute()

  def batch_update_requests(self, request_lists):
    """Batch update row with requests in target sheet.

    Args:
      request_lists: request data list.
    """
    batch_update_spreadsheet_request_body = {'requests': request_lists}
    self._sheets_service.batchUpdate(
        spreadsheetId=self._spreadsheet_id,
        body=batch_update_spreadsheet_request_body).execute()

  def get_sheet_id_by_name(self, sheet_name):
    """Get sheet id by sheet name.

    Args:
      sheet_name: sheet name.

    Returns:
      sheet_id: id of the sheet with the given name. Not a spreadsheet id.
    """
    spreadsheet = self._sheets_service.get(
        spreadsheetId=self._spreadsheet_id).execute()

    for _sheet in spreadsheet['sheets']:
      if _sheet['properties']['title'] == sheet_name:
        return _sheet['properties']['sheetId']

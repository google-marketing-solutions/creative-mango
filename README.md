# Creative automation using Google Ads API

Creative-mango serves as a feed-centric creative management solution tailored for ACi and ACe. 
It comes equipped with automated capabilities for seamlessly uploading videos to YouTube.

With this tool, clients can conveniently manage their desired actions within a spreadsheet.
The tool then takes charge, handling the process of pulling creatives and subsequently refreshing your App campaigns with the latest updates.


**NOTE**: This library is _not_ compatible with Python versions less than Python 3.7.
**NOTE**: Google Ads API version: v12


## Prerequisites

*   For your convenience, you can run the following command from this directory
    to install all needed dependencies via [pip](https://pip.pypa.io/):
    ```
      $ pip3 install -r requirements.txt
    ```

## Setup Authentication and Configuration

We are assuming you've checked out the code and are reading this from a local
directory. If not, check out the code to a local directory.

1.  [Open Cloud project library](https://console.developers.google.com/apis/library)

    *   Search 'Google Ads API' and Enable it.
    *   Search 'Google Drive API' and Enable it.
    *   Search 'Google Sheets API' and Enable it.
    *   Search 'YouTube Data API v3' and Enable it.

2.  Make a copy of [Template sheet](https://docs.google.com/spreadsheets/d/1L-rC9kunww4Z8UVE_3pmDhbmJcuQkukFcYjQPSzByr8/copy)

3.  Set up your credentials through [step 3a. OAuth Client ID credentials (Recommended)] or [step 3b. Service Account].

    3a. Authentication using OAuth2 Client ID credentials [Installed App Flow] (Recommended for new implementation.)
    *   Open [Cloud credentials](https://console.developers.google.com/apis/credentials)
    *   Create credentials -> Create 'OAuth client ID' -> Web Application
        *   If you haven’t configured consent screen, setup consent screen first.
        *   User Type: External / Publishing Status: In production
        *   If you want to run the tool in testing mode, make sure to add "test user" and add following "scopes": 
            Google Ads API, Google Drive API, Google Sheets API, YouTube Data API v3
    *   Add the follwing 'Authorized redirect URIs' : 'http://localhost:8008/' and 'http://localhost:8080/'
    *   Download the json and save the json as 'client_secret.json'
    *   Open config/setup.yaml file and update clientSecret to 'client_secret.json'
    *   Generate access token:
        *   Grant the cloud account email with 'Viewer' access to all 'Google Drives' [Cloud account email is any 'Owner' role email in]
        *   Grant the cloud account email with 'Editor' access to the 'Sheet'  you just copied in step 2.
        *   Grant cloud account email with [standard access](https://support.google.com/google-ads/answer/6372672?hl=en) your AdWords account
            *   Cloud account email is any 'Owner' role email in [cloud project](https://console.developers.google.com/iam-admin)
        *   Generate the access tokens for the application with the following command:

            $ python3 auth.py

        - The app will open a browser window.
        - Login with the cloud account email and grant the app the required permissions.
        - An access/refresh token is generated for future authentication of the app and stored in the token.json file in the same folder.
        - Don't move 'token.json' as it will be used everytime the app is running.

    3b. Authentication using a Service Account (This flow will be deprecated in Oct, 2022.)
    *   Open [Cloud credentials](https://console.developers.google.com/apis/credentials)
    *   Create credentials -> Create 'OAuth client ID' -> Desktop App
    *   Download the json and savie the json as “_SECRETS_JSON” after creating
    *   Create credentials -> Create 'Service account'
        *   Go to the [Service Accounts page](https://console.cloud.google.com/iam-admin/serviceaccounts)
        *   Select the project
        *   Click the email address of the service account that you want to
            create a key for
        *   Click the Add key drop-down menu, then select Create new key
        *   Select JSON as the Key type and click Create
        *   Download the json and save the json as '_SERVICE_JSON' after
            creating
    *   Open '_SERVICE_JSON' and copy the email address.
    *   Grant the email address to `Viewer` access to all `Google Drives`
    *   Grant the email address to `Editor` access to the `Sheet` you just copied.
    * Grant cloud account email with [standard access](https://support.google.com/google-ads/answer/6372672?hl=en) your AdWords account
        *   Cloud account email is any 'Owner' role email in [cloud project](https://console.developers.google.com/iam-admin)

4.  In google-ads.yaml file update following fields:

    *   [developer_token](https://developers.google.com/google-ads/api/docs/first-call/dev-token)
    *   client_id
        *   Find client_id in 'client_secret' from step 3a or '_SECRETS_JSON' from step 3b.
    *   client_secret
        *   Find client_secret in 'client_secret' from step 3a or '_SECRETS_JSON' from step 3b.
    *   [refresh_token]
        *   For step 3a. OAuth2 Client ID credentials, Copy the refresh token generated in step 3a. which is stored in token.json
        *   For step 3b. Service Account generate refresh_token by using the cloud account email. (https://developers.google.com/google-ads/api/docs/client-libs/python/oauth-desktop#step_3_-_generating_a_refresh_token)
    *   [Optional] login_customer_id, only if you setup under [manager account](https://support.google.com/google-ads/answer/6139186)

5.  Update configuration in the config/setup.yaml

    *   spreadsheetIds,
    *   serviceAccount,
        *   use '_SERVICE_JSON' path from step 3b. If you choose step 3a, do not change.
    *   clientSecret,
        *   use 'client_secret.json' path from step 3a. If you choose step 3b, do not change.
    *   adsAccount,
        *   use 'config/google-ads.yaml' in step 4.
    *   [Optional] to setup YouTube API to upload videos,
        *   youtubeServiceEnable = True,
        *   youtubeSecret,
            *   use 'client_secret.json' path from step 3a.
            *   OR use '_SECRETS_JSON' path from step 3b.
    *   [Optional] if you want the tool to automatically update mapping sheets up-to-date,
        *   refreshMappingSheetEnable = True,
    *   [Optional] if you want the specify Google Drive folder ids for uploading image/video assets,
        *   driveFolderIds = [REPLACE_DRIVE_FOLDER_IDS]
        *   Setting driveFolderIds can reduce time for searching files in the Google Drive.
    *   [Optional] if you want the tool to download videos from your YouTube channel as input source to the tool,
        *   youtubeWindow: 6
        *   Set youtubeWindow with the number of months in the past the tool should retrieve videos for.
        *   Configure the YouTube API by setting up youtubeServiceEnable and youtubeSecret respectively.

6.  To run the tool in a set order at once
    (get asset file urls -> remove assets -> upload assets -> refresh mapping sheet)
    
    *   Schedule the scripts to run:
        ```
        $ python3 creative_mango_main.py
        ```
    To customize the order of each step,
    *   Schedule each script to run:
        ```
          $ python3 refresh_mapping_sheet.py
          $ python3 get_file.py
          $ python3 creative_remover.py
          $ python3 creative_uploader.py
        ```

7.  About uploading YouTube video via YouTube API

    *   Ask your Google support to help you increase the YouTube API quota.
        Default is 6 videos per day.
    *   You will need to be add as YouTube `Channel managers` to upload videos.
    *   You should see a pop window asking you to grant the access to your
        YouTube channel. You will only need to grant the access once. After you
        grant the access, you should find 'yt_token.json' generated
        in same folder. Don't move 'yt_token.json' as it will be
        used in 'youtube_api.py'. If you choose the wrong channel, you can
        delete 'yt_token.json' and rerun step 6.

**NOTE**: This is not an officially supported Google product.

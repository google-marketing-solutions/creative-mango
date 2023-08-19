# App Campaign Creative Automation Solution

App Campaign Creative Automation Solution serves as a feed-centric creative management solution tailored for App campaign.
It also facilitates effortless video uploads to YouTube.<br/>

With this tool, clients can conveniently manage their desired creative actions within a spreadsheet.
The tool then takes charge, handling the process of pulling creatives and subsequently refreshing your App campaigns with the latest updates.<br/>
<br/>

The overall solution architect is as follows.
![solution architect](https://github.com/google-marketing-solutions/creative-mango/assets/66818527/57647a9b-d781-4418-b7c1-c10b784c0c16)


## Business logics
1. Easily set up scheduled promotions for your flighted creatives in the App Campaign.

![flighted creatives](https://github.com/google-marketing-solutions/creative-mango/assets/66818527/5d191a86-a3e5-477b-b824-a3907fefc219)

2. Automatically replace underperforming creatives with new ones once you reach the maximum creative limit.


![underperforming creatives](https://github.com/google-marketing-solutions/creative-mango/assets/66818527/8bea9d97-7a1c-4b20-b91e-c365e1d29d87)



**NOTE**: This library is _not_ compatible with Python versions less than Python 3.7.



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

3.  Set up your credentials.

    - 3a Generate Client ID and Client Secret credentials
        *   Open [Cloud credentials](https://console.developers.google.com/apis/credentials)
        *   Create credentials -> Create 'OAuth client ID' -> Web Application
            *   If you haven’t configured consent screen, setup consent screen first.
            *   User Type: External / Publishing Status: In production
            *   If you want to run the tool in testing mode, make sure to add "test user" and add following "scopes":
                Google Ads API, Google Drive API, Google Sheets API, YouTube Data API v3
            *   Add the follwing 'Authorized redirect URIs' : 'http://localhost:8008/' and 'http://localhost:8080/' and 'https://developers.google.com/oauthplayground'
            *   Copy 'client_id' and 'client_client_secret' from previous step into 'config/google-ads.yaml' and 'config/token.json' and 'config/yt_token.json'
    - 3b   Generate refresh token:
        *   Open [Oauth Playground](https://developers.google.com/oauthplayground)
            *   On the right panel, find the 'OAuth 2.0 configuration' button
            *   Tick 'Use your own OAuth credentials' box and then fill in 'client_id' and 'client_client_secret'
            *   On the left panel, select the scopes of
                * 'https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/adwords', 'https://www.googleapis.com/auth/drive'
            *   Click 'Authorize APIs' and select the correct account
            *   Click 'Exchange authorization code for tokens' and
            *   Copy the 'Refresh token' and paste it 'config/google-ads.yaml' and 'config/token.json'
            *   Copy the 'Access token' and paste it 'config/token.json'
    - 3c [Optional] Generate refresh token for YouTube:
         *   Open [Oauth Playground](https://developers.google.com/oauthplayground)
             *   On the right panel, find the 'OAuth 2.0 configuration' button
             *   Tick 'Use your own OAuth credentials' box and then fill in 'client_id' and 'client_client_secret'
             *   On the left panel, select the scopes of
                 *   https://www.googleapis.com/auth/youtube' 'https://www.googleapis.com/auth/youtube.upload', 'https://www.googleapis.com/auth/youtube.readonly'
             *   Click 'Authorize APIs' and select the correct account
             *   Click 'Exchange authorization code for tokens' and
             *   Copy the 'Refresh token' and paste it 'config/yt_token.json'
             *   Copy the 'Access token' and paste it 'config/yt_token.json'
    - 3d. Grant access to sheet and drive:
         *   Grant the cloud account email with 'Viewer' access to all 'Google Drives' [Cloud account email is any 'Owner' role email in]
         *   Grant the cloud account email with 'Editor' access to the 'Sheet'  you just copied in step 2.
         *   Grant cloud account email with [standard access](https://support.google.com/google-ads/answer/6372672?hl=en) your AdWords account
             *   Cloud account email is any 'Owner' role email in [cloud project](https://console.developers.google.com/iam-admin)
5.  In google-ads.yaml file update following fields:

    *   [developer_token](https://developers.google.com/google-ads/api/docs/first-call/dev-token)
    *   [Optional] login_customer_id, only if you setup under [manager account](https://support.google.com/google-ads/answer/6139186)

6.  Update configuration in the config/setup.yaml

    *   spreadsheetIds,
    *   [Optional] to setup YouTube API to upload videos,
        *   youtubeServiceEnable = True
    *   [Optional] if you want the tool to automatically update mapping sheets up-to-date,
        *   refreshMappingSheetEnable = True,
    *   [Optional] if you want the specify Google Drive folder ids for uploading image/video assets,
        *   driveFolderIds = [REPLACE_DRIVE_FOLDER_IDS]
        *   Setting driveFolderIds can reduce time for searching files in the Google Drive.

7.  To run the tool in a set order at once
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

8.  About uploading YouTube video via YouTube API

    *   You might want to raise YouTube API quota. Default is 6 videos per day.
    *   You will need to be add as YouTube `Channel managers` to upload videos.

**NOTE**: This is not an officially supported Google product.

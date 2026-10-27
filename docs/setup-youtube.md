# Connecting YouTube

ClipQueue uploads with **your own** Google Cloud OAuth client. This is standard for self-hosted YouTube tools: no shared app, no middleman, and your quota is yours. It takes about 10–15 minutes and is free.

## 1. Create a Google Cloud project

1. Go to <https://console.cloud.google.com/projectcreate>.
2. Name it anything (for example "ClipQueue") and click **Create**.

## 2. Enable the YouTube Data API

1. Open <https://console.cloud.google.com/apis/library/youtube.googleapis.com>.
2. Make sure your new project is selected at the top, then click **Enable**.

## 3. Set up the consent screen

1. Open **Google Auth Platform**: <https://console.cloud.google.com/auth/overview>.
2. Click **Get started**.
3. Enter an app name (e.g. "ClipQueue") and your email.
4. For **Audience**, choose **External**.
5. Finish the wizard.
6. Under **Audience → Test users**, add the Google account that owns your YouTube channel.

## 4. Create the OAuth client

1. Under **Clients**, click **Create client**.
2. Application type: **Desktop app**. Any name works.
3. Click **Create**, then **Download JSON**.

> It must be a **Desktop app** client. ClipQueue rejects "Web application" clients because their redirect URLs don't match a local app.

## 5. Add it to ClipQueue

In ClipQueue (setup wizard, or **Settings → YouTube**):

1. Choose the downloaded JSON file and click **Add client file**.
2. Click **Connect YouTube** and sign in with the account you added as a test user.
3. Google will say **"Google hasn't verified this app."** That's expected, because you are the developer. Click **Continue**.
4. Allow the requested access: upload videos, and view your channel name.

You'll land back in ClipQueue and see your channel name.

## Troubleshooting

### "Sign-in expired" after a week

Google expires sign-ins after **7 days** for projects in **Testing** mode. You have two options:

- Click **Connect YouTube** again when it happens, or
- In **Google Auth Platform → Audience**, click **Publish app** to move it to *In production*. For personal use you don't need to submit for verification. You'll keep seeing the "unverified app" warning when you sign in, but sign-ins stop expiring.

### If uploads end up private

Google has at times locked uploads from **unverified** API projects to private. When that happens, ClipQueue shows "YouTube kept it private" on the clip. Options:

- Publish those videos by hand in YouTube Studio (ClipQueue links to each one).
- Apply for a YouTube API **compliance audit** for your project. It's free but takes time: <https://support.google.com/youtube/contact/yt_api_form>.

### "Daily limit reached"

Each Google project gets a daily API quota, and uploads use a large share of it. ClipQueue pauses until the next day and carries on automatically. Keep **Max uploads per day** in Settings at about 5 or lower.

### Where are my credentials stored?

In your ClipQueue data folder (default `~/.clipqueue`): `client_secret.json` and `youtube_token.json`. Don't share them. To revoke access, click **Disconnect** in ClipQueue and remove the app at <https://myaccount.google.com/permissions>.

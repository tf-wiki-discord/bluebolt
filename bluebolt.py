import discord
import requests
import pytz
import datetime
import asyncio
import threading
import os
from http.server import SimpleHTTPRequestHandler, HTTPServer
from dotenv import load_dotenv


load_dotenv()
SLEEP_SECONDS = int(os.getenv('SLEEP_SECONDS'))
DID = os.getenv('DID')
DISCORD_TOKEN = os.getenv('BLUEBOLT_TOKEN')
CHANNEL_ID = int(os.getenv('LIVE_CHANNEL_ID'))

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.messages = True
intents.guild_messages = True
intents.guilds = True

bot = discord.Client(intents=intents)

last_post_timestamp = None
first_check = True
timezone = pytz.timezone('Europe/London')


def fetch_bluesky_posts():
    print(f"Fetching posts for DID: {DID}")
    posts = requests.get(
        "https://bsky.social/xrpc/com.atproto.repo.listRecords",
        params={
            "repo": DID,
            "collection": "app.bsky.feed.post",
            "reverse": "true",  # FIX: ensures newest posts come first
        }
    )
    print(f"Response status: {posts.status_code}")
    return posts.json()


def convert_at_to_https(post_url):
    """Converts an at:// URI to a bsky.app HTTPS URL for any DID type."""
    if post_url.startswith('at://'):
        # FIX: handle all DID types, not just did:plc
        parts = post_url[len('at://'):].split('/')
        # parts = [did, 'app.bsky.feed.post', rkey]
        if len(parts) == 3:
            did, _, rkey = parts
            return f"https://bsky.app/profile/{did}/post/{rkey}"
    return post_url


async def send_new_post(channel, post):
    post_url = post.get('uri', '')
    post_url = convert_at_to_https(post_url)
    print(f"Sending post to Discord: {post_url}")
    try:
        await channel.send(post_url)
        print(f"Successfully sent post!")
    except discord.DiscordException as e:
        print(f"Error sending message: {e}")


async def check_new_posts():
    global last_post_timestamp, first_check
    await bot.wait_until_ready()

    channel = bot.get_channel(CHANNEL_ID)
    if channel is None:
        print("Channel not found. Check the channel ID.")
        return
    else:
        print(f"Channel found: {channel.name} (ID: {channel.id})")

    while not bot.is_closed():
        print(f"\n--- Checking for new posts at {datetime.datetime.now()} ---")
        try:
            posts_data = fetch_bluesky_posts()
            print(f"Posts data keys: {posts_data.keys() if posts_data else 'None'}")

            if posts_data and 'records' in posts_data:
                print(f"Found {len(posts_data['records'])} total records")

                for i, post_item in enumerate(posts_data['records']):
                    post_data = post_item.get('value', {})
                    is_reply = post_data.get('reply', {})
                    post_timestamp = post_data.get('createdAt', '')

                    print(f"Post {i}: timestamp={post_timestamp}, is_reply={bool(is_reply)}")

                    if not is_reply:
                        try:
                            post_time = datetime.datetime.fromisoformat(
                                post_timestamp.replace('Z', '+00:00')
                            )
                        except ValueError as e:
                            print(f"Error parsing timestamp: {e}")
                            continue

                        if first_check:
                            # FIX: on first run, just record the timestamp without posting,
                            # so the bot doesn't re-announce the latest post on every restart.
                            print(f"First check — storing latest timestamp: {post_time} (not reposting)")
                            last_post_timestamp = post_time
                            first_check = False
                        elif post_time > last_post_timestamp:
                            print(f"New post found! {last_post_timestamp} -> {post_time}")
                            last_post_timestamp = post_time
                            await send_new_post(channel, post_item)
                        else:
                            print(f"No new posts. Latest: {last_post_timestamp}")

                        break  # Only check the newest non-reply post
            else:
                print("No records found or invalid response")

        except Exception as e:
            print(f"Error in check_new_posts: {e}")
            import traceback
            traceback.print_exc()

        print(f"Sleeping for {SLEEP_SECONDS} seconds...")
        await asyncio.sleep(SLEEP_SECONDS)


@bot.event
async def on_ready():
    print(f'Bot connected as {bot.user}')
    bot.loop.create_task(check_new_posts())


def run_http_server():
    port = 8000
    server_address = ('', port)
    httpd = HTTPServer(server_address, SimpleHTTPRequestHandler)
    print(f"HTTP server running on port {port}")
    httpd.serve_forever()


if __name__ == "__main__":
    # FIX: run HTTP server in background thread, keep bot on main thread
    http_thread = threading.Thread(target=run_http_server, daemon=True)
    http_thread.start()

    bot.run(DISCORD_TOKEN)

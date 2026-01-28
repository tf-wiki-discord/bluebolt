import discord
import requests
import pytz
import datetime
import asyncio
import threading
import os
from http.server import SimpleHTTPRequestHandler, HTTPServer
from dotenv import load_dotenv


# Bot config
load_dotenv()
SLEEP_SECONDS = int(os.getenv('SLEEP_SECONDS'))
DID = os.getenv('DID') # tfwiki bluesky DID
DISCORD_TOKEN = os.getenv('BLUEBOLT_TOKEN')
CHANNEL_ID = int(os.getenv('LIVE_CHANNEL_ID')) # bluesky
#CHANNEL_ID = int(os.getenv('TEST_CHANNEL_ID')) # coding

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.messages = True
intents.guild_messages = True
intents.guilds = True

bot = discord.Client(intents=intents)

last_post_id = None
timezone = pytz.timezone('Europe/London')

def fetch_bluesky_posts():
    posts = requests.get(
        "https://bsky.social/xrpc/com.atproto.repo.listRecords",
        params={
            "repo": DID,
            "collection": "app.bsky.feed.post",
    })
    return posts.json()

def convert_at_to_https(post_url):
    if post_url.startswith('at://'):
        # Converts the at:// link to https://bsky.app/profile/...
        post_url = post_url.replace('at://did:plc:', 'https://bsky.app/profile/did:plc:')
        post_url = post_url.replace('/app.bsky.feed.post/', '/post/')
    return post_url

async def send_new_post(channel, post):
    post_url = post.get('uri', '')
    post_url = convert_at_to_https(post_url)  # Convert the post URL if necessary
    try:
        await channel.send(post_url)
    except discord.DiscordException as e:
        print(f"Error on sending message: {e}")



# Global variable to store the timestamp of the last post
last_post_timestamp = None

async def check_new_posts():
    global last_post_timestamp
    await bot.wait_until_ready()

    channel = bot.get_channel(CHANNEL_ID)
    if channel is None:
        print("Channel not found. Check the channel ID.")
        return

    while not bot.is_closed():
        posts_data = fetch_bluesky_posts()
        if posts_data and 'records' in posts_data:
            # Since posts are in reverse chronological order (newest first),
            # we only need to check the first non-reply post
            for post_item in posts_data['records']:
                post_data = post_item.get('value', {})
                is_reply = post_data.get('reply', {})  # Check if there's a reply
                
                if not is_reply:  # Only processes if there is no reply
                    post_id = post_item.get('uri', '')
                    post_timestamp = post_data.get('createdAt', '')
                    
                    # Converts post timestamp to datetime
                    try:
                        post_time = datetime.datetime.fromisoformat(post_timestamp.replace('Z', '+00:00'))
                    except ValueError:
                        continue

                    # Checks if the post is new and occurs after the last registered timestamp
                    if (last_post_timestamp is None) or (post_time > last_post_timestamp):
                        print(f"Latest vs current timestamp: {last_post_timestamp} vs {post_time}")
                        last_post_timestamp = post_time  # Updates the timestamp of the last post processed
                        await send_new_post(channel, post_item)
                    
                    # Break after processing the first non-reply post (newest non-reply)
                    # to avoid reprocessing old posts
                    break
        
        await asyncio.sleep(SLEEP_SECONDS)  # Checks for new posts every SLEEP_SECONDS seconds.

@bot.event
async def on_ready():
    print(f'Bot connected as {bot.user}')
    bot.loop.create_task(check_new_posts())

def run_http_server():
    port = 8080
    server_address = ('', port)
    httpd = HTTPServer(server_address, SimpleHTTPRequestHandler)
    print(f"HTTP server running on port {port}")
    httpd.serve_forever()

if __name__ == "__main__":
    # Runs the Discord bot in parallel with the HTTP server
    bot_thread = threading.Thread(target=bot.run, args=(DISCORD_TOKEN,))
    bot_thread.start()

    run_http_server()

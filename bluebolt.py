import discord
from discord.ext import commands
import requests
import pytz
import datetime
import asyncio
import os
from http.server import SimpleHTTPRequestHandler, HTTPServer
import threading

# Bot config
SLEEP_SECONDS = 300
DID = "did:plc:dfkv7k7rxcrvaj7ncbvlnjy7" # tfwiki bluesky DID
DISCORD_TOKEN = os.environ['BLUEBOLT_TOKEN']
channel_id = int("1315876382257053746") # test-bloosk

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.messages = True
intents.guild_messages = True
intents.guilds = True

bot = commands.Bot(command_prefix='!-', intents=intents)

last_post_id = None
timezone = pytz.timezone('Europe/London')

def fetch_bluesky_posts():
    my_posts = requests.get(
        "https://bsky.social/xrpc/com.atproto.repo.listRecords",
        params={
            "repo": DID,
            "collection": "app.bsky.feed.post",
    })
    return my_posts.json()

def fetch_bluesky_posts_loop():
    all_posts = []

    more_posts = True
    cursor = ''

    while more_posts:
        try:
            post_batch = requests.get(
                "https://bsky.social/xrpc/com.atproto.repo.listRecords",
                params={
                    "repo": DID,
                    "collection": "app.bsky.actor.post",
                    "cursor": cursor
                },
            ).json()

        except Exception as e:
            print(f"Error in accessing Bluesky API: {e}")
            return None

        all_posts.extend(post_batch['records'])

        if 'cursor' in post_batch:
            cursor = post_batch['cursor']
        else:
            more_posts = False

    return all_posts


def convert_at_to_https(post_url):
    if post_url.startswith('at://'):
        # Converts the at:// link to https://bsky.app/profile/...
        post_url = post_url.replace('at://did:plc:', 'https://bsky.app/profile/did:plc:')
        post_url = post_url.replace('/app.bsky.feed.post/', '/post/')
    return post_url

async def send_new_post(channel, post):
    post_url = convert_at_to_https(post_url)  # Convert the post URL if necessary
    try:
        await channel.send(post_url)
    except discord.DiscordException as e:
        print(f"Error on sending message: {e}")

    """
    post_content = post.get('value', {}).get('text', "Post with no content available.")
    author = "TFWiki"
    author_handle = "tfwiki.net"
    #author_avatar = author.get('avatar', '')  # URL profile photo
    post_url = post.get('uri', '')
    #post_url = post.get('value', {}).get('uri', '')
    """

    """
    embed = discord.Embed(
        description=post_content,
        color=0xff0053  # hex code of embed color
    )
    
    # Add the Bluesky icon next to the author's name
    bluesky_icon = "https://bsky.app/static/favicon-16x16.png"
    embed.set_author(name=f"@{author_handle}", icon_url=bluesky_icon)
    
    # Add the image to the embed if available
    embed_data = post.get('value', {}).get('embed', {})
    if embed_data and embed_data.get('$type') == 'app.bsky.embed.images':
        images = embed_data.get('images', [])
        if images:
            fullsize_image_url = images[0].get('fullsize', '')
            if fullsize_image_url.startswith(('http://', 'https://')):
                embed.set_image(url=fullsize_image_url)

    # Add author avatar to embed
    #if author_avatar.startswith(('http://', 'https://')):
    #    embed.set_thumbnail(url=author_avatar)


    # Add the author's icon as a thumbnail next to the embed
    embed.description += f"\n\n[View on BlueSky]({post_url})"

    try:
        message = await channel.send(embed=embed)
        print(f"Message sent: {post_url}")
        
        # Adds a red heart reaction to the sent message
        # await message.add_reaction("❤️")
    except discord.DiscordException as e:
        print(f"Error on sending message: {e}")
"""

# Global variable to store the timestamp of the last post
last_post_timestamp = None

async def check_new_posts():
    global last_post_timestamp
    await bot.wait_until_ready()

    channel = bot.get_channel(channel_id)
    if channel is None:
        print("Channel not found. Check the channel ID.")
        return

    while not bot.is_closed():
        posts_data = fetch_bluesky_posts()
        #await channel.send(f"test bloosk retrieval: {posts_data['records'][0]}")
        if posts_data and 'records' in posts_data:
            for post_item in posts_data['records']:
                post_data = post_item.get('value', {})
                root = post_item.get('reply', {}).get('root', None)  # Check if there is an associated root

                if root is None:  # Only processes if there is no root (normal posting)
                    post_id = post_item.get('uri', '')
                    post_timestamp = post_data.get('createdAt', '')
                    
                    # Converts post timestamp to datetime
                    try:
                        post_time = datetime.datetime.fromisoformat(post_timestamp.replace('Z', '+00:00'))
                    except ValueError:
                        continue

                    # Checks if the post is new and occurs after the last registered timestamp
                    if (last_post_timestamp is None) or (post_time > last_post_timestamp):
                        await channel.send(f"Latest vs current timestamp: {last_post_timestamp} vs {post_time}")
                        last_post_timestamp = post_time  # Updates the timestamp of the last post processed
                        await send_new_post(channel, post_item)
        
        await asyncio.sleep(SLEEP_SECONDS)  # Checks for new posts every SLEEP_SECONDS seconds.

@bot.event
async def on_ready():
    print(f'Bot connected as {bot.user}')
    bot.loop.create_task(check_new_posts())

"""
@bot.command(name="clean", help="Deletes all messages sent by the bot.")
@commands.has_permissions(administrator=True)
async def clear(ctx):
    if ctx.author.guild_permissions.administrator:
        channel = ctx.channel
        def is_bot_msg(msg):
            return msg.author == bot.user
        deleted = await channel.purge(limit=100, check=is_bot_msg, bulk=True)
        await ctx.send(f"All bot messages deleted! ({len(deleted)} messages deleted.)")
    else:
        await ctx.send("You don't have permissions to use that command.")
"""

# Function to start simple HTTP server
def run_http_server():
    port = 8000
    server_address = ('', port)
    httpd = HTTPServer(server_address, SimpleHTTPRequestHandler)
    print(f"HTTP server running on port {port}")
    httpd.serve_forever()

if __name__ == "__main__":
    # Runs the Discord bot in parallel with the HTTP server
    bot_thread = threading.Thread(target=bot.run, args=(DISCORD_TOKEN,))
    bot_thread.start()

    run_http_server()

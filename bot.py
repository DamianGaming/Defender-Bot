import nextcord
from nextcord.ext import commands, tasks
from nextcord import Interaction, SlashOption
from nextcord.ui import Button, View
import youtube_dl
import os
import json
import asyncio
import random
from datetime import datetime
from googleapiclient.discovery import build

# Bot setup
intents = nextcord.Intents.default()
intents.members = True
intents.message_content = True
intents.guilds = True
intents.voice_states = True

bot = commands.Bot(command_prefix='/', intents=intents)

# Configuration
config = {
    "welcome_channel": None,
    "leave_channel": None,
    "mod_log_channel": None,
    "auto_mod_level": "medium",
    "youtube_channel_id": None,
    "youtube_api_key": None,
    "last_video_id": None,
}

if not os.path.isfile("config.json"):
    with open("config.json", "w") as f:
        json.dump(config, f)

with open("config.json", "r") as f:
    config = json.load(f)

def save_config():
    with open("config.json", "w") as f:
        json.dump(config, f)

# Event Listeners
@bot.event
async def on_ready():
    print(f'Bot is online as {bot.user}')
    check_new_videos.start()

@bot.event
async def on_member_join(member):
    if config["welcome_channel"]:
        channel = bot.get_channel(config["welcome_channel"])
        await channel.send(f"Welcome to the server, {member.mention}!")

@bot.event
async def on_member_remove(member):
    if config["leave_channel"]:
        channel = bot.get_channel(config["leave_channel"])
        await channel.send(f"{member.mention} has left the server.")

# Auto Moderation
bad_words = [
    "fuck", "bitch", "shit", "asshole", "bastard", "cunt", "damn", "dick",
    "douche", "fag", "faggot", "motherfucker", "nigger", "prick", "pussy",
    "slut", "twat", "whore", "wanker"
]

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    if any(word in message.content.lower() for word in bad_words):
        await message.delete()
        await message.channel.send(f"{message.author.mention}, watch your language!")
        log_channel = bot.get_channel(config["mod_log_channel"])
        if log_channel:
            embed = nextcord.Embed(title="Auto Moderation", description=f"Message deleted in {message.channel.mention}", color=0xFF0000)
            embed.add_field(name="User", value=message.author.mention)
            embed.add_field(name="Message", value=message.content)
            embed.set_footer(text=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            await log_channel.send(embed=embed)

    await bot.process_commands(message)

# Moderation Commands
@bot.slash_command(description="Kick a member")
@commands.has_permissions(kick_members=True)
async def kick(interaction: Interaction, member: nextcord.Member, reason: str = None):
    await member.kick(reason=reason)
    await interaction.response.send_message(f"{member.mention} has been kicked for {reason}")
    log_channel = bot.get_channel(config["mod_log_channel"])
    if log_channel:
        embed = nextcord.Embed(title="Kick", description=f"{member.mention} was kicked", color=0xFFA500)
        embed.add_field(name="Reason", value=reason)
        embed.set_footer(text=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        await log_channel.send(embed=embed)

@bot.slash_command(description="Ban a member")
@commands.has_permissions(ban_members=True)
async def ban(interaction: Interaction, member: nextcord.Member, reason: str = None):
    await member.ban(reason=reason)
    await interaction.response.send_message(f"{member.mention} has been banned for {reason}")
    log_channel = bot.get_channel(config["mod_log_channel"])
    if log_channel:
        embed = nextcord.Embed(title="Ban", description=f"{member.mention} was banned", color=0xFF0000)
        embed.add_field(name="Reason", value=reason)
        embed.set_footer(text=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        await log_channel.send(embed=embed)

@bot.slash_command(description="Mute a member")
@commands.has_permissions(manage_roles=True)
async def mute(interaction: Interaction, member: nextcord.Member, reason: str = None):
    role = nextcord.utils.get(interaction.guild.roles, name="Muted")
    if not role:
        role = await interaction.guild.create_role(name="Muted")
        for channel in interaction.guild.channels:
            await channel.set_permissions(role, speak=False, send_messages=False)
    await member.add_roles(role, reason=reason)
    await interaction.response.send_message(f"{member.mention} has been muted for {reason}")
    log_channel = bot.get_channel(config["mod_log_channel"])
    if log_channel:
        embed = nextcord.Embed(title="Mute", description=f"{member.mention} was muted", color=0xFFFF00)
        embed.add_field(name="Reason", value=reason)
        embed.set_footer(text=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        await log_channel.send(embed=embed)

@bot.slash_command(description="Unmute a member")
@commands.has_permissions(manage_roles=True)
async def unmute(interaction: Interaction, member: nextcord.Member):
    role = nextcord.utils.get(interaction.guild.roles, name="Muted")
    if role in member.roles:
        await member.remove_roles(role)
        await interaction.response.send_message(f"{member.mention} has been unmuted")
        log_channel = bot.get_channel(config["mod_log_channel"])
        if log_channel:
            embed = nextcord.Embed(title="Unmute", description=f"{member.mention} was unmuted", color=0x00FF00)
            embed.set_footer(text=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            await log_channel.send(embed=embed)
    else:
        await interaction.response.send_message(f"{member.mention} is not muted")

# Music Commands
ytdl_format_options = {
    'format': 'bestaudio/best',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0'  # bind to ipv4 since ipv6 addresses cause issues sometimes
}

ffmpeg_options = {
    'options': '-vn'
}

ytdl = youtube_dl.YoutubeDL(ytdl_format_options)

class YTDLSource(nextcord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get('title')
        self.url = data.get('url')

    @classmethod
    async def from_url(cls, url, *, loop=None, stream=False):
        loop = loop or asyncio.get_event_loop()
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=not stream))
        if 'entries' in data:
            data = data['entries'][0]
        filename = data['url'] if stream else ytdl.prepare_filename(data)
        return cls(nextcord.FFmpegPCMAudio(filename, **ffmpeg_options), data=data)

@bot.slash_command(description="Join voice channel")
async def join(interaction: Interaction, channel: nextcord.VoiceChannel):
    if interaction.user.voice is None:
        await interaction.response.send_message("You are not in a voice channel!")
        return
    vc = await channel.connect()
    await interaction.response.send_message(f"Connected to {channel}")

@bot.slash_command(description="Leave voice channel")
async def leave(interaction: Interaction):
    if interaction.guild.voice_client is None:
        await interaction.response.send_message("Not connected to a voice channel.")
        return
    await interaction.guild.voice_client.disconnect()
    await interaction.response.send_message("Disconnected from voice channel.")

@bot.slash_command(description="Play music")
async def play(interaction: Interaction, url: str):
    if interaction.guild.voice_client is None:
        await interaction.response.send_message("Not connected to a voice channel.")
        return
    async with interaction.typing():
        player = await YTDLSource.from_url(url, loop=bot.loop, stream=True)
        interaction.guild.voice_client.play(player, after=lambda e: print(f'Player error: {e}') if e else None)
        await interaction.response.send_message(f"Now playing: {player.title}")

# Polls
@bot.slash_command(description="Create a poll")
async def poll(interaction: Interaction, question: str, option1: str, option2: str):
    embed = nextcord.Embed(title="Poll", description=question, color=0x00ff00)
    embed.add_field(name="Option 1", value=option1, inline=False)
    embed.add_field(name="Option 2", value=option2, inline=False)
    message = await interaction.channel.send(embed=embed)
    await message.add_reaction("1️⃣")
    await message.add_reaction("2️⃣")
    await interaction.response.send_message("Poll created!", ephemeral=True)

# Giveaways
@bot.slash_command(description="Start a giveaway")
async def giveaway(interaction: Interaction, duration: int, prize: str):
    embed = nextcord.Embed(title="Giveaway!", description=f"Prize: {prize}", color=0x00ff00)
    embed.add_field(name="Hosted by", value=interaction.user.mention, inline=False)
    embed.set_footer(text=f"Ends in {duration} seconds!")
    message = await interaction.channel.send(embed=embed)
    await message.add_reaction("🎉")
    await interaction.response.send_message("Giveaway started!", ephemeral=True)

    for remaining in range(duration, 0, -1):
        await asyncio.sleep(1)
        embed.set_footer(text=f"Ends in {remaining} seconds!")
        await message.edit(embed=embed)

    new_message = await interaction.channel.fetch_message(message.id)
    users = await new_message.reactions[0].users().flatten()
    users.pop(users.index(bot.user))

    if len(users) == 0:
        await interaction.channel.send("No one participated in the giveaway.")
        return

    winner = random.choice(users)
    await interaction.channel.send(f"Congratulations {winner.mention}, you won the prize: {prize}!")

# Dashboard Command
@bot.slash_command(description="Open the dashboard for configuration")
async def dashboard(interaction: Interaction):
    embed = nextcord.Embed(title="Bot Dashboard", description="Configure your bot settings", color=0x00ff00)
    embed.add_field(name="Welcome Channel", value=f"<#{config['welcome_channel']}>" if config["welcome_channel"] else "Not set")
    embed.add_field(name="Leave Channel", value=f"<#{config['leave_channel']}>" if config["leave_channel"] else "Not set")
    embed.add_field(name="Mod Log Channel", value=f"<#{config['mod_log_channel']}>" if config["mod_log_channel"] else "Not set")
    embed.add_field(name="Auto Mod Level", value=config["auto_mod_level"])
    embed.add_field(name="YouTube Channel ID", value=config["youtube_channel_id"] if config["youtube_channel_id"] else "Not set")

    button = Button(label="Configure", style=nextcord.ButtonStyle.green)
    view = View()
    view.add_item(button)

    async def button_callback(interaction):
        await interaction.user.send(embed=embed)

    button.callback = button_callback
    await interaction.response.send_message("Dashboard sent to your DMs!", ephemeral=True)

# YouTube Video Uploads
def get_latest_video(youtube, channel_id):
    request = youtube.search().list(
        part="snippet",
        channelId=channel_id,
        maxResults=1,
        order="date"
    )
    response = request.execute()
    if "items" in response and len(response["items"]) > 0:
        return response["items"][0]
    return None

@tasks.loop(minutes=5)
async def check_new_videos():
    if not config["youtube_channel_id"] or not config["youtube_api_key"]:
        return

    channel = bot.get_channel(config["mod_log_channel"])
    if not channel:
        return

    youtube = build("youtube", "v3", developerKey=config["AIzaSyBi8YHvMmTbxQ-xgQ1HibaSjWUNjlXpX9k"])
    latest_video = get_latest_video(youtube, config["youtube_channel_id"])

    if latest_video:
        video_id = latest_video["id"]["videoId"]
        if video_id != config["last_video_id"]:
            video_title = latest_video["snippet"]["title"]
            video_url = f"https://www.youtube.com/watch?v={video_id}"
            await channel.send(f"New video uploaded: {video_title} - {video_url}")
            config["last_video_id"] = video_id
            save_config()

# Run the bot
bot.run('MTI2NzA0MDgxMTUwNjIwODgxOQ.Gt9nip.mw0CckqV7KTfcjUJ0yklK03onHW2vpVYiW3OUM')

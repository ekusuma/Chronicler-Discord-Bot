#!/usr/bin/python3

import discord
import datetime
import pytz


################################################################################
# Initialization: read token file + create new client object
################################################################################

try:
    token_file = open('.token', 'r')
    TOKEN = token_file.read().strip()
    token_file.close()
    if len(TOKEN) < 1:
        print('ERROR: .token file appears to be empty.')
        exit(1)
except FileNotFoundError:
    print('ERROR: Unable to read a .token file. Please make sure it exists.')
    exit(1)

client = discord.Client()


################################################################################
# Misc helper functions
################################################################################

def log(msg):
    ct = datetime.datetime.now()
    ct_pst = ct.astimezone(pytz.timezone('US/Pacific'))
    cts = ct_pst.strftime("%Y/%m/%d %H:%M:%S")
    print("[{}] {}".format(cts, msg))


################################################################################
# Discord event functions
################################################################################

@client.event
async def on_ready():
    log('BEEP BEEP. Logged in as <{0.user}>'.format(client))

@client.event
async def on_message(message):
    if message.author == client.user:
        return
    if message.content.startswith('$hello'):
        await message.channel.send('Orayo~!')

@client.event
async def on_raw_reaction_add(payload):
    # Need these for future ops
    guild = client.get_guild(payload.guild_id)
    channel = client.get_channel(payload.channel_id)

    # Get message, quoter, and quote author
    message = await channel.fetch_message(payload.message_id)
    member_saver = payload.member
    member_author = await guild.fetch_member(message.author.id)
    # Should know if the message is from a bot or not
    is_bot = message.author.bot

    # Exit early if not reacting with what we want
    if str(payload.emoji) != '💬':
        return

    # Log the operation to console
    log('Member {} is trying to save a quote:'.format(member_saver.nick))
    if (is_bot):
        log('  Request denied: tried to save a bot quote')
    else:
        log('  Author     :{}'.format(member_author.nick))
        log('  Channel    :{}'.format(channel.name))
        log('  Message    :{}'.format(message.content))

    # Remove reaction
    await message.clear_reaction('💬')

    # Don't accept if the quote author is a bot
    if (is_bot):
        await channel.send('Sorry {}, I don\'t save quotes from non-humans!'.format(member_saver.nick))
    else:
        # Acknowledge save with check mark emoji
        await message.add_reaction('✅')


################################################################################
# Run the bot
################################################################################

client.run(TOKEN)

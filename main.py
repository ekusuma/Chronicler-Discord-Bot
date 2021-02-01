#!/usr/bin/python3

import discord
import datetime
import pytz
import random

import dbhelper as db


################################################################################
# Useful globals
################################################################################

# Bot's private token, to be read from the .token file (DO NOT PUT IN REPO)
TOKEN = ''

# Global instance of the bot's Discord client
CLIENT = None

# Connection to the bot's MySQL DB
CONN = None

# Name of the quotes table
QUOTES_TABLE = 'quotes'

# Emojis to watch reactions for (aliased to variable names since typing emoji
# can be annoying)
EMOJI_QUOTE     = '💬'      # For quoting a message
EMOJI_DELQUOTE  = '❌'      # For deleting a message
# Use this set to determine if an emoji is in it
KEY_REACTS = {
    EMOJI_QUOTE,
    EMOJI_DELQUOTE
}
# These emoji are reactions for the bot to report a status
EMOJI_BOT_CONFIRM   = '✅'

# Fun statuses for the bot
BOT_STATUSES = [
    'I\'m DOG!',
    'WOWOWOWOWOW',
    'Orayo~!',
    'Hotate!',
    'tetaHo!',
    'Yubi yubi 🎵',
    'I\'m die, thank you forever',
    'Water in the fire...WHY?!',
    'Have confidence! ...no confidence!',
    'Eekum Bokum'
]


################################################################################
# Initialization
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

# Create new instance of Discord client
CLIENT = discord.Client()
# Create connection to Chronicler's MySQL DB
CONN = db.create_srv_conn('localhost', 'chronicler', TOKEN, 'chrondb')
if CONN == None:
    print('ERROR: Unable to connect to DB.')
    exit(1)
QUOTES_TABLE = 'quotes'

# Try to create the 'quotes' table--ignore the error if it exists
table_cols = """
    author_id BIGINT NOT NULL,
    quoter_id BIGINT,
    message_id BIGINT PRIMARY KEY,
    guild_id BIGINT NOT NULL,
    channel_id BIGINT NOT NULL
"""
db.create_table(CONN, QUOTES_TABLE, table_cols)


################################################################################
# Misc helper functions
################################################################################

def log(msg):
    ct = datetime.datetime.now()
    ct_pst = ct.astimezone(pytz.timezone('US/Pacific'))
    cts = ct_pst.strftime("%Y/%m/%d %H:%M:%S")
    print("[{}] {}".format(cts, msg))

def startswith_word(phrase, startswith):
    return len(phrase.split()) > 0 and phrase.split()[0] == startswith

async def set_rand_status():
    status = discord.CustomActivity(random.choice(BOT_STATUSES))
    await CLIENT.change_presence(activity=status)

async def roll_rand_status():
    num = random.randint(1, 100)
    # 5% chance to get a random status
    if (num <= 5):
        await set_rand_status()


################################################################################
# Helper classes
################################################################################

class Quote:
    def __init__(self, author=None, quoter=None, message=None):
        self.author = author
        self.quoter = quoter
        self.message= message

    async def save_to_db(self):
        author_id = self.author.id
        quoter_id = self.quoter.id
        message_id = self.message.id
        guild_id = self.message.guild.id
        channel_id = self.message.channel.id
        is_bot = self.author.bot

        # Debug logging
        log('Member {} is trying to save a quote:'.format(self.quoter.name))
        if is_bot:
            log('  Request denied: tried to save a bot quote')
        else:
            log('  Author       :{}'.format(self.author.name))
            log('  Channel      :{}'.format(self.message.channel.name))
            log('  Message      :{}'.format(self.message.content))

        # Don't accept if the quote author is a bot
        if (is_bot):
            await self.message.clear_reaction('💬')
            await self.message.channel.send(
                'Sorry {}, I don\'t save quotes from non-humans!'.format(member_saver.nick))
            return

        cols = 'author_id, quoter_id, message_id, guild_id, channel_id'
        vals = '{}, {}, {}, {}, {}'.format(
                author_id, quoter_id, message_id, guild_id, channel_id)
        db.insert_partial(CONN, QUOTES_TABLE, cols, vals)

        # Acknowledge save with check mark emoji
        await self.message.clear_reaction(EMOJI_QUOTE)
        await self.message.add_reaction(EMOJI_BOT_CONFIRM)

    async def remove_from_db(self):
        log('Member {} is trying to delete a quote:'.format(self.quoter.name))
        log('  Author       :{}'.format(self.author.name))
        log('  Channel      :{}'.format(self.message.channel.name))
        log('  Message      :{}'.format(self.message.content))

        retval = db.delete(CONN, QUOTES_TABLE, 'message_id={}'.format(self.message.id))
        if retval != 0:
            log('  Error: Unable to delete message')
        else:
            # Acknowledge deletee with removing check mark emoji
            await self.message.clear_reaction(EMOJI_DELQUOTE)
            await self.message.clear_reaction(EMOJI_BOT_CONFIRM)

    async def fill_from_entry(self, entry):
        # Assumes that entry is tuple of:
        #   (author_id, quoter_id, message_id, guild_id, channel_id)
        if len(entry) < 5:
            log('ERROR: Tried to populate quote object with invalid entry')
            return 1
        author_id = int(entry[0])
        quoter_id = int(entry[1])
        msg_id = int(entry[2])
        guild_id = int(entry[3])
        channel_id = int(entry[4])

        guild = await CLIENT.fetch_guild(guild_id)
        channel = await CLIENT.fetch_channel(channel_id)
        self.author = await guild.fetch_member(author_id)
        self.quoter = await guild.fetch_member(quoter_id)
        self.message = await channel.fetch_message(msg_id)


################################################################################
# Main helper functions
################################################################################

async def repeat_quote(channel, quote):
    # Get URL to quoted message
    server_id = channel.guild.id
    channel_id = channel.id
    msg_id = quote.message.id
    url = 'https://discordapp.com/channels/{}/{}/{}'.format(
        server_id, channel_id, msg_id)

    embed = discord.Embed(
        title='Quotes from the Chronicler!',
        color=discord.Color.red(),
        description='> ' + quote.message.content,
        url=url
    )
    embed.set_author(name=CLIENT.user, icon_url=CLIENT.user.avatar_url)
    embed.set_thumbnail(url=quote.author.avatar_url)

    # Construct footer
    ctime = quote.message.created_at
    ctime_pst = ctime.astimezone(pytz.timezone('US/Pacific'))
    ctime_str = ctime_pst.strftime('%b %-d, %Y at %H:%M (%Z)')
    footer = 'posted in #{} by {} on {}'.format(
        quote.message.channel.name, quote.author.nick, ctime_str)
    embed.set_footer(text=footer)

    await channel.send(embed=embed)

async def rquote_help(channel):
    embed = discord.Embed(
        title='How to Quote!',
        color=discord.Color.red()
    )
    embed.set_author(name=CLIENT.user, icon_url=CLIENT.user.avatar_url)

    embed.add_field(name='Adding a quote', inline=True,
        value='React to a message with the `:speech_balloon:` emoji (💬)')
    embed.add_field(name='Removing a quote', inline=True,
        value='React to a message with the `:x:` emoji (❌)')
    embed.add_field(name='Picking a quote', inline=False,
        value='`$rquote` without mentions for a random quote')
    embed.add_field(name='Picking a quote from a user', inline=False,
        value='`$rquote @user` to pick a random quote from `user`')
    embed.set_footer(text='Run `$rquote help` to display this message again')

    await channel.send(embed=embed)

async def rquote(message):
    log('$rquote request from {}'.format(message.author.name))

    if 'help' in message.content.split():
        await rquote_help(message.channel)
        return

    tagged_member = None
    mentions = message.mentions
    if len(mentions) > 1:
        log('  ERROR: more than one user is tagged')
        await message.delete()
        await message.channel.send(
            'You cannot tag more than one user for `$rquote`!')
        return
    elif len(mentions) == 1:
        tagged_member = mentions[0]

    #TODO filter by channel ID?
    #where = 'channel_id = {}'.format(message.channel.id)
    if tagged_member != None:
        where = 'author_id = {}'.format(tagged_member.id)
        #where = ' AND author_id = {}'.format(tagged_member.id)
    else:
        where = None

    results = db.select(CONN, QUOTES_TABLE, '*', where)
    if len(results) == 0:
        log('  No quotes found.')
        await message.channel.send(
            'No quotes found! Use `$rquote help` for usage information.')
        return
    result = random.choice(results)

    quote = Quote()
    await quote.fill_from_entry(result)
    log('  Author       :{}'.format(quote.author.name))
    log('  Channel      :{}'.format(quote.message.channel.name))
    log('  Message      :{}'.format(quote.message.content))

    await repeat_quote(message.channel, quote)


################################################################################
# Discord event functions
################################################################################

@CLIENT.event
async def on_ready():
    log('BEEP BEEP. Logged in as <{0.user}>'.format(CLIENT))
    await set_rand_status()

@CLIENT.event
async def on_message(message):
    if message.author == CLIENT.user:
        return
    if message.content.startswith('$hello'):
        await message.channel.send('Orayo~!')
    if startswith_word(message.content, '$rquote'):
        await rquote(message)
    await roll_rand_status()

@CLIENT.event
async def on_raw_reaction_add(payload):
    # Need to cast to string, since Discord emoji not really an emoji
    emoji = str(payload.emoji)
    # Exit early if not reacting with what we want
    if emoji not in KEY_REACTS:
        return

    # Need these for future ops
    guild = CLIENT.get_guild(payload.guild_id)
    channel = CLIENT.get_channel(payload.channel_id)

    # Get message, quoter, and quote author
    message = await channel.fetch_message(payload.message_id)
    member_saver = payload.member
    user_author = message.author
    member_author = await guild.fetch_member(user_author.id)
    # Should know if the message is from a bot or not
    is_bot = message.author.bot

    # Construct new quote object
    quote = Quote(member_author, member_saver, message)

    # Ugh, why doesn't Python have switch statements...?
    if (emoji == EMOJI_QUOTE):
        await quote.save_to_db()
    elif (emoji == EMOJI_DELQUOTE):
        await quote.remove_from_db()


################################################################################
# Run the bot
################################################################################

CLIENT.run(TOKEN)

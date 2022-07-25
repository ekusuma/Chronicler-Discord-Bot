#!/usr/bin/python3

"""
the Chronicler -- Discord bot
=============================

A fun Discord bot meant for saving and repeating quotes--usually without
context.

The quoting function is first and foremost, with any additions of functionality
later on being a bonus.
"""

__title__ = 'the Chronicler bot'
__author__ = 'edgykuma'
__license__ = 'MIT'

import datetime
import pytz
import random
import asyncio
from time import sleep

import discord

import dbhelper as db


################################################################################
# Useful globals
################################################################################

# Set to True for debug mode
#   Will sign in to SQL as "chronicler_DBG", and use DB "chrondb_DBG" with table "quotes_DBG"
#   It is highly recommended to have a separate bot for this mode
BOT_DEBUGMODE   = False

# Emojis to watch reactions for (aliased to variable names since typing emoji
# can be annoying)
EMOJI_QUOTE     = '💬'      # For quoting a message
EMOJI_DELQUOTE  = '❌'      # For deleting a message
EMOJI_LEFT      = '◀'       # Navigate to prev in menu
EMOJI_RIGHT     = '▶'       # Navigate to next in menu
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

# Percent chance that the bot rerolls its status
STATUS_RR_CHANCE = 1

# Setting for allowing/disallowing cross-channel quotes...to be decided later
ALLOW_XCHAN = True

# Maximum size of the "repeat buffer"
REPEAT_BUF_SIZE = 25

# Number of quotes to display per page for `$quotes` command
MAX_QUOTES_PER_PAGE = 5
# Number of characters for a quoted message preview
MESSAGE_PREVIEW_LEN = 80
# Time in seconds for quotes list react timeout
QUOTES_REACT_TIMEOUT = 60


################################################################################
# Globals used by bot, DO NOT EDIT!
################################################################################

# Name of the quotes table
QUOTES_TABLE = 'quotes_DBG' if BOT_DEBUGMODE else 'quotes'

# Strings of all the supported commands
BOT_COMMAND_NAMES = [
    '`$help`',
    '`$quotes`',
    '`$quote`',
    '`$rquote`',
    '`$remindme`'
]

# (Revolving) list of messages to not repeat
REPEAT_BUF = []

# Bot's private token, to be read from the .token file (DO NOT PUT IN REPO)
TOKEN = ''

# Global instance of the bot's Discord client
CLIENT = None

# Connection to the bot's MySQL DB
CONN = None



################################################################################
# Initialization
################################################################################

# Attempt to open and read the bot's .token file
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
if BOT_DEBUGMODE:
    CONN = db.create_srv_conn('localhost', 'chronicler_DBG', TOKEN, 'chrondb_DBG')
else:
    CONN = db.create_srv_conn('localhost', 'chronicler', TOKEN, 'chrondb')
if CONN == None:
    print('ERROR: Unable to connect to DB.')
    exit(1)

# Try to create the 'quotes' table--ignore the error if it exists
# TODO: a more elegant way to check if table exists in SQL?
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
    """Helpful log printing, with timestamp (in PST)

    Parameters
    ==========
    msg : str
        Message to print with timestamp.
    """
    ct = datetime.datetime.now()
    ct_pst = ct.astimezone(pytz.timezone('US/Pacific'))
    cts = ct_pst.strftime("%Y/%m/%d %H:%M:%S")
    print("[{}] {}".format(cts, msg))

def startswith_word(phrase, startswith):
    """Check if a string starts with a word

    Basic startswith method doesn't separate into words, so checking if a string
    starts with '$foo' will return true for both '$foo' and '$fooooooo'.

    Parameters
    ==========
    phrase : str
        Phrase to check startswith against.
    startswith : str
        Word to check whether or not phrase starts with it.

    Returns
    =======
    bool
        True if the first word of phrase is startswith, False otherwise.
    """
    return len(phrase.split()) > 0 and phrase.split()[0] == startswith

async def set_rand_status():
    """Set the bot's status to one of the strings in BOT_STATUSES"""
    activity = discord.Activity(type=discord.ActivityType.watching,
            name=random.choice(BOT_STATUSES))
    await CLIENT.change_presence(activity=activity)

async def roll_rand_status():
    """Roll for a chance to set the bot's status to a random one

    Will be used to periodically change statuses.

    TODO: Might adversely affect performance, investigate at some point.
    """
    num = random.randint(1, 100)
    if (num <= STATUS_RR_CHANCE):
        await set_rand_status()

def reset_sql_conn():
    log('Resetting DB connection...')
    global CONN
    db.close_srv_conn(CONN)
    CONN = db.create_srv_conn('localhost', 'chronicler', TOKEN, 'chrondb')

def add_to_repeat_buf(msg_id):
    """Add a message ID to the repeat buffer, kicking out oldest ID if full

    The point of the repeat buffer is to prevent the bot from picking the same
    set of quotes. If a quote (identified by message ID) is in the buffer, then
    the bot will find another quote (if it exists).

    Parameters
    ==========
    msg_id : int
        The ID of the message to add
    """
    # Pop off front of buffer if full
    if len(REPEAT_BUF) >= REPEAT_BUF_SIZE:
        removed = REPEAT_BUF.pop(0)
        log('  Removed {} from repeat buffer'.format(removed))
    REPEAT_BUF.append(msg_id)
    log('  Added {} to repeat buffer'.format(msg_id))

def convert_index(index, total):
    """Flip an index to its reverse (i.e., make index 0 become the last index, and vice versa).

    Parameters
    ==========
    index : int
        The index to convert.
    total : int
        The total number of indices in whatever iterable.
    """
    return total - index - 1


################################################################################
# Helper classes
################################################################################

class Quote:
    """Class that tracks everything we need for a quote.

    Attributes
    ==========
    author : discord.Member
        The Member that wrote the quote.
    quoter : discord.Member
        The Member that saved the quote.
    message : discord.Message
        The Message to quote.

    Note: Could have performance issues since we pass around the entire Member
    and Message objects, rather than the ID. However since this avoids future
    API calls to match ID->object, this is probably fine.

    Methods
    =======
    save_to_db()
        Save a quote to the database.
    remove_from_db()
        Remove a quote from the database.
    fill_from_entry(entry)
        Takes an entry that was taken from the database, and makes the necessary
        API calls to populate a Quote's attributes.
    """
    def __init__(self, author=None, quoter=None, message=None):
        """
        Parameters
        ==========
        author : discord.Member
            The Member that wrote the quote.
        quoter : discord.Member
            The Member that saved the quote.
        message : discord.Message
            The Message to quote.

        Note: We allow None for the attributes so a blank Quote can be made
        with the intent to fill it out later.
        """
        self.author = author
        self.quoter = quoter
        self.message= message

    async def save_to_db(self):
        """Save a quote to the database"""
        if (self.author == None or self.quoter == None or self.message == None):
            log('ERROR: Tried to call save_to_db() on a blank Quote')
            return

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
            log('  Channel      :#{}'.format(self.message.channel.name))
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
        try:
            db.insert_partial(CONN, QUOTES_TABLE, cols, vals)
        except:
            reset_sql_conn()
            db.insert_partial(CONN, QUOTES_TABLE, cols, vals)

        # Acknowledge save with check mark emoji
        await self.message.clear_reaction(EMOJI_QUOTE)
        await self.message.add_reaction(EMOJI_BOT_CONFIRM)

    async def remove_from_db(self):
        """Remove a quote from the database"""
        if (self.author == None or self.quoter == None or self.message == None):
            log('ERROR: Tried to call remove_from_db() on a blank Quote')
            return

        log('Member {} is trying to delete a quote:'.format(self.quoter.name))
        log('  Author       :{}'.format(self.author.name))
        log('  Channel      :#{}'.format(self.message.channel.name))
        log('  Message      :{}'.format(self.message.content))

        try:
            retval = db.delete(CONN, QUOTES_TABLE, 'message_id={}'.format(self.message.id))
        except:
            reset_sql_conn()
            retval = db.delete(CONN, QUOTES_TABLE, 'message_id={}'.format(self.message.id))
        if retval != 0:
            log('  Error: Unable to delete message')
        else:
            # Acknowledge deletee with removing check mark emoji
            await self.message.clear_reaction(EMOJI_DELQUOTE)
            await self.message.clear_reaction(EMOJI_BOT_CONFIRM)

    async def fill_from_entry(self, entry):
        """Populate Quote attributes from a database entry

        Parameters
        ==========
        entry : (int, int, int, int, int)
            A tuple describing a quote's
            (author_id, quoter_id, msg_id, guild_id, channel_id)
            This is an entry that would be taken directly from the database.
        """
        # Assumes that entry is tuple of:
        #   (author_id, quoter_id, message_id, guild_id, channel_id)
        if len(entry) < 5:
            log('ERROR: Tried to populate quote object with invalid entry')
            return
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
    """Send a selected quote to a specific channel.

    Quotes are formatted with Discord's embed.

    Parameters
    ==========
    channel : discord.Channel
        The channel that the bot should send the quote to.
    quote : Quote
        The quote that the bot should send.
    """
    # Add a quote formatter (>) to start of each line
    fmt_content = quote.message.content.replace('\n', '\n > ')
    embed = discord.Embed(
        title='Quotes from the Chronicler!',
        color=discord.Color.red(),
        # Markdown-esque formatting, for a quote
        # User can click on quote to jump to it
        description='> {}'.format(fmt_content)
    )
    # Author of the embed is the bot
    embed.set_author(name=CLIENT.user, icon_url=CLIENT.user.avatar_url)
    # But thumbnail should be avatar of the quote's author
    embed.set_thumbnail(url=quote.author.avatar_url)
    # Clickable link to jump to message
    embed.add_field(name='View context...?', inline=False,
        value='[{}]({})'.format('Click here to jump', quote.message.jump_url))

    # Construct footer
    ctime = quote.message.created_at
    ctime_pst = ctime.astimezone(pytz.timezone('US/Pacific'))
    ctime_str = ctime_pst.strftime('%b %-d, %Y at %H:%M (%Z)')
    footer = 'posted in #{} by {} on {}'.format(
        quote.message.channel.name, quote.author.nick, ctime_str)
    embed.set_footer(text=footer)

    await channel.send(embed=embed)

async def rquote_help(channel):
    """Send a help message for usage of the $rquote command

    Parameters
    ==========
    channel : discord.Channel
        Channel to send the help message to.
    """
    embed = discord.Embed(
        title='How to Quote!',
        color=discord.Color.red()
    )
    embed.set_author(name=CLIENT.user, icon_url=CLIENT.user.avatar_url)

    embed.add_field(name='Adding a quote', inline=True,
        value='React to a message with the `:speech_balloon:` emoji (💬)')
    embed.add_field(name='Removing a quote', inline=True,
        value='React to a message with the `:x:` emoji (❌)')
    embed.add_field(name='Picking a random quote', inline=False,
        value='`$rquote` without mentions for a random quote')
    embed.add_field(name='Picking a random quote from a user', inline=False,
        value='`$rquote @user` to pick a random quote from `user`')
    embed.add_field(name='Picking a specific quote', inline=False,
        value='`$quote <number>` without mentions for a specific quote')
    embed.add_field(name='Picking a specific quote from a user', inline=False,
        value='`$quote @user <number>` to pick a specific quote from `user`')
    embed.add_field(name='Listing all quotes', inline=False,
        value='`$quotes` to list all quotes saved by the bot')
    embed.add_field(name='Listing all quotes from a user', inline=False,
        value='`$quotes @user` to list all quotes saved by the bot, made by `user`')
    embed.set_footer(text='Run `$quote help` to display this message again')

    await channel.send(embed=embed)

async def rquote(message):
    """Handle a user's request to use the $rquote command

    Parameters
    ==========
    message : discord.Message
        User message that triggered the command.
    """
    log('$rquote request from {}'.format(message.author.name))

    # Asking for help will override any tokens
    if 'help' in message.content.split():
        await rquote_help(message.channel)
        return

    # Look to see who was tagged, if any
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

    # Filter by channel ID, if cross-channel setting is disabled
    if ALLOW_XCHAN:
        if tagged_member != None:
            where = 'author_id = {}'.format(tagged_member.id)
        else:
            where = None
    else:
        where = 'channel_id = {}'.format(message.channel.id)
        if tagged_member != None:
            where += ' AND author_id = {}'.format(tagged_member.id)

    # Grab all results that match our criteria
    try:
        results = db.select(CONN, QUOTES_TABLE, '*', where)
    except:
        reset_sql_conn()
        results = db.select(CONN, QUOTES_TABLE, '*', where)
    if len(results) == 0:
        log('  No quotes found.')
        await message.channel.send(
            'No quotes found! Use `$quote help` for usage information.')
        return
    # Pick a random quote from the bunch
    result = random.choice(results)
    # Reroll if the result is in the repeat buffer
    #   Message ID is Index 2 of the results tuple
    #   If there is only one result remaining, then pick that anyway
    while (len(results) > 1 and result[2] in REPEAT_BUF):
        results.remove(result)
        result = random.choice(results)
    # If the final chosen one isn't in repeat buffer, then add it
    if result[2] not in REPEAT_BUF:
        add_to_repeat_buf(result[2])

    quote = Quote()
    await quote.fill_from_entry(result)
    log('  Author       :{}'.format(quote.author.name))
    log('  Channel      :#{}'.format(quote.message.channel.name))
    log('  Message      :{}'.format(quote.message.content))

    await repeat_quote(message.channel, quote)

async def list_quotes(invoke_message, quote_list, quote_index=-1):
    """List out the quotes provided in a list to the user, with interactible menu

    Parameters
    ==========
    invoke_message : discord.Message
        The invoking message.
    quote_list : sql.results[]
        List of SQL query results.
    quote_index : int
        Specify one quote to repeat. If this is negative, then this function will only list the quotes.
    """
    # Store length of list once so we don't have to do O(n) operation every time
    listlen = len(quote_list)
    if listlen < 1:
        return
    # Number of pages for given list length
    max_pages = listlen // MAX_QUOTES_PER_PAGE

    # quote_index is indexed starting at 1, so need to -1 later
    if quote_index > 0 and quote_index <= listlen:
        chosen_quote = Quote()
        chosen_index = convert_index(quote_index-1, listlen)
        await chosen_quote.fill_from_entry(quote_list[chosen_index])
        await repeat_quote(invoke_message.channel, chosen_quote)
        return
    elif quote_index == 0 or quote_index > listlen:
        await invoke_message.channel.send('Invalid quote number, {}! Run `$quotes` to see what numbers are valid.'.format(invoke_message.author.mention))
        await invoke_message.delete()
        return
    # Otherwise no index was specified, so continue execution

    embed = discord.Embed(
        title='Quotes from the Chronicler!',
        color=discord.Color.red(),
        description='View the whole quote with `$quote` command using the number of the quote (i.e. `$quote 3` for quote #3)\n\nIf a user is mentioned, don\'t forget to include that mention as well in `$quote` command.'
        #description='Type the number of message you want to view:'
    )
    embed.set_footer(text='Use the left/right emoji reactions to page through the list.\nPaging may be slow due to Discord API calls, so please be patient.')

    # We iterate backwards, as we want to display the most recent quotes first
    pageno      = 0
    quote       = Quote()
    log('    Formatting quote list embed...')
    # We only have to send the embed once, so use this bool to note that
    embed_sent = False
    sent_message = None

    # This function is to check if any user responds with left/right arrow emoji
    def check_reaction(reaction, user):
        return (not user.bot) and (reaction.emoji == EMOJI_LEFT or reaction.emoji == EMOJI_RIGHT) and reaction.message == sent_message

    while True:
        start_idx   = min(pageno * MAX_QUOTES_PER_PAGE, listlen-1)
        end_idx     = min((pageno+1) * MAX_QUOTES_PER_PAGE, listlen)
        for i in range(start_idx, end_idx):
            # fill_from_entry() calls API to retrieve message info, so should only call when we need the info
            await quote.fill_from_entry(quote_list[i])
            # Only take the first MESSAGE_PREVIEW_LEN characters
            if len(quote.message.content) > MESSAGE_PREVIEW_LEN:
                message = '> {}...'.format(discord.utils.escape_markdown(quote.message.content[0:MESSAGE_PREVIEW_LEN]))
            else:
                message = '> {}'.format(discord.utils.escape_markdown(quote.message.content))
            # Replace newlines with spaces to clean output
            message = message.replace('\n', ' ')
            embed.add_field(inline=False, name='{}'.format(convert_index(i, listlen)+1), value='{}\n*by **{}***'.format(message, quote.author.name))
        if not embed_sent:
            sent_message = await invoke_message.channel.send(embed=embed)
            embed_sent = True
        else:
            await sent_message.edit(embed=embed)
        await sent_message.add_reaction(EMOJI_LEFT)
        await sent_message.add_reaction(EMOJI_RIGHT)
        log('    Sent quotes list to #{}.'.format(invoke_message.channel.name))

        try:
            reaction, user = await CLIENT.wait_for('reaction_add', check=check_reaction, timeout=QUOTES_REACT_TIMEOUT)
            if reaction.emoji == EMOJI_LEFT:
                if pageno == 0:             # Wrap around to last page (lowest message IDs)
                    pageno = max_pages
                else:
                    pageno -= 1
            elif reaction.emoji == EMOJI_RIGHT:
                if pageno == max_pages:   # Wrap around to first page (highest message IDs)
                    pageno = 0
                else:
                    pageno += 1
            # Reset the embed
            await sent_message.clear_reactions()
            embed.clear_fields()
            continue
        except asyncio.TimeoutError:
            #log('    User timed out.')
            #message = 'Too slow to respond, {}!'.format(invoke_message.author.mention)
            #await invoke_message.channel.send(message)
            break

async def quotes(message, pick_quote=False):
    """List all quotes saved by the bot

    Parameters
    ==========
    message : discord.Message
        User message that triggered the command.
    pick_quote : bool
        True if the user is trying to pick a specific quote to repeat.
    """
    if pick_quote:
        log('$quote request from {}'.format(message.author.name))
    else:
        log('$quotes request from {}'.format(message.author.name))

    # Asking for help will override any tokens
    if 'help' in message.content.split():
        await rquote_help(message.channel)
        return

    # If picking a quote, parse out the numerical token (choosing the first number we find)
    quotenum = -1
    if pick_quote:
        for word in message.content.split():
            if word.isnumeric():
                quotenum = int(word)
                log('    Choosing Quote #{}'.format(quotenum))
                break
        if quotenum < 0:    # User didn't specify an argument
            log('    ERROR: Did not specify number for $quote command')
            await message.channel.send('You must specify a valid, positive number for `$quote`, {}!'.format(message.author.mention))
            await message.delete()
            return

    # Look to see who was tagged, if any
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

    # Filter by channel ID, if cross-channel setting is disabled
    if ALLOW_XCHAN:
        if tagged_member != None:
            where = 'author_id = {}'.format(tagged_member.id)
        else:
            where = None
    else:
        where = 'channel_id = {}'.format(message.channel.id)
        if tagged_member != None:
            where += ' AND author_id = {}'.format(tagged_member.id)

    # Grab all results that match our criteria
    orderby = 'message_id'
    log('    Pulling list of quotes...')
    try:
        # Rely on discord message ID being sequential, and order with highest ID first
        results = db.select(CONN, QUOTES_TABLE, '*', where, orderby, orderasc=False)
    except:
        reset_sql_conn()
        results = db.select(CONN, QUOTES_TABLE, '*', where, orderby, orderasc=False)
    if len(results) == 0:
        log('  No quotes found.')
        await message.channel.send('No quotes found! Use `$quote help` for usage information.')
        return

    await list_quotes(message, results, quote_index=quotenum)

async def remindme_help(channel):
    """Send a help message for usage of the $remindme command

    Parameters
    ==========
    channel : discord.Channel
        Channel to send the help message to.
    """
    embed = discord.Embed(
        title='How to use Reminders!',
        color=discord.Color.red()
    )
    embed.set_author(name=CLIENT.user, icon_url=CLIENT.user.avatar_url)

    embed.add_field(name='Usage', inline=False,
        value='`$remindme <time> <memo>`')
    embed.add_field(name='What it does', inline = False,
        value='Get a reminder in the channel some time later')
    embed.add_field(name='Memo', inline=False,
        value='**[Optional]** Memo is the message that will be repeated to you')
    embed.add_field(name='Valid time units', inline=False,
        value='`weeks`, `days`, `hours`, `minutes`')
    embed.add_field(name='Example', inline=False,
        value='`$remindme 1 minute A reminder 1 minute from now!`')
    embed.add_field(name='Notes', inline=False,
        value='Note that if the bot dies, all pending reminders are lost!')
    embed.set_footer(text='Run `$remindme help` to display this message again')

    await channel.send(embed=embed)

async def remindme_errmsg(message):
    """Send an error message to the channel.

    Parameters
    ==========
    message : discord.Message
        The calling message.
    """
    log('  ERROR: invalid args for {}'.format(message.content))
    await message.channel.send(
        'Invalid arguments for `$remindme`! Use `$remindme help` for help.')

async def remindme(message):
    """Set and send a reminder for a user.

    Parameters
    ==========
    message : discord.Message
        The calling message, starting with `$remindme`
    """
    log('$remindme request from {}'.format(message.author.name))

    # Asking for help will override any tokens
    if 'help' in message.content.split():
        await remindme_help(message.channel)
        return

    token_arr = message.content.split()
    # Error out if there are no arguments
    if len(token_arr) <= 1:
        await remindme_errmsg(message)
        return

    # Parse the time
    weeks = 0
    days = 0
    hours = 0
    minutes = 0
    memo = ''
    was_number = False
    set_time = False
    # 0th index of this array should be '$remindme'
    for i in range(1, len(token_arr)):
        # Skip token if it's a number
        if token_arr[i].isnumeric():
            if was_number:
                await remindme_errmsg(message)
                return
            was_number = True
            continue
        if token_arr[i] == 'week' or token_arr[i] == 'weeks':
            # If there was no number before, then it's invalid
            if not was_number:
                await remindme_errmsg(message)
                return
            weeks = int(token_arr[i-1])
            was_number = False
            set_time = True
        elif token_arr[i] == 'day' or token_arr[i] == 'days':
            if not was_number:
                await remindme_errmsg(message)
                return
            days = int(token_arr[i-1])
            was_number = False
            set_time = True
        elif token_arr[i] == 'hour' or token_arr[i] == 'hours' or token_arr[i] == 'hr' or token_arr[i] == 'hrs':
            if not was_number:
                await remindme_errmsg(message)
                return
            hours = int(token_arr[i-1])
            was_number = False
            set_time = True
        elif token_arr[i] == 'minute' or token_arr[i] == 'minutes' or token_arr[i] == 'min' or token_arr[i] == 'mins':
            if not was_number:
                await remindme_errmsg(message)
                return
            minutes = int(token_arr[i-1])
            was_number = False
            set_time = True
        # Otherwise, the rest of the message is the memo
        # Note that if there are more time units after the start of the memo,
        # they are subsequently ignored.
        else:
            # Error if no time was set
            if not set_time:
                await remindme_errmsg(message)
                return
            memo = ' '.join(token_arr[i:len(token_arr)])
            break
    # If the memo is empty, then make it '`<none>`'
    if len(memo) == 0:
        memo = '`<none>`'
    # Log the operation
    log('  wk|d|h|m: {}|{}|{}|{}'.format(weeks, days, hours, minutes))
    log('  Memo: {}'.format(memo))

    # Construct the confirmation message
    conf = 'Okay! I\'ll remind you in this channel in**'
    if weeks > 0:
        if weeks > 1:
            conf += ' {} weeks'.format(weeks)
        else:
            conf += ' {} week'.format(weeks)
    if days > 0:
        if days > 1:
            conf += ' {} days'.format(days)
        else:
            conf += ' {} day'.format(days)
    if hours > 0:
        if hours > 1:
            conf += ' {} hours'.format(hours)
        else:
            conf += ' {} hour'.format(hours)
    if minutes > 0:
        if minutes > 1:
            conf += ' {} minutes'.format(minutes)
        else:
            conf += ' {} minute'.format(minutes)
    conf += '**.'
    await message.channel.send(conf)

    curr_time = datetime.datetime.now()
    target_time = curr_time + datetime.timedelta(weeks=weeks, days=days, hours=hours, minutes=minutes)
    # NOTE: If the bot is killed, all pending reminders are lost...at this point
    # I have no obvious solution so consider it a beta
    log('  Awaiting time...')
    await discord.utils.sleep_until(target_time)

    # Send the reminder as an embed
    embed = discord.Embed(title='Your reminder!', color=discord.Color.red())
    embed.set_author(name=CLIENT.user, icon_url=CLIENT.user.avatar_url)
    embed.add_field(name='Requestor', inline=False, value=message.author.mention)
    embed.add_field(name='Reminder', inline=False, value=memo)
    embed.add_field(name='Jump to message', inline=False,
        value='[{}]({})'.format('Click here', message.jump_url))
    await message.channel.send(content=message.author.mention, embed=embed)
    log('  Reminder sent!')

async def helpcmd(channel):
    """List all of the available commands.

    Parameters
    ==========
    channel : discord.Channel
        The channel to send the help message to.
    """
    cmdlist = ', '.join(BOT_COMMAND_NAMES)
    embed = discord.Embed(title='Available commands', color=discord.Color.red(),
        description=cmdlist)
    embed.add_field(name='Further usage', inline=False,
        value='Add `help` after the command')
    await channel.send(embed=embed)


################################################################################
# Discord event functions
################################################################################

@CLIENT.event
async def on_ready():
    """Bot routines to run once it's up and ready"""
    log('BEEP BEEP. Logged in as <{0.user}>'.format(CLIENT))
    await set_rand_status()

@CLIENT.event
async def on_message(message):
    """Bot routines to run whenever a new message is sent

    Basically just check for target keywords.

    Parameters
    ==========
    message : discord.Message
        The message that was just sent.
    """
    # Ignore the message if it's from a bot
    if message.author.bot:
        return
    if startswith_word(message.content, '$help'):
        await helpcmd(message.channel)
    if startswith_word(message.content, '$hello'):
        await message.channel.send('ぉぁ~ょ')
    if startswith_word(message.content, '$rquote'):
        await rquote(message)
    if startswith_word(message.content, '$quotes'):
        await quotes(message)
    if startswith_word(message.content, '$quote'):
        await quotes(message, pick_quote=True)
    if startswith_word(message.content, '$remindme'):
        await remindme(message)

    # Chance to change the bot status on new message
    await roll_rand_status()

@CLIENT.event
async def on_raw_reaction_add(payload):
    """Bot routine to run whenever a reaction is added to any message

    We use the raw event handler since we can't rely on the bot's cache (as this
    has to work for ANY message, not just the cached ones).

    Parameters
    ==========
    payload : discord.RawReactionActionEvent
        The payload of the reaction event.
    """
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

# Wow, so elegant!
CLIENT.run(TOKEN)

#!/usr/bin/python3

import discord
import datetime
import pytz

import dbhelper as db


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

# Useful globals
# Create new instance of Discord client
client = discord.Client()
# Create connection to Chronicler's MySQL DB
conn = db.create_srv_conn('localhost', 'chronicler', TOKEN, 'chrondb')
if conn == None:
    print('ERROR: Unable to connect to DB.')
    exit(1)
table_name = 'quotes'

# Try to create the 'quotes' table--ignore the error if it exists
table_cols = """
    author_id BIGINT NOT NULL,
    quoter_id BIGINT,
    message_id BIGINT PRIMARY KEY
"""
db.create_table(conn, table_name, table_cols)


################################################################################
# Misc helper functions
################################################################################

def log(msg):
    ct = datetime.datetime.now()
    ct_pst = ct.astimezone(pytz.timezone('US/Pacific'))
    cts = ct_pst.strftime("%Y/%m/%d %H:%M:%S")
    print("[{}] {}".format(cts, msg))


################################################################################
# Helper classes
################################################################################

#TODO: what do do if a member leaves?
class Quote:
    def __init__(self, author=None, quoter=None, msg_id=0):
        self.author = author
        self.quoter = quoter
        self.msg_id = msg_id

    async def save_to_db(self, message):
        author_id = self.author.id
        quoter_id = self.quoter.id
        is_bot = self.author.bot

        # Debug logging
        log('Member {} is trying to save a quote:'.format(self.quoter.nick))
        if is_bot:
            log('  Request denied: tried to save a bot quote')
        else:
            log('  Author       :{}'.format(self.author.nick))
            log('  Channel      :[]'.format(message.channel.name))
            log('  Message      :{}'.format(message.content))

        # Don't accept if the quote author is a bot
        if (is_bot):
            await message.clear_reaction('💬')
            await message.channel.send(
                'Sorry {}, I don\'t save quotes from non-humans!'.format(member_saver.nick))
            return

        cols = 'author_id, quoter_id, message_id'
        vals = '{}, {}, {}'.format(author_id, quoter_id, self.msg_id)
        db.insert_partial(conn, table_name, cols, vals)

        # Acknowledge save with check mark emoji
        await message.clear_reaction('💬')
        await message.add_reaction('✅')

    async def remove_from_db(self, message):
        log('Member {} is trying to delete a quote:'.format(self.quoter.nick))
        log('  Author       :{}'.format(self.author.nick))
        log('  Channel      :[]'.format(message.channel.name))
        log('  Message      :{}'.format(message.content))

        retval = db.delete(conn, table_name, 'message_id={}'.format(self.msg_id))
        if retval != 0:
            log('  Error: Unable to delete message')
        else:
            # Acknowledge deletee with removing check mark emoji
            await message.clear_reaction('❌')
            await message.clear_reaction('✅')

    #def fill_from_entry(self, entry):


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
    # Exit early if not reacting with what we want
    emoji = str(payload.emoji)
    if emoji != '💬' and emoji != '❌':
        return

    # Need these for future ops
    guild = client.get_guild(payload.guild_id)
    channel = client.get_channel(payload.channel_id)

    # Get message, quoter, and quote author
    message = await channel.fetch_message(payload.message_id)
    member_saver = payload.member
    user_author = message.author
    member_author = await guild.fetch_member(user_author.id)
    # Should know if the message is from a bot or not
    is_bot = message.author.bot

    # Construct new quote object
    quote = Quote(member_author, member_saver, payload.message_id)

    if (emoji == '💬'):
        await quote.save_to_db(message)
    elif (emoji == '❌'):
        await quote.remove_from_db(message)


################################################################################
# Run the bot
################################################################################

client.run(TOKEN)

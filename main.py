#!/usr/bin/python3

import discord

# Read token file
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

@client.event
async def on_ready():
    print('BEEP BEEP. Logged in as <{0.user}>'.format(client))

@client.event
async def on_message(message):
    if message.author == client.user:
        return
    if message.content.startswith('$hello'):
        await message.channel.send('Orayo~!')

client.run(TOKEN)

# the Chronicler: A Discord Bot
A bot for saving and regurgitating quotes in a Discord server. Usually out of context.

# Requirements
* Python3, version 3.6.9 or higher
* `discord.py` library, located [here](https://discordpy.readthedocs.io/en/latest/index.html)
* MySQL, Ver 14.14 Distrib 5.7.32, for Linux (x86_64) (see MySQL requirements section)

### MySQL requirements
This assumes that your SQL server is running on the same machine. If this is not true, you
will have to edit `main.py` to not use `localhost` as the server hostname.

The requirements here are quite strict, mostly because this is a personal project. Future 
work will probably make this more configurable.

1. Create a database called `chrondb` (for Chronicler DB)
```sql
CREATE DATABASE chrondb;
```
2. Create a user called `chronicler`, that has all permissions for the 'chrondb' database,
and is identified **with the password being your bot's token**
```sql
CREATE USER 'chronicler'@'localhost' IDENTIFIED BY '<BOT TOKEN>';
```

The bot will automatically create the table(s) necessary, so no more configuration is
necessary.

# Installation
1. Clone the repo
```bash
git clone https://github.com/edgykuma/Chronicler-Discord-Bot.git
```
2. In the same directory as `main.py`, create a file named `.token`. This file should contain
only one line, with the token of your bot. If you don't know how to get this, 
[follow the guidance here](https://www.writebots.com/discord-bot-token/).
3. Make sure your bot is also invited to your server(s)
4. Run the bot
```bash
python3 main.py
```

# Usage
The bot will print a usage message if you send `$rquote help` in the Discord.

### Saving quotes
Simply react with the `:speech_balloon:` (💬) emote to a message. To know if this worked,
the bot should add a ✅ emote and remove your reaction.

### Deleting quotes
React with the `:x:` (❌) emote to a message. In response the bot should remove your reaction
and remove the previous ✅ emote as well.

### Getting a random quote
Getting a random quote is done by sending an `$rquote` message. This will repeat a random quote.
Note that **the quote repeated can come from any channel, and be sent to any channel**. So be
careful with what you quote ;-)

You can also tag a user with @ right after the command, i.e. `$rquote @user` and the bot will
pick a random quote by that user.

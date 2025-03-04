import os
import discord
from discord.ext import commands
from discord import app_commands

from myserver import server_on

bot = commands.Bot(command_prefix='A!', intents=discord.Intents.all())



# //////////////////// Bot Event /////////////////////////
# คำสั่ง bot พร้อมใช้งานแล้ว
@bot.event
async def on_ready():
    print("Bot Online!")
    print("555")
    synced = await bot.tree.sync()
    print(f"{len(synced)} command(s)")


# ///////////////////// Commands /////////////////////
# กำหนดคำสั่งให้บอท

@bot.command()
async def hello(ctx):
    await ctx.send(f"hello {ctx.author.name}!")


@bot.command()
async def test(ctx, arg):
    await ctx.send(arg)


# Slash Commands
@bot.tree.command(name='hellobot', description='Replies with Hello')
async def hellocommand(interaction):
    await interaction.response.send_message("Hello It's me ASTRALIS BOT")


@bot.tree.command(name='name')
@app_commands.describe(name = "What's your name?")
async def namecommand(interaction, name : str):
    await interaction.response.send_message(f"Hello {name}")


# Embeds

@bot.tree.command(name='help', description='Bot Commands')
async def helpcommand(interaction):
    emmbed = discord.Embed(title='Help Me! - Bot Commands',
                           description='Bot Commands',
                           color=0x66FFFF,
                           timestamp= discord.utils.utcnow())


    # ใส่ข้อมูล
    emmbed.add_field(name='/hello1', value='Hello Commmand', inline=True)
    emmbed.add_field(name='/hello2', value='Hello Commmand', inline=True)
    emmbed.add_field(name='/hello3', value='Hello Commmand', inline=False)

    emmbed.set_author(name='Author')

    # Footer เนื้อหาส่วนท้าย
    emmbed.set_footer(text='Footer')

    await interaction.response.send_message(embed = emmbed)


server_on()

bot.run(os.getenv('TOKEN'))
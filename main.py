import discord
from discord import app_commands
from discord.ext import commands
from PIL import Image, ImageDraw, ImageFont
import requests
from io import BytesIO
import json
import os

from pydrive2.auth import GoogleAuth
from pydrive2.drive import GoogleDrive

from myserver import server_on

# 🔹 ตั้งค่า Google Drive API
gauth = GoogleAuth()
gauth.LocalWebserverAuth()
drive = GoogleDrive(gauth)

DATA_FILE = "student_data.json"
DRIVE_FOLDER_ID = "1Zwv6cZux1z0I9vrSqRCNkc0N9NRjCftC"  # 📂 ใส่ ID ของโฟลเดอร์ใน Google Drive

class StudentCardBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="A!", intents=discord.Intents.all())
        self.load_data()

    async def on_ready(self):
        await self.tree.sync()
        print(f"บอท {self.user} ออนไลน์แล้ว!")

    def load_data(self):
        """โหลดข้อมูลจาก Google Drive"""
        file_list = drive.ListFile({'q': f"'{DRIVE_FOLDER_ID}' in parents and title = '{DATA_FILE}'"}).GetList()
        if file_list:
            file_id = file_list[0]['id']
            file = drive.CreateFile({'id': file_id})
            file.GetContentFile(DATA_FILE)
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                self.student_data = json.load(f)
        else:
            self.student_data = {}

    def save_data(self):
        """บันทึกข้อมูลไปยัง Google Drive"""
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(self.student_data, f, ensure_ascii=False, indent=4)

        file_list = drive.ListFile({'q': f"'{DRIVE_FOLDER_ID}' in parents and title = '{DATA_FILE}'"}).GetList()
        if file_list:
            file = drive.CreateFile({'id': file_list[0]['id']})
        else:
            file = drive.CreateFile({'title': DATA_FILE, 'parents': [{'id': DRIVE_FOLDER_ID}]})

        file.SetContentFile(DATA_FILE)
        file.Upload()

bot = StudentCardBot()

# ✅ Modal กรอกข้อมูล
class StudentCardModal(discord.ui.Modal, title="กรอกข้อมูลบัตรนักเรียน"):
    house = discord.ui.TextInput(label="บ้าน", required=True)
    class_name = discord.ui.TextInput(label="ชั้น", required=True)
    DOB = discord.ui.TextInput(label="วันเกิด", required=True)
    name = discord.ui.TextInput(label="ชื่อ", required=True)
    partner = discord.ui.TextInput(label="คู่หู", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        bot.student_data[str(interaction.user.id)] = {
            "house": self.house.value,
            "class_name": self.class_name.value,
            "DOB": self.DOB.value,
            "name": self.name.value,
            "partner": self.partner.value,
            "profile_image_url": None,
            "waiting_for_image": True
        }
        bot.save_data()

        await interaction.followup.send("โปรดแนบรูปภาพของคุณ", ephemeral=True)

@bot.tree.command(name="studentcard", description="สร้าง/แก้ไขบัตรนักเรียน")
async def studentcard(interaction: discord.Interaction):
    await interaction.response.send_modal(StudentCardModal())

@bot.tree.command(name="viewcard", description="ดูบัตรนักเรียนของคุณหรือของผู้อื่น")
@app_commands.describe(user="เลือกผู้ใช้ที่ต้องการดูบัตร (ไม่ระบุ = ดูของตัวเอง)")
async def viewcard(interaction: discord.Interaction, user: discord.Member = None):
    target_user = user or interaction.user
    user_id = str(target_user.id)

    if user_id not in bot.student_data or not bot.student_data[user_id].get("profile_image_url"):
        await interaction.response.send_message(f"{target_user.mention} ยังไม่มีบัตรนักเรียน", ephemeral=False)
        return

    data = bot.student_data[user_id]
    card_path = f"{user_id}_card.png"
    create_student_card(card_path, **data)

    await interaction.response.defer()

    file = discord.File(card_path)
    await interaction.followup.send(file=file)

# ✅ รับรูปภาพและอัปโหลดไป Google Drive
@bot.event
async def on_message(message):
    if message.author.bot:
        return

    user_id = str(message.author.id)
    if user_id not in bot.student_data or not bot.student_data[user_id].get("waiting_for_image", False):
        return

    if message.attachments:
        image_url = message.attachments[0].url

        # อัปโหลดรูปไปยัง Google Drive
        img_data = requests.get(image_url).content
        img_path = f"{user_id}_profile.png"
        with open(img_path, "wb") as img_file:
            img_file.write(img_data)

        file = drive.CreateFile({'title': img_path, 'parents': [{'id': DRIVE_FOLDER_ID}]})
        file.SetContentFile(img_path)
        file.Upload()
        file_url = f"https://drive.google.com/uc?id={file['id']}"

        bot.student_data[user_id]["profile_image_url"] = file_url
        bot.student_data[user_id]["waiting_for_image"] = False
        bot.save_data()

        await message.reply("รูปภาพถูกบันทึกแล้ว! ใช้ `/viewcard` เพื่อดูบัตรของคุณ")

def create_student_card(card_path, house, class_name, DOB, name, partner, profile_image_url):
    """สร้างบัตรนักเรียน"""
    if os.path.exists(card_path):
        os.remove(card_path)

    response = requests.get(profile_image_url)
    response.raise_for_status()
    img = Image.open(BytesIO(response.content))

    background = Image.open("student_card.png")
    width, height = 1934, 1015
    card = background.resize((width, height))
    draw = ImageDraw.Draw(card)
    font = ImageFont.truetype("K2D-Regular.ttf", size=45)

    draw.text((639, 280), house, font=font, fill="black")
    draw.text((857, 375), class_name, font=font, fill="black")
    draw.text((858, 480), DOB, font=font, fill="black")
    draw.text((876, 581), name, font=font, fill="black")
    draw.text((909, 680), partner, font=font, fill="black")

    img = img.resize((490, 540))
    card.paste(img, (158, 362), img.convert("RGBA").getchannel("A"))

    card.save(card_path)

server_on()

bot.run(os.getenv('TOKEN'))
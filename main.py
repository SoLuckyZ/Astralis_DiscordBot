import discord
import os
from discord import app_commands
from discord.ext import commands
from PIL import Image, ImageDraw, ImageFont
import requests
from io import BytesIO
import firebase_admin
from firebase_admin import credentials, firestore
from myserver import server_on

# ตั้งค่า Firestore
cred = credentials.Certificate('/etc/secrets/serviceAccountKey.json')
firebase_admin.initialize_app(cred)
db = firestore.client()

class StudentCardBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="A!", intents=discord.Intents.all())
        self.load_data()

    async def on_ready(self):
        await self.tree.sync()
        print(f"บอท {self.user} ออนไลน์แล้ว!")

    def load_data(self):
        """โหลดข้อมูลจาก Firestore"""
        user_ref = db.collection('student_cards')
        docs = user_ref.stream()
        
        self.student_data = {}
        for doc in docs:
            self.student_data[doc.id] = doc.to_dict()

    def save_data(self):
        """บันทึกข้อมูลลง Firestore"""
        user_ref = db.collection('student_cards')
        
        for user_id, data in self.student_data.items():
            user_ref.document(user_id).set(data) 

bot = StudentCardBot()

# ✅ Modal กรอกข้อมูล
class StudentCardModal(discord.ui.Modal, title="กรอกข้อมูลบัตรนักเรียน"):
    house = discord.ui.TextInput(label="บ้าน", placeholder="เช่น มังกรฟ้า , วิหกเพลิง", required=True)
    class_name = discord.ui.TextInput(label="ชั้น", placeholder="ใส่ชั้นเรียนของคุณ", required=True)
    DOB = discord.ui.TextInput(label="วันเกิด", placeholder="วว/ดด/ปปปป", required=True)
    name = discord.ui.TextInput(label="ชื่อ", placeholder="ใส่ชื่อของคุณ", required=True)
    partner = discord.ui.TextInput(label="คู่หู", placeholder="ใส่ชื่อคู่หูคุณ", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)
        
        # บันทึกข้อมูลผู้ใช้ลง Firestore
        db.collection('student_cards').document(user_id).set({
            "house": self.house.value,
            "class_name": self.class_name.value,
            "DOB": self.DOB.value,
            "name": self.name.value,
            "partner": self.partner.value,
            "profile_image_url": None,  # ยังไม่มีการกำหนดรูปภาพ
            "waiting_for_image": True  # กำลังรอรูปภาพ
        })
        
        # บันทึกข้อมูลในตัวแปรของบอท
        bot.student_data[user_id] = {
            "house": self.house.value,
            "class_name": self.class_name.value,
            "DOB": self.DOB.value,
            "name": self.name.value,
            "partner": self.partner.value,
            "profile_image_url": None,
            "waiting_for_image": True
        }

        await interaction.response.send_message("โปรดแนบรูปภาพที่ต้องการใช้บนบัตร (กรอบรูปมีขนาด 490 x 540)", ephemeral=False)

# ✅ Modal แก้ไขข้อมูล (แยกจาก StudentCardModal)
class EditInfoModal(discord.ui.Modal, title="แก้ไขข้อมูลบัตรนักเรียน"):
    house = discord.ui.TextInput(label="บ้าน", placeholder="เช่น มังกรฟ้า , วิหกเพลิง", required=True)
    class_name = discord.ui.TextInput(label="ชั้น", placeholder="ใส่ชั้นเรียนของคุณ", required=True)
    DOB = discord.ui.TextInput(label="วันเกิด", placeholder="วว/ดด/ปปปป", required=True)
    name = discord.ui.TextInput(label="ชื่อ", placeholder="ใส่ชื่อของคุณ", required=True)
    partner = discord.ui.TextInput(label="คู่หู", placeholder="ใส่ชื่อคู่หูคุณ", required=True)

    def __init__(self, user_id: str):
        super().__init__()
        self.user_id = user_id

    async def on_submit(self, interaction: discord.Interaction):
        # บันทึกข้อมูลใหม่ลง Firestore โดยไม่เปลี่ยนรูป
        if self.user_id in bot.student_data:
            db.collection('student_cards').document(self.user_id).update({
                "house": self.house.value,
                "class_name": self.class_name.value,
                "DOB": self.DOB.value,
                "name": self.name.value,
                "partner": self.partner.value,
            })
            
            bot.student_data[self.user_id].update({
                "house": self.house.value,
                "class_name": self.class_name.value,
                "DOB": self.DOB.value,
                "name": self.name.value,
                "partner": self.partner.value,
            })

            await interaction.response.send_message("ข้อมูลของคุณถูกอัปเดตแล้ว! ใช้ `/viewcard` เพื่อดูข้อมูลใหม่", ephemeral=False)
        else:
            await interaction.response.send_message("ไม่พบข้อมูลบัตรของคุณ!", ephemeral=True)

# ✅ คำสั่งสร้างบัตร
@bot.tree.command(name="studentcard", description="สร้าง/แก้ไขบัตรนักเรียน")
async def studentcard(interaction: discord.Interaction):
    await interaction.response.send_modal(StudentCardModal())

# ✅ คำสั่งเปิดดูบัตร (ดูของตัวเองหรือของผู้อื่น)
@bot.tree.command(name="viewcard", description="ดูบัตรนักเรียนของคุณหรือของผู้อื่น")
@app_commands.describe(user="เลือกผู้ใช้ที่ต้องการดูบัตร (ไม่ระบุ = ดูของตัวเอง)")
async def viewcard(interaction: discord.Interaction, user: discord.Member = None):
    target_user = user or interaction.user
    user_id = str(target_user.id)

    # ตรวจสอบว่าผู้ใช้มีบัตรนักเรียนหรือไม่
    doc_ref = db.collection('student_cards').document(user_id)
    doc = doc_ref.get()
    
    if not doc.exists:
        msg = "คุณยังไม่มีบัตรนักเรียน ใช้ `/studentcard` เพื่อสร้าง" if user is None else f"{target_user.mention} ยังไม่มีบัตรนักเรียน"
        await interaction.response.send_message(msg, ephemeral=False)
        return
    
    # ดึงข้อมูลจาก Firestore
    data = doc.to_dict()
    house = data["house"]
    class_name = data["class_name"]
    DOB = data["DOB"]
    name = data["name"]
    partner = data["partner"]
    profile_image_url = data["profile_image_url"]
    
    # สร้างบัตรนักเรียน
    card_path = f"{user_id}_card.png"
    create_student_card(card_path, house, class_name, DOB, name, partner, profile_image_url)

    await interaction.response.defer()

    view = EditCardView(user_id) if user_id == str(interaction.user.id) else None

    if view:  # ถ้าดูบัตรตัวเอง มีปุ่มแก้ไข
        await interaction.followup.send(file=discord.File(card_path), view=view)
    else:  # ถ้าดูบัตรของคนอื่น ไม่ต้องส่ง view
        await interaction.followup.send(file=discord.File(card_path))

# ✅ ปุ่มแก้ไขข้อมูลและเปลี่ยนรูปโปรไฟล์
class EditCardView(discord.ui.View):
    def __init__(self, user_id):
        super().__init__()
        self.user_id = user_id

    @discord.ui.button(label="แก้ไขข้อมูล", style=discord.ButtonStyle.primary)
    async def edit_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if str(interaction.user.id) != self.user_id:
            await interaction.response.send_message("คุณไม่สามารถแก้ไขบัตรของคนอื่นได้!", ephemeral=True)
            return
        
        # บันทึกข้อมูลใหม่ใน Firestore แต่ไม่สร้างรูปใหม่
        await interaction.response.send_modal(EditInfoModal(self.user_id))

    @discord.ui.button(label="เปลี่ยนรูปโปรไฟล์", style=discord.ButtonStyle.secondary)
    async def change_image_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if str(interaction.user.id) != self.user_id:
            await interaction.response.send_message("คุณไม่สามารถเปลี่ยนรูปของคนอื่นได้!", ephemeral=True)
            return

        # ตั้งค่าให้บอทรอรับรูปใหม่
        db.collection('student_cards').document(str(interaction.user.id)).update({"waiting_for_image": True})

        await interaction.response.send_message("โปรดส่งรูปภาพที่คุณต้องการใช้ใหม่! (กรอบรูปมีขนาด 490 x 540)", ephemeral=False)

# ✅ รับไฟล์รูปภาพและอัพเดทข้อมูล
@bot.event
async def on_message(message):
    if message.author.bot:
        return

    # ตรวจสอบว่าผู้ใช้ได้กรอกข้อมูลบัตรไว้หรือไม่และบอทกำลังรอรูปภาพ
    user_id = str(message.author.id)
    doc_ref = db.collection('student_cards').document(user_id)
    doc = doc_ref.get()
    
    if not doc.exists or not doc.to_dict().get("waiting_for_image", False):
        return  # ไม่ทำอะไรหากบอทยังไม่รอรูปภาพ

    # ตรวจสอบไฟล์แนบ
    if message.attachments:
        image_url = message.attachments[0].url
        
        # อัปเดต URL รูปภาพในข้อมูลของผู้ใช้
        db.collection('student_cards').document(user_id).update({
            "profile_image_url": image_url,
            "waiting_for_image": False  # ไม่ต้องรอรูปภาพแล้ว
        })

        await message.reply("รูปภาพถูกบันทึกเรียบร้อยแล้ว! ใช้คำสั่ง `/viewcard` เพื่อดูบัตรของคุณ")

def create_student_card(card_path, house, class_name, DOB, name, partner, profile_image_url):
    """สร้างบัตรนักเรียน พร้อมพื้นหลัง"""
    # ลบไฟล์เก่าหากมี
    if os.path.exists(card_path):
         os.remove(card_path)

    # ดึงรูปจาก URL
    response = requests.get(profile_image_url)
    response.raise_for_status()  # ตรวจสอบว่า URL สามารถเข้าถึงได้หรือไม่
    img = Image.open(BytesIO(response.content))

    # โหลด background image
    background = Image.open("student_card.png")  # กำหนด path รูป background ที่คุณต้องการใช้

    # ขนาดบัตรที่กำหนด
    width, height = 1934, 1015
    card = background.resize((width, height))  # ขยาย background ให้ตรงกับขนาดบัตร
    draw = ImageDraw.Draw(card)
    font = ImageFont.truetype("K2D-Regular.ttf", size=45)

    # เพิ่มข้อความ
    draw.text((639, 280), f"{house}", font=font, fill="black")
    draw.text((857, 375), f"{class_name}", font=font, fill="black")
    draw.text((858, 480), f"{DOB}", font=font, fill="black")
    draw.text((876, 581), f"{name}", font=font, fill="black")
    draw.text((909, 680), f"{partner}", font=font, fill="black")

    # ปรับขนาดรูปโปรไฟล์ให้พอดีกับบัตร
    img = img.resize((490, 540))  # ปรับขนาดรูปโปรไฟล์ให้พอดี

    # แทรกรูปโปรไฟล์ในตำแหน่งที่ต้องการ
    card.paste(img, (158, 362), img.convert("RGBA").getchannel("A"))  # ใช้ channel alpha เพื่อรักษาความโปร่งใส

    # บันทึกไฟล์บัตรนักเรียน
    card.save(card_path)

# คำสั่งเพิ่ม point
@bot.tree.command(name="addpoints", description="เพิ่ม point ให้ผู้ใช้")
@app_commands.describe(user="ผู้ใช้", amount="จำนวน point ที่ต้องการเพิ่ม")
@app_commands.checks.has_permissions(administrator=True)
async def addpoints(interaction: discord.Interaction, user: discord.Member, amount: int):
    await interaction.response.defer() 

    ref = db.collection("points").document(str(user.id))
    doc = ref.get()

    if doc.exists:
        new_points = doc.to_dict()["points"] + amount
    else:
        new_points = amount

    ref.set({"points": new_points})

    await interaction.followup.send(f"เพิ่ม {amount} point ให้ {user.mention} แล้ว!") 

# คำสั่งลด point
@bot.tree.command(name="removepoints", description="ลด point ของผู้ใช้")
@app_commands.describe(user="ผู้ใช้", amount="จำนวน point ที่ต้องการลด")
@app_commands.checks.has_permissions(administrator=True)
async def removepoints(interaction: discord.Interaction, user: discord.Member, amount: int):
    await interaction.response.defer()  

    ref = db.collection("points").document(str(user.id))
    doc = ref.get()

    if doc.exists and doc.to_dict()["points"] >= amount:
        new_points = doc.to_dict()["points"] - amount
        ref.set({"points": new_points})
        await interaction.followup.send(f"ลด {amount} point ของ {user.mention} แล้ว!")  
    else:
        await interaction.followup.send("Point ไม่เพียงพอหรือไม่มีข้อมูล!") 

# คำสั่งดู point
@bot.tree.command(name="points", description="ดู point ของตัวเองหรือผู้อื่น")
@app_commands.describe(user="ผู้ใช้ (ใส่หรือไม่ใส่ก็ได้)")
async def points(interaction: discord.Interaction, user: discord.Member = None):
    await interaction.response.defer() 

    if user is None:
        user = interaction.user

    ref = db.collection("points").document(str(user.id))
    doc = ref.get()
    points = doc.to_dict()["points"] if doc.exists else 0

    embed = discord.Embed(title=f"Point ของ {user.name}", description=f"{points} Points!", color=0x191970)

    await interaction.followup.send(embed=embed) 

# คำสั่ง help
@bot.tree.command(name='help', description='วิธีใช้งานคำสั่งต่างๆ')
async def helpcommand(interaction):
    emmbed = discord.Embed(title='Bot Commands - คำสั่งที่สามารถใช้งานได้ ', description='[Slash Command]', color=0x191970, timestamp= discord.utils.utcnow())

    # ใส่ข้อมูล
    emmbed.add_field(name='General', value='`/points @ผู้ใช้`  - เพื่อดูพอยต์ของคุณ\n`/studentcard` - เพื่อสร้างบัตรนักเรียน\n`/viewcard @ผู้ใช้` - เพื่อดูบัตรนักเรียนของคุณ', inline=False)
    emmbed.add_field(name='Administrator', value='`/addpoints @ผู้ใช้ จำนวน` - เพื่อเพิ่มพอยต์ให้ @ผู้ใช้\n`/removepoints @ผู้ใช้ จำนวน` - เพื่อลดพอยต์ของ @ผู้ใช้', inline=False)

    # Footer เนื้อหาส่วนท้าย
    emmbed.set_footer(text='Footer')

    await interaction.response.send_message(embed = emmbed)

server_on()

bot.run(os.getenv('TOKEN'))

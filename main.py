import discord
import os
from discord import app_commands, ui
from discord.ext import commands
from discord.ui import View, Button
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
    house = discord.ui.TextInput(label="บ้าน", placeholder="ลิลิธ/ซาราเซล/เลเซีย/บารัน/ซูซากุ", required=True)
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

        await interaction.response.send_message("โปรดส่งรูปภาพที่คุณต้องการใช้บนบัตร (กรอบรูปมีขนาด 490 x 540)", ephemeral=False)

# ✅ Modal แก้ไขข้อมูล (แยกจาก StudentCardModal)
class EditInfoModal(discord.ui.Modal, title="แก้ไขข้อมูลบัตรนักเรียน"):
    house = discord.ui.TextInput(label="บ้าน", placeholder="ลิลิธ/ซาราเซล/เลเซีย/บารัน/ซูซากุ", required=True)
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

        await interaction.response.send_message("โปรดส่งรูปภาพที่คุณต้องการใช้ใหม่ (กรอบรูปมีขนาด 490 x 540)", ephemeral=False)

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

async def update_points(targets, amount):
    """อัปเดตพอยต์ให้กับผู้ใช้หลายคน"""
    batch = db.batch()
    for user in targets:
        doc_ref = db.collection("points").document(str(user.id))
        doc = doc_ref.get()

        if doc.exists:
            current_points = doc.to_dict().get("points", 0)
        else:
            current_points = 0

        batch.set(doc_ref, {"points": current_points + amount}, merge=True)

    batch.commit()

@bot.tree.command(name="addpoints", description="เพิ่มพอยต์ให้ผู้ใช้หรือยศที่ถูก Mention")
async def addpoints(interaction: discord.Interaction, user: discord.Member | discord.Role, amount: int):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("คุณไม่มีสิทธิ์ใช้คำสั่งนี้ (ต้องเป็นผู้ดูแลเซิร์ฟเวอร์)", ephemeral=True)
        return
    
    await interaction.response.defer()

    if isinstance(user, discord.Role):  # ถ้าเป็น Role ให้ดึงสมาชิกทั้งหมด
        members = [member for member in user.members if not member.bot]
        if not members:
            await interaction.followup.send(f"⚠️ ไม่มีสมาชิกในยศ {user.mention} ที่สามารถเพิ่มพอยต์ได้!", ephemeral=True)
            return
    else:  # ถ้าเป็น Member ปกติ
        members = [user]

    await update_points(members, amount)

    await interaction.followup.send(f"เพิ่ม {amount} พอยต์ให้กับ {', '.join(member.mention for member in members)} สำเร็จ!", ephemeral=True)

@bot.tree.command(name="removepoints", description="ลดพอยต์ของผู้ใช้หรือยศที่ถูก Mention")
async def removepoints(interaction: discord.Interaction, user: discord.Member | discord.Role, amount: int):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("คุณไม่มีสิทธิ์ใช้คำสั่งนี้ (ต้องเป็นผู้ดูแลเซิร์ฟเวอร์)", ephemeral=True)
        return
    
    await interaction.response.defer()

    if isinstance(user, discord.Role):
        members = [member for member in user.members if not member.bot]
        if not members:
            await interaction.followup.send(f"⚠️ ไม่มีสมาชิกในยศ {user.mention} ที่สามารถลดพอยต์ได้!", ephemeral=True)
            return
    else:
        members = [user]

    await update_points(members, -amount)

    await interaction.followup.send(f"ลด {amount} พอยต์จาก {', '.join(member.mention for member in members)} สำเร็จ!", ephemeral=True)

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

#ระบบกระดานคะแนน
@bot.tree.command(name="leaderboard", description="แสดงกระดานคะแนน")
async def leaderboard(interaction: discord.Interaction):
    await interaction.response.defer()

    users_ref = db.collection("points").order_by("points", direction=firestore.Query.DESCENDING).stream()
    
    data = []
    for user in users_ref:
        user_id = user.id
        user_data = user.to_dict()
        points = user_data.get("points", 0)

        # ดึงชื่อผู้ใช้จาก ID
        try:
            discord_user = await bot.fetch_user(user_id)
            username = discord_user.name  # ใช้ชื่อปกติ
        except:
            username = f"Unknown ({user_id})"  # ถ้าหาชื่อไม่เจอ

        data.append({"username": username, "points": points})

    if not data:
        await interaction.followup.send("ไม่มีข้อมูลกระดานคะแนน", ephemeral=True)
        return

    view = LeaderboardView(data)
    await interaction.followup.send(embed=view.generate_embed(), view=view)

class LeaderboardView(discord.ui.View):
    def __init__(self, data, page=0):
        super().__init__()
        self.data = data
        self.page = page
        self.items_per_page = 10
        self.max_page = (len(self.data) - 1) // self.items_per_page
        self.update_buttons()

    def generate_embed(self):
        """สร้าง embed ของกระดานคะแนนตามหน้าปัจจุบัน"""
        embed = discord.Embed(title="🏆 Leaderboard", color=0x191970, timestamp=discord.utils.utcnow())

        start = self.page * self.items_per_page
        end = start + self.items_per_page

        for i, entry in enumerate(self.data[start:end], start=start + 1):
            embed.add_field(
                name=f"#{i} {entry['username']}",  # ใช้ชื่อผู้ใช้แทนไอดี
                value=f"▫️ {entry['points']} พอยต์",
                inline=False
            )

        # ✅ แสดงเลขหน้า
        embed.set_footer(text=f"หน้า {self.page + 1} / {self.max_page + 1}")

        return embed

    def update_buttons(self):
        """อัปเดตปุ่มเปลี่ยนหน้า"""
        self.clear_items()

        self.prev_page = discord.ui.Button(label="⬅️", style=discord.ButtonStyle.primary, disabled=self.page == 0)
        self.next_page = discord.ui.Button(label="➡️", style=discord.ButtonStyle.primary, disabled=self.page >= self.max_page)

        self.prev_page.callback = self.go_prev
        self.next_page.callback = self.go_next

        self.add_item(self.prev_page)
        self.add_item(self.next_page)

    async def go_prev(self, interaction: discord.Interaction):
        """ย้อนหน้ากระดานคะแนน"""
        self.page -= 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.generate_embed(), view=self)

    async def go_next(self, interaction: discord.Interaction):
        """ไปหน้าถัดไปของกระดานคะแนน"""
        self.page += 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.generate_embed(), view=self)

# เพิ่มไอเทมในร้านค้า
@bot.tree.command(name="addshop", description="เพิ่มไอเทมเข้าร้านค้า")
async def addshop(interaction: discord.Interaction, item_name: str, price: int, quantity: int):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("คุณไม่มีสิทธิ์ใช้คำสั่งนี้ (ต้องเป็นผู้ดูแลเซิร์ฟเวอร์)", ephemeral=True)
        return

    await interaction.response.defer()
    
    shop_ref = db.collection("shop").document(item_name)
    item_data = shop_ref.get().to_dict()
    
    if item_data:
        # ถ้ามีไอเทมนี้อยู่แล้ว ให้เพิ่มจำนวนเข้าไป
        new_quantity = item_data["quantity"] + quantity
        shop_ref.update({"quantity": new_quantity})
    else:
        # ถ้ายังไม่มีไอเทมนี้ ให้สร้างใหม่
        shop_ref.set({"name": item_name, "price": price, "quantity": quantity})

    # ✅ ใช้ followup.send แทน send_message เพื่อป้องกันปัญหา
    await interaction.followup.send(f"✅ ไอเทม '{item_name}' ถูกเพิ่มเข้าไปในร้านค้าแล้ว!", ephemeral=True)

@bot.tree.command(name="removeshop", description="ลบไอเทมออกจากร้านค้า")
@discord.app_commands.describe(item_name="ชื่อไอเทมที่ต้องการลบ", amount="จำนวนที่ต้องการลบ")
async def removeshop(interaction: discord.Interaction, item_name: str, amount: int):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("คุณไม่มีสิทธิ์ใช้คำสั่งนี้ (ต้องเป็นผู้ดูแลเซิร์ฟเวอร์)", ephemeral=True)
        return
    await interaction.response.defer()

    if amount <= 0:
        await interaction.followup.send("❌ จำนวนต้องมากกว่า 0", ephemeral=True)
        return

    shop_ref = db.collection("shop").document(item_name.lower())
    shop_doc = shop_ref.get()

    if shop_doc.exists:
        shop_data = shop_doc.to_dict()
        current_quantity = shop_data.get("quantity", 0)

        if current_quantity >= amount:
            shop_ref.update({"quantity": current_quantity - amount})
            await interaction.followup.send(f"🛒 ลบ {amount} ชิ้นของ '{item_name}' ออกจากร้านค้าแล้ว!")
        else:
            await interaction.followup.send("❌ จำนวนไอเทมในร้านค้าไม่เพียงพอ", ephemeral=True)
    else:
        await interaction.followup.send("❌ ไม่พบไอเทมนี้ในร้านค้า", ephemeral=True)

@bot.tree.command(name="setprice", description="เปลี่ยนราคาไอเทมในร้านค้า")
@discord.app_commands.describe(item_name="ชื่อไอเทมที่ต้องการเปลี่ยนราคา", new_price="ราคาที่ต้องการตั้งใหม่")
async def setprice(interaction: discord.Interaction, item_name: str, new_price: int):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("คุณไม่มีสิทธิ์ใช้คำสั่งนี้ (ต้องเป็นผู้ดูแลเซิร์ฟเวอร์)", ephemeral=True)
        return
    await interaction.response.defer()

    if new_price < 0:
        await interaction.followup.send("❌ ราคาต้องเป็นเลขจำนวนเต็มบวก", ephemeral=True)
        return

    shop_ref = db.collection("shop").document(item_name.lower())
    shop_doc = shop_ref.get()

    if shop_doc.exists:
        shop_ref.update({"price": new_price})
        await interaction.followup.send(f"💰 เปลี่ยนราคา '{item_name}' เป็น {new_price} พอยต์แล้ว!")
    else:
        await interaction.followup.send("❌ ไม่พบไอเทมนี้ในร้านค้า", ephemeral=True)

# แสดงร้านค้า
@bot.tree.command(name="shop", description="แสดงร้านค้า")
async def shop(interaction: discord.Interaction):
    await interaction.response.defer()

    shop_ref = db.collection("shop")
    items = [doc.to_dict() for doc in shop_ref.stream() if doc.to_dict()["quantity"] > 0]

    if not items:
        await interaction.followup.send("🛒 ร้านค้าว่างเปล่า ไม่มีสินค้าให้ซื้อ!", ephemeral=True)
        return

    view = ShopView(items)  # ✅ ใช้ View ใหม่ที่รองรับปุ่มเปลี่ยนหน้า
    await interaction.followup.send(embed=view.generate_embed(), view=view)

class ShopView(discord.ui.View):
    def __init__(self, items, page=0):
        super().__init__()
        self.items = items
        self.page = page
        self.items_per_page = 5
        self.max_page = (len(self.items) - 1) // self.items_per_page

        # ✅ ต้องสร้าง dropdown ก่อนเรียก `update_buttons()`
        self.dropdown = discord.ui.Select(
            placeholder="เลือกไอเทมที่ต้องการซื้อ...",
            options=self.generate_dropdown_options()
        )
        self.dropdown.callback = self.select_item

        self.update_buttons()  # ✅ เรียกอัปเดตปุ่มหลังจากมี dropdown แล้ว

    def generate_embed(self):
        """สร้าง embed ของร้านค้าตามหน้าปัจจุบัน"""
        embed = discord.Embed(title="🛒 ร้านค้า", color=0x191970, timestamp= discord.utils.utcnow())

        start = self.page * self.items_per_page
        end = start + self.items_per_page

        for item in self.items[start:end]:
            embed.add_field(
                name=item["name"],
                value=f"💰 ราคา: {item['price']} พอยต์ | 📦 คงเหลือ: {item['quantity']}",
                inline=False
            )

        return embed

    def generate_dropdown_options(self):
        """สร้างตัวเลือก dropdown ตามหน้าปัจจุบัน"""
        start = self.page * self.items_per_page
        end = start + self.items_per_page

        return [
            discord.SelectOption(
                label=item["name"],
                description=f"{item['price']} พอยต์",
                value=item["name"]
            )
            for item in self.items[start:end]
        ]

    async def select_item(self, interaction: discord.Interaction):
        """เมื่อเลือกไอเทมจาก Dropdown ให้แสดง Modal"""
        item_name = self.dropdown.values[0]
        item_data = next((item for item in self.items if item["name"] == item_name), None)

        if item_data:
            modal = PurchaseModal(item_data["name"], item_data["price"], item_data["quantity"])
            await interaction.response.send_modal(modal)

    def update_buttons(self):
        """อัปเดตปุ่มเปลี่ยนหน้า"""
        self.clear_items()
        self.add_item(self.dropdown)  # ✅ เพิ่ม dropdown กลับเข้ามาหลังจาก clear

        self.prev_page = discord.ui.Button(label="⬅️", style=discord.ButtonStyle.primary, disabled=self.page == 0)
        self.next_page = discord.ui.Button(label="➡️", style=discord.ButtonStyle.primary, disabled=self.page >= self.max_page)

        self.prev_page.callback = self.go_prev
        self.next_page.callback = self.go_next

        self.add_item(self.prev_page)
        self.add_item(self.next_page)

    async def go_prev(self, interaction: discord.Interaction):
        """กดปุ่มย้อนหน้าร้านค้า"""
        self.page -= 1
        self.update_buttons()
        self.dropdown.options = self.generate_dropdown_options()
        await interaction.response.edit_message(embed=self.generate_embed(), view=self)

    async def go_next(self, interaction: discord.Interaction):
        """กดปุ่มไปหน้าถัดไปร้านค้า"""
        self.page += 1
        self.update_buttons()
        self.dropdown.options = self.generate_dropdown_options()
        await interaction.response.edit_message(embed=self.generate_embed(), view=self)

class PurchaseModal(discord.ui.Modal):
    def __init__(self, item_name, price, quantity_available):
        super().__init__(title="ยืนยันการซื้อ")
        self.item_name = item_name
        self.price = price
        self.quantity_available = quantity_available

        self.quantity_input = discord.ui.TextInput(
            label="จำนวนที่ต้องการซื้อ",
            placeholder=f"สูงสุด {quantity_available}",
            required=True
        )
        self.add_item(self.quantity_input)

    async def on_submit(self, interaction: discord.Interaction):
        quantity = int(self.quantity_input.value)
        total_price = self.price * quantity

        user_ref = db.collection("points").document(str(interaction.user.id))
        user_doc = user_ref.get()

        current_points = user_doc.to_dict().get("points", 0) if user_doc.exists else 0

        if current_points >= total_price and quantity <= self.quantity_available:
            user_ref.update({"points": current_points - total_price})
            shop_ref = db.collection("shop").document(self.item_name.lower())
            shop_ref.update({"quantity": self.quantity_available - quantity})

            inventory_ref = db.collection("inventory").document(str(interaction.user.id))
            inventory_doc = inventory_ref.get()

            if inventory_doc.exists:
                inventory_data = inventory_doc.to_dict()
                inventory_data[self.item_name] = inventory_data.get(self.item_name, 0) + quantity
                inventory_ref.update(inventory_data)
            else:
                inventory_ref.set({self.item_name: quantity})

            await interaction.response.send_message(f"✅ คุณซื้อ {quantity} ชิ้นของ '{self.item_name}' รวม {total_price} พอยต์!", ephemeral=True)
        else:
            await interaction.response.send_message("❌ คุณไม่มียอดพอยต์เพียงพอ หรือสินค้าหมด", ephemeral=True)

# ให้ไอเทมผู้ใช้
@bot.tree.command(name="additem", description="เพิ่มไอเทมให้กับผู้ใช้")
async def additem(interaction: discord.Interaction, user: discord.Member, item_name: str, quantity: int):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("คุณไม่มีสิทธิ์ใช้คำสั่งนี้ (ต้องเป็นผู้ดูแลเซิร์ฟเวอร์)", ephemeral=True)
        return
    await interaction.response.defer()

    inventory_ref = db.collection("inventory").document(str(user.id))
    inventory_doc = inventory_ref.get()

    if inventory_doc.exists:
        inventory_data = inventory_doc.to_dict()
        inventory_data[item_name] = inventory_data.get(item_name, 0) + quantity
        inventory_ref.update(inventory_data)
    else:
        inventory_ref.set({item_name: quantity})

    await interaction.followup.send(f"✅ เพิ่มไอเทม '{item_name}' จำนวน {quantity} ชิ้นให้กับ {user.mention} สำเร็จ!", ephemeral=True)

@bot.tree.command(name="removeitem", description="ลบไอเทมออกจาก inventory ของผู้ใช้")
@discord.app_commands.describe(user="ผู้ใช้ที่ต้องการลบไอเทม", item_name="ชื่อไอเทม", amount="จำนวนที่ต้องการลบ")
async def removeitem(interaction: discord.Interaction, user: discord.User, item_name: str, amount: int):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("คุณไม่มีสิทธิ์ใช้คำสั่งนี้ (ต้องเป็นผู้ดูแลเซิร์ฟเวอร์)", ephemeral=True)
        return
    await interaction.response.defer()

    if amount <= 0:
        await interaction.followup.send("❌ จำนวนต้องมากกว่า 0", ephemeral=True)
        return

    inventory_ref = db.collection("inventory").document(str(user.id))
    inventory_doc = inventory_ref.get()

    if inventory_doc.exists:
        inventory_data = inventory_doc.to_dict()
        current_quantity = inventory_data.get(item_name, 0)

        if current_quantity >= amount:
            if current_quantity == amount:
                del inventory_data[item_name]  # ลบไอเทมออกจาก inventory ถ้าจำนวนเป็น 0
            else:
                inventory_data[item_name] -= amount

            inventory_ref.set(inventory_data)
            await interaction.followup.send(f"📦 ลบ {amount} ชิ้นของ '{item_name}' ออกจาก inventory ของ {user.display_name} แล้ว!")
        else:
            await interaction.followup.send("❌ จำนวนไอเทมใน inventory ไม่เพียงพอ", ephemeral=True)
    else:
        await interaction.followup.send("❌ ผู้ใช้ไม่มีไอเทมนี้", ephemeral=True)

# ดู inventory
@bot.tree.command(name="inventory", description="ดูรายการไอเทมของคุณหรือของผู้อื่น")
@discord.app_commands.describe(user="ระบุผู้ใช้ที่ต้องการดู Inventory")
async def inventory(interaction: discord.Interaction, user: discord.User | None = None):
    await interaction.response.defer()

    # ถ้าไม่ระบุ user → ดู inventory ของตัวเอง
    target_user = user or interaction.user

    inventory_ref = db.collection("inventory").document(str(target_user.id))
    inventory_doc = inventory_ref.get()

    if inventory_doc.exists:
        inventory_data = inventory_doc.to_dict()
        items = [f"{item} - {quantity} ชิ้น" for item, quantity in inventory_data.items()]
        embed = discord.Embed(
            title=f"📦 รายการไอเทมของ {target_user.display_name}",
            description="\n".join(items),
            color=0x191970, 
            timestamp= discord.utils.utcnow()
            )
        await interaction.followup.send(embed=embed)
    else:
        await interaction.followup.send(f"❌ {target_user.display_name} ยังไม่มีไอเทมใน inventory", ephemeral=True)

# คำสั่ง help
@bot.tree.command(name='help', description='วิธีใช้งานคำสั่งต่างๆ')
async def helpcommand(interaction):
    emmbed = discord.Embed(title='Bot Commands - คำสั่งที่สามารถใช้งานได้ ', description='[ใช้ Slash Command]', color=0x191970, timestamp= discord.utils.utcnow())

    # ใส่ข้อมูล
    emmbed.add_field(name='General', value='`/points [@ผู้ใช้]`  - เพื่อดูพอยต์ของคุณหรือคนอื่น\n`/studentcard` - เพื่อสร้างบัตรนักเรียน\n`/viewcard [@ผู้ใช้]` - เพื่อดูบัตรนักเรียนของคุณ\n`/inventory [@ผู้ใช้]` - เพื่อดูไอเทมในกระเป๋าคุณหรือคนอื่น\n`/shop` - เพื่อเปิดดูร้านค้า', inline=False)
    emmbed.add_field(name='Administrator', value='`/addpoints [@ผู้ใช้] [จำนวน]` - เพื่อเพิ่มพอยต์ให้ @ผู้ใช้\n`/removepoints [@ผู้ใช้] [จำนวน]` - เพื่อลดพอยต์ของ @ผู้ใช้\n`/addshop [ชื่อไอเทม] [ราคาไอเทม] [จำนวนที่จะเพิ่ม]` - เพื่อเพิ่มไอเทมเข้าไปยังร้านค้า\n`/removeshop [ชื่อไอเทม] [จำนวนที่จะลบ]` - เพื่อลบไอเทมในร้านค้า\n`/setprice [ชื่อไอเทม] [ราคาใหม่]` - เพื่อเปลี่ยนราคาไอเทมในร้านค้า\n`/additem [@ผู้ใช้] [ชื่อไอเทม] [จำนวน]` - เพื่อเพิ่มไอเทมไปยังกระเป๋าของ @ผู้ใช้\n`/removeitem [@ผู้ใช้] [ชื่อไอเทม] [จำนวน]` - เพื่อลบไอเทมในกระเป๋าของ @ผู้ใช้', inline=False)

    await interaction.response.send_message(embed = emmbed)

server_on()

bot.run(os.getenv('TOKEN'))

"""Offline operator manual for the existing GTK desktop workflows."""

from gi.repository import Gdk, Gtk, Pango


CHAPTERS = (
    ('start', 'เริ่มต้น', 'เริ่มใช้งาน AQUA COMMAND', (
        ('ลำดับงานประจำ',
         'เปิด «ติดตามค่า» เพื่อดูค่าล่าสุด ใช้ «งานเฝ้าระวัง» เพื่อตั้งรอบตรวจและการแจ้งเตือน ถ้าข้อมูลไม่มา ให้ตรวจที่ «ผังการสื่อสาร» '
         'ถ้ารายชื่อจากไฟล์ WinCC เปลี่ยน ให้เปิดคลัง Tag แล้วกดรีเฟรชคลัง'),
        ('เลือกแหล่งอ่านข้อมูล',
         'เปิดฟันเฟืองมุมขวาล่าง สำหรับ OPC UA ให้ใช้แท็บ WinCC OPC UA '
         'ส่วน OPC DA, REST และ MQTT อยู่ในแท็บแหล่งข้อมูล'),
        ('อ่านสถานะให้ถูกต้อง',
         'ชื่อ Tag ในคลังมาจากไฟล์ตั้งค่า WinCC ค่าปัจจุบันต้องมีผลอ่านพร้อมคุณภาพและเวลา '
         'ถ้าไม่เคยอ่านจะขึ้นยังไม่ได้สังเกต ถ้าค่าหมดอายุจะขึ้นข้อมูลเก่า'),
    )),
    ('f1', 'ติดตามค่า', 'ดูค่าและรายละเอียด Tag', (
        ('ค้นหาและดูรายละเอียด',
         'เลือกกลุ่มอุปกรณ์ด้านซ้ายหรือพิมพ์ชื่อ Tag ในช่องค้นหา กดปุ่มแว่นขยายหรือกด Enter '
         'บนแถวที่โฟกัสเพื่อดูค่า แหล่งข้อมูล และเวลาต้นทาง'),
        ('เลือกและผูกกับ Task',
         'คลิกแถวเพื่อเลือกหรือยกเลิก ใช้ Shift+คลิกเพื่อเลือกเป็นช่วง '
         'กด + Task สำหรับแถวเดียว หรือใช้ปุ่มเพิ่มเข้า Task เมื่อเลือกหลายแถว'),
        ('เมื่อค่าไม่อัปเดต',
         'ดูป้ายแหล่งข้อมูลด้านบน จากนั้นดูสถานะและเวลาของ Tag ในรายละเอียด '
         'การรีเฟรชคลัง Tag จะอัปเดตรายชื่อจากไฟล์ WinCC'),
    )),
    ('f2', 'งานเฝ้าระวัง', 'ตั้งรอบตรวจและการแจ้งเตือน', (
        ('เลือกหรือสร้าง Task',
         'เลือก Task เดิมหรือสร้างงานใหม่ แล้วตั้งชื่อ รอบตรวจ และวิธีบันทึกหรือแจ้งเตือน'),
        ('จัดการ Tag และบันทึก',
         'เพิ่ม Tag จากหน้าติดตามค่า แล้วตรวจรายการ Tag ด้านขวาของหน้าต่างงานเฝ้าระวัง '
         'เลือกแถวเพื่อเอาออก เปิดใช้งานเมื่อพร้อม แล้วกดบันทึก Task ที่ท้ายหน้าต่าง'),
        ('แหล่งข้อมูลสำหรับ Task',
         'แหล่งสำรอง OPC DA, REST และ MQTT ใช้แสดงค่าในหน้าติดตามค่า '
         'การประเมิน Task และแจ้งเตือนจากแหล่งสำรองยังไม่ได้เชื่อม'),
    )),
    ('f3', 'ผังการสื่อสาร', 'ดูว่าข้อมูลเดินทางถึงขั้นไหน', (
        ('อ่านผังจากซ้ายไปขวา',
         'ดูต้นทาง WinCC การประมวลผลใน AQUA COMMAND และทางออกแจ้งเตือน '
         'คลิกอุปกรณ์เพื่อดูรายละเอียดผลตรวจและเวลา'),
        ('แยกสถานะของแต่ละขั้น',
         'การเชื่อมต่อเครือข่าย เซสชัน OPC UA ผลอ่าน และการส่ง Telegram เป็นคนละขั้น '
         'ดูหลักฐานของขั้นที่ต้องการโดยตรง'),
        ('โหมดจำลอง',
         'ป้าย SIMULATED ระบุข้อมูลทดสอบ หากกดปุ่มจำลองและส่ง Telegram '
         'โปรแกรมอาจส่งข้อความจริงไปยังปลายทางที่ตั้งไว้'),
    )),
    ('f4', 'ข้อมูลเครื่อง', 'ตรวจข้อมูลเครื่องที่รัน AQUA', (
        ('ดูข้อมูลระบบ',
         'เปิดข้อมูลเครื่องเพื่อดูระบบปฏิบัติการ CPU หน่วยความจำ พื้นที่จัดเก็บ และ IP ของเครื่อง '
         'ดูหลักฐานการเชื่อมต่อ WinCC เพิ่มเติมในหน้าผังการสื่อสาร'),
    )),
    ('f5', 'คลัง Tag', 'ดูและรีเฟรชคลัง WinCC', (
        ('ตรวจชื่อและชนิดของ Tag',
         'เปิดคลัง Tag เพื่อดูชื่อ กลุ่ม ชนิด ที่อยู่ และการเชื่อมต่อจากไฟล์ส่งออกของ WinCC '
         'กดรีเฟรชคลัง เมื่อไฟล์ต้นทางเปลี่ยน'),
        ('ใช้ชื่อที่ตรงกัน',
         'เมื่อตั้งค่าแหล่งข้อมูลหรือผูก Task ให้ใช้ชื่อ Tag ตรงกับคลัง '
         'เปิดหน้าติดตามค่าเพื่อดูค่าที่อ่านได้'),
    )),
    ('opcua', 'WinCC OPC UA', 'ตั้งค่า WinCC OPC UA', (
        ('กรอกค่าที่ผู้ดูแลให้',
         'ใส่ URL เซิร์ฟเวอร์ เลือกความปลอดภัยและวิธีเข้าสู่ระบบให้ตรงกับ WinCC '
         'ถ้าใช้ Username ให้กรอกข้อมูลในช่องที่แสดง'),
        ('บันทึกและทดสอบก่อนเริ่มอ่าน',
         'กดบันทึก WinCC แล้วทดสอบการเชื่อมต่อ หากต้องอนุมัติใบรับรองให้เทียบ Fingerprint กับผู้ดูแล '
         'ผลทดสอบการเชื่อมต่อและผลอ่าน Tag จริงตรวจแยกกัน'),
        ('อ่านและตรวจสถานะ',
         'กดเริ่มอ่านเมื่อพร้อม แล้วดูค่า คุณภาพ และเวลาในหน้าติดตามค่า '
         'ใช้ปุ่มพักหรือหยุดในแท็บ WinCC OPC UA เมื่อต้องการหยุดการอ่าน'),
    )),
    ('opcda', 'OPC DA · Windows Gateway', 'อ่าน OPC DA ผ่าน Windows Gateway', (
        ('เตรียมที่เครื่อง WinCC',
         'เปิด Windows Reader บนเครื่อง WinCC เลือก Tag สถานะหรือ Analog '
         'จากนั้นอนุญาตให้อ่านและส่งไป Gateway ตามสิทธิ์ที่ได้รับ'),
        ('เลือกฐานข้อมูล Gateway',
         'เปิดแท็บแหล่งข้อมูล เลือก OPC DA · Windows Gateway ใส่รหัส Reader เช่น PC-01 '
         'แล้วเลือกไฟล์ aqua.sqlite3 ของ Gateway บนเครื่องนี้'),
        ('อ่านค่าที่ได้รับ',
         'ใส่ชื่อ Tag หนึ่งชื่อต่อบรรทัด แล้วกดอ่านครั้งเดียวหรือเริ่มอ่านตามรอบ '
         'หน้าติดตามค่าใช้เวลาต้นทางของแต่ละ Tag เพื่อบอกว่าค่านั้นอ่านมาเมื่อไร'),
    )),
    ('rest', 'REST · HTTPS', 'อ่านค่า Tag ผ่าน REST', (
        ('กรอกปลายทาง',
         'เปิดแท็บแหล่งข้อมูล เลือก REST · HTTPS ตั้งรหัสแหล่ง แล้วใส่ URL HTTPS ที่ Gateway ให้ '
         'ปลายทางต้องส่ง snapshot ตามรูปแบบ AQUA COMMAND'),
        ('ไฟล์ความปลอดภัย',
         'เลือกไฟล์ CA เมื่อปลายทางใช้ CA ภายใน ใส่พาธไฟล์ Bearer token เมื่อ Gateway ต้องการ'),
        ('ตรวจค่าที่อ่าน',
         'ใส่ชื่อ Tag หนึ่งชื่อต่อบรรทัด กดอ่านครั้งเดียว แล้วตรวจค่าและชื่อแหล่งในหน้าติดตามค่า '
         'เมื่อพร้อมจึงกดเริ่มอ่านตามรอบ'),
    )),
    ('mqtt', 'MQTT · TLS', 'รับค่า Tag ผ่าน MQTT', (
        ('กรอก broker และ Topic',
         'เปิดแท็บแหล่งข้อมูล เลือก MQTT · TLS ตั้งรหัสแหล่ง ใส่ URL mqtts '
         'และชื่อ Topic ที่ตรงกับที่ Gateway ส่ง ใช้ชื่อแบบเจาะจงโดยไม่ใส่ # หรือ +'),
        ('เลือกใบรับรองตามที่ broker ใช้',
         'ใส่ไฟล์ CA เมื่อใช้ CA ภายใน ถ้า broker ใช้ mTLS ให้ใส่ใบรับรองและกุญแจ client คู่กัน'),
        ('เริ่มอ่าน',
         'ใส่ชื่อ Tag หนึ่งชื่อต่อบรรทัด แล้วกดอ่านครั้งเดียวหรือเริ่มอ่านตามรอบ '
         'โปรแกรมรอ snapshot ใหม่จาก Topic นั้น ข้อความ retained ที่ได้รับตอน subscribe จะถูกข้าม'),
    )),
    ('telegram', 'Telegram', 'ตั้งค่าปลายทาง Telegram', (
        ('ระบุปลายทาง',
         'เปิดแท็บ Telegram ใส่ Bot Token และ Chat ID ที่จะรับข้อความ แล้วกดบันทึกปลายทาง'),
        ('ตรวจสอบปลายทางก่อนส่ง',
         'ปุ่มส่งข้อความทดสอบจริงจะส่งข้อความไปยัง Chat ID ที่กรอก '
         'ตรวจชื่อห้องและข้อความให้ถูกต้องก่อนกดส่ง'),
    )),
    ('history', 'ประวัติเหตุการณ์', 'อ่านประวัติเหตุการณ์', (
        ('ดูเหตุการณ์ล่าสุด',
         'เปิดแท็บประวัติเหตุการณ์เพื่อดูเวลา แหล่งที่มา ระดับ สถานะ และรายละเอียด '
         'เมื่อต้องตรวจปัญหา ให้เทียบเวลากับผลอ่านในหน้าติดตามค่า หรือหลักฐานในหน้าผังการสื่อสาร'),
    )),
    ('shortcuts', 'คีย์ลัด', 'คีย์ลัดใน AQUA COMMAND', (
        ('เปิดหน้าหลัก',
         'F1   ติดตามค่า\nF2   งานเฝ้าระวัง\nF3   ผังการสื่อสาร\n'
         'F4   ข้อมูลเครื่อง\nF5   คลัง Tag\nF6 หรือ Ctrl+,   ตั้งค่าการเชื่อมต่อ'),
        ('คำสั่งทั่วไป',
         'F7   รีเฟรชคลัง Tag\nF8   ปิดโปรแกรม\nF9   เปิดคู่มือการใช้งาน\nEsc   ปิดหน้าต่างคู่มือ'),
        ('เมื่ออยู่หน้าติดตามค่า',
         '/   โฟกัสช่องค้นหา\n↑ หรือ ↓   เลื่อนโฟกัสระหว่างแถว\nEnter   ดูรายละเอียดแถวที่โฟกัส\n'
         'Space   เลือกหรือยกเลิกแถวที่โฟกัส\nShift+คลิก   เลือกแถวเป็นช่วง'),
    )),
)


def text_label(text, css=''):
    label = Gtk.Label(label=text, xalign=0, wrap=True)
    label.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
    if css:
        label.add_css_class(css)
    return label


class HelpManual(Gtk.Window):
    def __init__(self, parent):
        super().__init__(title='คู่มือการใช้งาน AQUA COMMAND', transient_for=parent,
                         modal=True, destroy_with_parent=True, hide_on_close=True,
                         default_width=860, default_height=640)
        self.set_size_request(620, 420)
        self.add_css_class('aqua-manual')
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_child(root)

        header = Gtk.Box(spacing=12)
        header.add_css_class('manual-header')
        heading = text_label('คู่มือการใช้งาน', 'page-title')
        heading.set_hexpand(True)
        header.append(heading)
        self.close_button = Gtk.Button(label='ปิด')
        self.close_button.add_css_class('fkey-btn')
        self.close_button.connect('clicked', lambda _: self.close())
        header.append(self.close_button)
        root.append(header)

        body = Gtk.Box(vexpand=True)
        root.append(body)
        self.chapters = Gtk.Stack(hexpand=True, vexpand=True, hhomogeneous=False, vhomogeneous=False)
        self.sidebar = Gtk.StackSidebar(stack=self.chapters)
        self.sidebar.set_size_request(196, -1)
        body.append(self.sidebar)
        body.append(self.chapters)

        for key, caption, title, sections in CHAPTERS:
            scroll = Gtk.ScrolledWindow()
            scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
            content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20)
            content.add_css_class('manual-content')
            content.append(text_label(title, 'page-title'))
            for name, description in sections:
                section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
                section.append(text_label(name, 'manual-section-title'))
                section.append(text_label(description, 'manual-copy'))
                content.append(section)
            scroll.set_child(content)
            self.chapters.add_titled(scroll, key, caption)
        self.chapters.set_visible_child_name('start')

        keyboard = Gtk.EventControllerKey()
        keyboard.connect('key-pressed', self.on_key_pressed)
        self.add_controller(keyboard)

    def on_key_pressed(self, _, key, _code, _state):
        if key != Gdk.KEY_Escape:
            return False
        self.close()
        return True

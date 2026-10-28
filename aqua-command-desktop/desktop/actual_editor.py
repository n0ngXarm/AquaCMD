"""Explicit actual-source/deployment setup; saving never starts a worker."""
import pathlib,secrets
from gi.repository import Gtk,GLib
from model import owned_directory,atomic_json,read_tag_names
from production import validate_settings
from consent import ConsentBook

def text(s,css=None):
 w=Gtk.Label(label=s,xalign=0);w.set_wrap(True)
 if css:w.add_css_class(css)
 return w

class ActualEditor(Gtk.Window):
 def __init__(self,owner):
  super().__init__(title='ตั้งค่าการใช้งานจริง',transient_for=owner,modal=True);self.owner=owner;self.set_default_size(800,700)
  outer=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=12);outer.add_css_class('dialog-body');self.set_child(outer)
  outer.append(text('เลือกต้นทางและบทบาทด้วยตนเอง','page-title'));outer.append(text('บันทึกอย่างเดียว ยังไม่อ่าน ไม่เปิด OPC DA ไม่เชื่อม LAN และไม่ส่งข้อมูล','notice'))
  choices=['WinCC OPC DA — ใช้ Windows Runtime Reader.exe','อ่าน Runtime CSV จริงบนเครื่องนี้','Gateway รับข้อมูลจากเครื่องที่ลงทะเบียน']
  self.mode=Gtk.DropDown.new_from_strings(choices);self.mode.set_selected({'runtime':0,'csv':1,'gateway':2}.get(owner.source_mode,0));outer.append(self.mode)
  sc=Gtk.ScrolledWindow();sc.set_vexpand(True);outer.append(sc);body=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=12);sc.set_child(body)
  self.runtime=text('ตัวอ่าน OPC DA เป็น Windows .exe บนเครื่อง WinCC และใช้ OPCServer.WinCC แบบอ่านอย่างเดียว\nต้องได้รับอนุญาตจากหน่วยงานและเปิดช่องทางโดยผู้ดูแลก่อน แล้วจึงกดเริ่มอ่านด้วยตนเอง\nการตรวจ registration ไม่เปิด COM server; การเชื่อมต่อหลังอนุญาตอาจเริ่ม COM local server\nLinux โปรแกรมนี้ใช้เป็น Gateway ได้ ไม่ใช้ข้อมูลจำลองแทน WinCC','detail-copy');body.append(self.runtime)
  self.fields={};self.agent=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=8);body.append(self.agent);self.gateway=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=8);body.append(self.gateway)
  s=owner.settings;d=s.get('deployment',{});self.add(self.agent,'sourceDirectory','โฟลเดอร์ Runtime CSV จริง',s.get('sourceDirectory',''));self.add(self.agent,'agentId','Agent ID: PC-01 / PC-02 / PC-03',d.get('id','PC-01') if d.get('role')=='agent' else 'PC-01');self.add(self.agent,'gatewayUrl','HTTPS Gateway พร้อม private IP และพอร์ต',d.get('gatewayUrl',''));self.add(self.agent,'gatewaySecret','คีย์เฉพาะ Agent นี้ (64 hex)',d.get('gatewaySecret',''),True);self.add(self.agent,'caFile','CA certificate สำหรับเครื่องรับ (ว่าง = OS trust)',d.get('caFile',''));self.add(self.agent,'agentPort','พอร์ตควบคุมภายในเครื่อง (127.0.0.1 เท่านั้น)',str(d.get('listenPort',4181)) if d.get('role')=='agent' else '4181')
  self.agent.append(text('Tag ที่อนุญาตอ่าน: หนึ่งชื่อต่อบรรทัด (เฉพาะ complete configured CSV frames)'));self.tags=Gtk.TextView();self.tags.set_wrap_mode(Gtk.WrapMode.WORD_CHAR);self.tags.get_buffer().set_text('\n'.join(s.get('tags',[])));ts=Gtk.ScrolledWindow();ts.set_min_content_height(100);ts.set_child(self.tags);self.agent.append(ts);imp=Gtk.Button(label='นำเข้ารายชื่อ Tag');imp.connect('clicked',self.import_tags);self.agent.append(imp);self.confirmed=Gtk.CheckButton(label='ตรวจแล้วว่า0=OFF,1=ON สำหรับ Tag ที่เลือก');self.confirmed.set_active(s.get('mappingConfirmed') is True);self.agent.append(self.confirmed)
  self.add(self.gateway,'listenHost','IP ของ Gateway เครื่องนี้ (ระบุเอง ไม่สแกน)',d.get('listenHost','127.0.0.1'));self.add(self.gateway,'listenPort','พอร์ต HTTPS รับข้อมูล',str(d.get('listenPort',4174)));self.add(self.gateway,'certFile','TLS certificate ของเครื่องนี้ (IP SAN ต้องตรง)',d.get('certFile',''));self.add(self.gateway,'keyFile','TLS private key ของเครื่องนี้',d.get('keyFile',''));self.gateway.append(text('ลงทะเบียนคีย์แยกตามเครื่องต้นทาง เว้นว่างเครื่องที่ไม่อนุญาต ไม่รับข้อมูลจำลอง'))
  for id in ('PC-01','PC-02','PC-03'):
   self.add(self.gateway,id,id+' — shared key64hex',d.get('peers',{}).get(id,''),True)
   b=Gtk.Button(label='สร้างคีย์ใหม่ให้ '+id);b.connect('clicked',lambda _,i=id:self.fields[i].set_text(secrets.token_hex(32)));self.gateway.append(b)
  self.gateway.append(text('ปลายทางแจ้งเตือน'));self.telegram=Gtk.DropDown.new_from_strings(['เก็บใน Gateway / Telegram dry-run (ไม่ส่งภายนอก)','Telegram จริง — ต้องอนุญาตส่งแยกและตั้งค่า env']);self.telegram.set_selected(1 if d.get('telegramMode')=='telegram' else 0);self.gateway.append(self.telegram);self.gateway.append(text('Telegram จริงใช้ TELEGRAM_ENABLED, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID และ TELEGRAM_APPROVED_ENDPOINT=https://api.telegram.org; ไม่มี probe จนกดอนุญาตส่ง','caption'))
  self.error=text('','notice');outer.append(self.error);row=Gtk.Box(spacing=8);outer.append(row);self.save_button=Gtk.Button(label='บันทึก ยังไม่เริ่มงาน');self.save_button.connect('clicked',self.save);row.append(self.save_button);cancel=Gtk.Button(label='ยกเลิก');cancel.connect('clicked',lambda _:self.close());row.append(cancel);self.mode.connect('notify::selected',lambda *_:self.update());self.connect('close-request',lambda _:self.released());self.update()
 def released(self):self.owner.source_editor=None;return False
 def add(self,parent,key,title,value,secret=False):
  parent.append(text(title,'caption'));entry=Gtk.PasswordEntry(show_peek_icon=True) if secret else Gtk.Entry();entry.set_text(value);parent.append(entry);self.fields[key]=entry
 def update(self):
  n=self.mode.get_selected();self.runtime.set_visible(n==0);self.agent.set_visible(n==1);self.gateway.set_visible(n==2)
 def import_tags(self,_):
  def done(d,result):
   try:self.tags.get_buffer().set_text('\n'.join(read_tag_names(d.open_finish(result).get_path())))
   except GLib.Error:pass
   except (OSError,ValueError,UnicodeError) as e:self.error.set_text(str(e))
  Gtk.FileDialog(title='เลือกไฟล์รายชื่อ Tag').open(self,None,done)
 def save(self,_):
  get=lambda k:self.fields[k].get_text().strip();n=self.mode.get_selected();mode=['runtime','csv','gateway'][n]
  try:
   if n==0:s={}
   elif n==1:
    buf=self.tags.get_buffer();tags=[t.strip() for t in buf.get_text(buf.get_start_iter(),buf.get_end_iter(),False).splitlines() if t.strip()];s={'sourceDirectory':get('sourceDirectory'),'tags':tags,'timezoneOffset':'+07:00','mappingConfirmed':self.confirmed.get_active(),'deployment':{'role':'agent','id':get('agentId'),'listenHost':'127.0.0.1','listenPort':int(get('agentPort')),'gatewayUrl':get('gatewayUrl'),'gatewaySecret':get('gatewaySecret'),'caFile':get('caFile')}}
   else:s={'deployment':{'role':'gateway','id':'PC-04','listenHost':get('listenHost'),'listenPort':int(get('listenPort')),'certFile':get('certFile'),'keyFile':get('keyFile'),'peers':{id:get(id) for id in ('PC-01','PC-02','PC-03') if get(id)},'telegramMode':['dry-run','telegram'][self.telegram.get_selected()]}}
   if s:s=validate_settings(s)
   root=owned_directory(self.owner.state_root,s.get('sourceDirectory'));root.mkdir(parents=True,exist_ok=True,mode=0o700);atomic_json(root/'preferences.json',{'version':2,'mode':mode,'source':s})
  except (OSError,ValueError,TypeError) as e:self.error.set_text(str(e));return
  o=self.owner;o.source_mode=mode;o.settings=s;o.book=ConsentBook(o.state_root,s.get('sourceDirectory'));o.last_export=None;o.source_editor=None;o.render({});o.message.set_text('บันทึกการตั้งค่าจริงแล้ว — ยังไม่เริ่มงาน');self.destroy()

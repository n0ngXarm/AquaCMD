"""Validate explicit actual-use profiles. No service, probe or source reads."""
import copy,hashlib,ipaddress,json,os,pathlib,re
from urllib.parse import urlsplit
from model import valid_tags,owned_directory,atomic_json

def private_ip(value):
 try:
  ip=ipaddress.IPv4Address(value)
  return str(ip)==value and (ip.is_loopback or any(ip in ipaddress.ip_network(n) for n in ('10.0.0.0/8','172.16.0.0/12','192.168.0.0/16')))
 except (ValueError,TypeError):return False

def required_file(value):
 if not isinstance(value,str) or not pathlib.Path(value).is_file():raise ValueError('เลือกไฟล์ certificate / key ที่มีอยู่แล้ว โปรแกรมไม่สร้างหรือเปิดบริการให้เอง')
 return str(pathlib.Path(value).resolve())

def validate_settings(settings):
 s=copy.deepcopy(settings)
 if not isinstance(s,dict) or set(s)-{'deployment','sourceDirectory','tags','timezoneOffset','mappingConfirmed'}:raise ValueError('การตั้งค่าไม่รองรับ')
 d=s.get('deployment')
 if not isinstance(d,dict) or d.get('role') not in ('agent','gateway'):raise ValueError('ต้องเลือกบทบาทจริง Agent หรือ Gateway')
 role=d['role'];allowed={'role','id','listenHost','listenPort'}|({'gatewayUrl','gatewaySecret','caFile'} if role=='agent' else {'certFile','keyFile','peers','telegramMode'})
 if set(d)-allowed:raise ValueError('ไม่รองรับ field หรือโหมดจำลองในการตั้งค่านี้')
 if not private_ip(d.get('listenHost')) or role=='agent' and d['listenHost']!='127.0.0.1':raise ValueError('Agent ควบคุมเฉพาะเครื่องนี้; Gateway ต้องระบุ private IP ชัดเจน ไม่ใช้ wildcard')
 if type(d.get('listenPort')) is not int or not 1024<=d['listenPort']<=65400:raise ValueError('พอร์ตต้องอยู่ระหว่าง1024–65400')
 def key(v):return isinstance(v,str) and re.fullmatch('[a-f0-9]{64}',v)
 if role=='gateway':
  if d.get('id')!='PC-04' or d.get('telegramMode') not in ('dry-run','telegram'):raise ValueError('Gateway identity / notification mode ไม่ถูกต้อง')
  if set(s)!={'deployment'}:raise ValueError('Gateway ไม่อ่าน source บนเครื่องนี้')
  peers=d.get('peers')
  if not isinstance(peers,dict) or not peers or any(i not in ('PC-01','PC-02','PC-03') or not key(k) for i,k in peers.items()) or len(set(peers.values()))!=len(peers):raise ValueError('ระบุคีย์แยกกัน64ตัวอักษรสำหรับแต่ละเครื่องที่อนุญาต')
  d['certFile']=required_file(d.get('certFile'));d['keyFile']=required_file(d.get('keyFile'))
 else:
  if d.get('id') not in ('PC-01','PC-02','PC-03') or not key(d.get('gatewaySecret')):raise ValueError('Agent ID / คีย์เครื่องรับไม่ถูกต้อง')
  try:
   u=urlsplit(d.get('gatewayUrl',''));valid=u.scheme=='https' and private_ip(u.hostname) and u.path in ('','/') and not(u.username or u.password or u.query or u.fragment) and u.port is not None and 1024<=u.port<=65400
  except (ValueError,TypeError):valid=False
  if not valid:raise ValueError('เครื่องรับต้องเป็น HTTPS private IPv4 พร้อมพอร์ต ไม่มี user/password หรือ path')
  if d.get('caFile'):d['caFile']=required_file(d['caFile'])
  else:d.pop('caFile',None)
  source=s.get('sourceDirectory')
  if not isinstance(source,str) or not pathlib.Path(source).is_dir():raise ValueError('ต้องเลือกโฟลเดอร์ Runtime CSV จริง ไม่มี LAB fallback')
  s['sourceDirectory']=str(pathlib.Path(source).resolve());valid_tags(s.get('tags'))
  if not re.fullmatch(r'[+-](?:0\d|1[0-3]):[0-5]\d|[+-]14:00',s.get('timezoneOffset','+07:00')):raise ValueError('เขตเวลาไม่ถูกต้อง')
  if type(s.get('mappingConfirmed')) is not bool:raise ValueError('ต้องตรวจ mapping ของ Tag ก่อน')
 return s

def permission_material(settings):
 d=settings.get('deployment',{});material={'settings':settings,'files':{}}
 for k in ('caFile','certFile','keyFile'):
  if d.get(k):
   try:material['files'][k]=hashlib.sha256(pathlib.Path(d[k]).read_bytes()).hexdigest()
   except OSError:material['files'][k]='UNAVAILABLE'
 if d.get('telegramMode')=='telegram':material['telegram']=hashlib.sha256(json.dumps({k:os.environ.get(k,'') for k in ('TELEGRAM_BOT_TOKEN','TELEGRAM_CHAT_ID','TELEGRAM_APPROVED_ENDPOINT')},sort_keys=True).encode()).hexdigest()
 return material

def prepare_actual_profile(state_root,settings):
 s=validate_settings(settings);root=owned_directory(state_root,s.get('sourceDirectory'))
 # Network changes retain the same source/archive dataset; consent changes separately.
 identity={'role':s['deployment']['role'],'id':s['deployment']['id']}
 fingerprint=hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:20]
 root.mkdir(parents=True,exist_ok=True,mode=0o700);config=root/('actual-'+fingerprint+'.json');atomic_json(config,s)
 return {'config':config,'data':root/'actual-profiles'/fingerprint,'settings':s}

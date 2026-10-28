"""Actual native deployment/Windows-Core HTTPS interop. Synthetic inputs ONLY in test project."""
import argparse,json,pathlib,tempfile,time,sys,subprocess,os
import gi
gi.require_version('Gtk','4.0')
from gi.repository import Gtk,GLib
p=argparse.ArgumentParser();p.add_argument('--dotnet',required=True);p.add_argument('--core-tests',required=True);p.add_argument('--out',required=True);p.add_argument('--installed-root');p.add_argument('--width',type=int,default=1440);p.add_argument('--height',type=int,default=900);p.add_argument('--scale',type=float,default=1);args=p.parse_args()
if args.installed_root:sys.path.insert(0,str(pathlib.Path(args.installed_root)/'desktop'))
from app import AquaApplication,AquaWindow
from actual_editor import ActualEditor
if args.scale!=1:Gtk.Settings.get_default().set_property('gtk-xft-dpi',int(96*1024*args.scale))
ctx=GLib.MainContext.default();out=pathlib.Path(args.out);out.mkdir(parents=True,exist_ok=True)
def spin(t=.2):
 end=time.monotonic()+t
 while time.monotonic()<end:
  while ctx.pending():ctx.iteration(False)
  time.sleep(.01)
def wait(fn,t=20):
 end=time.monotonic()+t
 while time.monotonic()<end:
  spin(.03)
  if fn():return
 raise AssertionError('Actual native/interop test timeout')
def snap(w,name):
 paint=Gtk.WidgetPaintable.new(w);nodes=[]
 def render():
  s=Gtk.Snapshot();paint.snapshot(s,w.get_width(),w.get_height());n=s.to_node()
  if n is not None:nodes.append(n);return True
  return False
 wait(render,5);assert w.get_renderer().render_texture(nodes[-1],None).save_to_png(str(out/name))
with tempfile.TemporaryDirectory(prefix='aqua-actual-native-') as temp:
 root=pathlib.Path(temp);cert=root/'cert.pem';key=root/'key.pem';state=root/'state';port=31474
 subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-keyout',str(key),'-out',str(cert),'-days','1','-subj','/CN=AQUA test-only','-addext','subjectAltName=IP:127.0.0.1'],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 app=AquaApplication(state,31473);app.register(None);w=AquaWindow(app,state,31473);w.set_default_size(args.width,args.height);w.set_size_request(args.width,args.height);w.present()
 try:
  spin(.5);assert (w.get_width(),w.get_height())==(args.width,args.height);assert w.client is None and not state.exists();assert w.source_mode=='runtime';assert not w.start_button.get_sensitive();snap(w,'actual-idle.png')
  w.source_dialog(None);ed=w.source_editor;assert isinstance(ed,ActualEditor);assert ed.mode.get_model().get_n_items()==3,'Normal installation exposes no LAB mode';ed.mode.set_selected(2);spin();ed.fields['listenHost'].set_text('127.0.0.1');ed.fields['listenPort'].set_text(str(port));ed.fields['certFile'].set_text(str(cert));ed.fields['keyFile'].set_text(str(key));ed.fields['PC-01'].set_text('a'*64);snap(ed,'actual-setup.png');ed.save_button.emit('clicked');spin();assert w.source_mode=='gateway' and w.client is None;assert not (state/'actual-profiles').exists();assert (state/'preferences.json').stat().st_mode&0o777==0o600
  w.start_button.emit('clicked');assert w.consent_dialog;w.consent_dialog.cancel_button.emit('clicked');spin();assert w.client is None
  w.start_button.emit('clicked');w.consent_dialog.approve_button.emit('clicked');wait(lambda:w.status.get('gateway',{}).get('receiveAllowed') is True);assert w.status['transferAllowed'] is False;assert w.status['gateway']['egress']['checkedAt'] is None;snap(w,'actual-gateway-ready.png')
  proc=subprocess.Popen([args.dotnet,args.core_tests,'--interop',f'https://127.0.0.1:{port}',str(cert),'a'*64],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
  wait(lambda:proc.poll() is not None,30);stdout,stderr=proc.communicate();assert proc.returncode==0,(stdout,stderr);(out/'core-interop.txt').write_text(stdout+stderr)
  wait(lambda:len(w.console.last_model['signals'])==1);m=w.console.last_model;r=m['signals'][0];assert r['mode']=='OPC_DA' and r['raw']==1 and r['state']=='ON' and r['quality_code']==192;assert r['read_at']!='Not reported' and r['source_timestamp']=='2020-01-01T07:00:00+07:00',json.dumps({'signal':r,'remoteSources':w.status.get('remoteSources')});assert m['metrics']['gateway']['value']==3 and m['metrics']['snapshots']['value']==2;assert all(d['id']!='CENTRAL-LAB' for d in m['devices']);assert m['metrics']['central']['value'] is None;assert w.status['transferAllowed'] is False;assert w.status['gateway']['egress']['checkedAt'] is None
  for page in ('overview','network','sources','items','values','delivery','logs'):
   w.pages.set_visible_child_name(page);spin(.15)
   for c in (w.page_title,w.mode,w.pages,w.start_button,w.export_button):
    ok,b=c.compute_bounds(w);assert ok and b.get_x()>=0 and b.get_y()>=0 and b.get_x()+b.get_width()<=w.get_width()+1 and b.get_y()+b.get_height()<=w.get_height()+1,(page,c.get_name())
   snap(w,'actual-'+page+'.png')
  w.console.select_signal(r['key']);spin();assert 'OPC source timestamp:' in w.console.signal_detail.get_text()
  w.export_button.emit('clicked');wait(lambda:w.last_export is not None);data=w.last_export.read_text();assert 'source_timestamp' in data and ';192;' in data
  w.send_button.emit('clicked');assert w.consent_dialog;w.consent_dialog.cancel_button.emit('clicked');spin();assert w.status['transferAllowed'] is False
  process=w.client.process;w.end_button.emit('clicked');wait(lambda:w.client is None and not w.switching and process.poll() is not None)
  w2=AquaWindow(app,state,31473);w2.present();spin(.4);assert w2.source_mode=='gateway' and w2.client is None;w2.close();spin()
  (out/'actual-native-results.json').write_text(json.dumps({'result':'PASS','actualSize':[w.get_width(),w.get_height()],'fontScale':args.scale,'titlePixelHeight':w.page_title.get_layout().get_pixel_size()[1],'noNormalLabMode':True,'idleNoWorker':True,'cancelNoWorker':True,'actualGatewayTLS':True,'windowsCoreInterop':'TLS/HMAC/ACK3events','separateReceiveAndEgress':True,'noEgressBeforeApproval':True,'rawQualityAndTimesPreserved':True,'receivedNotFakeAgentReachability':True,'noInventedCentral':True,'csvExport':True,'relaunchIdle':True,'inputEvidence':'Synthetic observations confined to Tests project; no actual Windows/WinCC/physicalLAN assertion'},indent=2));print('PASS actual native Gateway + Windows Core TLS interop (test-only observations)',flush=True)
 finally:
  process=w.client.process if w.client else None;w.close();wait(lambda:process is None or process.poll() is not None);spin()

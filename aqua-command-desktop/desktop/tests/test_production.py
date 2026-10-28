import unittest,tempfile,pathlib,sys,json,datetime
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
from production import validate_settings,prepare_actual_profile,permission_material
from presentation import console_state
class ActualProfileTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=pathlib.Path(self.tmp.name);self.source=self.root/'input';self.source.mkdir();self.cert=self.root/'cert.pem';self.cert.write_text('public-cert');self.key=self.root/'key.pem';self.key.write_text('private-key')
 def tearDown(self):self.tmp.cleanup()
 def gateway(self):return {'deployment':{'role':'gateway','id':'PC-04','listenHost':'127.0.0.1','listenPort':4174,'certFile':str(self.cert),'keyFile':str(self.key),'peers':{'PC-01':'a'*64},'telegramMode':'dry-run'}}
 def agent(self):return {'sourceDirectory':str(self.source),'tags':['PUMP.RUN_S'],'timezoneOffset':'+07:00','mappingConfirmed':True,'deployment':{'role':'agent','id':'PC-01','listenHost':'127.0.0.1','listenPort':4181,'gatewayUrl':'https://192.168.50.20:4174','gatewaySecret':'a'*64,'caFile':str(self.cert)}}
 def test_validation_prepares_no_runtime_and_rejects_unsafe_modes(self):
  before=list(self.root.iterdir());validate_settings(self.agent());self.assertEqual(before,list(self.root.iterdir()))
  for patch in ({'gatewayUrl':'http://192.168.50.20:4174'},{'gatewayUrl':'https://example.com:4174'},{'listenHost':'0.0.0.0'},{'gatewaySecret':'short'},{'fixture':True}):
   s=self.agent();s['deployment'].update(patch)
   with self.assertRaises(ValueError):validate_settings(s)
 def test_real_profile_is_private_and_never_creates_fixture(self):
  state=self.root/'state';p=prepare_actual_profile(state,self.gateway());self.assertFalse(p['data'].exists());self.assertEqual(json.loads(p['config'].read_text())['deployment']['role'],'gateway');self.assertEqual(p['config'].stat().st_mode&0o777,0o600)
 def test_tag_and_source_changes_preserve_source_dataset_identity(self):
  state=self.root/'state';s=self.agent();a=prepare_actual_profile(state,s);s['tags']=['OTHER.RUN_S'];b=prepare_actual_profile(state,s);self.assertEqual(a['data'],b['data'])
  other=self.root/'other';other.mkdir();s['sourceDirectory']=str(other);c=prepare_actual_profile(state,s);self.assertEqual(a['data'],c['data'])
 def test_source_storage_overlap_rejected_without_source_writes(self):
  before=list(self.source.iterdir())
  with self.assertRaises(ValueError):prepare_actual_profile(self.source/'state',self.agent())
  self.assertEqual(before,list(self.source.iterdir()))
 def test_certificate_change_invalidates_permission_material(self):
  s=self.gateway();before=permission_material(s);self.cert.write_text('rotated-cert');self.assertNotEqual(before,permission_material(s))
 def test_no_lab_fallback_for_missing_real_csv(self):
  s=self.agent();s.pop('sourceDirectory')
  with self.assertRaises(ValueError):validate_settings(s)
class ActualBindingTests(unittest.TestCase):
 def test_gateway_received_values_are_not_reported_as_live_agent_or_lab(self):
  t='2026-10-28T14:00:00Z';s={'deployment':{'role':'gateway','id':'PC-04','listenHost':'192.168.50.20','listenPort':4174,'peerIds':['PC-01']},'captureAllowed':True,'gateway':{'id':'PC-04','online':True,'lastSeen':t,'archiveCount':2,'received':2},'remoteSources':[{'id':'PC-01','sourceAdapter':'wincc-opc-da','simulated':False,'observedAt':t,'readAt':t,'lastExport':t,'lastReceivedAt':t,'pumps':{'PUMP.RUN_S':False},'observations':{'PUMP.RUN_S':{'raw_value':0,'quality_code':192,'read_error':0,'quality':'GOOD','source_timestamp':'2026-10-27T01:00:00Z'}}}]}
  v=console_state(s,'gateway',{'deployment':s['deployment']},4173,True,datetime.datetime(2026,10,28,14,0,2,tzinfo=datetime.timezone.utc));self.assertEqual(v['signals'][0]['mode'],'OPC_DA');self.assertEqual(v['signals'][0]['state'],'OFF');self.assertEqual(v['signals'][0]['source_timestamp'],'2026-10-27T08:00:00+07:00');self.assertFalse(any(d['id']=='CENTRAL-LAB' for d in v['devices']));self.assertNotIn('SIMULATED',v['reading_modes']);self.assertEqual(v['metrics']['gateway']['value'],2)

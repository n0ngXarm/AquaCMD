using Aqua.Reader.Core;
using Aqua.Reader.Tests;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;

static class Tests {
 static int passed;
 static void Check(bool value,string name){if(!value)throw new Exception(name);passed++;}
 static void Reject(Action action,string name){try{action();}catch{passed++;return;}throw new Exception(name);}
 static ReadFrame Frame(long? value=0,uint? quality=192,int error=0)=>new(DateTimeOffset.UtcNow.ToString("O"),[new("RUN_S",value,quality,error,DateTimeOffset.UtcNow.ToString("O"))]);
 static async Task<int> Main(string[] args){
  var path=Path.Combine(Path.GetTempPath(),"aqua-reader-tests-"+Guid.NewGuid());Directory.CreateDirectory(path);
  try{
   var config=new ReaderConfig{SourceId="PC-01",Tags=["RUN_S"],MappingConfirmed=true,GatewayUrl="https://127.0.0.1:4174",Secret=new string('a',64)};
   if(args.Length>0&&args[0]=="--emit-test-events"){
    using var store=new DurableSpool(path,config.ProfileId());store.Append(config,Frame());store.Append(config,Frame(1));Directory.CreateDirectory(args[1]);File.WriteAllText(Path.Combine(args[1],"events.json"),"["+string.Join(",",store.Pending().Select(r=>r.Payload))+"]");Console.WriteLine("TEST-ONLY synthetic observations emitted by Tests project");return 0;
   }
   if(args.Length==4&&args[0]=="--interop-analog"){
    config.GatewayUrl=args[1];config.CaFile=args[2];config.Secret=args[3];
    var levels=new Dictionary<string,double>{
     ["LEVEL"]=73.25,["ZERO"]=-0.0,["SMALL"]=1e-7,["FIXED_MIN"]=1e-6,["LARGE"]=1e21,
     ["FIXED_MAX"]=1e20,["NEGATIVE"]=-0.25,["DOUBLE_MAX"]=double.MaxValue,["SUBNORMAL"]=double.Epsilon
    };
    config.AnalogTags=levels.Keys.ToList();
    config.Tags.AddRange(config.AnalogTags);
    using var store=new DurableSpool(path,config.ProfileId());
    ReadFrame Mixed(double pump)=>new(Wire.Stamp(),[
     new("RUN_S",pump,192,0,"2026-10-28T01:00:00.000Z"),
     ..levels.Select(level=>new Observation(level.Key,level.Value,192,0,"2026-10-28T01:00:01.000Z"))
    ]);
    store.Append(config,Mixed(0));store.Append(config,Mixed(1));
    using var sender=new AquaSender(config);
    Check(await sender.SendBatchAsync(store,CancellationToken.None)==3&&store.PendingCount==0,
     "Signed mixed snapshots and binary transition accepted with exact digest ACKs");
    Console.WriteLine("PASS Analog TLS/HMAC/ACK interoperability");
    return 0;
   }
   if(args.Length==4&&(args[0]=="--interop"||args[0]=="--interop-numeric")){
    config.GatewayUrl=args[1];config.CaFile=args[2];config.Secret=args[3];if(args[0]=="--interop-numeric")config.Tags=["20","3","RUN_S"];ReadFrame InteropFrame(long state)=>new(Wire.Stamp(),config.Tags.Select(t=>new Observation(t,t=="RUN_S"?state:0,192,0,"2020-01-01T00:00:00Z")).ToList());using var store=new DurableSpool(path,config.ProfileId());store.Append(config,InteropFrame(0));store.Append(config,InteropFrame(1));using var sender=new AquaSender(config);var sent=await sender.SendBatchAsync(store,CancellationToken.None);Check(sent==3&&store.Pending().Count==0,"Actual HTTPS signed handshake/event/ACK integration");Console.WriteLine("PASS actual TLS/HMAC/ACK integration; TEST-ONLY observations; real WinCC not tested");return 0;
   }
   config.ValidateCapture();Reject(()=>new ReaderConfig{Tags=["__proto__"]}.ValidateCapture(),"unsafe Tag rejected");Reject(()=>new ReaderConfig{Tags=["RUN_S","RUN_S"]}.ValidateCapture(),"duplicate rejected");
   Reject(()=>new ReaderConfig{GatewayUrl="http://192.168.1.20:4174",Secret=new string('a',64)}.ValidateTransfer(),"insecure LAN rejected");Reject(()=>new ReaderConfig{GatewayUrl="https://example.com",Secret=new string('a',64)}.ValidateTransfer(),"public DNS rejected");
   var original=path;
   using(var store=new DurableSpool(path,config.ProfileId())){
    Reject(()=>new DurableSpool(path,config.ProfileId()),"single owner lock");store.Append(config,Frame());Check(store.Pending().Count==1,"initial read only snapshot");store.Append(config,Frame(1));Check(store.Pending().Count==3,"snapshot+transition");
    var records=store.Pending();var raw=records[0].Payload;using var doc=JsonDocument.Parse(raw);Check(doc.RootElement.GetProperty("source_adapter").GetString()=="wincc-opc-da"&&!doc.RootElement.GetProperty("simulated").GetBoolean(),"real provenance");Check(doc.RootElement.GetProperty("observations").GetProperty("RUN_S").GetProperty("quality_code").GetInt32()==192,"raw OPC quality preserved");
    Reject(()=>store.Acknowledge([new(records[0].Id,new string('0',64))]),"wrong ACK retained");Check(store.Pending().Count==3,"wrong ACK no removal");store.Acknowledge(records.Select(r=>new Ack(r.Id,r.Digest)).ToList());Check(store.Pending().Count==0&&store.Sequence==3,"exact ACK removes pending");
    store.Append(config,Frame(0,0));store.Append(config,Frame(1));Check(store.Pending().Count==2,"bad breaks transition continuity");store.Append(config,Frame(0,64));Check(store.Latest!.Observations[0].State(true)==null,"uncertain never OFF");
    var exported=Path.Combine(path,"pending.csv");store.ExportCsv(exported);Check(File.ReadAllText(exported).StartsWith("event_id;sequence;kind;read_at;"),"owned pending CSV export works");var exportedHash=Wire.Hash(File.ReadAllText(exported));Reject(()=>store.ExportCsv(exported),"CSV cannot overwrite an existing file");Check(Wire.Hash(File.ReadAllText(exported))==exportedHash,"existing export unchanged");var outside=path+"-input.csv";File.WriteAllText(outside,"untouched source");try{Reject(()=>store.ExportCsv(outside),"outside source export rejected");Check(File.ReadAllText(outside)=="untouched source","outside input remains byte identical");}finally{File.Delete(outside);}
    var seq=store.Sequence;using var reopenedMarker=new MemoryStream();store.PinDestination("first");Reject(()=>store.PinDestination("other"),"destination immutable while pending");Check(store.Sequence==seq,"pin does not advance seq");
   }
   using(var store=new DurableSpool(path,config.ProfileId())){Check(store.Sequence==6&&store.Pending().Count==3,"restart sequence/backlog");Reject(()=>store.Append(config,new ReadFrame(DateTimeOffset.UtcNow.ToString("O"),[])),"incomplete frame rejected");}
   Reject(()=>new DurableSpool(path,"wrong-profile"),"profile collision denied");
   Check(Frame(0,128).Observations[0].State(true)==null,"WinCC128 is not OPC GOOD");Check(Frame(0).Observations[0].State(true)==false,"RAW0 valid OFF");Check(Frame(1).Observations[0].State(false)==null,"mapping consent required");Check(Frame(2).Observations[0].State(true)==null,"nonbinary unknown");
   var analogConfig=new ReaderConfig{Tags=["LEVEL","RUN_S"],AnalogTags=["LEVEL"],MappingConfirmed=true};
   analogConfig.ValidateCapture();
   Reject(()=>new ReaderConfig{Tags=["RUN_S"],AnalogTags=["LEVEL"]}.ValidateCapture(),"unlisted Analog Tag rejected");
   Check(OpcScalar.FromVariant(73.25f,true)==73.25d&&OpcScalar.FromVariant(-2.5m,true)==-2.5d,"floating and decimal COM scalars");
   Check(OpcScalar.FromVariant(true,true)==null&&OpcScalar.FromVariant("1",true)==null&&
         OpcScalar.FromVariant(new[]{1},true)==null&&OpcScalar.FromVariant(double.NaN,true)==null&&
         OpcScalar.FromVariant(double.PositiveInfinity,true)==null&&OpcScalar.FromVariant(ulong.MaxValue,true)==null,
         "unsupported Analog scalars never become a number");
   Check(OpcScalar.FromVariant(false,false)==0&&OpcScalar.FromVariant(1.0000000000000002d,false)==null,
         "binary converter accepts false and rejects fractions near one");
   var level=new Observation("LEVEL",73.25,192,0,"2026-10-28T01:00:01.000Z");
   Check(level.Quality(false,true)=="GOOD"&&level.State(true,true)==null,"Analog quality is separate from pump mapping");
   Check((level with {QualityCode=64}).Quality(true,true)=="UNCERTAIN"&&
         (level with {ReadError=-1}).Quality(true,true)=="BAD"&&
         (level with {RawValue=null}).Quality(true,true)=="UNSUPPORTED_VALUE","Analog quality failures");
   var mixed=new ReadFrame(Wire.Stamp(),[level,new("RUN_S",1,192,0,null)]);
   var analogPath=Path.Combine(path,"analog");
   using(var analogStore=new DurableSpool(analogPath,analogConfig.ProfileId())){
    analogStore.Append(analogConfig,mixed);
    analogStore.Append(analogConfig,mixed with {Observations=[level with {RawValue=0},new("RUN_S",0,192,0,null)]});
    Check(analogStore.PendingCount==3,"Analog change emits no state transition while binary change emits one");
    using var body=JsonDocument.Parse(analogStore.Pending()[0].Payload);
    var sample=body.RootElement.GetProperty("observations").GetProperty("LEVEL");
    Check(sample.GetProperty("raw_value").GetDouble()==73.25&&sample.GetProperty("value_type").GetString()=="analog"&&
          sample.GetProperty("source_timestamp").GetString()==level.SourceTimestamp,"wire preserves value, type and source time");
    Check(body.RootElement.GetProperty("values").GetProperty("LEVEL").ValueKind==JsonValueKind.Null,
          "Analog never goes into the pump state map");
   }
   using(var analogStore=new DurableSpool(analogPath,analogConfig.ProfileId())){
    Check(analogStore.Latest!.Observations[0].RawValue==0&&analogStore.PendingCount==3,"Analog queue reopens");
    Check(analogConfig.CaptureRevision()!=new ReaderConfig{Tags=analogConfig.Tags,MappingConfirmed=true}.CaptureRevision(),
          "Changing Tag type changes capture revision");
   }
   Check(Wire.Encode(new[]{-0.0,1e-6,1e-7,1e20,1e21,-73.25})==
         "[0,0.000001,1e-7,100000000000000000000,1e+21,-73.25]","Gateway JSON number notation boundaries");
   var quotaPath=path+"-quota";try{using var q=new DurableSpool(quotaPath,config.ProfileId(),maxPending:1);q.Append(config,Frame());Reject(()=>q.Append(config,Frame(1)),"quota must retain prior state");Check(q.Sequence==1&&q.Pending().Count==1,"quota atomic");}finally{Directory.Delete(quotaPath,true);}
   foreach(var mode in new[]{"mac","digest","partial","duplicate"}){
    var faultPath=path+"-"+mode;try{using var fault=new DurableSpool(faultPath,config.ProfileId());fault.Append(config,Frame());fault.Append(config,Frame(1));using var sender=new AquaSender(config,new HttpClient(new FakeGateway(config.Secret,mode)));try{await sender.SendBatchAsync(fault,CancellationToken.None);throw new Exception("Fault accepted");}catch(InvalidOperationException){Check(fault.PendingCount==3,"bad "+mode+" retains entire batch");}}finally{Directory.Delete(faultPath,true);}
   }
   var largeConfig=new ReaderConfig{SourceId="PC-01",Tags=Enumerable.Range(0,100).Select(n=>"TAG_"+n.ToString("D3")+new string('A',90)).ToList(),MappingConfirmed=true,GatewayUrl=config.GatewayUrl,Secret=config.Secret};var bigPath=path+"-big";
   try{using var big=new DurableSpool(bigPath,largeConfig.ProfileId());for(var n=0;n<35;n++)big.Append(largeConfig,new ReadFrame(Wire.Stamp(),largeConfig.Tags.Select(t=>new Observation(t,0,192,0,null)).ToList()));var handler=new FakeGateway(config.Secret);using var sender=new AquaSender(largeConfig,new HttpClient(handler));await sender.SendBatchAsync(big,CancellationToken.None);Check(handler.LastBatchCount is >0 and <32,"large valid backlog uses bounded prefix");Check(big.PendingCount>0,"large backlog remainder retained");}finally{Directory.Delete(bigPath,true);}
   var stallPath=path+"-stall";try{using var stalled=new DurableSpool(stallPath,config.ProfileId());stalled.Append(config,Frame());using var sender=new AquaSender(config,new HttpClient(new FakeGateway(config.Secret,"stall-once")));var watch=System.Diagnostics.Stopwatch.StartNew();try{await sender.SendBatchAsync(stalled,CancellationToken.None);throw new Exception("Stalled response accepted");}catch(TimeoutException){Check(watch.Elapsed<TimeSpan.FromSeconds(11)&&stalled.PendingCount==1,"body deadline is retryable timeout and retains queue");}Check(await sender.SendBatchAsync(stalled,CancellationToken.None)==1&&stalled.PendingCount==0,"approved session can retry after request timeout");}finally{Directory.Delete(stallPath,true);}
   var cancelPath=path+"-cancel";try{using var stopped=new DurableSpool(cancelPath,config.ProfileId());stopped.Append(config,Frame());using var sender=new AquaSender(config,new HttpClient(new FakeGateway(config.Secret,"stall")));using var cancel=new CancellationTokenSource(50);try{await sender.SendBatchAsync(stopped,cancel.Token);throw new Exception("Cancellation ignored");}catch(OperationCanceledException){Check(stopped.PendingCount==1,"operator cancellation remains cancellation and retains queue");}}finally{Directory.Delete(cancelPath,true);}
   var numericConfig=new ReaderConfig{Tags=["20","3","4294967295","03","RUN_S","4294967294"],MappingConfirmed=true};var numericFrame=new ReadFrame(Wire.Stamp(),numericConfig.Tags.Select(t=>new Observation(t,0,192,0,null)).ToList());var numericEvent=Events.Build(numericConfig,numericFrame,new SpoolState()).Single();using(var numericJson=JsonDocument.Parse(numericEvent.Payload)){var expected=new[]{"3","20","4294967294","4294967295","03","RUN_S"};Check(numericJson.RootElement.GetProperty("values").EnumerateObject().Select(p=>p.Name).SequenceEqual(expected)&&numericJson.RootElement.GetProperty("observations").EnumerateObject().Select(p=>p.Name).SequenceEqual(expected),"JS array-index ordering matches Node even at uint32 boundary");}
   var revisionPath=path+"-revision";try{
    var changed=new ReaderConfig{SourceId=config.SourceId,Tags=["RUN_S"],MappingConfirmed=false,GatewayUrl=config.GatewayUrl,Secret=config.Secret};Check(changed.ProfileId()==config.ProfileId()&&changed.CaptureRevision()!=config.CaptureRevision(),"mapping keeps source stream but changes capture revision");
    using(var changing=new DurableSpool(revisionPath,config.ProfileId())){changing.Append(config,Frame(0));var first=changing.Pending().Single();changing.Append(changed,Frame(1));Check(changing.Sequence==2&&changing.PendingCount==2&&changing.Pending()[0].Payload==first.Payload,"mapping change preserves pending+sequence and no fabricated transition");changing.Acknowledge(changing.Pending().Select(r=>new Ack(r.Id,r.Digest)).ToList());}
    var tagChange=new ReaderConfig{SourceId=config.SourceId,Tags=["OTHER_RUN_S"],MappingConfirmed=true};using(var changing=new DurableSpool(revisionPath,tagChange.ProfileId())){changing.Append(tagChange,new ReadFrame(Wire.Stamp(),[new Observation("OTHER_RUN_S",1,192,0,null)]));Check(changing.Sequence==3&&changing.PendingCount==1,"tag change after ACK/restart advances same sequence");changing.Append(config,Frame(1));Check(changing.Sequence==4&&changing.PendingCount==2,"returning tag selection resets continuity and retains prior queue");changing.Append(config,Frame(0));Check(changing.Sequence==6,"within unchanged revision transitions still emit");}
   }finally{Directory.Delete(revisionPath,true);}
   File.WriteAllText(Path.Combine(path,"state.json"),"corrupt");Reject(()=>new DurableSpool(path,config.ProfileId()),"corruption fails closed");
   var signature=Wire.Sign(new string('a',64),"hello");Check(signature==Convert.ToHexStringLower(HMACSHA256.HashData(Encoding.UTF8.GetBytes(new string('a',64)),Encoding.UTF8.GetBytes("hello"))),"literal UTF8 secret not hex decoded");
   Console.WriteLine($"PASS {passed} core assertions; test doubles only in Tests project");return 0;
  }finally{Directory.Delete(path,true);}
 }
}

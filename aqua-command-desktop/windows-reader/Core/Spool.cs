using System.Text.Json;
namespace Aqua.Reader.Core;

/// <summary>One locked state document: sequence, previous values and pending records commit together.</summary>
public sealed class DurableSpool:IDisposable {
 readonly string directory,file;readonly FileStream ownership;readonly int maxPending;readonly long maxBytes;readonly object gate=new();SpoolState state;
 public DurableSpool(string directory,string profileId,int maxPending=10000,long maxBytes=64*1024*1024){
  this.directory=Path.GetFullPath(directory);this.file=Path.Combine(this.directory,"state.json");this.maxPending=maxPending;this.maxBytes=maxBytes;
  if(maxPending<1||maxBytes<1024)throw new ArgumentOutOfRangeException(nameof(maxPending));
  for(var p=new DirectoryInfo(this.directory);p is not null;p=p.Parent)if(p.Exists&&(p.Attributes&FileAttributes.ReparsePoint)!=0)throw new InvalidOperationException("AQUA storage cannot traverse a link/reparse point");
  Directory.CreateDirectory(this.directory);ownership=new FileStream(Path.Combine(this.directory,"owner.lock"),FileMode.OpenOrCreate,FileAccess.ReadWrite,FileShare.None);
  try{
   if(File.Exists(file)){var info=new FileInfo(file);if((info.Attributes&FileAttributes.ReparsePoint)!=0||info.Length>maxBytes)throw new InvalidOperationException("Invalid/oversized spool; existing data retained");state=JsonSerializer.Deserialize<SpoolState>(File.ReadAllText(file),Wire.Json)??throw new InvalidOperationException("Missing spool document");Validate(profileId);}
   else state=new SpoolState{ProfileId=profileId};
  }catch{ownership.Dispose();throw;}
 }
 void Validate(string profile){
  if(state.Version!=1||state.ProfileId!=profile||state.Sequence<0||state.Sequence>9007199254740991L||state.Pending is null||state.Previous is null||state.Pending.Count>maxPending||state.Acked<0||state.Snapshots<0)throw new InvalidOperationException("Spool identity or metadata mismatch; no reset performed");
  long previous=0;var ids=new HashSet<string>();
  foreach(var r in state.Pending){using var document=JsonDocument.Parse(r.Payload);var e=document.RootElement;if(r.Sequence<=previous||r.Sequence>state.Sequence||!ids.Add(r.Id)||r.Digest!=Wire.Hash(r.Payload)||e.GetProperty("sequence").GetInt64()!=r.Sequence||e.GetProperty("event_id").GetString()!=r.Id||e.GetProperty("schema").GetString()!="aqua.runtime.v3"||e.GetProperty("simulated").GetBoolean())throw new InvalidOperationException("Corrupt pending record; data retained");previous=r.Sequence;}
 }
 SpoolState Copy()=>JsonSerializer.Deserialize<SpoolState>(Wire.Encode(state),Wire.Json)!;
 void Commit(SpoolState next){
  var raw=System.Text.Encoding.UTF8.GetBytes(Wire.Encode(next));if(raw.Length>maxBytes)throw new InvalidOperationException("Local spool byte quota reached; pending records retained");
  var temporary=Path.Combine(directory,".commit-"+Guid.NewGuid()+".tmp");
  try{using(var output=new FileStream(temporary,FileMode.CreateNew,FileAccess.Write,FileShare.None,4096,FileOptions.WriteThrough)){output.Write(raw);output.Flush(true);}File.Move(temporary,file,true);state=next;}finally{if(File.Exists(temporary))File.Delete(temporary);}
 }
 public long Sequence{get{lock(gate)return state.Sequence;}}
 public long Snapshots{get{lock(gate)return state.Snapshots;}}
 public long Acked{get{lock(gate)return state.Acked;}}
 public ReadFrame? Latest{get{lock(gate)return state.Latest;}}
 public IReadOnlyList<PendingRecord> Pending(int limit=32){lock(gate)return state.Pending.Take(limit).ToList();}
 public int PendingCount{get{lock(gate)return state.Pending.Count;}}
 public void Append(ReaderConfig config,ReadFrame frame){lock(gate){if(state.ProfileId!=config.ProfileId())throw new InvalidOperationException("Profile changed; close active session first");var revision=config.CaptureRevision();var basis=Copy();if(basis.CaptureRevision!=revision)basis.Previous.Clear();var records=Events.Build(config,frame,basis);if(state.Pending.Count+records.Count>maxPending)throw new InvalidOperationException("Pending quota reached; no records or previous values discarded");var next=Copy();next.CaptureRevision=revision;next.Pending.AddRange(records);next.Sequence=records[^1].Sequence;next.Snapshots++;next.Previous=frame.Observations.ToDictionary(o=>o.Tag,o=>o.State(config.MappingConfirmed,config.IsAnalog(o.Tag)));next.Latest=frame;Commit(next);}}
 public void PinDestination(string pin){lock(gate){if(state.DestinationPin==pin)return;if(state.DestinationPin is not null&&state.Pending.Count>0)throw new InvalidOperationException("Pending queue is pinned to another approved Gateway/certificate. Restore it before changing destination.");var next=Copy();next.DestinationPin=pin;Commit(next);}}
 public void Acknowledge(IReadOnlyList<Ack> acks){lock(gate){if(acks.Count==0||acks.Select(a=>a.event_id).Distinct().Count()!=acks.Count)throw new InvalidOperationException("Invalid ACK set");var pending=state.Pending.ToDictionary(r=>r.Id);if(acks.Any(a=>!pending.TryGetValue(a.event_id,out var record)||!Wire.Equal(a.sha256,record.Digest)))throw new InvalidOperationException("ACK digest/set mismatch; queue retained");var ids=acks.Select(a=>a.event_id).ToHashSet();var next=Copy();next.Pending.RemoveAll(r=>ids.Contains(r.Id));next.Acked+=acks.Count;Commit(next);}}
 public void ExportCsv(string path){lock(gate){var target=Path.GetFullPath(path);if(Path.GetDirectoryName(target)!=directory)throw new InvalidOperationException("CSV export must remain in the AQUA profile directory");using var output=new StreamWriter(new FileStream(target,FileMode.CreateNew,FileAccess.Write,FileShare.None),new System.Text.UTF8Encoding(false));output.WriteLine("event_id;sequence;kind;read_at;tag_name;raw_value;quality_code;read_error;quality;source_timestamp");foreach(var r in state.Pending){using var doc=JsonDocument.Parse(r.Payload);var e=doc.RootElement;foreach(var o in e.GetProperty("observations").EnumerateObject()){var v=o.Value;output.WriteLine(string.Join(";",new[]{r.Id,r.Sequence.ToString(),e.GetProperty("kind").GetString(),e.GetProperty("read_at").GetString(),o.Name,v.GetProperty("raw_value").ToString(),v.GetProperty("quality_code").ToString(),v.GetProperty("read_error").ToString(),v.GetProperty("quality").GetString(),v.GetProperty("source_timestamp").GetString()}.Select(s=>(s??"").Replace(";","_").Replace("\r","").Replace("\n",""))));}}}}
 public void Dispose()=>ownership.Dispose();
}

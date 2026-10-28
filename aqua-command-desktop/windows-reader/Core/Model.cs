using System.Security.Cryptography;
using System.Text;
using System.Text.Encodings.Web;
using System.Text.Json;
using System.Text.RegularExpressions;
using System.Net;

namespace Aqua.Reader.Core;
public static class Wire {
 public static readonly JsonSerializerOptions Json = new(){Encoder=JavaScriptEncoder.UnsafeRelaxedJsonEscaping};
 public static string Encode<T>(T value)=>JsonSerializer.Serialize(value,Json);
 public static string Hash(string text)=>Convert.ToHexStringLower(SHA256.HashData(Encoding.UTF8.GetBytes(text)));
 public static string Sign(string secret,string text)=>Convert.ToHexStringLower(HMACSHA256.HashData(Encoding.UTF8.GetBytes(secret),Encoding.UTF8.GetBytes(text)));
 public static bool Equal(string? a,string b)=>a is not null&&a.Length==b.Length&&CryptographicOperations.FixedTimeEquals(Encoding.UTF8.GetBytes(a),Encoding.UTF8.GetBytes(b));
 public static ulong ArrayIndexOrder(string key)=>uint.TryParse(key,System.Globalization.NumberStyles.None,System.Globalization.CultureInfo.InvariantCulture,out var n)&&n<uint.MaxValue&&n.ToString(System.Globalization.CultureInfo.InvariantCulture)==key?n:ulong.MaxValue;
 public static string Stamp()=>DateTimeOffset.UtcNow.ToString("yyyy-MM-ddTHH:mm:ss.fffZ");
 public static bool Date(string? value)=>value is not null&&DateTimeOffset.TryParse(value,System.Globalization.CultureInfo.InvariantCulture,System.Globalization.DateTimeStyles.RoundtripKind,out _);
}
public sealed class ReaderConfig {
 public string SourceId{get;set;}="PC-01";
 public List<string> Tags{get;set;}=[];
 public bool MappingConfirmed{get;set;}
 public string GatewayUrl{get;set;}="";
 public string Secret{get;set;}="";
 public string CaFile{get;set;}="";
 public const string ProgId="OPCServer.WinCC";
 public void ValidateCapture(){
  if(!new[]{"PC-01","PC-02","PC-03"}.Contains(SourceId))throw new InvalidOperationException("Source ID must be PC-01,PC-02 or PC-03");
  if(Tags.Count<1||Tags.Count>100||Tags.Distinct(StringComparer.Ordinal).Count()!=Tags.Count||Tags.Any(t=>!Regex.IsMatch(t,@"^[-A-Za-z0-9_.]{1,100}$")||new[]{"__proto__","constructor","prototype","toString","valueOf","hasOwnProperty","isPrototypeOf","propertyIsEnumerable","toLocaleString","__defineGetter__","__defineSetter__","__lookupGetter__","__lookupSetter__"}.Contains(t)))throw new InvalidOperationException("Choose1–100 unique exact binary Tag names (letters,digits,_,.,-)");
 }
 public Uri ValidateTransfer(){
  if(!Regex.IsMatch(Secret,"^[a-f0-9]{64}$"))throw new InvalidOperationException("A64-character lowercase enrollment key is required");
  if(!Uri.TryCreate(GatewayUrl,UriKind.Absolute,out var u)||u.Scheme!="https"||u.UserInfo.Length!=0||u.AbsolutePath!="/"||u.Query.Length!=0||u.Fragment.Length!=0||!IPAddress.TryParse(u.Host,out var ip)||ip.AddressFamily!=System.Net.Sockets.AddressFamily.InterNetwork)throw new InvalidOperationException("Gateway must be an explicit HTTPS private IPv4 endpoint");
  var b=ip.GetAddressBytes();if(!(b[0]==10||b[0]==192&&b[1]==168||b[0]==172&&b[1]>=16&&b[1]<=31||b[0]==127))throw new InvalidOperationException("Public Gateway addresses are not allowed");
  if(CaFile.Length>0&&(!Path.IsPathFullyQualified(CaFile)||!File.Exists(CaFile)||new FileInfo(CaFile).Length>1024*1024))throw new InvalidOperationException("Chosen CA certificate file is not available");
  return u;
 }
 public string ProfileId(){ValidateCapture();return Wire.Hash(Wire.Encode(new{version=1,SourceId,server=ProgId}));}
 public string CaptureRevision()=>Wire.Hash(Wire.Encode(new{Tags,MappingConfirmed}));
 public string DestinationPin(string? approvedCaDigest=null){var u=ValidateTransfer();return Wire.Hash(Wire.Encode(new{endpoint=u.AbsoluteUri,server="PC-04",ca=CaFile.Length==0?"OS_TRUST":approvedCaDigest??Convert.ToHexStringLower(SHA256.HashData(File.ReadAllBytes(CaFile)))}));}
}
public sealed record Observation(string Tag,long? RawValue,uint? QualityCode,int ReadError,string? SourceTimestamp){
 public string Quality(bool mapping){if(ReadError!=0||QualityCode is null)return "BAD";var mask=QualityCode.Value&0xc0;if(mask==0x40)return "UNCERTAIN";if(mask!=0xc0)return "BAD";if(!mapping)return "UNVERIFIED_MAPPING";return RawValue is 0 or 1?"GOOD":"UNSUPPORTED_VALUE";}
 public bool? State(bool mapping)=>Quality(mapping)=="GOOD"?RawValue==1:null;
}
public sealed record ReadFrame(string ReadAt,List<Observation> Observations);
public sealed record Ack(string event_id,string sha256);
public sealed record PendingRecord(string Id,long Sequence,string Payload,string Digest);
public sealed class SpoolState {
 public int Version{get;set;}=1;
 public string ProfileId{get;set;}="";
 public string? CaptureRevision{get;set;}
 public long Sequence{get;set;}
 public long Snapshots{get;set;}
 public long Acked{get;set;}
 public string? DestinationPin{get;set;}
 public Dictionary<string,bool?> Previous{get;set;}=[];
 public List<PendingRecord> Pending{get;set;}=[];
 public ReadFrame? Latest{get;set;}
}
public static class Events {
 public static List<PendingRecord> Build(ReaderConfig config,ReadFrame frame,SpoolState state){
  config.ValidateCapture();if(!Wire.Date(frame.ReadAt)||frame.Observations.Count!=config.Tags.Count||frame.Observations.Select(o=>o.Tag).Distinct().Count()!=config.Tags.Count||config.Tags.Except(frame.Observations.Select(o=>o.Tag)).Any())throw new InvalidOperationException("Read frame must contain exactly the selected Tag allowlist");
  var values=new Dictionary<string,bool?>();var observations=new Dictionary<string,object>();
  foreach(var o in frame.Observations.OrderBy(o=>Wire.ArrayIndexOrder(o.Tag))){if(o.SourceTimestamp is not null&&!Wire.Date(o.SourceTimestamp))throw new InvalidOperationException("Invalid source timestamp");values.Add(o.Tag,o.State(config.MappingConfirmed));observations.Add(o.Tag,new{raw_value=o.RawValue,quality_code=o.QualityCode,read_error=o.ReadError,quality=o.Quality(config.MappingConfirmed),source_timestamp=o.SourceTimestamp});}
  var kinds=new List<(string Kind,Observation? Changed,bool? Before)>{("SNAPSHOT",null,null)};
  foreach(var o in frame.Observations)if(values[o.Tag] is bool value&&state.Previous.TryGetValue(o.Tag,out var old)&&old is bool before&&before!=value)kinds.Add(("STATE_CHANGE",o,before));
  var result=new List<PendingRecord>();var seq=state.Sequence;
  foreach(var k in kinds){if(++seq>9007199254740991L)throw new InvalidOperationException("Sequence limit reached; retain queue");var id=config.SourceId+":"+Guid.NewGuid();var e=new Dictionary<string,object?>{{"event_id",id},{"schema","aqua.runtime.v3"},{"schema_version",3},{"source_id",config.SourceId},{"sequence",seq},{"kind",k.Kind},{"at",Wire.Stamp()},{"simulated",false},{"observed_at",frame.ReadAt},{"source_adapter","wincc-opc-da"},{"read_at",frame.ReadAt},{"values",values},{"observations",observations}};if(k.Changed is not null){e.Add("tag_name",k.Changed.Tag);e.Add("before",k.Before);e.Add("value",values[k.Changed.Tag]);}var payload=Wire.Encode(e);result.Add(new(id,seq,payload,Wire.Hash(payload)));}
  return result;
 }
}

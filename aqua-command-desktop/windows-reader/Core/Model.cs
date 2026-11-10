using System.Security.Cryptography;
using System.Text;
using System.Text.Encodings.Web;
using System.Text.Json;
using System.Text.RegularExpressions;
using System.Net;
using System.Globalization;
using System.Text.Json.Serialization;

namespace Aqua.Reader.Core;
public static class Wire {
 public static readonly JsonSerializerOptions Json = new(){Encoder=JavaScriptEncoder.UnsafeRelaxedJsonEscaping,Converters={new WireDoubleConverter()}};
 public static string Encode<T>(T value)=>JsonSerializer.Serialize(value,Json);
 public static string Hash(string text)=>Convert.ToHexStringLower(SHA256.HashData(Encoding.UTF8.GetBytes(text)));
 public static string Sign(string secret,string text)=>Convert.ToHexStringLower(HMACSHA256.HashData(Encoding.UTF8.GetBytes(secret),Encoding.UTF8.GetBytes(text)));
 public static bool Equal(string? a,string b)=>a is not null&&a.Length==b.Length&&CryptographicOperations.FixedTimeEquals(Encoding.UTF8.GetBytes(a),Encoding.UTF8.GetBytes(b));
 public static ulong ArrayIndexOrder(string key)=>uint.TryParse(key,System.Globalization.NumberStyles.None,System.Globalization.CultureInfo.InvariantCulture,out var n)&&n<uint.MaxValue&&n.ToString(System.Globalization.CultureInfo.InvariantCulture)==key?n:ulong.MaxValue;
 public static string Stamp()=>DateTimeOffset.UtcNow.ToString("yyyy-MM-ddTHH:mm:ss.fffZ");
 public static bool Date(string? value)=>value is not null&&DateTimeOffset.TryParse(value,System.Globalization.CultureInfo.InvariantCulture,System.Globalization.DateTimeStyles.RoundtripKind,out _);
}
// Gateway ACKs hash JSON.stringify(event). Use its fixed/scientific boundary and exponent spelling.
sealed class WireDoubleConverter : JsonConverter<double> {
 public override double Read(ref Utf8JsonReader reader,Type typeToConvert,JsonSerializerOptions options)
  =>reader.GetDouble();

 public override void Write(Utf8JsonWriter writer,double value,JsonSerializerOptions options){
  if(!double.IsFinite(value))throw new JsonException("Nonfinite OPC value");
  if(value==0){writer.WriteNumberValue(0);return;}
  var components=Math.Abs(value).ToString("R",CultureInfo.InvariantCulture).Split('E');
  var mantissa=components[0];
  var exponent=components.Length==2?int.Parse(components[1],CultureInfo.InvariantCulture):0;
  var point=mantissa.IndexOf('.');
  var digits=mantissa.Replace(".","");
  var leading=digits.Length-digits.TrimStart('0').Length;
  point=(point<0?mantissa.Length:point)+exponent-leading;
  digits=digits[leading..].TrimEnd('0');
  string number;
  if(point>0&&point<=21)
   number=point>=digits.Length?digits.PadRight(point,'0'):digits.Insert(point,".");
  else if(point<=0&&point>-6)
   number="0."+new string('0',-point)+digits;
  else {
   var scientificExponent=point-1;
   number=(digits.Length==1?digits:digits.Insert(1,"."))+"e"+
    (scientificExponent>=0?"+":"")+scientificExponent.ToString(CultureInfo.InvariantCulture);
  }
  writer.WriteRawValue((value<0?"-":"")+number);
 }
}

public static class OpcScalar {
 public static double? FromVariant(object? value,bool analog){
  if(!analog&&value is bool flag)return flag?1:0;
  if(value is not (byte or sbyte or short or ushort or int or uint or long or ulong or float or double or decimal))return null;
  if(value is long signed&&(signed < -9007199254740991L||signed > 9007199254740991L))return null;
  if(value is ulong unsigned&&unsigned > 9007199254740991UL)return null;
  var number=Convert.ToDouble(value,CultureInfo.InvariantCulture);
  if(!double.IsFinite(number))return null;
  if(analog)return number;
  return Math.Abs(number)<=1000000000000000d&&Math.Truncate(number)==number?number:null;
 }
}

public sealed class ReaderConfig {
 public string SourceId{get;set;}="PC-01";
 public List<string> Tags{get;set;}=[];
 public List<string> AnalogTags{get;set;}=[];
 public bool MappingConfirmed{get;set;}
 public bool IsAnalog(string tag)=>AnalogTags.Contains(tag,StringComparer.Ordinal);
 public string GatewayUrl{get;set;}="";
 public string Secret{get;set;}="";
 public string CaFile{get;set;}="";
 public const string ProgId="OPCServer.WinCC";
 public void ValidateCapture(){
  if(!new[]{"PC-01","PC-02","PC-03"}.Contains(SourceId))throw new InvalidOperationException("Source ID must be PC-01,PC-02 or PC-03");
  if(Tags.Count<1||Tags.Count>100||Tags.Distinct(StringComparer.Ordinal).Count()!=Tags.Count||Tags.Any(t=>!Regex.IsMatch(t,@"^[-A-Za-z0-9_.]{1,100}$")||new[]{"__proto__","constructor","prototype","toString","valueOf","hasOwnProperty","isPrototypeOf","propertyIsEnumerable","toLocaleString","__defineGetter__","__defineSetter__","__lookupGetter__","__lookupSetter__"}.Contains(t)))throw new InvalidOperationException("Choose1–100 unique exact Tag names (letters,digits,_,.,-)");
  if(AnalogTags.Count!=AnalogTags.Distinct(StringComparer.Ordinal).Count()||
     AnalogTags.Except(Tags,StringComparer.Ordinal).Any())
   throw new InvalidOperationException("Analog Tags must be a unique subset of selected Tags");
 }
 public Uri ValidateTransfer(){
  if(!Regex.IsMatch(Secret,"^[a-f0-9]{64}$"))throw new InvalidOperationException("A64-character lowercase enrollment key is required");
  if(!Uri.TryCreate(GatewayUrl,UriKind.Absolute,out var u)||u.Scheme!="https"||u.UserInfo.Length!=0||u.AbsolutePath!="/"||u.Query.Length!=0||u.Fragment.Length!=0||!IPAddress.TryParse(u.Host,out var ip)||ip.AddressFamily!=System.Net.Sockets.AddressFamily.InterNetwork)throw new InvalidOperationException("Gateway must be an explicit HTTPS private IPv4 endpoint");
  var b=ip.GetAddressBytes();if(!(b[0]==10||b[0]==192&&b[1]==168||b[0]==172&&b[1]>=16&&b[1]<=31||b[0]==127))throw new InvalidOperationException("Public Gateway addresses are not allowed");
  if(CaFile.Length>0&&(!Path.IsPathFullyQualified(CaFile)||!File.Exists(CaFile)||new FileInfo(CaFile).Length>1024*1024))throw new InvalidOperationException("Chosen CA certificate file is not available");
  return u;
 }
 public string ProfileId(){ValidateCapture();return Wire.Hash(Wire.Encode(new{version=1,SourceId,server=ProgId}));}
 public string CaptureRevision()=>Wire.Hash(AnalogTags.Count==0
  ?Wire.Encode(new{Tags,MappingConfirmed})
  :Wire.Encode(new{Tags,MappingConfirmed,AnalogTags=AnalogTags.Order(StringComparer.Ordinal)}));
 public string DestinationPin(string? approvedCaDigest=null){var u=ValidateTransfer();return Wire.Hash(Wire.Encode(new{endpoint=u.AbsoluteUri,server="PC-04",ca=CaFile.Length==0?"OS_TRUST":approvedCaDigest??Convert.ToHexStringLower(SHA256.HashData(File.ReadAllBytes(CaFile)))}));}
}
public sealed record Observation(string Tag,double? RawValue,uint? QualityCode,int ReadError,string? SourceTimestamp){
 public string Quality(bool mapping,bool analog=false){
  if(ReadError!=0||QualityCode is null)return "BAD";
  var mask=QualityCode.Value&0xc0;
  if(mask==0x40)return "UNCERTAIN";
  if(mask!=0xc0)return "BAD";
  if(analog)return RawValue is double number&&double.IsFinite(number)?"GOOD":"UNSUPPORTED_VALUE";
  if(!mapping)return "UNVERIFIED_MAPPING";
  return RawValue is 0 or 1?"GOOD":"UNSUPPORTED_VALUE";
 }
 public bool? State(bool mapping,bool analog=false)=>!analog&&Quality(mapping)=="GOOD"?RawValue==1:null;
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
  foreach(var o in frame.Observations.OrderBy(o=>Wire.ArrayIndexOrder(o.Tag))){
   if(o.SourceTimestamp is not null&&!Wire.Date(o.SourceTimestamp))throw new InvalidOperationException("Invalid source timestamp");
   var analog=config.IsAnalog(o.Tag);
   values.Add(o.Tag,o.State(config.MappingConfirmed,analog));
   var detail=new Dictionary<string,object?>{
    ["raw_value"]=o.RawValue,["quality_code"]=o.QualityCode,["read_error"]=o.ReadError,
    ["quality"]=o.Quality(config.MappingConfirmed,analog),["source_timestamp"]=o.SourceTimestamp
   };
   if(analog)detail.Add("value_type","analog");
   observations.Add(o.Tag,detail);
  }
  var kinds=new List<(string Kind,Observation? Changed,bool? Before)>{("SNAPSHOT",null,null)};
  foreach(var o in frame.Observations)if(values[o.Tag] is bool value&&state.Previous.TryGetValue(o.Tag,out var old)&&old is bool before&&before!=value)kinds.Add(("STATE_CHANGE",o,before));
  var result=new List<PendingRecord>();var seq=state.Sequence;
  foreach(var k in kinds){if(++seq>9007199254740991L)throw new InvalidOperationException("Sequence limit reached; retain queue");var id=config.SourceId+":"+Guid.NewGuid();var e=new Dictionary<string,object?>{{"event_id",id},{"schema","aqua.runtime.v3"},{"schema_version",3},{"source_id",config.SourceId},{"sequence",seq},{"kind",k.Kind},{"at",Wire.Stamp()},{"simulated",false},{"observed_at",frame.ReadAt},{"source_adapter","wincc-opc-da"},{"read_at",frame.ReadAt},{"values",values},{"observations",observations}};if(k.Changed is not null){e.Add("tag_name",k.Changed.Tag);e.Add("before",k.Before);e.Add("value",values[k.Changed.Tag]);}var payload=Wire.Encode(e);result.Add(new(id,seq,payload,Wire.Hash(payload)));}
  return result;
 }
}

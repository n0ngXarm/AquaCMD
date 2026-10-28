using Aqua.Reader.Core;
using System.Net;
using System.Text;
using System.Text.Json;
namespace Aqua.Reader.Tests;
// Test project only. No fake gateway/source is included in the Windows application.
sealed class FakeGateway(string secret,string mode="ok"):HttpMessageHandler {
 public int LastBatchCount{get;private set;}bool stalled;
 protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage req,CancellationToken token){
  var raw=await req.Content!.ReadAsStringAsync(token);using var doc=JsonDocument.Parse(raw);var nonce=req.Headers.GetValues("x-aqua-nonce").Single();var time=req.Headers.GetValues("x-aqua-time").Single();var path=req.RequestUri!.AbsolutePath;
  if(req.Headers.GetValues("x-aqua-mac").Single()!=Wire.Sign(secret,"POST\n"+path+"\n"+time+"\n"+nonce+"\n"+Wire.Hash(raw)))throw new Exception("Invalid client HMAC");
  if(mode=="stall"||mode=="stall-once"&&!stalled){stalled=true;return new(HttpStatusCode.OK){Content=new StalledContent()};}
  string body;
  if(path=="/v1/handshake")body=Wire.Encode(new{clientNonce=doc.RootElement.GetProperty("clientNonce").GetString(),gatewayId="PC-04",ready=true,session=new string('b',64),expiresAt=DateTimeOffset.UtcNow.ToUnixTimeMilliseconds()+30000});
  else{var acks=doc.RootElement.GetProperty("events").EnumerateArray().Select(e=>new Ack(e.GetProperty("event_id").GetString()!,mode=="digest"?new string('0',64):Wire.Hash(e.GetRawText()))).ToList();LastBatchCount=acks.Count;if(mode=="partial")acks.RemoveAt(acks.Count-1);if(mode=="duplicate"&&acks.Count>1)acks[^1]=acks[0];body=Wire.Encode(new{acks});}
  var answer=new HttpResponseMessage(HttpStatusCode.OK){Content=new StringContent(body,Encoding.UTF8,"application/json")};answer.Headers.Add("x-aqua-response",mode=="mac"?new string('0',64):Wire.Sign(secret,"RESPONSE\n200\n"+nonce+"\n"+Wire.Hash(body)));return answer;
 }
 sealed class StalledContent:HttpContent {
  protected override Task SerializeToStreamAsync(Stream stream,TransportContext? context)=>throw new NotSupportedException();
  protected override bool TryComputeLength(out long length){length=0;return false;}
  protected override Task<Stream>CreateContentReadStreamAsync()=>Task.FromResult<Stream>(new StalledStream());
  protected override Task<Stream>CreateContentReadStreamAsync(CancellationToken token)=>Task.FromResult<Stream>(new StalledStream());
 }
 sealed class StalledStream:Stream {
  public override bool CanRead=>true;public override bool CanSeek=>false;public override bool CanWrite=>false;public override long Length=>throw new NotSupportedException();public override long Position{get=>0;set=>throw new NotSupportedException();}
  public override void Flush(){}public override int Read(byte[]b,int offset,int count)=>throw new NotSupportedException();public override long Seek(long offset,SeekOrigin origin)=>throw new NotSupportedException();public override void SetLength(long value)=>throw new NotSupportedException();public override void Write(byte[]b,int offset,int count)=>throw new NotSupportedException();
  public override async ValueTask<int>ReadAsync(Memory<byte>buffer,CancellationToken token=default){await Task.Delay(Timeout.Infinite,token);return 0;}
 }
}

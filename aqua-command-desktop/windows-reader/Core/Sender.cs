using System.Net;
using System.Net.Http;
using System.Net.Security;
using System.Security.Cryptography;
using System.Security.Cryptography.X509Certificates;
using System.Text;
using System.Text.Json;
namespace Aqua.Reader.Core;

/// <summary>Explicit approved HTTPS peer only; never scans, redirects or opens a listener.</summary>
public sealed class AquaSender:IDisposable {
 readonly ReaderConfig config;readonly HttpClient client;readonly Uri endpoint;readonly X509Certificate2? ca;readonly string destinationPin;string? session;long expires;
 public AquaSender(ReaderConfig config,HttpClient? testClient=null){
  this.config=config;endpoint=config.ValidateTransfer();
  var handler=new SocketsHttpHandler{AllowAutoRedirect=false,UseProxy=false};
  var policy=new X509ChainPolicy{DisableCertificateDownloads=true,RevocationMode=X509RevocationMode.NoCheck,VerificationFlags=X509VerificationFlags.NoFlag};policy.ApplicationPolicy.Add(new Oid("1.3.6.1.5.5.7.3.1"));
  if(config.CaFile.Length>0){var bytes=File.ReadAllBytes(config.CaFile);ca=X509CertificateLoader.LoadCertificate(bytes);policy.TrustMode=X509ChainTrustMode.CustomRootTrust;policy.CustomTrustStore.Add(ca);destinationPin=config.DestinationPin(Convert.ToHexStringLower(SHA256.HashData(bytes)));}else destinationPin=config.DestinationPin();
  // Apply the no-download policy before TLS validates, including the OS-trust branch.
  handler.SslOptions.CertificateChainPolicy=policy;handler.SslOptions.RemoteCertificateValidationCallback=(_,_,_,errors)=>errors==SslPolicyErrors.None;
  if(testClient is not null){handler.Dispose();client=testClient;}else client=new HttpClient(handler){Timeout=TimeSpan.FromSeconds(8)};
 }
 async Task<JsonDocument> Request(string path,string body,CancellationToken token){
  var caller=token;using var deadline=CancellationTokenSource.CreateLinkedTokenSource(token);deadline.CancelAfter(TimeSpan.FromSeconds(8));token=deadline.Token;try{
  var nonce=Convert.ToHexStringLower(RandomNumberGenerator.GetBytes(20));var time=DateTimeOffset.UtcNow.ToUnixTimeMilliseconds().ToString(System.Globalization.CultureInfo.InvariantCulture);using var req=new HttpRequestMessage(HttpMethod.Post,new Uri(endpoint,path));
  req.Headers.Add("x-aqua-id",config.SourceId);req.Headers.Add("x-aqua-time",time);req.Headers.Add("x-aqua-nonce",nonce);req.Headers.Add("x-aqua-mac",Wire.Sign(config.Secret,"POST\n"+path+"\n"+time+"\n"+nonce+"\n"+Wire.Hash(body)));req.Content=new StringContent(body,Encoding.UTF8,"application/json");
  using var response=await client.SendAsync(req,HttpCompletionOption.ResponseHeadersRead,token).ConfigureAwait(false);await using var input=await response.Content.ReadAsStreamAsync(token).ConfigureAwait(false);using var raw=new MemoryStream();var buffer=new byte[8192];int got;while((got=await input.ReadAsync(buffer,token).ConfigureAwait(false))>0){if(raw.Length+got>512*1024)throw new InvalidOperationException("Gateway response exceeds limit");raw.Write(buffer,0,got);}var text=Encoding.UTF8.GetString(raw.ToArray());
  var signature=response.Headers.TryGetValues("x-aqua-response",out var values)?values.SingleOrDefault():null;if(!Wire.Equal(signature,Wire.Sign(config.Secret,"RESPONSE\n"+(int)response.StatusCode+"\n"+nonce+"\n"+Wire.Hash(text))))throw new InvalidOperationException("Gateway response authentication failed; local queue retained");
  if(response.StatusCode!=HttpStatusCode.OK)throw new InvalidOperationException("Authenticated Gateway rejected request (HTTP"+(int)response.StatusCode+"); local queue retained");token.ThrowIfCancellationRequested();return JsonDocument.Parse(text);
  }catch(OperationCanceledException)when(!caller.IsCancellationRequested){throw new TimeoutException("Gateway request deadline exceeded; local queue retained");}
 }
 public async Task<int> SendBatchAsync(DurableSpool store,CancellationToken token){
  token.ThrowIfCancellationRequested();var pending=store.Pending();if(pending.Count==0)return 0;var rows=new List<PendingRecord>();var bytes=110;foreach(var record in pending){var size=Encoding.UTF8.GetByteCount(record.Payload)+1;if(bytes+size>500*1024)break;rows.Add(record);bytes+=size;}if(rows.Count==0)throw new InvalidOperationException("One event exceeds protocol bound; local queue retained");store.PinDestination(destinationPin);
  try{
   if(session is null||expires<=DateTimeOffset.UtcNow.ToUnixTimeMilliseconds()){
    var nonce=Convert.ToHexStringLower(RandomNumberGenerator.GetBytes(20));using var hello=await Request("/v1/handshake",Wire.Encode(new{clientNonce=nonce}),token).ConfigureAwait(false);var h=hello.RootElement;
    if(h.GetProperty("clientNonce").GetString()!=nonce||h.GetProperty("gatewayId").GetString()!="PC-04"||!h.GetProperty("ready").GetBoolean())throw new InvalidOperationException("Enrolled Gateway is not ready to receive");var expiresAt=h.GetProperty("expiresAt").GetInt64();var tokenValue=h.GetProperty("session").GetString();if(tokenValue is null||!System.Text.RegularExpressions.Regex.IsMatch(tokenValue,"^[a-f0-9]{64}$")||expiresAt<=DateTimeOffset.UtcNow.ToUnixTimeMilliseconds()||expiresAt>DateTimeOffset.UtcNow.ToUnixTimeMilliseconds()+60000)throw new InvalidOperationException("Gateway handshake mismatch");session=tokenValue;expires=expiresAt;
   }
   token.ThrowIfCancellationRequested();var body="{\"session\":"+Wire.Encode(session)+",\"events\":["+string.Join(",",rows.Select(r=>r.Payload))+"]}";if(Encoding.UTF8.GetByteCount(body)>500*1024)throw new InvalidOperationException("Batch size exceeds protocol bound");using var answer=await Request("/v1/events",body,token).ConfigureAwait(false);var acks=answer.RootElement.GetProperty("acks").EnumerateArray().Select(a=>new Ack(a.GetProperty("event_id").GetString()??"",a.GetProperty("sha256").GetString()??"")).ToList();var expected=rows.ToDictionary(r=>r.Id,r=>r.Digest);if(acks.Count!=expected.Count||acks.Select(a=>a.event_id).Distinct().Count()!=acks.Count||acks.Any(a=>!expected.TryGetValue(a.event_id,out var hash)||!Wire.Equal(a.sha256,hash)))throw new InvalidOperationException("ACK digest/set mismatch; local queue retained");token.ThrowIfCancellationRequested();store.Acknowledge(acks);return acks.Count;
  }catch{session=null;expires=0;throw;}
 }
 public void Dispose(){client.Dispose();ca?.Dispose();}
}

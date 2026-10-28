using Aqua.Reader.Core;
using System.Diagnostics;
using System.Text.Json;
namespace Aqua.Reader.Windows;
public sealed class WorkerSession:IDisposable {
 readonly Process process;readonly CancellationTokenSource life=new();
 public WorkerSession(){var exe=Environment.ProcessPath??throw new InvalidOperationException("Executable path unavailable");process=new Process{StartInfo=new ProcessStartInfo(exe,"--read-worker"){UseShellExecute=false,RedirectStandardInput=true,RedirectStandardOutput=true,RedirectStandardError=true,CreateNoWindow=true}};}
 async Task<WorkerReply> Reply(CancellationToken token){
  using var timeout=CancellationTokenSource.CreateLinkedTokenSource(token,life.Token);timeout.CancelAfter(TimeSpan.FromSeconds(8));
  try{var line=await process.StandardOutput.ReadLineAsync(timeout.Token);if(line is null||line.Length>100000)throw new InvalidOperationException("Reader exited or exceeded reply limit");var reply=JsonSerializer.Deserialize<WorkerReply>(line,Wire.Json)??throw new InvalidOperationException("Missing reader reply");if(!reply.Ready||reply.Error is not null)throw new InvalidOperationException(reply.Error??"Reader unavailable");return reply;}catch(OperationCanceledException)when(!token.IsCancellationRequested){Stop();throw new TimeoutException("Local OPC read/connection exceeded8seconds; only the owned reader was stopped. WinCC was not terminated.");}catch{Stop();throw;}
 }
 public async Task StartAsync(ReaderConfig config,CancellationToken token){token.ThrowIfCancellationRequested();if(!process.Start())throw new InvalidOperationException("Cannot start owned reader");await process.StandardInput.WriteLineAsync(Wire.Encode(new WorkerConfig(Environment.ProcessId,config.Tags,true)));await process.StandardInput.FlushAsync(token);await Reply(token);}
 public async Task<ReadFrame> ReadAsync(CancellationToken token){token.ThrowIfCancellationRequested();await process.StandardInput.WriteLineAsync("READ");await process.StandardInput.FlushAsync(token);return(await Reply(token)).Frame??throw new InvalidOperationException("Reader returned no frame");}
 public void Stop(){life.Cancel();try{if(process.Id>0&&!process.HasExited)process.Kill(false);}catch(InvalidOperationException){}catch(System.ComponentModel.Win32Exception){}}
 public void Dispose(){Stop();try{if(process.Id>0)process.WaitForExit(1000);}catch(InvalidOperationException){}process.Dispose();life.Dispose();}
}

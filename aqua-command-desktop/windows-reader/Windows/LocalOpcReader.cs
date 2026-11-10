using Aqua.Reader.Core;
using Microsoft.Win32;
using System.Runtime.InteropServices;
using System.Globalization;
namespace Aqua.Reader.Windows;

public sealed record Registration(Guid Clsid,string Executable,string View);
public static class Readiness {
 // Registry inspection only: CLSIDFromProgID may create a registration and is deliberately absent.
 public static Registration Inspect(){
  if(!OperatingSystem.IsWindows())throw new PlatformNotSupportedException("WinCC OPC DA requires Windows");
  foreach(var view in new[]{RegistryView.Registry64,RegistryView.Registry32}){
   using var machine=RegistryKey.OpenBaseKey(RegistryHive.LocalMachine,view);using var prog=machine.OpenSubKey(@"SOFTWARE\Classes\"+ReaderConfig.ProgId+@"\CLSID",false);var text=prog?.GetValue(null) as string;if(!Guid.TryParse(text,out var clsid))continue;
   using var server=machine.OpenSubKey(@"SOFTWARE\Classes\CLSID\"+clsid.ToString("B"),false);if(server is null)continue;
   using var local=server.OpenSubKey("LocalServer32",false);var exe=local?.GetValue(null) as string;if(string.IsNullOrWhiteSpace(exe))continue;
   using var app=machine.OpenSubKey(@"SOFTWARE\Classes\AppID\"+(server.GetValue("AppID") as string??clsid.ToString("B")),false);
   using var redirect=server.OpenSubKey("TreatAs",false);using var current=RegistryKey.OpenBaseKey(RegistryHive.CurrentUser,view);using var overrideClass=current.OpenSubKey(@"SOFTWARE\Classes\CLSID\"+clsid.ToString("B"),false);
   if(server.GetValue("RemoteServerName") is not null||app?.GetValue("RemoteServerName") is not null||redirect is not null||overrideClass is not null)throw new InvalidOperationException("Remote/redirected COM registration is not allowed");
   return new(clsid,exe,view.ToString());
  }
  throw new InvalidOperationException("OPCServer.WinCC LocalServer32 is not registered. Ask the WinCC owner to verify existing readiness. AQUA will not enable/install/register it.");
 }
}
[ComImport,Guid("85C0B427-2893-4cbc-BD78-E5FC5146F08F"),InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
interface ILocalItemRead {
 [PreserveSig] int Read(int count,[MarshalAs(UnmanagedType.LPArray,ArraySubType=UnmanagedType.LPWStr,SizeParamIndex=0)]string[] items,[MarshalAs(UnmanagedType.LPArray,ArraySubType=UnmanagedType.U4,SizeParamIndex=0)]uint[] maxAge,out IntPtr values,out IntPtr quality,out IntPtr time,out IntPtr errors);
 // Only the documented first Read slot is projected; no Write/WriteVQT method is exposed.
}
public sealed class LocalOpcReader:IDisposable {
 readonly ILocalItemRead reader;bool initialized;
 [DllImport("ole32.dll",ExactSpelling=true)]static extern int CoInitializeEx(IntPtr reserved,uint concurrency);
 [DllImport("ole32.dll",ExactSpelling=true)]static extern void CoUninitialize();
 [DllImport("ole32.dll",ExactSpelling=true)]static extern int CoCreateInstance(ref Guid clsid,IntPtr outer,uint context,ref Guid iid,out IntPtr value);
 [DllImport("oleaut32.dll")]static extern int VariantClear(IntPtr value);
 public LocalOpcReader(Registration registration){
  if(Thread.CurrentThread.GetApartmentState()!=ApartmentState.STA)throw new InvalidOperationException("OPC reader must run in owned STA process");
  // STAThread declares the apartment; initialize native COM before direct P/Invoke activation.
  var initializedResult=CoInitializeEx(IntPtr.Zero,2 /* COINIT_APARTMENTTHREADED */);Marshal.ThrowExceptionForHR(initializedResult);initialized=true;
  try{var clsid=registration.Clsid;var iid=typeof(ILocalItemRead).GUID;var hr=CoCreateInstance(ref clsid,IntPtr.Zero,4u|(registration.View=="Registry32"?0x40000u:0x80000u) /* LOCAL_SERVER plus matching architecture */,ref iid,out var p);Marshal.ThrowExceptionForHR(hr);try{reader=(ILocalItemRead)Marshal.GetObjectForIUnknown(p);}finally{Marshal.Release(p);}}
  catch{CoUninitialize();initialized=false;throw;}
 }
 public ReadFrame Read(IReadOnlyList<string> tags,IReadOnlySet<string> analogTags){
  var items=tags.ToArray();var maxAge=items.Select(_=>uint.MaxValue).ToArray();IntPtr values=IntPtr.Zero,quality=IntPtr.Zero,times=IntPtr.Zero,errors=IntPtr.Zero;var successful=false;var stride=IntPtr.Size==8?24:16;
  try{
   var hr=reader.Read(items.Length,items,maxAge,out values,out quality,out times,out errors);Marshal.ThrowExceptionForHR(hr);successful=true;if(values==IntPtr.Zero||quality==IntPtr.Zero||times==IntPtr.Zero||errors==IntPtr.Zero)throw new InvalidOperationException("OPC returned incomplete value/quality/time/error arrays");var readAt=Wire.Stamp();var observations=new List<Observation>();
   for(var i=0;i<items.Length;i++){
    var error=Marshal.ReadInt32(errors,i*4);var q=unchecked((ushort)Marshal.ReadInt16(quality,i*2));double? raw=null;string? timestamp=null;
    if(error>=0){var value=Marshal.GetObjectForNativeVariant(IntPtr.Add(values,i*stride));raw=OpcScalar.FromVariant(value,analogTags.Contains(items[i]));}
    try{var ft=Marshal.ReadInt64(times,i*8);if(ft>0)timestamp=DateTimeOffset.FromFileTime(ft).UtcDateTime.ToString("yyyy-MM-ddTHH:mm:ss.fffZ",CultureInfo.InvariantCulture);}catch(ArgumentOutOfRangeException){}
    observations.Add(new(items[i],raw,q,error,timestamp));
   }
   return new(readAt,observations);
  }finally{
   if(successful&&values!=IntPtr.Zero)for(var i=0;i<items.Length;i++)VariantClear(IntPtr.Add(values,i*stride));
   foreach(var p in new[]{values,quality,times,errors})if(p!=IntPtr.Zero)Marshal.FreeCoTaskMem(p);
  }
 }
 public void Dispose(){try{if(Marshal.IsComObject(reader))Marshal.FinalReleaseComObject(reader);}finally{if(initialized){CoUninitialize();initialized=false;}}}
}
public sealed record WorkerConfig(int ParentId,List<string> Tags,List<string> AnalogTags,bool OrganizationalReadAuthorization);
public sealed record WorkerReply(bool Ready,ReadFrame? Frame,string? Error);
public static class Worker {
 public static int Run(){
  try{
   var line=Console.In.ReadLine();if(line is null||line.Length>20000)throw new InvalidOperationException("Missing bounded parent scope");var config=System.Text.Json.JsonSerializer.Deserialize<WorkerConfig>(line,Wire.Json)??throw new InvalidOperationException("Missing scope");if(!config.OrganizationalReadAuthorization||config.ParentId<=0)throw new InvalidOperationException("Read authorization required");new ReaderConfig{Tags=config.Tags,AnalogTags=config.AnalogTags}.ValidateCapture();
   var analogTags=config.AnalogTags.ToHashSet(StringComparer.Ordinal);
   using var parent=System.Diagnostics.Process.GetProcessById(config.ParentId);if(parent.HasExited)throw new InvalidOperationException("Parent session ended");var parentStart=parent.StartTime;
   _=Task.Run(async()=>{while(true){await Task.Delay(1000);try{using var p=System.Diagnostics.Process.GetProcessById(config.ParentId);if(p.HasExited||p.StartTime!=parentStart)Environment.Exit(10);}catch{Environment.Exit(10);}}});
   var registration=Readiness.Inspect();using var source=new LocalOpcReader(registration);Console.WriteLine(Wire.Encode(new WorkerReply(true,null,null)));Console.Out.Flush();
   while((line=Console.In.ReadLine()) is not null){if(line!="READ")throw new InvalidOperationException("Read-only command required");var frame=source.Read(config.Tags,analogTags);Console.WriteLine(Wire.Encode(new WorkerReply(true,frame,null)));Console.Out.Flush();}
   return 0;
  }catch(Exception e){Console.WriteLine(Wire.Encode(new WorkerReply(false,null,"Read failed: "+e.GetType().Name+" /0x"+unchecked((uint)e.HResult).ToString("X8"))));Console.Out.Flush();return 1;}
 }
}

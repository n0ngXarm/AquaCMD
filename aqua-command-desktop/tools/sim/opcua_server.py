"""SIMULATED OPC UA source; binds only 127.0.0.1:4850 in a separate process."""
import argparse
import asyncio
import json
import math
import ipaddress
import signal
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from asyncua import Server,ua
from asyncua.crypto import cert_gen
from cryptography import x509
from cryptography.hazmat.primitives.serialization import Encoding
from cryptography.x509.oid import ExtendedKeyUsageOID

ENDPOINT='opc.tcp://127.0.0.1:4850/aqua-sim/'
URI='urn:aqua-command:sim'


async def serve(directory,level):
    directory.mkdir(parents=True,exist_ok=True);directory.chmod(0o700)
    cert,key=directory/'server.der',directory/'server-key.pem'
    if not cert.exists() or not key.exists():
        private_key=cert_gen.generate_private_key()
        certificate=cert_gen.generate_self_signed_app_certificate(private_key,'AQUA COMMAND SIMULATED server',
            {'organizationName':'AQUA COMMAND SIMULATED'},
            [x509.UniformResourceIdentifier(URI),x509.DNSName('localhost'),x509.IPAddress(ipaddress.ip_address('127.0.0.1'))],
            extended=[ExtendedKeyUsageOID.SERVER_AUTH],days=365)
        key.write_bytes(cert_gen.dump_private_key_as_pem(private_key));key.chmod(0o600)
        cert.write_bytes(certificate.public_bytes(Encoding.DER));cert.chmod(0o600)
    server=Server();await server.init()
    server.set_endpoint(ENDPOINT);server.set_server_name('AQUA COMMAND SIMULATED source')
    await server.set_application_uri(URI)
    await server.load_certificate(cert);await server.load_private_key(key)
    server.set_security_policy([ua.SecurityPolicyType.NoSecurity,ua.SecurityPolicyType.Basic256Sha256_SignAndEncrypt])
    namespace=await server.register_namespace(URI)
    tank=await server.nodes.objects.add_object(ua.NodeId('T-101',namespace),'T-101')
    node=await tank.add_variable(ua.NodeId('T-101.level',namespace),'level',level,ua.VariantType.Double)
    await node.set_writable()
    stop=asyncio.Event()
    for number in (signal.SIGTERM,signal.SIGINT):asyncio.get_running_loop().add_signal_handler(number,stop.set)
    async with server:
        print(json.dumps({'ready':True,'source':'sim','label':'SIMULATED','endpoint':ENDPOINT,
            'node_id':node.nodeid.to_string(),'certificate':str(cert)}),flush=True)
        await stop.wait()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir',required=True,type=Path)
    parser.add_argument('--level',required=True,type=float)
    options=parser.parse_args()
    if not math.isfinite(options.level):parser.error('Level must be finite')
    asyncio.run(serve(options.data_dir,options.level))


if __name__=='__main__':main()

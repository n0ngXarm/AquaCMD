"""Change only the explicitly SIMULATED T-101 source on 127.0.0.1:4850."""
import argparse
import asyncio
import json
import math
from asyncua import Client,ua


async def set_level(level):
    async with Client('opc.tcp://127.0.0.1:4850/aqua-sim/',timeout=2,auto_reconnect=False) as client:
        namespace=await client.get_namespace_index('urn:aqua-command:sim')
        node=client.get_node(ua.NodeId('T-101.level',namespace))
        await node.write_value(level,ua.VariantType.Double)
        value=await node.read_value()
        print(json.dumps({'source':'sim','label':'SIMULATED','node_id':node.nodeid.to_string(),'observed_level':value}),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('level',type=float)
    options=parser.parse_args()
    if not math.isfinite(options.level):parser.error('Level must be finite')
    asyncio.run(set_level(options.level))

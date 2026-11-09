"""Explicit GetEndpoints/session/Value reads; protocol results are persisted, never inferred."""
import asyncio
import dataclasses
import enum
import json
import math
import time
from datetime import datetime
from pathlib import Path

from asyncua import Client,ua
from asyncua.crypto import security_policies,uacrypto
from cryptography.hazmat.primitives import hashes,serialization
from .probe_once import os_result


class CertificateError(ValueError):
    pass


def certificate_info(data):
    try:certificate=uacrypto.x509_from_der(data)
    except ValueError as error:raise CertificateError(str(error)) from error
    if certificate is None:return None
    return {'subject':certificate.subject.rfc4514_string(),'issuer':certificate.issuer.rfc4514_string(),
            'not_before':certificate.not_valid_before_utc.isoformat(),'not_after':certificate.not_valid_after_utc.isoformat(),
            'sha256':certificate.fingerprint(hashes.SHA256()).hex()}


def json_value(value):
    if value is None or isinstance(value,(str,bool,int)):return value
    if isinstance(value,float):return value if math.isfinite(value) else {'type':'float','value':str(value)}
    if isinstance(value,datetime):return value.isoformat()
    if isinstance(value,bytes):return {'type':'bytes','hex':value.hex()}
    if isinstance(value,enum.Enum):return {'type':type(value).__name__,'name':value.name,'value':json_value(value.value)}
    if dataclasses.is_dataclass(value):return json_value(dataclasses.asdict(value))
    if isinstance(value,dict):return {str(key):json_value(item) for key,item in value.items()}
    if isinstance(value,(tuple,list)):return [json_value(item) for item in value]
    return {'type':type(value).__name__,'text':str(value)}


def failure(error):
    if isinstance(error,CertificateError):return 'CERT_ERROR'
    if isinstance(error,OSError):return os_result(error)
    if isinstance(error,ua.UaStatusCodeError):
        name=ua.StatusCode(error.code).name
        if 'Certificate' in name:return 'CERT_ERROR'
        if 'Access' in name or 'Identity' in name:return 'ACCESS_DENIED'
        return 'UA_ERROR'
    if isinstance(error,ua.UaError):return 'SECURITY_ERROR'
    return 'ERROR'


async def read_target(target,timeout,store,output=print):
    host,source,settings=target['host'],target['source'],target['ua']
    endpoint=settings['endpoint']
    base={'endpoint':endpoint,'port':target['port'],'security_policy':settings['security_policy'],'authentication':'Anonymous'}
    emit=lambda row:output(json.dumps(row,ensure_ascii=False))

    def failed(check,error,started,detail):
        detail=dict(detail,exception=type(error).__name__)
        if isinstance(error,ua.UaStatusCodeError):detail['status_code']=ua.StatusCode(error.code).name
        emit(store.record(host,check,(failure(error),str(error),(time.perf_counter()-started)*1000,detail),source))

    discovery=Client(endpoint,timeout=timeout,auto_reconnect=False)
    started=time.perf_counter()
    try:
        endpoints=await asyncio.wait_for(discovery.connect_and_get_server_endpoints(),timeout)
        observed=[]
        for item in endpoints:
            try:certificate=certificate_info(item.ServerCertificate)
            except ValueError as error:certificate={'parse_error':str(error)}
            observed.append({'endpoint':item.EndpointUrl,'security_policy':item.SecurityPolicyUri,
                             'security_mode':item.SecurityMode.name,'application_uri':item.Server.ApplicationUri,'certificate':certificate})
        emit(store.record(host,'ua_endpoints',('ok',None,(time.perf_counter()-started)*1000,
                                             dict(base,endpoints=observed)),source))
    except (OSError,ua.UaError,ValueError,asyncio.TimeoutError) as error:
        failed('ua_endpoints',error,started,base)
        return
    finally:
        discovery.disconnect_socket()

    client=Client(endpoint,timeout=timeout,auto_reconnect=False)
    started=time.perf_counter();session=dict(base,session_attempted=False)
    try:
        try:
            secured=settings['security_policy']=='Basic256Sha256'
            selected=Client.find_endpoint(endpoints,ua.MessageSecurityMode.SignAndEncrypt if secured else ua.MessageSecurityMode.None_,
                                          'http://opcfoundation.org/UA/SecurityPolicy#'+settings['security_policy'])
            session['certificate']=certificate_info(selected.ServerCertificate)
            if secured:
                from desktop.opcua_pki import PkiManager
                pki=PkiManager(Path(settings['pki_dir']) if settings.get('pki_dir') else None)
                certificate=uacrypto.x509_from_der(selected.ServerCertificate)
                if certificate is None:raise CertificateError('Selected secure endpoint did not provide its certificate')
                der=certificate.public_bytes(serialization.Encoding.DER)
                validation=pki.validate_server_certificate(der,expected_host=host,expected_uri=selected.Server.ApplicationUri,check_trust_store=True)
                session['certificate_validation']=validation
                if not validation['valid']:raise CertificateError(validation['status_code']+': '+str(validation['error']))
                cert,key=pki.ensure_client_certificate()
                client.application_uri=pki.DEFAULT_APP_URI
                await asyncio.wait_for(client.set_security(security_policies.SecurityPolicyBasic256Sha256,cert,key,
                                        server_certificate=der,mode=ua.MessageSecurityMode.SignAndEncrypt),timeout)
            else:
                session['certificate_validation']='NOT_AUTHENTICATED_SECURITY_POLICY_NONE'
            session['session_attempted']=True
            await asyncio.wait_for(client.connect(auto_reconnect=False),timeout)
            session['peer_certificate']=certificate_info(client.security_policy.peer_certificate)
            emit(store.record(host,'ua_session',('ok',None,(time.perf_counter()-started)*1000,session),source))
        except (OSError,ua.UaError,ValueError,asyncio.TimeoutError) as error:
            failed('ua_session',error,started,session)
            return
        for tag,node_id in settings['nodes'].items():
            started=time.perf_counter();detail=dict(base,tag=tag,node_id=node_id,certificate=session.get('peer_certificate'))
            try:
                value=await asyncio.wait_for(client.get_node(node_id).read_data_value(raise_on_bad_status=False),timeout)
                quality=value.StatusCode.name
                observed=json_value(value.Value.Value if value.Value is not None else None)
                detail.update(value=observed,quality=quality,status_code=value.StatusCode.value,
                    source_ts=value.SourceTimestamp.isoformat() if value.SourceTimestamp else None,
                    server_ts=value.ServerTimestamp.isoformat() if value.ServerTimestamp else None,
                    data_type=value.Value.VariantType.name if value.Value is not None else None)
                observation=('ok' if value.StatusCode.is_good() else 'BAD_QUALITY',None if value.StatusCode.is_good() else quality,
                             (time.perf_counter()-started)*1000,detail)
                emit(store.record_read(host,tag,node_id,observation,observed,quality,source))
            except (OSError,ua.UaError,asyncio.TimeoutError) as error:
                failed('ua_read',error,started,detail)
    finally:
        started=time.perf_counter()
        try:
            await asyncio.wait_for(client.disconnect(),timeout)
            emit(store.record(host,'ua_close',('ok',None,(time.perf_counter()-started)*1000,
                dict(base,operation='disconnect completed',socket_closed=client.uaclient.protocol is None)),source))
        except Exception as error:
            failed('ua_close',error,started,base)
        finally:
            client.disconnect_socket()

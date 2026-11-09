"""Temporary-DB/OS-error tests; protocol success uses a separate tools/sim process."""
import errno
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import Mock,patch

from collector import probe_once as probe

ROOT=Path(__file__).resolve().parents[1]


class ProbeOnceTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory=Path(self.temporary.name)

    def config(self,**overrides):
        value={'targets':[{'host':'192.0.2.11','port':4840}], 'ping_timeout_s':1,'tcp_timeout_s':2}
        value.update(overrides)
        path=self.directory/'config.json';path.write_text(json.dumps(value))
        return path

    def test_default_route_to_a_different_subnet_is_not_no_route(self):
        raw=json.dumps([{'dst':'198.51.100.11','gateway':'192.0.2.1','dev':'lab'}])
        with patch.object(probe.subprocess,'run',return_value=Mock(returncode=0,stdout=raw,stderr='')) as command:
            result,error,latency,detail=probe.ip_check(['ip','-j','route','get','198.51.100.11'])
        self.assertEqual(result,'ok');self.assertIsNone(error)
        self.assertEqual(detail['stdout'],raw)
        self.assertEqual(command.call_args.args[0],['ip','-j','route','get','198.51.100.11'])

    def test_os_route_failure_is_preserved(self):
        message='RTNETLINK answers: Network is unreachable\n'
        with patch.object(probe.subprocess,'run',return_value=Mock(returncode=2,stdout='',stderr=message)):
            result,error,*_=probe.ip_check(['ip','-j','route','get','192.0.2.11'])
        self.assertEqual(result,'NO_ROUTE');self.assertEqual(error,message)

    def test_unavailable_os_tool_is_error_not_remote_unreachable(self):
        with patch.object(probe.subprocess,'run',side_effect=FileNotFoundError(errno.ENOENT,'No such file or directory','ip')):
            result,error,*_=probe.ip_check(['ip','-j','route'])
        self.assertEqual(result,'ERROR');self.assertIn('No such file',error)

    def test_invalid_os_json_is_not_success(self):
        with patch.object(probe.subprocess,'run',return_value=Mock(returncode=0,stdout='not JSON',stderr='')):
            result,error,*_=probe.ip_check(['ip','-j','addr'])
        self.assertEqual(result,'ERROR');self.assertTrue(error)

    def test_transport_errors_keep_real_errno_and_message(self):
        for code,expected in ((errno.ECONNREFUSED,'REFUSED'),(errno.ENETUNREACH,'NO_ROUTE'),
                              (errno.EHOSTUNREACH,'NO_ROUTE'),(errno.EACCES,'ERROR')):
            with self.subTest(errno=code),patch.object(probe.socket,'socket') as socket:
                error=OSError(code,os.strerror(code))
                socket.return_value.__enter__.return_value.connect.side_effect=error
                result,message,elapsed,detail=probe.tcp_check('192.0.2.11',4840,2)
            self.assertEqual(result,expected);self.assertEqual(message,str(error))
            self.assertEqual(detail['errno'],code);self.assertGreaterEqual(elapsed,0)

    def test_timeout_is_not_fabricated_success_or_fixed_latency(self):
        with patch.object(probe.socket,'socket') as socket:
            socket.return_value.__enter__.return_value.connect.side_effect=TimeoutError('timed out')
            result,error,elapsed,detail=probe.tcp_check('192.0.2.11',4840,2)
        self.assertEqual(result,'TIMEOUT');self.assertEqual(error,'timed out')
        self.assertNotEqual(elapsed,2000)
        socket.return_value.__enter__.return_value.settimeout.assert_called_once_with(2)

    def test_ping_is_one_numeric_packet_and_retains_packet_loss(self):
        output='1 packets transmitted, 0 received, 100% packet loss\n'
        with patch.object(probe.subprocess,'run',return_value=Mock(returncode=1,stdout=output,stderr='')) as command:
            result,error,*_=probe.ping_check('192.0.2.11',1)
        self.assertEqual(result,'TIMEOUT');self.assertEqual(error,output)
        self.assertEqual(command.call_args.args[0],['ping','-n','-c','1','-W','1','-w','1','192.0.2.11'])

    def test_invalid_configuration_never_opens_a_socket_or_database(self):
        cases=[{'targets':[{'host':'example.invalid','port':4840}]},
               {'targets':[{'host':'192.0.2.11','port':0}]}, {'targets':[]},
               {'targets':[{'host':True,'port':4840}]},
               {'targets':[{'host':'255.255.255.255','port':4840}]},
               {'tcp_timeout_s':float('nan')}, {'ping_timeout_s':0},
               {'targets':[{'host':'192.0.2.11','port':4840}]*2}]
        for case in cases:
            with self.subTest(case=case),patch.object(probe.socket,'socket') as socket,patch.object(probe.subprocess,'run') as command:
                with self.assertRaises(ValueError):probe.run(self.config(**case),self.directory/'not-created.db')
                socket.assert_not_called();command.assert_not_called()
                self.assertFalse((self.directory/'not-created.db').exists())

    def test_failure_is_committed_with_its_reason_and_real_rowid(self):
        store=probe.EvidenceStore(self.directory/'evidence.db')
        self.addCleanup(store.close)
        record=store.record('192.0.2.11','tcp',('REFUSED','[Errno 111] Connection refused',0.25,{'errno':111}))
        row=store.connection.execute('SELECT * FROM probe_evidence').fetchone()
        self.assertEqual(row['result'],'REFUSED');self.assertEqual(row['error'],record['error'])
        self.assertEqual(row['id'],record['id']);self.assertEqual(row['latency_ms'],0.25)
        self.assertEqual(os.stat(store.path).st_mode&0o777,0o600)

    def test_every_configured_host_is_checked_even_when_route_and_transport_fail(self):
        path=self.config(targets=[{'host':'192.0.2.11','port':4840},{'host':'192.0.2.12','port':4840}])
        failed=('NO_ROUTE','RTNETLINK: Network is unreachable',0.2,{'returncode':2})
        lines=[]
        with patch.object(probe,'ip_check',return_value=failed),patch.object(probe,'ping_check',return_value=failed) as ping, \
             patch.object(probe,'tcp_check',return_value=('TIMEOUT','timed out',2012.1,{'exception':'TimeoutError'})) as tcp:
            probe.run(path,self.directory/'evidence.db',lines.append)
        self.assertEqual(ping.call_count,2);self.assertEqual(tcp.call_count,2)
        with closing(sqlite3.connect(self.directory/'evidence.db')) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM probe_evidence').fetchone()[0],8)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM probe_evidence WHERE result="ok"').fetchone()[0],0)
        self.assertEqual(len(lines),8)
        self.assertTrue(all(json.loads(line)['error'] for line in lines))

    def test_actual_tcp_success_uses_a_separate_labelled_listener_process(self):
        child=subprocess.Popen([sys.executable,'-B',str(ROOT/'tools/sim/tcp_accept_server.py')],stdout=subprocess.PIPE,text=True)
        self.addCleanup(lambda:child.poll() is None and child.terminate())
        endpoint=json.loads(child.stdout.readline())
        self.assertEqual(endpoint['label'],'SIMULATED')
        result,error,elapsed,detail=probe.tcp_check(endpoint['host'],endpoint['port'],2)
        self.assertEqual(result,'ok');self.assertIsNone(error);self.assertGreater(elapsed,0)
        self.assertEqual(child.wait(timeout=3),0);child.stdout.close()

    def test_scanner_rejects_banned_runtime_tokens_and_keeps_schema_enums(self):
        root=self.directory/'guard';(root/'scripts').mkdir(parents=True);(root/'src').mkdir()
        shutil.copy2(ROOT/'scripts/no_fake_check.sh',root/'scripts/no_fake_check.sh')
        source=root/'src/collector.py'
        source.write_text("STATUS_TIMEOUT = 'TIMEOUT'\n")
        good=subprocess.run(['bash',str(root/'scripts/no_fake_check.sh')],capture_output=True,text=True)
        self.assertEqual(good.returncode,0,good.stdout+good.stderr)
        for token in ('from unittest import mock','faker.Faker()','Math.random()','random.random()'):
            source.write_text(token+'\n')
            bad=subprocess.run(['bash',str(root/'scripts/no_fake_check.sh')],capture_output=True,text=True)
            self.assertEqual(bad.returncode,1,bad.stdout+bad.stderr)


if __name__=='__main__':
    unittest.main()

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from screenshot_watcher.adb import Adb, AdbError, Cancelled, RemoteFile, parse_stat, validate_directory
from screenshot_watcher.storage import Store, atomic_rename, digest, mtime_epoch
from screenshot_watcher.watcher import Watcher


class FakeAdb:
    def __init__(self):
        self.serial = 'TARGET'
        self.stop = threading.Event()
        self.files = {}
        self.state_value = 'device'
        self.pulls = []
        self.fail_pull = False
        self.corrupt = False
        self.change_on_pull = False
        self.discover_count = 0
        self.clock_count = 0
        self.scan_error = False

    def add(self, name='new.png', data=b'raw screenshot', version=1):
        path = '/screenshots/' + name
        remote = RemoteFile(path, len(data), 100, 100, str(len(self.files) + 1),
                            f'2026-01-01 00:00:00.{version:09d} +0000',
                            f'2026-01-01 00:00:00.{version:09d} +0000')
        if path in self.files:
            remote = replace(remote, inode=self.files[path][0].inode)
        self.files[path] = (remote, data)
        return remote

    def state(self):
        if self.state_value == 'disconnected':
            raise AdbError('device not found')
        return self.state_value

    def discover(self, custom=None):
        self.discover_count += 1
        return (custom or ['/screenshots'], [])

    def scan(self, directories):
        if self.scan_error:
            raise AdbError('scan failed')
        return [value[0] for value in self.files.values()]

    def clock(self):
        self.clock_count += 1
        return {'device_minus_host_seconds': 0, 'uncertainty_seconds': 1}

    def stat(self, path):
        return self.files[path][0]

    def sha256(self, path):
        return hashlib.sha256(self.files[path][1]).hexdigest()

    def pull(self, path, destination):
        self.pulls.append(path)
        if self.fail_pull:
            raise AdbError('transfer failed')
        destination.write_bytes(b'bad' if self.corrupt else self.files[path][1])
        if self.change_on_pull:
            remote, data = self.files[path]
            self.files[path] = (replace(remote, ctime_full='new write'), data)


class WatchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.adb = FakeAdb()
        self.store = Store(self.root, self.adb.serial)
        self.events = []
        self.watcher = Watcher(self.adb, self.store, emit=lambda k, v: self.events.append((k, v)))
        self.now = time.monotonic()

    def stable(self, watcher=None):
        watcher = watcher or self.watcher
        files = self.adb.scan([])
        watcher.process(files, self.now)
        watcher.process(files, self.now + .6)

    def rows(self):
        return [json.loads(line) for line in self.store.manifest.read_text().splitlines()]

    def test_baseline_never_pulls_history(self):
        self.adb.add('old.jpg')
        self.watcher.initialize()
        self.stable()
        self.assertEqual(self.adb.pulls, [])

    def test_baseline_ctime_only_update_is_not_imported(self):
        remote = self.adb.add('old.jpg')
        self.watcher.initialize()
        self.adb.files[remote.path] = (replace(remote, ctime_full='late scanner'), self.adb.files[remote.path][1])
        self.stable()
        self.assertEqual(self.adb.pulls, [])

    def test_stable_file_original_bytes_and_hash(self):
        remote = self.adb.add('new.webp', b'unchanged bytes')
        self.stable()
        self.assertEqual(self.store.count, 1)
        row = self.rows()[0]
        local = Path(row['local_path'])
        self.assertEqual(local.suffix, '.webp')
        self.assertEqual(local.read_bytes(), b'unchanged bytes')
        self.assertEqual(digest(local), self.adb.sha256(remote.path))
        self.assertEqual(row['sha256'], row['source_sha256'])
        self.assertEqual(list(self.store.directory.glob('*.part')), [])

    def test_ten_images_exactly_once(self):
        for i in range(10):
            self.adb.add(f'{i}.png', f'raw {i}'.encode())
        for i in range(5):
            self.watcher.process(self.adb.scan([]), self.now + i)
        self.assertEqual(self.store.count, 10)
        self.assertEqual(len(self.adb.pulls), 10)
        self.assertEqual(len({r['local_path'] for r in self.rows()}), 10)

    def test_same_filename_size_and_second_new_nanoseconds(self):
        first = self.adb.add(data=b'AAAA', version=1)
        self.stable()
        second = self.adb.add(data=b'BBBB', version=2)
        self.assertEqual((first.mtime, first.size, first.inode), (second.mtime, second.size, second.inode))
        self.stable()
        self.assertEqual(self.store.count, 2)
        self.assertEqual([Path(r['local_path']).read_bytes() for r in self.rows()], [b'AAAA', b'BBBB'])

    def test_same_bytes_different_files_are_not_lost(self):
        self.adb.add('1.png', b'same')
        self.adb.add('2.png', b'same')
        self.stable()
        self.assertEqual(self.store.count, 2)

    def test_late_ctime_only_update_does_not_duplicate(self):
        remote = self.adb.add()
        self.stable()
        self.adb.files[remote.path] = (replace(remote, ctime_full='late metadata'), self.adb.files[remote.path][1])
        self.stable()
        self.assertEqual(self.store.count, 1)
        self.assertEqual(len(self.adb.pulls), 1)

    def test_same_mtime_size_but_content_and_ctime_changed(self):
        remote = self.adb.add(data=b'AAAA')
        self.stable()
        self.adb.files[remote.path] = (replace(remote, ctime_full='new write'), b'BBBB')
        self.stable()
        self.assertEqual(self.store.count, 2)

    def test_zero_byte_not_collected(self):
        self.adb.add(data=b'')
        self.stable()
        self.assertEqual(self.adb.pulls, [])

    def test_growth_resets_stability(self):
        self.adb.add(data=b'a')
        self.watcher.process(self.adb.scan([]), self.now)
        self.adb.add(data=b'complete', version=2)
        self.watcher.process(self.adb.scan([]), self.now + .6)
        self.assertEqual(self.adb.pulls, [])
        self.watcher.process(self.adb.scan([]), self.now + 1.2)
        self.assertEqual(self.store.count, 1)

    def test_pull_failure_retries_and_logs_not_success(self):
        self.adb.add()
        self.adb.fail_pull = True
        self.stable()
        self.assertEqual(self.store.count, 0)
        self.assertEqual(self.rows()[0]['transfer_status'], 'failed')
        self.assertIsNone(self.rows()[0]['local_path'])
        self.adb.fail_pull = False
        self.watcher.process(self.adb.scan([]), self.now + 100)
        self.assertEqual(self.store.count, 1)
        self.assertEqual([r['transfer_status'] for r in self.rows()], ['failed', 'success'])

    def test_failure_does_not_block_other_image(self):
        self.adb.add('bad.png')
        self.adb.add('good.png')
        original = self.adb.pull
        def pull(source, destination):
            if source.endswith('bad.png'):
                raise AdbError('one file failed')
            original(source, destination)
        self.adb.pull = pull
        self.stable()
        self.assertEqual(self.store.count, 1)
        self.assertEqual(len(self.rows()), 2)

    def test_hash_mismatch_keeps_no_final_or_temporary(self):
        self.adb.add()
        self.adb.corrupt = True
        self.stable()
        self.assertEqual(self.store.count, 0)
        self.assertEqual(list(self.store.directory.glob('*.png')), [])
        self.assertEqual(list(self.store.directory.glob('*.part')), [])
        self.assertIn('SHA-256', self.rows()[0]['error_message'])

    def test_source_mutation_during_pull_discarded(self):
        self.adb.add()
        self.adb.change_on_pull = True
        self.stable()
        self.assertEqual(self.store.count, 0)
        self.adb.change_on_pull = False
        self.watcher.process(self.adb.scan([]), self.now + 2)
        self.watcher.process(self.adb.scan([]), self.now + 3)
        self.assertEqual(self.store.count, 1)

    def test_new_session_excludes_stopped_period(self):
        self.watcher.initialize()
        self.adb.add('during-stop.png')
        other_store = Store(self.root, self.adb.serial)
        other = Watcher(self.adb, other_store)
        other.initialize()
        self.stable(other)
        self.assertEqual(other_store.count, 0)
        self.adb.add('after-resume.png')
        self.stable(other)
        self.assertEqual(other_store.count, 1)

    def test_disconnect_keeps_baseline_and_collects_gap_file(self):
        self.adb.add('old.png')
        self.watcher.initialize()
        self.adb.state_value = 'disconnected'
        with self.assertRaises(AdbError):
            self.watcher.tick()
        self.watcher.was_disconnected = True
        self.adb.add('gap.png')
        self.adb.state_value = 'device'
        self.watcher.tick()
        self.watcher.process(self.adb.scan([]), time.monotonic() + 1)
        self.assertEqual(self.store.count, 1)
        self.assertEqual(self.adb.discover_count, 1)
        self.assertEqual(self.adb.clock_count, 2)

    def test_unauthorized_offline_not_initialized(self):
        for state in ('unauthorized', 'offline'):
            self.adb.state_value = state
            with self.assertRaises(AdbError):
                self.watcher.tick()
            self.assertFalse(self.watcher.initialized)

    def test_run_survives_disconnect_and_stops(self):
        self.adb.state_value = 'disconnected'
        thread = threading.Thread(target=self.watcher.run)
        thread.start()
        time.sleep(.1)
        self.assertTrue(thread.is_alive())
        self.adb.stop.set()
        thread.join(2)
        self.assertFalse(thread.is_alive())
        self.assertIn('暂停检测', self.events[0][1])

    def test_disappeared_candidate_is_removed(self):
        self.adb.add()
        self.watcher.process(self.adb.scan([]), self.now)
        self.adb.files.clear()
        self.watcher.process([], self.now + 1)
        self.assertEqual(self.watcher.pending, {})

    def test_seen_file_reappears_not_downloaded(self):
        self.adb.add()
        self.stable()
        self.watcher.process([], self.now + 1)
        self.stable()
        self.assertEqual(self.store.count, 1)

    def test_scan_failure_does_not_replace_baseline(self):
        self.adb.add('old.png')
        self.watcher.initialize()
        baseline = self.watcher.seen.copy()
        self.adb.scan_error = True
        with self.assertRaises(AdbError):
            self.watcher.tick()
        self.assertEqual(self.watcher.seen, baseline)

    def test_session_collision_preserves_existing(self):
        second = Store(self.root, 'OTHER')
        self.assertNotEqual(second.directory, self.store.directory)
        self.assertTrue(self.store.manifest.exists())

    def test_manifest_failure_rolls_back_own_publication(self):
        self.adb.add()
        with patch.object(self.store, 'append', side_effect=OSError('disk full')):
            self.stable()
        self.assertEqual(self.store.count, 0)
        self.assertEqual(list(self.store.directory.glob('*.png')), [])
        self.assertEqual(list(self.store.directory.glob('*.part')), [])

    def test_manifest_fsync_failure_leaves_no_false_success(self):
        self.adb.add()
        with patch('screenshot_watcher.storage.os.fsync', side_effect=[None, OSError('disk full'), None]):
            self.stable()
        self.assertEqual(self.store.count, 0)
        self.assertEqual([r['transfer_status'] for r in self.rows()], ['failed'])
        self.assertEqual(list(self.store.directory.glob('*.png')), [])

    def test_atomic_rename_never_overwrites(self):
        source = self.root / 'temporary.part'
        target = self.root / 'existing.png'
        source.write_bytes(b'new')
        target.write_bytes(b'old')
        with self.assertRaises(FileExistsError):
            atomic_rename(source, target)
        self.assertEqual(target.read_bytes(), b'old')
        self.assertEqual(source.read_bytes(), b'new')

    def test_retry_initialize_after_metadata_write_failure(self):
        with patch.object(self.store, 'metadata', side_effect=OSError('full')):
            with self.assertRaises(OSError):
                self.watcher.initialize()
        self.watcher.initialize()
        self.assertTrue(self.watcher.initialized)

    def test_burst_registers_all_candidates_before_transfers(self):
        self.adb.add('1.png')
        self.adb.add('2.png')
        self.watcher.process(self.adb.scan([]), self.now)
        self.adb.add('3.png')
        original = self.store.collect
        def collect(*args):
            self.assertIn('/screenshots/3.png', self.watcher.pending)
            return original(*args)
        self.store.collect = collect
        self.watcher.process(self.adb.scan([]), self.now + .6)
        self.assertEqual(self.store.count, 2)

    def test_stop_prevents_collection(self):
        self.adb.add()
        self.adb.stop.set()
        self.stable()
        self.assertEqual(self.adb.pulls, [])

    def test_invalid_intervals(self):
        for value in (0, -.1, float('nan'), float('inf')):
            with self.assertRaises(ValueError):
                Watcher(self.adb, self.store, interval=value)


class AdbTests(unittest.TestCase):
    def test_stat_precise_and_spaces(self):
        remote = parse_stat('/space name.png', '4|100|101|25|mtime nanoseconds|ctime nanoseconds\n')
        self.assertEqual(remote.size, 4)
        self.assertEqual(remote.mtime_full, 'mtime nanoseconds')
        with self.assertRaises(AdbError):
            parse_stat('/x', 'broken')

    def test_directory_validation(self):
        for path in ('relative', '/a\ncommand', '/a\x00b'):
            with self.assertRaises(ValueError):
                validate_directory(path)
        self.assertEqual(validate_directory('/sdcard/A B/'), '/sdcard/A B')

    def test_scan_nul_framing_and_extension_filter(self):
        adb = Adb('S')
        raw = (b"/screenshots/A \n'quote.PNG\x004|1|2|3|nano1|nano2\n"
               b'/screenshots/tmp.part\x001|1|2|3|x|y\n')
        with patch.object(adb, 'shell', return_value=raw) as shell:
            files = adb.scan(["/screenshots/a'; echo payload #"])
        self.assertEqual(len(files), 1)
        self.assertIn("'\"'\"'", shell.call_args[0][0])
        self.assertEqual(files[0].path, "/screenshots/A \n'quote.PNG")

    def test_incomplete_scan_raises(self):
        adb = Adb('S')
        with patch.object(adb, 'shell', return_value=b'/x\x00broken'):
            with self.assertRaises(AdbError):
                adb.scan(['/screenshots'])

    def test_devices_include_unauthorized_and_offline(self):
        adb = Adb()
        raw = b'List of devices attached\nA device model:X\nB unauthorized\nC offline\n'
        with patch.object(adb, 'run', return_value=raw) as run:
            devices = adb.devices()
        self.assertEqual([d.state for d in devices], ['device', 'unauthorized', 'offline'])
        run.assert_called_once_with(['devices', '-l'], global_command=True)

    def test_all_target_commands_use_serial(self):
        adb = Adb('TARGET')
        process = unittest.mock.Mock()
        process.communicate.return_value = (b'device\n', b'')
        process.returncode = 0
        process.poll.return_value = 0
        with patch('subprocess.Popen', return_value=process) as popen:
            self.assertEqual(adb.state(), 'device')
        self.assertEqual(popen.call_args[0][0], ['adb', '-s', 'TARGET', 'get-state'])
        self.assertNotIn('shell', popen.call_args.kwargs)

    def test_missing_serial_and_global_command_rejected(self):
        with self.assertRaises(ValueError):
            Adb().state()
        with self.assertRaises(ValueError):
            Adb().run(['kill-server'], global_command=True)

    def test_two_devices_route_only_selected_target(self):
        discovery = Adb()
        with patch.object(discovery, 'run', return_value=b'List of devices attached\nA device\nB device\n'):
            devices = discovery.devices()
        selected = devices[1]
        process = unittest.mock.Mock()
        process.communicate.return_value = (b'device\n', b'')
        process.returncode = 0
        process.poll.return_value = 0
        with patch('subprocess.Popen', return_value=process) as popen:
            Adb(selected.serial).state()
        self.assertEqual(popen.call_args.args[0], ['adb', '-s', 'B', 'get-state'])

    def test_precise_clock_and_mtime(self):
        adb = Adb('S')
        with patch.object(adb, 'shell', return_value=b'100.125000000\n'), patch('time.time', side_effect=[100, 100.1]):
            clock = adb.clock()
        self.assertAlmostEqual(clock['device_minus_host_seconds'], .075)
        self.assertAlmostEqual(clock['uncertainty_seconds'], .05)
        remote = RemoteFile('/x.png', 1, 100, 100, '1', '1970-01-01 00:01:40.125000000 +0000', '')
        self.assertEqual(mtime_epoch(remote), 100.125)

    def test_clock_without_nanoseconds(self):
        with patch.object(Adb, 'shell', return_value=b'100.%N\n'):
            clock = Adb('S').clock()
        self.assertEqual(clock['device_date_precision'], 'seconds')
        self.assertGreaterEqual(clock['uncertainty_seconds'], 1)

    def test_mediastore_fallback_and_alias_dedup(self):
        adb = Adb('S')
        def shell(script):
            if script.startswith('if '):
                return b''
            if script.startswith('content '):
                return b'Row: 0 _data=/sdcard/Custom/Screenshots/image.png\n'
            return script.split('readlink -f ', 1)[1].split(' 2>', 1)[0].encode() + b'\n'
        with patch.object(adb, 'shell', side_effect=shell):
            directories, notes = adb.discover()
        self.assertIn('/sdcard/Custom/Screenshots', directories)

    def test_custom_directory_skips_mediastore(self):
        adb = Adb('S')
        with patch.object(adb, 'shell', return_value=b'/canonical\n') as shell:
            directories, _ = adb.discover(['/sdcard/a', '/sdcard/b'])
        self.assertEqual(directories, ['/canonical'])
        self.assertTrue(all(c.args[0].startswith('readlink') for c in shell.call_args_list))

    def test_real_child_timeout_reaped(self):
        actual = subprocess.Popen
        children = []
        def launch(*args, **kwargs):
            child = actual([sys.executable, '-c', 'import time; time.sleep(60)'], **kwargs)
            children.append(child)
            return child
        with patch('subprocess.Popen', side_effect=launch):
            with self.assertRaises(AdbError):
                Adb('S', timeout=.15).state()
        self.assertIsNotNone(children[0].poll())

    def test_real_child_cancellation_reaped(self):
        actual = subprocess.Popen
        children = []
        stop = threading.Event()
        def launch(*args, **kwargs):
            child = actual([sys.executable, '-c', 'import time; time.sleep(60)'], **kwargs)
            children.append(child)
            return child
        timer = threading.Timer(.15, stop.set)
        timer.start()
        try:
            with patch('subprocess.Popen', side_effect=launch):
                with self.assertRaises(Cancelled):
                    Adb('S', stop=stop).state()
        finally:
            timer.join()
        self.assertIsNotNone(children[0].poll())


if __name__ == '__main__':
    unittest.main()

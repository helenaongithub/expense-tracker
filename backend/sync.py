import uuid
import threading
import time
import os
import subprocess
from datetime import datetime
from pathlib import Path

JOBS_DIR = Path('data/sync_jobs')
JOBS_DIR.mkdir(parents=True, exist_ok=True)

os.makedirs('scripts', exist_ok=True)

_jobs = {}  # job_id -> dict with pid, started_at, running, returncode, log_path, error

def _run_process_and_stream(cmd_argv, log_path, job_id, env=None):
    """Run process, redirect stdout/stderr to log file, update _jobs metadata."""
    _jobs[job_id]['running'] = True
    _jobs[job_id]['started_at'] = time.strftime('%Y-%m-%d %H:%M:%S')
    try:
        with open(log_path, 'a', encoding='utf-8', errors='ignore') as logf:
            logf.write(f'Running: {' '.join(cmd_argv)}\n\n')
            logf.flush()

            # start process and let the OS write stdout/stderr directly to the file
            # avoids Python-level streaming and frequent flushes
            proc = subprocess.Popen(
                cmd_argv,
                stdout=logf,
                stderr=subprocess.STDOUT,
                text=True,
                env=env,
                close_fds=True
            )

            _jobs[job_id]['pid'] = proc.pid

            # wait for completion (blocking inside the worker thread)
            proc.wait()

            _jobs[job_id]['returncode'] = proc.returncode
            _jobs[job_id]['running'] = False
            logf.write(f'\nProcess finished with returncode={proc.returncode}\n')
            logf.flush()
    except Exception as e:
        _jobs[job_id]['running'] = False
        _jobs[job_id]['error'] = str(e)
        with open(log_path, 'a', encoding='utf-8', errors='ignore') as logf:
            logf.write(f'\nException: {e}\n')


def start_sync_job(script_path, argv=None, env=None):
    """
    Start a background job that runs 'script_path' with optional argv list.
    Returns job_id and metadata. Note: pid may be None for a short moment until the thread starts.
    """
    if argv is None:
        argv = []

    script_abspath = str(Path(script_path).expanduser().resolve())

    if not Path(script_abspath).exists():
        raise FileNotFoundError(f'{script_abspath} not found')

    job_id = uuid.uuid4().hex
    log_path = str(JOBS_DIR / f'{job_id}.log')

    # run the script via bash
    cmd = ['/bin/bash', script_abspath] + argv

    _jobs[job_id] = {
        'job_id': job_id,
        'pid': None,
        'started_at': None,
        'running': True,
        'returncode': None,
        'log_path': log_path,
        'error': None
    }

    # start non-daemon worker thread, so it runs to completion
    t = threading.Thread(target=_run_process_and_stream, args=(cmd, log_path, job_id, env))
    t.daemon = False
    t.start()

    # return a shallow copy, caller can query get_job(job_id) to see updates
    return _jobs[job_id].copy()

def get_job(job_id):
    return _jobs.get(job_id)

def tail_log(job_id, max_bytes=32_000):
    meta = _jobs.get(job_id)
    if not meta:
        return None
    p = Path(meta['log_path'])
    if not p.exists():
        return {'ok': True, 'log': ''}

    try:
        filesize = p.stat().st_size
        with p.open('rb') as f:
            if filesize > max_bytes:
                f.seek(filesize - max_bytes)
            data = f.read().decode('utf-8', errors='ignore')
    except Exception:
        data = p.read_text(encoding='utf-8', errors='ignore')

    if len(data) > max_bytes:
        return {'ok': True, 'log': data[-max_bytes:], 'truncated': True}
    return {'ok': True, 'log': data}

def run_sync_job(script_path, argv=None, env=None):
    """
    run 'script_path' synchronously (blocking)
    waits until the process completes before returning
    """
    if argv is None:
        argv = []

    try:
        script_abspath = str(Path(script_path).expanduser().resolve())
        if not Path(script_abspath).exists():
            print('No path set for SYNC_DOWNLOAD_SCRIPT. Using local database version.')
            return
    except Exception as e:
        print('No path set for SYNC_DOWNLOAD_SCRIPT. Using local database version.')
        return

    job_id = uuid.uuid4().hex
    log_path = str(JOBS_DIR / f'{job_id}.log')

    cmd = ['/bin/bash', script_abspath] + argv

    _jobs[job_id] = {
        'job_id': job_id,
        'pid': None,
        'started_at': datetime.utcnow().isoformat(),
        'running': True,
        'returncode': None,
        'log_path': log_path,
        'error': None,
    }

    try:
        # call the process runner directly (not in a thread)
        _run_process_and_stream(cmd, log_path, job_id, env)
    except Exception as e:
        print(f'SYNC_DOWNLOAD_SCRIPT had an error while being executed: {str(e)}')
        _jobs[job_id]['error'] = str(e)
        _jobs[job_id]['running'] = False
        _jobs[job_id]['returncode'] = -1

    return _jobs[job_id].copy()

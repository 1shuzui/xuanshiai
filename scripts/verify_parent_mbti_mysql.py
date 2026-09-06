"""Run integration tests against a fresh, private MySQL instance (never the configured DB).

Usage: python scripts/verify_parent_mbti_mysql.py --mysqld PATH --artifacts DIRECTORY
The generated database is retained for diagnosis after shutdown. Credentials stay private.
"""
from __future__ import annotations

import argparse
import contextlib
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import tempfile
import time

import pymysql


def free_port():
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        return listener.getsockname()[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mysqld', type=Path, required=True)
    parser.add_argument('--artifacts', type=Path, required=True)
    args = parser.parse_args()
    binary = args.mysqld.resolve(strict=True)
    args.artifacts.mkdir(parents=True, exist_ok=True)
    owned = Path(tempfile.mkdtemp(prefix='parent-mbti-mysql-', dir=args.artifacts.resolve()))
    datadir = owned / 'data'
    port = free_port()
    password = secrets.token_hex(24)
    init_file = owned / 'init.sql'
    init_file.write_text("ALTER USER 'root'@'localhost' IDENTIFIED BY '" + password + "';\n"
                         "CREATE DATABASE parent_mbti_test CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;\n", encoding='utf-8')
    flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    base = [str(binary), '--no-defaults', '--basedir=' + str(binary.parent.parent), '--datadir=' + str(datadir)]
    process = None
    connection = None
    try:
        with (owned / 'initialize.log').open('wb') as log:
            subprocess.run(base + ['--initialize-insecure', '--console'], stdout=log, stderr=subprocess.STDOUT,
                           creationflags=flags, check=True, timeout=120)
        with (owned / 'server.log').open('wb') as log:
            process = subprocess.Popen(base + ['--console', '--bind-address=127.0.0.1', '--port=' + str(port),
                '--mysqlx=0', '--skip-log-bin', '--init-file=' + str(init_file)], stdout=log,
                stderr=subprocess.STDOUT, creationflags=flags)
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError('Isolated MySQL exited; inspect server.log')
            try:
                connection = pymysql.connect(host='127.0.0.1', port=port, user='root', password=password,
                    database='parent_mbti_test', charset='utf8mb4', autocommit=True, connect_timeout=1,
                    cursorclass=pymysql.cursors.DictCursor)
                break
            except pymysql.MySQLError:
                time.sleep(0.25)
        if connection is None:
            raise RuntimeError('Isolated MySQL startup timed out')
        init_file.unlink()
        env = dict(os.environ, ENVIRONMENT='testing', AUTO_INIT_DB='false',
            DATABASE_URL=f'mysql+aiomysql://root:{password}@127.0.0.1:{port}/parent_mbti_test',
            REDIS_URL=f'redis://127.0.0.1:{free_port()}/0', SECRET_KEY=secrets.token_hex(32),
            RUN_PARENT_MYSQL='1', PYTHONUTF8='1')
        # The only connection supplied to the schema bootstrap is this isolated instance.
        os.environ.update({key: env[key] for key in ['ENVIRONMENT', 'AUTO_INIT_DB', 'DATABASE_URL', 'REDIS_URL', 'SECRET_KEY']})
        root = Path(__file__).resolve().parents[1]
        sys.path.insert(0, str(root))
        from database_setup_marriage import DatabaseManager
        with connection.cursor() as cursor:
            DatabaseManager.__new__(DatabaseManager).init_all_tables(cursor)
        print('Isolated MySQL ready; running real HTTP, SQL and concurrency tests.', flush=True)
        result = subprocess.run([sys.executable, '-m', 'pytest', '-q', 'tests/test_parent_mbti_mysql.py'],
            cwd=root, env=env, creationflags=flags, timeout=240, capture_output=True, text=True, encoding='utf-8')
        output = (result.stdout + result.stderr).replace(password, '[redacted]')
        (owned / 'test-results.txt').write_text(output, encoding='utf-8')
        print(output)
        return result.returncode
    finally:
        if init_file.exists():
            init_file.unlink()
        if connection:
            with contextlib.suppress(Exception), connection.cursor() as cursor:
                cursor.execute('SHUTDOWN')
            connection.close()
        if process and process.poll() is None:
            try:
                process.wait(timeout=20)
            except subprocess.TimeoutExpired:
                process.terminate()
                process.wait(timeout=10)
        print('Isolated instance stopped. Diagnostics: ' + str(owned), flush=True)


if __name__ == '__main__':
    raise SystemExit(main())

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

ROOT = Path(__file__).resolve().parent
NEW_REPO_DIR = ROOT / 'saas-de-fidelidad-render'
REPO_CANDIDATES = ['saas-de-fidelidad-render', 'saas-de-fidelidad-new', 'saas-de-fidelidad-2']


def get_github_token():
    proc = subprocess.run(
        ['git', 'credential', 'fill'],
        input=b'protocol=https\nhost=github.com\n\n',
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if proc.returncode != 0:
        raise RuntimeError(f'git credential fill failed: {proc.stderr.decode().strip()}')
    data = {}
    for line in proc.stdout.decode().splitlines():
        if '=' in line:
            key, value = line.split('=', 1)
            data[key.strip()] = value.strip()
    token = data.get('password')
    if not token:
        raise RuntimeError('No GitHub token found in credential helper output')
    return token


def create_repo(token):
    for name in REPO_CANDIDATES:
        payload = json.dumps({
            'name': name,
            'description': 'Repositorio migrado para SaaS Fidelidad',
            'private': False,
            'visibility': 'public',
        }).encode('utf-8')
        req = Request('https://api.github.com/user/repos', data=payload, method='POST')
        req.add_header('Authorization', f'token {token}')
        req.add_header('Accept', 'application/vnd.github+json')
        req.add_header('User-Agent', 'create-new-repo-script')
        try:
            with urlopen(req) as resp:
                result = json.loads(resp.read().decode('utf-8'))
                print(result['full_name'])
                return result['full_name'], result['clone_url']
        except HTTPError as e:
            body = e.read().decode('utf-8') if e.fp else ''
            if e.code == 422 and 'name already exists' in body:
                continue
            raise
        except URLError as e:
            raise
    raise RuntimeError('No available repository name could be created')


def copy_project():
    if NEW_REPO_DIR.exists():
        raise FileExistsError(f'{NEW_REPO_DIR} already exists')
    exclude = {'.git', '.venv', '.pytest_cache', 'frontend/node_modules'}
    NEW_REPO_DIR.mkdir(parents=True)
    for item in ROOT.iterdir():
        if item.name in exclude:
            continue
        dest = NEW_REPO_DIR / item.name
        if item.is_dir():
            shutil.copytree(item, dest)
        else:
            shutil.copy2(item, dest)


def run(cmd, cwd=None, check=True):
    print('RUN:', ' '.join(cmd))
    proc = subprocess.run(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    print(proc.stdout, proc.stderr)
    if check and proc.returncode != 0:
        raise RuntimeError(f'Command failed: {cmd}\n{proc.stderr}')
    return proc


def init_and_push(clone_url):
    run(['git', 'init'], cwd=NEW_REPO_DIR)
    run(['git', 'checkout', '-b', 'main'], cwd=NEW_REPO_DIR)
    run(['git', 'add', '.'], cwd=NEW_REPO_DIR)
    run(['git', 'commit', '-m', 'Initial commit for new repository'], cwd=NEW_REPO_DIR)
    run(['git', 'remote', 'add', 'origin', clone_url], cwd=NEW_REPO_DIR)
    run(['git', 'push', '-u', 'origin', 'main'], cwd=NEW_REPO_DIR)


def main():
    token = get_github_token()
    print('GitHub token obtained')
    full_name, clone_url = create_repo(token)
    print('Created repository', full_name)
    copy_project()
    print('Project copied to', NEW_REPO_DIR)
    init_and_push(clone_url)
    print('Repository pushed successfully:', full_name)


if __name__ == '__main__':
    main()

"""Run from the uploaded project root after joining the installer parts."""
import hashlib
import json
import os
import shutil
from pathlib import Path

from eldoria import create_app
from eldoria.db import get_db
from eldoria.game_release import GAME_INFO

project=Path(__file__).resolve().parent
installer=project/'instance'/'releases'/GAME_INFO['filename']
manifest=json.loads((project/'game-manifest.json').read_text(encoding='utf-8'))
def file_hash(path):
    digest=hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):
            digest.update(chunk)
    return digest.hexdigest()


if not installer.is_file():
    installer.parent.mkdir(parents=True,exist_ok=True)
    temporary=installer.with_suffix('.exe.upload')
    if not temporary.exists():
        temporary.touch()
    completed=0
    for part_info in manifest['parts']:
        size=part_info['bytes']
        part=project.parent/part_info['name']
        if temporary.stat().st_size>=completed+size:
            with temporary.open('rb') as stream:
                stream.seek(completed)
                digest=hashlib.sha256(stream.read(size)).hexdigest()
            if digest!=part_info['sha256']:
                raise SystemExit('A montagem parcial está corrompida. Renomeie o .exe.upload e reenvie as partes.')
            completed+=size
            continue
        if not part.is_file() or part.stat().st_size!=size or file_hash(part)!=part_info['sha256']:
            raise SystemExit('Envie a parte original: '+part_info['name'])
        with temporary.open('r+b') as destination:
            destination.truncate(completed)
            destination.seek(completed)
            with part.open('rb') as source:
                shutil.copyfileobj(source,destination,1024*1024)
            destination.flush()
            os.fsync(destination.fileno())
        completed+=size
        # Verified upload chunks are temporary; remove one at a time to fit the free disk quota.
        part.unlink()
        print('Parte verificada e incorporada: '+part_info['name'])
    if temporary.stat().st_size!=manifest['bytes'] or file_hash(temporary)!=manifest['sha256']:
        raise SystemExit('Falha de integridade. O arquivo não foi publicado.')
    temporary.replace(installer)
digest=file_hash(installer)
if digest!=manifest['sha256'] or installer.stat().st_size!=manifest['bytes']:
    raise SystemExit('O arquivo está incompleto ou diferente do original. Verifique as três partes e tente novamente.')
app=create_app()
with app.app_context():
    db=get_db()
    db.execute("INSERT INTO site_settings VALUES ('game',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(json.dumps(GAME_INFO,ensure_ascii=False),))
    db.commit()
print('Crônicas de Eldoria 1.8.1: apresentação publicada e download verificado.')

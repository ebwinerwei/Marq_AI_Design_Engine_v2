"""Re-run released 2.0 tests without changing files in a user's installed application."""
from pathlib import Path
import sys,zipfile,tempfile,shutil,subprocess,hashlib
ROOT=Path(__file__).resolve().parents[1];archive=ROOT/'Marq_Facade_Workbench_2.0.zip'
assert hashlib.sha256(archive.read_bytes()).hexdigest()=='bbe668f145f739998c5b444fa746cafbb278bb9341236d4608b09386ca8f8aea'
with tempfile.TemporaryDirectory() as d:
    dest=Path(d)
    with zipfile.ZipFile(archive) as z:z.extractall(dest)
    app=dest/'marq-facade-studio';pkg=app/'node_modules'/'three';pkg.mkdir(parents=True)
    (pkg/'package.json').write_text('{"type":"module","exports":{".":"./index.js","./addons/*":"./addons/*"}}')
    (pkg/'index.js').symlink_to(app/'dist/vendor/three.module.js')
    (pkg/'addons').symlink_to(app/'dist/vendor/addons',target_is_directory=True)
    shutil.copy(ROOT/'tests/fixtures/warehouse-test.fbx',app/'tests/warehouse.fbx')
    for args in [['node','tests/core.mjs'],['node','tests/rendering.mjs'],['node','tests/validate-building.mjs',str(ROOT/'tests/fixtures/building01.fbx'),str(dest/'model/building01_facade_clean.glb')],[sys.executable,'-m','unittest','discover','-s','tests','-p','test_server.py']]:
        subprocess.run(args,cwd=app,check=True)

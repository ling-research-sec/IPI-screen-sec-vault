from pathlib import Path
import sys,json,hashlib,zipfile,tempfile,os,shutil
archive=Path(sys.argv[1]).resolve();out=Path(sys.argv[2]).resolve()
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
temp=Path(tempfile.mkdtemp(prefix='.verified-audit-restore-',dir=archive.parent));(temp/'.restore-owner').write_text(str(archive))
try:
 with zipfile.ZipFile(archive) as z:
  assert len(z.namelist())==len(set(z.namelist()));assert z.testzip() is None
  m=json.loads(z.read('manifest.json'));files=m['files'];links=m.get('symlinks',{})
  for rel,h in files.items():
   r=Path(rel);assert not r.is_absolute() and '..' not in r.parts
   p=temp/r;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(z.read(rel));assert sha(p)==h,rel
  for rel,target in links.items():
   r=Path(rel);assert not r.is_absolute() and '..' not in r.parts and z.read(rel).decode()==target
   p=temp/r;p.parent.mkdir(parents=True,exist_ok=True);os.symlink(target,p);assert os.readlink(p)==target
 result=dict(status='PASS',archive=str(archive),archive_sha256=sha(archive),restored_files=len(files),restored_symlinks=len(links),crc='PASS',independent_restore='PASS',all_restored_sha256='PASS')
 assert (temp/'.restore-owner').read_text()==str(archive);shutil.rmtree(temp);out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps(result,ensure_ascii=False))
except BaseException:
 print('RESTORE FAILED; preserved workspace:',temp,file=sys.stderr);raise

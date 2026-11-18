"""Build allowlist prevents credentials, firmware, archived models and test evidence shipping to Lambda."""
import argparse,shutil
from pathlib import Path
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('destination');a=p.parse_args();dest=Path(a.destination);dest.mkdir(parents=True,exist_ok=True)
 for folder,pattern in [('aws','*.py'),('plantcare','*.py'),('profiles','*.json'),('dashboard','*')]:
  target=dest/folder;target.mkdir(exist_ok=True)
  for f in Path(folder).glob(pattern):
   if f.name not in ('model.py','local_invoke.py','pothos.json') and f.is_file():shutil.copy2(f,target/f.name)

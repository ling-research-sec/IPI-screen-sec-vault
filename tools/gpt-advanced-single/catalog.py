"""The catalogue is reconstructed from the connected phone, never inferred from grid positions."""
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import os

SIZES = (16, 24, 32, 40, 48, 64)
GRAYS = tuple(range(1, 33))
class Problem(Exception):
    """A short, actionable message suitable for the desktop window."""

@dataclass
class Catalog:
    serial: str
    folder: str
    files: dict

    @classmethod
    def parse(cls, serial, folder, names):
        files = {}
        for name in names:
            if not name.lower().endswith(('.png','.jpg','.jpeg','.webp','.bmp','.heic','.avif')):
                continue
            m = re.fullmatch(r'(\d+)_f(\d+)-g(\d+)\.png', name, re.I)
            if not m:
                raise Problem('图片文件名不符合约定：' + name)
            _, f, g = map(int, m.groups())
            if f not in SIZES or g not in GRAYS:
                raise Problem('图片档位超出六组范围：' + name)
            if (f,g) in files:
                raise Problem(f'重复图片：{f} px / g{g}')
            files[f,g] = name
        missing = [(f,g) for f in SIZES for g in GRAYS if (f,g) not in files]
        if missing:
            f,g = missing[0]
            raise Problem(f'缺 {len(missing)} 张；第一张：{f} px / g{g}')
        return cls(serial, folder, files)

    @property
    def key(self):
        data = [self.serial, self.folder, sorted(self.files.values())]
        return hashlib.sha256(json.dumps(data).encode()).hexdigest()

class Progress:
    """Only commit after a proven end state. Never resume an active operation."""
    def __init__(self, path, key):
        self.path = Path(path)
        self.key = key
        try:
            self.all = json.loads(self.path.read_text()) if self.path.exists() else {}
            self.state = self.all.setdefault(key, {'font':16,'next':{},'done':[]})
            if self.state['font'] not in SIZES or not all(
                k in {str(f) for f in SIZES} and type(v) is int and v in GRAYS
                for k,v in self.state['next'].items()
            ) or not isinstance(self.state['done'],list):
                raise ValueError()
            marks=self.state.get('registered',[])
            if not isinstance(marks,list) or any(
                not isinstance(pair,list) or len(pair)!=2 or
                type(pair[0]) is not int or type(pair[1]) is not int or
                pair[0] not in SIZES or pair[1] not in GRAYS for pair in marks
            ) or len({tuple(pair) for pair in marks})!=len(marks):
                raise ValueError()
        except (OSError, ValueError, KeyError, AttributeError, TypeError) as e:
            raise Problem('本机进度文件异常，请先检查：' + str(path)) from e

    def next(self, f):
        return self.state['next'].get(str(f), 1)

    def started(self, f, g):
        self.state['font'] = f
        self.state['next'][str(f)] = g
        self.state['pending'] = [f,g]
        self.save()

    def completed(self, f, g, *, captured=False):
        # Commit the progress and screenshot mark in one atomic write.
        pair=[f,g]
        state={**self.state,'font':f,'next':{**self.state['next'],str(f):min(32,g+1)},
               'done':self.state['done'] if pair in self.state['done'] else [*self.state['done'],pair]}
        state.pop('pending',None)
        if captured:
            state['registered']=[list(p) for p in sorted(self.registered() | {(f,g)})]
        self._replace_state(state)

    def registered(self):
        # Legacy done entries mean "reached the sharing endpoint", not "recorded".
        return {tuple(pair) for pair in self.state.get('registered',[])}

    def _replace_state(self, state):
        data={**self.all,self.key:state}
        self.save(data)
        self.all,self.state=data,state

    def set_registered(self, f, g, value):
        if type(f) is not int or type(g) is not int or f not in SIZES or g not in GRAYS or type(value) is not bool:
            raise ValueError('无效的登记档位。')
        marks=self.registered()
        if ((f,g) in marks)==value:return
        if value:marks.add((f,g))
        else:marks.discard((f,g))
        self._replace_state({**self.state,'registered':[list(p) for p in sorted(marks)]})

    def clear_history(self):
        self._replace_state({**self.state,'registered':[]})

    def save(self, data=None):
        self.path.parent.mkdir(exist_ok=True,parents=True)
        tmp = self.path.with_suffix('.tmp')
        with tmp.open('w') as fp:
            json.dump(self.all if data is None else data,fp)
            fp.flush()
            os.fsync(fp.fileno())
        os.replace(tmp,self.path)

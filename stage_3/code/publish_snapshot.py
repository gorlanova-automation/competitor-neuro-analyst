"""Build public stage-3 data from executed Python results, not fabricated UI data."""
import json
import shutil
from pathlib import Path
from analyst import read

ROOT=Path(__file__).resolve().parents[1]


def main():
    docs=ROOT.parent/'docs'
    data={'portugal':read(ROOT/'results/current/result.json'),
          'companies':read(ROOT/'input/companies.json'),
          'user_additions':read(ROOT/'input/user_additions.json'),
          'shift':read(ROOT/'cases/shift/result.json'),
          'shiftCapture':{k:v for k,v in read(ROOT/'cases/shift/own_source.json').items() if k not in ('text','headings')}}
    (docs/'stage3-data.js').write_bytes(('window.STAGE3_DATA = '+json.dumps(data,ensure_ascii=False,separators=(',',':'))+';\n').encode('utf-8'))
    print('Published snapshot:',len(data['portugal']['evidence']),'observations,',len(data['companies'])-1,'competitors')


if __name__=='__main__': main()

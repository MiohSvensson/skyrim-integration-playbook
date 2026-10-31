"""Read-only external-resource inventory for Skyrim NIF 20.2.0.7 / BS 83 or100.

Header, name and BSShaderTextureSet layouts follow niftools/nifxml
970a6238218a106daaeb89a61bcda0eeaf9d08c4. No mesh bytes are edited.
"""
import pathlib, struct, hashlib

def inventory(path):
    data=pathlib.Path(path).read_bytes();pos=data.index(b'\n')+1
    def number(fmt):
        nonlocal pos
        value=struct.unpack_from('<'+fmt,data,pos)[0];pos+=struct.calcsize(fmt);return value
    def sized(fmt='I'):
        nonlocal pos
        size=number(fmt);value=data[pos:pos+size];pos+=size;return value.rstrip(b'\0').decode('utf-8','replace')
    assert number('I')==0x14020007 and number('B')==1
    user=number('I');count=number('I');bs=number('I');assert user==12 and bs in (83,100)
    exported=[sized('B') for _ in range(3)]
    types=[sized() for _ in range(number('H'))]
    indices=[number('H') for _ in range(count)];sizes=[number('I') for _ in range(count)]
    string_count=number('I');max_length=number('I');strings=[sized() for _ in range(string_count)]
    groups=[number('I') for _ in range(number('I'))];blocks=[]
    for index,(kind,size) in enumerate(zip(indices,sizes)):
        name=types[kind];start=pos;body=data[start:start+size];assert len(body)==size
        row={'index':index,'type':name,'offset':start,'bytes':size}
        if name in ['NiNode','BSFadeNode','BSTriShape','BSDynamicTriShape','BSSubIndexTriShape','NiTriShape','NiTriStrips']:
            n=struct.unpack_from('<I',body)[0];row['name']=strings[n] if n!=0xFFFFFFFF else ''
        if name=='BSShaderTextureSet':
            n=number('I');row['textures']=[sized() for _ in range(n)];assert pos==start+size
        pos=start+size;blocks.append(row)
    assert pos<=len(data)
    return {'path':str(pathlib.Path(path).resolve()),'sha256':hashlib.sha256(data).hexdigest(),
            'user_version':user,'bs_version':bs,'export_info':exported,'strings':strings,'blocks':blocks,'footer_bytes':len(data)-pos}

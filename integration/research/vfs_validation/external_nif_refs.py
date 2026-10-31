"""Additional typed external fields for SSE BS100 NIFs (nifxml schema)."""
import struct


def effect_textures(data,block):
    assert block['type']=='BSEffectShaderProperty'
    start=block['offset'];end=start+block['bytes'];extra=struct.unpack_from('<I',data,start+4)[0]
    pos=start+36+extra*4
    def sized():
        nonlocal pos
        if pos+4>end:raise ValueError('Truncated effect texture size')
        n=struct.unpack_from('<I',data,pos)[0];pos+=4
        if pos+n>end:raise ValueError('Truncated effect texture name')
        value=data[pos:pos+n].rstrip(b'\0').decode('utf-8');pos+=n;return value
    source=sized();pos+=44
    if pos>end:raise ValueError('Truncated effect shader fixed fields')
    grey=sized()
    if pos!=end:raise ValueError(('Unexpected SSE effect shader tail',pos,end))
    return [('Source Texture',source),('Greyscale Texture',grey)]
